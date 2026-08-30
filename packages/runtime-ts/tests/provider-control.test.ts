import assert from "node:assert/strict";
import test from "node:test";
import { ProviderError, ProviderTimeoutError, parseRetryAfter, retryDelayMs, retryableProviderError } from "../src/providers/errors.js";

test("provider retry metadata honors Retry-After and HTTP dates", () => {
  assert.equal(parseRetryAfter("2"), 2_000);
  assert.equal(parseRetryAfter("Thu, 01 Jan 1970 00:00:03 GMT", 1_000), 2_000);
  const error = new ProviderError("limited", { status: 429, retryAfterMs: 12_000, retryable: true, billingEffect: "none" });
  assert.equal(retryDelayMs(error, 0, () => 0), 12_000);
  assert.equal(retryableProviderError(error), true);
});

test("provider retry uses bounded full jitter without metadata", () => {
  assert.equal(retryDelayMs(new Error("network failed"), 3, () => 0.5), 2_000);
  assert.equal(retryDelayMs(new Error("network failed"), 20, () => 1), 60_000);
  assert.equal(retryableProviderError(new Error("authentication failed (401)")), false);
});

test("529 overload errors are retryable by status list and message", () => {
  const error = new ProviderError("overloaded", { status: 529, retryable: true, billingEffect: "unknown" });
  assert.equal(retryableProviderError(error), true);
  assert.equal(retryableProviderError(new Error("service overloaded (529)")), true);
});

test("ProviderTimeoutError is retryable with no billing effect", () => {
  const error = new ProviderTimeoutError("Anthropic", 1_500);
  assert.ok(error instanceof ProviderError);
  assert.equal(error.message, "Anthropic request timed out after 1500ms");
  assert.equal(error.details.retryable, true);
  assert.equal(error.details.billingEffect, "none");
  assert.equal(retryableProviderError(error), true);
});
