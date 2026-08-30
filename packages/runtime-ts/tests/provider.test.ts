import assert from "node:assert/strict";
import test from "node:test";
import os from "node:os";
import path from "node:path";
import { rm } from "node:fs/promises";
import { OpenAiCompatibleProvider } from "../src/providers/openai.js";
import { AnthropicMessagesProvider, toAnthropicMessages } from "../src/providers/anthropic.js";
import { ConfigurableProvider } from "../src/providers/configurable.js";
import { ProviderError, ProviderTimeoutError } from "../src/providers/errors.js";
import { SettingsStore } from "../src/settings.js";
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

test("OpenAI chat provider removes Anthropic thinking blocks from persisted history", async () => {
  const originalFetch = globalThis.fetch;
  let requestBody: Record<string, any> = {};
  globalThis.fetch = (async (_input, init) => {
    requestBody = JSON.parse(String(init?.body));
    return new Response(JSON.stringify({ choices: [{ message: { content: "continued" } }] }), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  try {
    await new OpenAiCompatibleProvider({ apiKey: "test", baseUrl: "http://mock/v1", model: "gpt-test" }).complete([
      { role: "user", content: "work" },
      { role: "assistant", content: [
        { type: "thinking", thinking: "inspect the repository", signature: "signed-1" },
        { type: "text", text: "I found the issue." },
      ] },
      { role: "user", content: "continue" },
    ], new ToolRegistry());

    assert.equal(requestBody.messages[1].content, "I found the issue.");
    assert.equal(requestBody.messages[1].reasoning_content, undefined);
    assert.equal(JSON.stringify(requestBody.messages).includes('"type":"thinking"'), false);
  } finally { globalThis.fetch = originalFetch; }
});

test("OpenAI Responses provider removes Anthropic thinking blocks from persisted history", async () => {
  const originalFetch = globalThis.fetch;
  let requestBody: Record<string, any> = {};
  globalThis.fetch = (async (_input, init) => {
    requestBody = JSON.parse(String(init?.body));
    return new Response(JSON.stringify({ output_text: "continued", status: "completed" }), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  try {
    await new OpenAiCompatibleProvider({ apiKey: "test", baseUrl: "http://mock/v1", model: "gpt-test", apiFormat: "openai_responses" }).complete([
      { role: "user", content: "work" },
      { role: "assistant", content: [
        { type: "thinking", thinking: "private reasoning", signature: "signed-1" },
        { type: "text", text: "Public answer" },
      ] },
      { role: "user", content: "continue" },
    ], new ToolRegistry());

    assert.deepEqual(requestBody.input[1], { role: "assistant", content: [{ type: "input_text", text: "Public answer" }] });
    assert.equal(JSON.stringify(requestBody.input).includes('"type":"thinking"'), false);
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
    assert.deepEqual(requestBody.thinking, { type: "enabled", budget_tokens: 24_576 });
    assert.equal(requestBody.output_config, undefined);
    assert.equal(requestBody.max_tokens, 24_576 + 4_096);

    const next = toAnthropicMessages([
      { role: "user", content: "work" },
      { role: "assistant", content: [...result.thinking_blocks!, { type: "text", text: result.text }] },
      { role: "user", content: "continue" },
    ]);
    assert.deepEqual(next[1]?.content[0], { type: "thinking", thinking: "inspect files", signature: "signed-1" });
  } finally { globalThis.fetch = originalFetch; }
});

test("OpenAI chat provider repairs malformed tool JSON instead of throwing", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => new Response(JSON.stringify({
    choices: [{ finish_reason: "length", message: { content: "", tool_calls: [{ id: "call-bad", function: { name: "read_file", arguments: '{"path":"a.txt"' } }] } }],
  }), { status: 200, headers: { "content-type": "application/json" } })) as typeof fetch;
  try {
    const tools = new ToolRegistry();
    tools.register({ name: "read_file", description: "read", permission: "read_only", schema: { type: "object", required: ["path"] }, invoke: async () => ({ ok: true, output: "" }) });
    const result = await new OpenAiCompatibleProvider({ baseUrl: "http://mock/v1", model: "gpt-test" }).complete([{ role: "user", content: "hi" }], tools);
    assert.deepEqual(result.tool_calls, [{ id: "call-bad", name: "read_file", input: {} }]);
    assert.equal(result.stop_reason, "max_tokens");
  } finally { globalThis.fetch = originalFetch; }
});

test("OpenAI chat provider preserves max_tokens finish reason", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => new Response(JSON.stringify({ choices: [{ finish_reason: "length", message: { content: "partial" } }] }), { status: 200, headers: { "content-type": "application/json" } })) as typeof fetch;
  try {
    const result = await new OpenAiCompatibleProvider({ baseUrl: "http://mock/v1", model: "gpt-test" }).complete([{ role: "user", content: "hi" }], new ToolRegistry());
    assert.equal(result.stop_reason, "max_tokens");
  } finally { globalThis.fetch = originalFetch; }
});

test("OpenAI Responses provider preserves incomplete max_output_tokens reason", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => new Response(JSON.stringify({ status: "incomplete", incomplete_details: { reason: "max_output_tokens" }, output_text: "partial" }), { status: 200, headers: { "content-type": "application/json" } })) as typeof fetch;
  try {
    const result = await new OpenAiCompatibleProvider({ baseUrl: "http://mock/v1", model: "gpt-test", apiFormat: "openai_responses" }).complete([{ role: "user", content: "hi" }], new ToolRegistry());
    assert.equal(result.stop_reason, "max_tokens");
  } finally { globalThis.fetch = originalFetch; }
});

test("OpenAI streaming provider repairs malformed tool JSON and preserves max_tokens", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    const encoder = new TextEncoder();
    const frames = [
      `data: ${JSON.stringify({ choices: [{ delta: { tool_calls: [{ index: 0, id: "call-bad", function: { name: "read_file", arguments: '{"path":"a.txt"' } }] } }] })}\n\n`,
      `data: ${JSON.stringify({ choices: [{ delta: {}, finish_reason: "length" }] })}\n\n`,
      "data: [DONE]\n\n",
    ];
    return new Response(new ReadableStream({ start(controller) { for (const frame of frames) controller.enqueue(encoder.encode(frame)); controller.close(); } }), { status: 200, headers: { "content-type": "text/event-stream" } });
  }) as typeof fetch;
  try {
    const tools = new ToolRegistry();
    tools.register({ name: "read_file", schema: { type: "object", required: ["path"] }, invoke: async () => ({ ok: true, output: "" }) });
    const result = await new OpenAiCompatibleProvider({ baseUrl: "http://mock/v1", model: "gpt-test", stream: true }).complete([{ role: "user", content: "hi" }], tools);
    assert.deepEqual(result.tool_calls, [{ id: "call-bad", name: "read_file", input: {} }]);
    assert.equal(result.stop_reason, "max_tokens");
  } finally { globalThis.fetch = originalFetch; }
});

test("Anthropic provider preserves max_tokens stop reason", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => new Response(JSON.stringify({ stop_reason: "max_tokens", content: [{ type: "text", text: "partial" }] }), { status: 200, headers: { "content-type": "application/json" } })) as typeof fetch;
  try {
    const result = await new AnthropicMessagesProvider({ apiKey: "test", baseUrl: "http://mock/v1", model: "claude-test" }).complete([{ role: "user", content: "hi" }], new ToolRegistry());
    assert.equal(result.stop_reason, "max_tokens");
  } finally { globalThis.fetch = originalFetch; }
});

test("OpenAI Responses provider strips cache_control from tool definitions", async () => {
  const originalFetch = globalThis.fetch;
  let requestBody: Record<string, any> = {};
  globalThis.fetch = (async (_input, init) => {
    requestBody = JSON.parse(String(init?.body));
    return new Response(JSON.stringify({ output_text: "done", status: "completed" }), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  try {
    const tools = new ToolRegistry();
    tools.register({ name: "read_file", description: "read", permission: "read_only", schema: { type: "object" }, invoke: async () => ({ ok: true, output: "" }) });
    await new OpenAiCompatibleProvider({ apiKey: "test", baseUrl: "http://mock/v1", model: "gpt-test", apiFormat: "openai_responses", cacheControl: true }).complete([{ role: "user", content: "hi" }], tools);
    assert.equal(JSON.stringify(requestBody.tools).includes("cache_control"), false);
    assert.equal(requestBody.tools[0].name, "read_file");
  } finally { globalThis.fetch = originalFetch; }
});

test("OpenAI chat provider keeps cache_control in tool definitions", async () => {
  const originalFetch = globalThis.fetch;
  let requestBody: Record<string, any> = {};
  globalThis.fetch = (async (_input, init) => {
    requestBody = JSON.parse(String(init?.body));
    return new Response(JSON.stringify({ choices: [{ message: { content: "ok" } }] }), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  try {
    const tools = new ToolRegistry();
    tools.register({ name: "read_file", description: "read", permission: "read_only", schema: { type: "object" }, invoke: async () => ({ ok: true, output: "" }) });
    await new OpenAiCompatibleProvider({ baseUrl: "http://mock/v1", model: "cached-model", cacheControl: true }).complete([{ role: "user", content: "hi" }], tools);
    assert.deepEqual(requestBody.tools[0].cache_control, { type: "ephemeral" });
  } finally { globalThis.fetch = originalFetch; }
});

test("OpenAI chat provider adapts sampling parameters for reasoning models", async () => {
  const originalFetch = globalThis.fetch;
  let requestBody: Record<string, any> = {};
  globalThis.fetch = (async (_input, init) => {
    requestBody = JSON.parse(String(init?.body));
    return new Response(JSON.stringify({ choices: [{ message: { content: "ok" } }] }), { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  try {
    const reasoning = new OpenAiCompatibleProvider({ apiKey: "test", baseUrl: "http://mock/v1", model: "o3-mini", maxOutputTokens: 4096, temperature: 0.7, topP: 0.9 });
    await reasoning.complete([{ role: "user", content: "hi" }], new ToolRegistry());
    assert.equal(requestBody.max_completion_tokens, 4096);
    assert.equal(requestBody.max_tokens, undefined);
    assert.equal(requestBody.temperature, undefined);
    assert.equal(requestBody.top_p, undefined);

    const regular = new OpenAiCompatibleProvider({ apiKey: "test", baseUrl: "http://mock/v1", model: "gpt-4o", maxOutputTokens: 4096, temperature: 0.7, topP: 0.9 });
    await regular.complete([{ role: "user", content: "hi" }], new ToolRegistry());
    assert.equal(requestBody.max_tokens, 4096);
    assert.equal(requestBody.max_completion_tokens, undefined);
    assert.equal(requestBody.temperature, 0.7);
    assert.equal(requestBody.top_p, 0.9);

    const effort = new OpenAiCompatibleProvider({ apiKey: "test", baseUrl: "http://mock/v1", model: "gpt-4o", maxOutputTokens: 4096, reasoningEffort: "high" });
    await effort.complete([{ role: "user", content: "hi" }], new ToolRegistry());
    assert.equal(requestBody.max_completion_tokens, 4096);
    assert.equal(requestBody.max_tokens, undefined);
    assert.equal(requestBody.reasoning_effort, "high");
  } finally { globalThis.fetch = originalFetch; }
});

test("Provider timeout aborts produce retryable ProviderTimeoutError", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (_input: unknown, init?: RequestInit) => {
    await new Promise((_resolve, reject) => { init?.signal?.addEventListener("abort", () => reject(init?.signal?.reason), { once: true }); });
    return new Response("unreachable");
  }) as typeof fetch;
  try {
    for (const [provider, errorName, prefix] of [
      [new AnthropicMessagesProvider({ apiKey: "test", baseUrl: "http://mock/v1", model: "claude-test", timeoutMs: 30 }), "ProviderTimeoutError", "Anthropic"],
      [new OpenAiCompatibleProvider({ baseUrl: "http://mock/v1", model: "gpt-test", timeoutMs: 30 }), "ProviderTimeoutError", "OpenAI-compatible"],
    ] as const) {
      await assert.rejects(
        provider.complete([{ role: "user", content: "hi" }], new ToolRegistry()),
        (error: unknown) => error instanceof ProviderTimeoutError && error instanceof ProviderError && error.name === errorName && error.message === `${prefix} request timed out after 30ms` && error.details.retryable === true && error.details.billingEffect === "none",
      );
    }
  } finally { globalThis.fetch = originalFetch; }
});

test("Anthropic provider applies idle timeout between stream chunks", async () => {
  const originalFetch = globalThis.fetch;
  const tokens: string[] = [];
  globalThis.fetch = (async (_input: unknown, init?: RequestInit) => {
    const encoder = new TextEncoder();
    let aborted = false;
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode(`event: content_block_delta\ndata: ${JSON.stringify({ index: 0, delta: { type: "text_delta", text: "slow" } })}\n\n`));
        init?.signal?.addEventListener("abort", () => { aborted = true; try { controller.error(new Error("aborted")); } catch { /* 流已结束 */ } }, { once: true });
      },
      async pull(controller) { await new Promise((resolve) => setTimeout(resolve, 100)); if (aborted) return; controller.enqueue(encoder.encode(`event: content_block_delta\ndata: ${JSON.stringify({ index: 0, delta: { type: "text_delta", text: "late" } })}\n\n`)); controller.close(); },
    });
    return new Response(stream, { status: 200, headers: { "content-type": "text/event-stream" } });
  }) as typeof fetch;
  try {
    await assert.rejects(
      new AnthropicMessagesProvider({ apiKey: "test", baseUrl: "http://mock/v1", model: "claude-test", timeoutMs: 50 }).complete([{ role: "user", content: "hi" }], new ToolRegistry(), undefined, (token) => tokens.push(token)),
      (error: unknown) => error instanceof ProviderTimeoutError && error.message.includes("50ms"),
    );
    assert.deepEqual(tokens, ["slow"]);
  } finally { globalThis.fetch = originalFetch; }
});

test("OpenAI provider keeps streaming while chunks arrive within the idle timeout", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => {
    const encoder = new TextEncoder();
    const chunks = ["data: {\"choices\":[{\"delta\":{\"content\":\"a\"}}]}\n\n", "data: {\"choices\":[{\"delta\":{\"content\":\"b\"}}]}\n\n", "data: [DONE]\n\n"];
    const stream = new ReadableStream<Uint8Array>({
      async pull(controller) { await new Promise((resolve) => setTimeout(resolve, 40)); controller.enqueue(encoder.encode(chunks.shift()!)); if (!chunks.length) controller.close(); },
    });
    return new Response(stream, { status: 200, headers: { "content-type": "text/event-stream" } });
  }) as typeof fetch;
  try {
    const result = await new OpenAiCompatibleProvider({ baseUrl: "http://mock/v1", model: "gpt-test", stream: true, timeoutMs: 70 }).complete([{ role: "user", content: "hi" }], new ToolRegistry());
    assert.equal(result.text, "ab");
    assert.equal(result.streamed, true);
  } finally { globalThis.fetch = originalFetch; }
});

test("configurable provider marks retry exhaustion even when max_retries exceeds the cap", async () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = (async () => { calls += 1; return new Response("unavailable", { status: 503, headers: { "retry-after": "0" } }); }) as typeof fetch;
  const settingsDir = path.join(os.tmpdir(), `sztu-provider-retry-${Date.now()}-${Math.random().toString(16).slice(2)}`);
  const originalKey = process.env.OPENAI_API_KEY;
  process.env.OPENAI_API_KEY = "test";
  try {
    const settings = new SettingsStore(path.join(settingsDir, "runtime-settings.json"));
    await settings.update({ max_retries: 99, timeout_s: 1, model: "gpt-test" });
    await assert.rejects(
      new ConfigurableProvider(settings).complete([{ role: "user", content: "hi" }], new ToolRegistry()),
      (error: unknown) => error instanceof ProviderError && error.details.retryExhausted === true && error.details.retryable === true,
    );
    assert.equal(calls, 10);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalKey === undefined) delete process.env.OPENAI_API_KEY;
    else process.env.OPENAI_API_KEY = originalKey;
    await rm(settingsDir, { recursive: true, force: true });
  }
});

