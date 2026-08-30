import assert from "node:assert/strict";
import test from "node:test";
import { ProviderError, parseRetryAfter, retryDelayMs, retryableProviderError } from "../src/providers/errors.js";

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
