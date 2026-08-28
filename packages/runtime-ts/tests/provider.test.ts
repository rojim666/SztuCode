import assert from "node:assert/strict";
import test from "node:test";
import { OpenAiCompatibleProvider } from "../src/providers/openai.js";
import { AnthropicMessagesProvider, toAnthropicMessages } from "../src/providers/anthropic.js";
import { ToolRegistry } from "../src/tools.js";

test("OpenAI Responses provider uses /responses and parses text and function calls", async () => {
  const originalFetch = globalThis.fetch;
  let requestUrl = "";
  let requestBody: Record<string, unknown> | undefined;
  globalThis.fetch = (async (input, init) => {
    requestUrl = String(input);
    requestBody = JSON.parse(String(init?.body)) as Record<string, unknown>;
    const payload = { output_text: "done", output: [{ type: "function_call", call_id: "call-1", name: "read_file", arguments: '{"path":"a.txt"}' }], usage: { input_tokens: 12, output_tokens: 4, input_tokens_details: { cached_tokens: 2 } } };
    return new Response(JSON.stringify(payload), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  try {
    const tools = new ToolRegistry();
    tools.register({ name: "read_file", description: "read", permission: "read_only", schema: { type: "object" }, invoke: async () => ({ ok: true, output: "" }) });
    const result = await new OpenAiCompatibleProvider({ apiKey: "test", baseUrl: "http://mock/v1", model: "gpt-test", apiFormat: "openai_responses" }).complete([{ role: "user", content: "hi" }], tools);
    assert.equal(requestUrl, "http://mock/v1/responses");
    assert.equal((requestBody?.model), "gpt-test");
    assert.deepEqual(result.tool_calls, [{ id: "call-1", name: "read_file", input: { path: "a.txt" } }]);
    assert.equal(result.text, "done");
    assert.deepEqual(result.usage, { input_tokens: 12, output_tokens: 4, cache_read_input_tokens: 2 });
  } finally { globalThis.fetch = originalFetch; }
});

test("OpenAI chat provider parses SSE deltas and emits incremental text", async () => {
  const originalFetch = globalThis.fetch;
  const tokens: string[] = [];
  const thinking: string[] = [];
  globalThis.fetch = (async () => {
    const encoder = new TextEncoder();
    const chunks = [
      `data: ${JSON.stringify({ choices: [{ delta: { reasoning_content: "think-", content: "hel" } }] })}\n\n`,
      `data: ${JSON.stringify({ choices: [{ delta: { content: "lo" } }] })}\n\n`,
      `data: ${JSON.stringify({ choices: [{ delta: { tool_calls: [{ index: 0, id: "call-1", function: { name: "read_file", arguments: '{"path":"a' } }] } }] })}\n\n`,
      `data: ${JSON.stringify({ choices: [{ delta: { tool_calls: [{ index: 0, function: { arguments: '.txt"}' } }] } }] })}\n\n`,
      `data: ${JSON.stringify({ usage: { prompt_tokens: 3, completion_tokens: 2 } })}\n\n`,
      "data: [DONE]\n\n",
    ];
    const body = new ReadableStream({ start(controller) { for (const chunk of chunks) controller.enqueue(encoder.encode(chunk)); controller.close(); } });
    return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
  }) as typeof fetch;
  try {
    const tools = new ToolRegistry();
    tools.register({ name: "read_file", description: "read", permission: "read_only", schema: { type: "object" }, invoke: async () => ({ ok: true, output: "" }) });
    const result = await new OpenAiCompatibleProvider({ apiKey: "test", baseUrl: "http://mock/v1", model: "gpt-test", stream: true }).complete([{ role: "user", content: "hi" }], tools, undefined, (token) => tokens.push(token), undefined, (delta) => thinking.push(delta));
    assert.deepEqual(tokens, ["hel", "lo"]);
    assert.deepEqual(thinking, ["think-"]);
    assert.equal(result.text, "hello");
    assert.equal(result.reasoning_content, "think-");
    assert.deepEqual(result.tool_calls, [{ id: "call-1", name: "read_file", input: { path: "a.txt" } }]);
    assert.equal(result.streamed, true);
  } finally { globalThis.fetch = originalFetch; }
});

test("OpenAI chat provider sends reasoning effort and emits non-streaming reasoning", async () => {
  const originalFetch = globalThis.fetch;
  let requestBody: Record<string, any> = {};
  const thinking: string[] = [];
  globalThis.fetch = (async (_input, init) => {
    requestBody = JSON.parse(String(init?.body));
    return new Response(JSON.stringify({ choices: [{ message: { content: "done", reasoning_content: "checked the repository" } }] }), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  try {
    const result = await new OpenAiCompatibleProvider({ apiKey: "test", baseUrl: "http://mock/v1", model: "reasoning-model", reasoningEffort: "high" }).complete([{ role: "user", content: "hi" }], new ToolRegistry(), undefined, undefined, undefined, (value) => thinking.push(value));
    assert.equal(requestBody.reasoning_effort, "high");
    assert.deepEqual(thinking, ["checked the repository"]);
    assert.equal(result.reasoning_content, "checked the repository");
  } finally { globalThis.fetch = originalFetch; }
});

test("OpenAI Responses provider emits streamed reasoning summaries", async () => {
  const originalFetch = globalThis.fetch;
  let requestBody: Record<string, any> = {};
  const thinking: string[] = [];
  globalThis.fetch = (async (_input, init) => {
    requestBody = JSON.parse(String(init?.body));
    const encoder = new TextEncoder();
    const frames = [
      `data: ${JSON.stringify({ type: "response.reasoning_summary_text.delta", delta: "inspect " })}\n\n`,
      `data: ${JSON.stringify({ type: "response.reasoning_summary_text.delta", delta: "files" })}\n\n`,
      `data: ${JSON.stringify({ type: "response.output_text.delta", delta: "done" })}\n\n`,
      `data: ${JSON.stringify({ type: "response.completed", response: { usage: { input_tokens: 3, output_tokens: 2 } } })}\n\n`,
    ];
    const body = new ReadableStream({ start(controller) { for (const frame of frames) controller.enqueue(encoder.encode(frame)); controller.close(); } });
    return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
  }) as typeof fetch;
  try {
    const result = await new OpenAiCompatibleProvider({ apiKey: "test", baseUrl: "http://mock/v1", model: "gpt-test", apiFormat: "openai_responses", reasoningEffort: "medium", stream: true }).complete([{ role: "user", content: "hi" }], new ToolRegistry(), undefined, undefined, undefined, (value) => thinking.push(value));
    assert.deepEqual(requestBody.reasoning, { effort: "medium", summary: "auto" });
    assert.deepEqual(thinking, ["inspect ", "files"]);
    assert.equal(result.reasoning_content, "inspect files");
    assert.equal(result.text, "done");
  } finally { globalThis.fetch = originalFetch; }
});

test("OpenAI chat provider sends reasoning_content back on assistant tool turns", async () => {
  const originalFetch = globalThis.fetch;
  let requestBody: Record<string, any> = {};
  globalThis.fetch = (async (_input, init) => {
    requestBody = JSON.parse(String(init?.body));
    return new Response(JSON.stringify({ choices: [{ message: { content: "continued" } }] }), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  try {
    const messages = [
      { role: "user" as const, content: "inspect" },
      { role: "assistant" as const, content: "", reasoning_content: "private reasoning", tool_calls: [{ id: "call-1", name: "read_file", input: { path: "a.txt" } }] },
      { role: "tool" as const, tool_call_id: "call-1", content: "file contents" },
    ];
    await new OpenAiCompatibleProvider({ apiKey: "test", baseUrl: "http://mock/v1", model: "reasoning-model" }).complete(messages, new ToolRegistry());
    assert.equal(requestBody.messages[1].reasoning_content, "private reasoning");
  } finally { globalThis.fetch = originalFetch; }
});

test("OpenAI-compatible provider supports keyless endpoints without an authorization header", async () => {
  const originalFetch = globalThis.fetch;
  let authorization: string | null = "not-called";
  globalThis.fetch = (async (_input, init) => {
    authorization = new Headers(init?.headers).get("authorization");
    return new Response(JSON.stringify({ choices: [{ message: { content: "ok" } }] }), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  try {
    const result = await new OpenAiCompatibleProvider({ baseUrl: "http://mock/v1", model: "free-model" }).complete([{ role: "user", content: "hi" }], new ToolRegistry());
    assert.equal(authorization, null); assert.equal(result.text, "ok");
  } finally { globalThis.fetch = originalFetch; }
});

test("OpenAI-compatible provider marks stable system and tool prefixes for caching", async () => {
  const originalFetch = globalThis.fetch; let requestBody: Record<string, any> = {};
  globalThis.fetch = (async (_input, init) => { requestBody = JSON.parse(String(init?.body)); return new Response(JSON.stringify({ choices: [{ message: { content: "ok" } }], usage: { prompt_tokens: 10, prompt_tokens_details: { cached_tokens: 6 } } }), { status: 200, headers: { "content-type": "application/json" } }); }) as typeof fetch;
  try {
    const tools = new ToolRegistry(); tools.register({ name: "read_file", description: "read", permission: "read_only", schema: { type: "object" }, invoke: async () => ({ ok: true, output: "" }) });
    const result = await new OpenAiCompatibleProvider({ baseUrl: "http://mock/v1", model: "cached-model", cacheControl: true }).complete([{ role: "system", content: "stable" }, { role: "user", content: "hi" }], tools);
    assert.deepEqual(requestBody.messages[0].cache_control, { type: "ephemeral" });
    assert.deepEqual(requestBody.tools[0].cache_control, { type: "ephemeral" });
    assert.equal(result.usage?.cache_read_input_tokens, 6);
  } finally { globalThis.fetch = originalFetch; }
});

test("Anthropic messages provider parses streaming text, tool JSON, and usage", async () => {
  const originalFetch = globalThis.fetch;
  const tokens: string[] = [];
  globalThis.fetch = (async (_input, init) => {
    const body = JSON.parse(String(init?.body)) as Record<string, unknown>;
    assert.equal(body.stream, true);
    const encoder = new TextEncoder();
    const frames = [
      `event: message_start\ndata: ${JSON.stringify({ message: { usage: { input_tokens: 7 } } })}\n\n`,
      `event: content_block_start\ndata: ${JSON.stringify({ index: 0, content_block: { type: "text", text: "" } })}\n\n`,
      `event: content_block_delta\ndata: ${JSON.stringify({ index: 0, delta: { type: "text_delta", text: "hel" } })}\n\n`,
      `event: content_block_delta\ndata: ${JSON.stringify({ index: 0, delta: { type: "text_delta", text: "lo" } })}\n\n`,
      `event: content_block_start\ndata: ${JSON.stringify({ index: 1, content_block: { type: "tool_use", id: "tool-1", name: "read_file", input: {} } })}\n\n`,
      `event: content_block_delta\ndata: ${JSON.stringify({ index: 1, delta: { type: "input_json_delta", partial_json: '{"path":"a' } })}\n\n`,
      `event: content_block_delta\ndata: ${JSON.stringify({ index: 1, delta: { type: "input_json_delta", partial_json: '.txt"}' } })}\n\n`,
      `event: message_delta\ndata: ${JSON.stringify({ delta: { stop_reason: "tool_use" }, usage: { output_tokens: 4 } })}\n\n`,
    ];
    const stream = new ReadableStream({ start(controller) { for (const frame of frames) controller.enqueue(encoder.encode(frame)); controller.close(); } });
    return new Response(stream, { status: 200, headers: { "content-type": "text/event-stream" } });
  }) as typeof fetch;
  try {
    const tools = new ToolRegistry();
    tools.register({ name: "read_file", description: "read", permission: "read_only", schema: { type: "object" }, invoke: async () => ({ ok: true, output: "" }) });
    const result = await new AnthropicMessagesProvider({ apiKey: "test", baseUrl: "http://mock/v1", model: "claude-test" }).complete([{ role: "user", content: "hi" }], tools, undefined, (token) => tokens.push(token));
    assert.deepEqual(tokens, ["hel", "lo"]);
    assert.equal(result.text, "hello");
    assert.deepEqual(result.tool_calls, [{ id: "tool-1", name: "read_file", input: { path: "a.txt" } }]);
    assert.equal(result.usage?.input_tokens, 7);
    assert.equal(result.usage?.output_tokens, 4);
    assert.equal(result.streamed, true);
  } finally { globalThis.fetch = originalFetch; }
});

test("Anthropic messages provider groups tool results and repairs missing results", () => {
  const messages = toAnthropicMessages([
    { role: "user", content: "inspect" },
    { role: "assistant", content: "", tool_calls: [
      { id: "call-1", name: "read_file", input: { path: "a.txt" } },
      { id: "call-2", name: "read_file", input: { path: "b.txt" } },
    ] },
    { role: "tool", tool_call_id: "call-1", content: "a" },
    { role: "tool", tool_call_id: "call-2", content: "not found", is_error: true },
    { role: "user", content: "continue" },
    { role: "assistant", content: "", tool_calls: [{ id: "call-3", name: "bash", input: { command: "pwd" } }] },
  ]);

  assert.deepEqual(messages, [
    { role: "user", content: [{ type: "text", text: "inspect" }] },
    { role: "assistant", content: [
      { type: "tool_use", id: "call-1", name: "read_file", input: { path: "a.txt" } },
      { type: "tool_use", id: "call-2", name: "read_file", input: { path: "b.txt" } },
    ] },
    { role: "user", content: [
      { type: "tool_result", tool_use_id: "call-1", content: "a" },
      { type: "tool_result", tool_use_id: "call-2", content: "not found", is_error: true },
      { type: "text", text: "continue" },
    ] },
    { role: "assistant", content: [{ type: "tool_use", id: "call-3", name: "bash", input: { command: "pwd" } }] },
    { role: "user", content: [{ type: "tool_result", tool_use_id: "call-3", content: "Tool execution was interrupted before a result was recorded.", is_error: true }] },
  ]);
});

test("Anthropic messages provider streams and preserves signed thinking blocks", async () => {
  const originalFetch = globalThis.fetch; const thinking: string[] = []; let requestBody: Record<string, any> = {};
  globalThis.fetch = (async (_input, init) => {
    requestBody = JSON.parse(String(init?.body)); const encoder = new TextEncoder();
    const frames = [
      `event: message_start\ndata: ${JSON.stringify({ message: { usage: { input_tokens: 5 } } })}\n\n`,
      `event: content_block_start\ndata: ${JSON.stringify({ index: 0, content_block: { type: "thinking", thinking: "", signature: "" } })}\n\n`,
      `event: content_block_delta\ndata: ${JSON.stringify({ index: 0, delta: { type: "thinking_delta", thinking: "inspect " } })}\n\n`,
      `event: content_block_delta\ndata: ${JSON.stringify({ index: 0, delta: { type: "thinking_delta", thinking: "files" } })}\n\n`,
      `event: content_block_delta\ndata: ${JSON.stringify({ index: 0, delta: { type: "signature_delta", signature: "signed-1" } })}\n\n`,
      `event: content_block_start\ndata: ${JSON.stringify({ index: 1, content_block: { type: "text", text: "" } })}\n\n`,
      `event: content_block_delta\ndata: ${JSON.stringify({ index: 1, delta: { type: "text_delta", text: "done" } })}\n\n`,
      `event: message_delta\ndata: ${JSON.stringify({ delta: { stop_reason: "end_turn" }, usage: { output_tokens: 3 } })}\n\n`,
    ];
    return new Response(new ReadableStream({ start(controller) { for (const frame of frames) controller.enqueue(encoder.encode(frame)); controller.close(); } }), { status: 200, headers: { "content-type": "text/event-stream" } });
  }) as typeof fetch;
  try {
    const provider = new AnthropicMessagesProvider({ apiKey: "test", baseUrl: "http://mock/v1", model: "claude-test", reasoningEffort: "high" });
    const result = await provider.complete([{ role: "user", content: "work" }], new ToolRegistry(), undefined, () => undefined, { runId: "run-thinking", step: 2 }, (delta) => thinking.push(delta));
    assert.deepEqual(thinking, ["inspect ", "files"]);
    assert.deepEqual(result.thinking_blocks, [{ type: "thinking", thinking: "inspect files", signature: "signed-1" }]);
    assert.deepEqual(requestBody.thinking, { type: "adaptive" }); assert.deepEqual(requestBody.output_config, { effort: "high" });

    const next = toAnthropicMessages([
      { role: "user", content: "work" },
      { role: "assistant", content: [...result.thinking_blocks!, { type: "text", text: result.text }] },
      { role: "user", content: "continue" },
    ]);
    assert.deepEqual(next[1]?.content[0], { type: "thinking", thinking: "inspect files", signature: "signed-1" });
  } finally { globalThis.fetch = originalFetch; }
});
