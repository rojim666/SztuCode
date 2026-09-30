import assert from "node:assert/strict";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test, { type TestContext } from "node:test";
import { OpenAiCompatibleProvider } from "../src/providers/openai.js";
import { openAiEndpoint } from "../src/providers/openai-endpoint.js";
import { ConfigurableProvider } from "../src/providers/configurable.js";
import { ProviderError, abortableDelay } from "../src/providers/errors.js";
import { isOpenAiReasoningModel } from "../src/providers/model-capabilities.js";
import { probeModel } from "../src/server-helpers.js";
import { SettingsStore } from "../src/settings.js";
import { ToolRegistry } from "../src/tools.js";
import { AgentLoop, type ChatMessage } from "../src/agent-loop.js";
import { EventBus } from "../src/event-bus.js";
import { Workspace } from "../src/workspace.js";

const messages = [{ role: "user" as const, content: "hello" }];
const tools = new ToolRegistry();
const ok = { choices: [{ message: { content: "OK" }, finish_reason: "stop" }], usage: { prompt_tokens: 20, completion_tokens: 2 } };

async function gateway(t: TestContext, handler: (request: IncomingMessage, response: ServerResponse, body: any) => void): Promise<string> {
  const server = createServer(async (request, response) => {
    const parts: Buffer[] = [];
    for await (const part of request) parts.push(Buffer.from(part));
    handler(request, response, JSON.parse(Buffer.concat(parts).toString()));
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(async () => { server.closeAllConnections(); await new Promise<void>((resolve) => server.close(() => resolve())); });
  const address = server.address();
  assert.ok(address && typeof address !== "string");
  return `http://127.0.0.1:${address.port}`;
}

test("OpenAI endpoint accepts host, explicit port, full endpoint and gateway prefix without losing query", () => {
  assert.equal(openAiEndpoint(" https://gateway.example:8443/ ", "openai_chat_completions"), "https://gateway.example:8443/v1/chat/completions");
  assert.equal(openAiEndpoint("https://gateway.example/relay/v1/responses/?api-version=1#ignored", "openai_chat_completions"), "https://gateway.example/relay/v1/chat/completions?api-version=1");
  assert.equal(openAiEndpoint("https://gateway.example/responses", "openai_responses"), "https://gateway.example/responses");
  assert.throws(() => openAiEndpoint("file:///local", "openai_responses"), /HTTP\(S\)/);
  assert.throws(() => openAiEndpoint("https://user:secret@gateway.example", "openai_responses"), /without embedded credentials/);
});

test("real gateway port uses the same address and authentication for connection test and agent", async (t) => {
  const requests: Array<{ url?: string; auth?: string; body: any }> = [];
  const base = await gateway(t, (req, res, body) => {
    requests.push({ url: req.url, auth: req.headers.authorization, body });
    res.setHeader("content-type", "application/json"); res.end(JSON.stringify(ok));
  });
  const baseUrl = `${base}/proxy/v1/chat/completions/?api-version=demo`;
  const probe = await probeModel({ base_url: baseUrl, model: "gpt-6-sol", api_key: "test-key" });
  assert.equal(probe.success, true);
  await new OpenAiCompatibleProvider({ baseUrl, model: "openai/gpt-6-sol", apiKey: "test-key", temperature: 0.5, topP: 0.7, maxOutputTokens: 4096 }).complete(messages, tools);
  assert.deepEqual(requests.map((req) => req.url), ["/proxy/v1/chat/completions?api-version=demo", "/proxy/v1/chat/completions?api-version=demo"]);
  assert.ok(requests.every((req) => req.auth === "Bearer test-key"));
  assert.equal(requests[1].body.max_completion_tokens, 4096);
  assert.equal(requests[1].body.model, "openai/gpt-6-sol");
  assert.equal(requests[1].body.temperature, undefined);
  assert.equal(requests[1].body.top_p, undefined);
  assert.equal(requests[1].body.store, undefined);
  assert.equal(isOpenAiReasoningModel("gpt-6-astra"), true);
});

test("gateway explicitly rejected optional fields are adapted once and remembered", async (t) => {
  const requests: any[] = [];
  const baseUrl = await gateway(t, (_req, res, body) => {
    requests.push(body);
    const param = body.stream_options ? "stream_options" : body.max_completion_tokens ? "max_completion_tokens" : undefined;
    res.setHeader("content-type", "application/json");
    if (param) { res.statusCode = 400; res.end(JSON.stringify({ error: { message: `Unsupported parameter: '${param}'` } })); }
    else res.end(JSON.stringify(ok));
  });
  const provider = new OpenAiCompatibleProvider({ baseUrl, model: "gpt-6-sol", stream: true, maxOutputTokens: 2048 });
  assert.equal((await provider.complete(messages, tools)).text, "OK");
  assert.equal(requests.length, 3);
  assert.equal(requests[2].max_tokens, 2048);
  assert.equal(requests[2].stream, true);
  await provider.complete(messages, tools);
  assert.equal(requests.length, 4);
  assert.equal(requests[3].stream_options, undefined);
  assert.equal(requests[3].max_completion_tokens, undefined);
});

test("authentication and reasoning rejections do not trigger compatibility retries", async (t) => {
  let requests = 0;
  const baseUrl = await gateway(t, (_req, res) => { requests++; res.statusCode = requests === 1 ? 401 : 400; res.end(JSON.stringify({ error: { message: "Unsupported reasoning_effort" } })); });
  const provider = new OpenAiCompatibleProvider({ baseUrl, model: "gpt-6-sol", reasoningEffort: "high" });
  await assert.rejects(provider.complete(messages, tools), /401/);
  await assert.rejects(provider.complete(messages, tools), /400/);
  assert.equal(requests, 2);
});

test("gateway SSE preserves split UTF-8, multi-line data, CRLF and final frame without separator", async (t) => {
  const baseUrl = await gateway(t, (_req, res) => {
    res.setHeader("content-type", "text/event-stream");
    res.write(": heartbeat\r\n\r\n");
    const frame = Buffer.from('data: {"choices":[{\r\ndata: "delta":{"content":"你好"}}]}\r\n\r\n');
    const offset = frame.indexOf(Buffer.from("你好")) + 1;
    res.write(frame.subarray(0, offset));
    setTimeout(() => res.end(Buffer.concat([frame.subarray(offset), Buffer.from("data: [DONE]")])), 5);
  });
  const tokens: string[] = [];
  const result = await new OpenAiCompatibleProvider({ baseUrl, model: "gpt-6-sol", stream: true }).complete(messages, tools, undefined, (token) => tokens.push(token));
  assert.equal(result.text, "你好");
  assert.equal(tokens.join(""), "你好");
});

test("Responses gateway exposes late API failures and recovers completed tool arguments", async (t) => {
  let requests = 0;
  const baseUrl = await gateway(t, (_req, res) => {
    res.setHeader("content-type", "text/event-stream");
    if (++requests === 1) res.end('data: {"type":"response.failed","response":{"error":{"code":"server_error","message":"upstream unavailable"}}}\n\n');
    else res.end([
      { type: "response.output_item.added", output_index: 0, item: { type: "function_call", call_id: "c1", name: "read_file", arguments: "" } },
      { type: "response.output_item.done", output_index: 0, item: { type: "function_call", call_id: "c1", name: "read_file", arguments: '{"path":"README.md"}' } },
      { type: "response.completed", response: { status: "completed", usage: { input_tokens: 10, output_tokens: 5 } } },
    ].map((event) => `data: ${JSON.stringify(event)}\n\n`).join(""));
  });
  const provider = new OpenAiCompatibleProvider({ baseUrl, model: "gpt-6-sol", apiFormat: "openai_responses", stream: true });
  await assert.rejects(provider.complete(messages, tools), (err: unknown) => err instanceof ProviderError && err.details.retryable && err.message.includes("upstream unavailable"));
  const result = await provider.complete(messages, tools);
  assert.deepEqual(result.tool_calls, [{ id: "c1", name: "read_file", input: { path: "README.md" } }]);
  assert.equal(result.usage?.output_tokens, 5);
});

test("partial gateway stream never returns success or retries duplicate output", async (t) => {
  let requests = 0;
  const baseUrl = await gateway(t, (_req, res) => {
    requests++;
    res.setHeader("content-type", "text/event-stream");
    res.end('data: {"choices":[{"delta":{"content":"partial"}}]}\n\n');
  });
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-openai-connection-"));
  const events = new EventBus(path.join(root, "events.jsonl"));
  t.after(async () => { await events.flush(); await rm(root, { recursive: true, force: true }); });
  const settings = new SettingsStore(path.join(root, "settings.json"));
  await settings.update({ api_key: "test", api_format: "openai_chat_completions", model: "gpt-6-sol", base_url: baseUrl, max_retries: 3 });
  const tokens: string[] = [];
  let checkpoint: ChatMessage[] = [];
  events.subscribe((event) => { if (event.type === "llm.token") tokens.push(event.token); });
  const loop = new AgentLoop(new ConfigurableProvider(settings), tools, { workspace: new Workspace(root) }, events, { check: async () => true }, { onCheckpoint: (value) => { if (value.phase === "failed") checkpoint = value.messages; } });
  await assert.rejects(loop.run("gateway-partial", "hello", 3), (error: unknown) => error instanceof ProviderError && error.details.partialResponse === true && error.details.retryable === false && error.details.retryExhausted === true);
  await events.flush();
  assert.equal(requests, 1);
  assert.equal(tokens.join(""), "partial");
  assert.deepEqual(checkpoint.at(-1), { role: "assistant", content: "partial" });
});

test("an empty failed stream retries, and empty saved keys fall back to environment credentials", async (t) => {
  let requests = 0; const auth: Array<string | undefined> = [];
  const baseUrl = await gateway(t, (req, res) => {
    auth.push(req.headers.authorization);
    res.setHeader("content-type", ++requests === 1 ? "text/event-stream" : "application/json");
    res.end(requests === 1 ? ": heartbeat\n\n" : JSON.stringify(ok));
  });
  const previous = process.env.OPENAI_API_KEY; process.env.OPENAI_API_KEY = "env-test-key";
  t.after(() => { if (previous === undefined) delete process.env.OPENAI_API_KEY; else process.env.OPENAI_API_KEY = previous; });
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-openai-empty-stream-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const settings = new SettingsStore(path.join(root, "settings.json"));
  await settings.update({ api_key: "", provider: "openai", keyless: false, api_format: "openai_chat_completions", base_url: baseUrl, model: "gpt-6-sol", max_retries: 2 });
  assert.equal((await new ConfigurableProvider(settings).complete(messages, tools)).text, "OK");
  assert.equal(requests, 2);
  assert.equal((await probeModel({ api_key: "", provider: "openai", model: "gpt-6-sol", base_url: baseUrl })).success, true);
  assert.deepEqual(auth, ["Bearer env-test-key", "Bearer env-test-key", "Bearer env-test-key"]);
});

test("Responses completion finishes even if the gateway leaves the connection open", async (t) => {
  const baseUrl = await gateway(t, (_req, res) => {
    res.setHeader("content-type", "text/event-stream");
    res.write('data: {"type":"response.output_text.delta","delta":"OK"}\n\n');
    res.write('data: {"type":"response.completed","response":{"status":"completed"}}\n\n');
  });
  const result = await new OpenAiCompatibleProvider({ baseUrl, model: "gpt-6-sol", apiFormat: "openai_responses", stream: true, timeoutMs: 1000 }).complete(messages, tools);
  assert.equal(result.text, "OK");
});

test("connection probe works with a stream-only Responses relay", async (t) => {
  const baseUrl = await gateway(t, (_req, res, body) => {
    if (body.stream !== true) { res.statusCode = 400; res.end("stream must be true"); return; }
    res.setHeader("content-type", "text/event-stream");
    res.end([
      { type: "response.output_text.delta", delta: "OK" },
      { type: "response.completed", response: { status: "completed", usage: { input_tokens: 12, output_tokens: 2 } } },
    ].map((event) => `data: ${JSON.stringify(event)}\n\n`).join(""));
  });
  const result = await probeModel({ base_url: `${baseUrl}/responses`, model: "gpt-6-sol", api_format: "openai_responses", api_key: "test-key" });
  assert.equal(result.success, true);
  assert.equal(result.input_tokens, 12);
  assert.equal(result.output_tokens, 2);
});

test("already cancelled connection and backoff send no requests", async (t) => {
  let requests = 0;
  const baseUrl = await gateway(t, (_req, res) => { requests++; res.end(JSON.stringify(ok)); });
  const controller = new AbortController(); controller.abort(new Error("user cancelled"));
  await assert.rejects(new OpenAiCompatibleProvider({ baseUrl, model: "gpt-6-sol" }).complete(messages, tools, controller.signal), /user cancelled/);
  await assert.rejects(abortableDelay(1000, controller.signal), /user cancelled/);
  assert.equal(requests, 0);
});
