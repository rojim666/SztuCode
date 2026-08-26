import assert from "node:assert/strict";
import { test } from "node:test";
import { normalizeProviderError, ProviderError, isRetryableProviderError } from "../src/index.js";
import { streamFromCompletion } from "../src/stream.js";
import type { Model } from "../src/types.js";

const model: Model = { provider: "test", id: "model-1", api: "test", contextWindow: 1000, maxTokens: 100, reasoning: true };

test("streamFromCompletion emits assistant lifecycle events", async () => {
  const events = [];
  for await (const event of streamFromCompletion(async (_model, _context, _options, callbacks) => {
    callbacks.onThinking?.("plan"); callbacks.onToken?.("hello");
    return { role: "assistant", text: "hello", toolCalls: [{ id: "call-1", name: "read", input: {} }], stopReason: "tool_use", usage: { inputTokens: 2, outputTokens: 3, cacheReadTokens: 0, cacheWriteTokens: 0, totalTokens: 5 } };
  }, model, { messages: [] })) events.push(event);
  assert.deepEqual(events.map((event) => event.type), ["thinking", "token", "tool_call", "usage", "completed"]);
});

test("provider errors normalize retry and abort semantics", () => {
  const rateLimit = normalizeProviderError(new Error("request failed (429)"));
  assert.equal(rateLimit.kind, "rate_limit"); assert.equal(rateLimit.retryable, true); assert.equal(isRetryableProviderError(rateLimit), true);
  const abort = normalizeProviderError(Object.assign(new Error("cancelled"), { name: "AbortError" }));
  assert.equal(abort.kind, "aborted"); assert.equal(abort.retryable, false);
  assert.equal(new ProviderError("authentication", "bad key").retryable, false);
});

test("streamFromCompletion emits aborted when the provider observes cancellation", async () => {
  const controller = new AbortController();
  controller.abort();
  const events = [];
  for await (const event of streamFromCompletion(async (_model, _context, options) => {
    if (options.signal?.aborted) throw Object.assign(new Error("cancelled"), { name: "AbortError" });
    await new Promise<void>((resolve, reject) => {
      options.signal?.addEventListener("abort", () => reject(Object.assign(new Error("cancelled"), { name: "AbortError" })), { once: true });
    });
    throw new Error("unreachable");
  }, model, { messages: [] }, { signal: controller.signal })) {
    events.push(event);
  }
  assert.deepEqual(events, [{ type: "aborted", reason: "Provider request was aborted" }]);
});
