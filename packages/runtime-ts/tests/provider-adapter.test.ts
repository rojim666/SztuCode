import assert from "node:assert/strict";
import { test } from "node:test";
import { OpenAiCompatibleProvider } from "../src/providers/openai.js";
import { AnthropicMessagesProvider } from "../src/providers/anthropic.js";
import type { Model } from "@sztucode/ai";

const model: Model = { provider: "test", id: "adapter-model", api: "openai_chat_completions", contextWindow: 4096, maxTokens: 512, reasoning: false };
const context = { messages: [{ role: "user" as const, content: "hi" }], tools: [] };

test("OpenAI adapter maps streamed callbacks to ai events", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => new Response(["data: {\"choices\":[{\"delta\":{\"content\":\"ok\"}}]}\n\n", "data: [DONE]\n\n"].join(""), { status: 200, headers: { "content-type": "text/event-stream" } })) as typeof fetch;
  try {
    const events = [];
    for await (const event of new OpenAiCompatibleProvider({ apiKey: "x", baseUrl: "http://mock/v1", model: "adapter-model", stream: true }).stream(model, context)) events.push(event);
    assert.deepEqual(events.map((event) => event.type), ["token", "usage", "completed"]);
    assert.equal(events.find((event) => event.type === "completed")?.message.text, "ok");
  } finally { globalThis.fetch = originalFetch; }
});

test("Anthropic adapter reports provider errors as events", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => new Response("bad key", { status: 401 })) as typeof fetch;
  try {
    const events = [];
    for await (const event of new AnthropicMessagesProvider({ apiKey: "x", baseUrl: "http://mock/v1", model: "adapter-model" }).stream({ ...model, api: "anthropic_messages" }, context)) events.push(event);
    assert.equal(events.at(-1)?.type, "error");
    assert.equal(events.at(-1)?.type === "error" ? events.at(-1).error.kind : "", "authentication");
  } finally { globalThis.fetch = originalFetch; }
});
