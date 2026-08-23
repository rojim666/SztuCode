import assert from "node:assert/strict";
import test from "node:test";
import { resolveComposerSubmitMode } from "../src/utils/composerSubmission";

test("idle submissions always use the queue path that starts a run immediately", () => {
  assert.equal(resolveComposerSubmitMode(false, "enter", true), "queue");
  assert.equal(resolveComposerSubmitMode(false, "accelerated", true), "queue");
});

test("accelerated submission reverses the preferred busy behavior", () => {
  assert.equal(resolveComposerSubmitMode(true, "enter", true, "queue"), "queue");
  assert.equal(resolveComposerSubmitMode(true, "accelerated", true, "queue"), "steer");
  assert.equal(resolveComposerSubmitMode(true, "enter", true, "steer"), "steer");
  assert.equal(resolveComposerSubmitMode(true, "accelerated", true, "steer"), "queue");
});

test("missing steering support falls back to queue", () => {
  assert.equal(resolveComposerSubmitMode(true, "accelerated", false, "queue"), "queue");
});
