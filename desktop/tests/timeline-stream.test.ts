import assert from "node:assert/strict";
import test from "node:test";
import type { TimelineStep } from "../src/components/timeline/types";
import { appendThinkingBatch, appendTokenBatch, createTokenFrameBatcher } from "../src/utils/timelineStream";

function emptyStep(): TimelineStep {
  return { step: 1, runId: "run-1", status: "thinking", tokens: [], toolCalls: [] };
}

test("appends a token batch without mutating the previous timeline step", () => {
  const previous = {
    ...emptyStep(),
    streamText: "Hello",
    events: [{ id: "text-1", kind: "text" as const, text: "Hello" }],
  };

  const next = appendTokenBatch(previous, [",", " world"]);

  assert.equal(next.streamText, "Hello, world");
  assert.equal(next.events?.at(-1)?.text, "Hello, world");
  assert.equal(previous.streamText, "Hello");
  assert.equal(previous.events.at(-1)?.text, "Hello");
});

test("coalesces tokens into one scheduled batch and preserves their order", () => {
  const scheduled: Array<() => void> = [];
  const batches: Array<{ runId: string; step: number; tokens: string[] }> = [];
  const batcher = createTokenFrameBatcher(
    (batch) => batches.push(batch),
    (callback) => { scheduled.push(callback); return scheduled.length; },
    () => undefined,
  );

  batcher.enqueue("run-1", 3, "A");
  batcher.enqueue("run-1", 3, "B");
  batcher.enqueue("run-1", 3, "C");

  assert.equal(scheduled.length, 1);
  assert.deepEqual(batches, []);
  scheduled[0]();
  assert.deepEqual(batches, [{ runId: "run-1", step: 3, tokens: ["A", "B", "C"] }]);
});

test("flushes pending tokens synchronously before a later run event", () => {
  const batches: Array<{ runId: string; step: number; tokens: string[] }> = [];
  const batcher = createTokenFrameBatcher(
    (batch) => batches.push(batch),
    () => 1,
    () => undefined,
  );

  batcher.enqueue("run-1", 2, "first");
  batcher.flushRun("run-1");

  assert.deepEqual(batches, [{ runId: "run-1", step: 2, tokens: ["first"] }]);
});

test("appends a thinking batch to the step without mutating the previous one", () => {
  const previous = {
    ...emptyStep(),
    thinking: "第一步思考",
    events: [{ id: "thinking-1", kind: "thinking" as const, text: "第一步思考" }],
  };

  const next = appendThinkingBatch(previous, ["、", "第二步思考"]);

  assert.equal(next.thinking, "第一步思考、第二步思考");
  assert.equal(next.events?.at(-1)?.text, "第一步思考、第二步思考");
  assert.equal(previous.thinking, "第一步思考");
  assert.equal(previous.events.at(-1)?.text, "第一步思考");
});

test("appendThinkingBatch creates a thinking event when the tail is not thinking", () => {
  const previous = {
    ...emptyStep(),
    events: [{ id: "text-1", kind: "text" as const, text: "正文" }],
  };

  const next = appendThinkingBatch(previous, ["思考内容"]);

  assert.equal(next.thinking, "思考内容");
  assert.equal(next.events?.length, 2);
  assert.equal(next.events?.at(-1)?.kind, "thinking");
  assert.equal(next.events?.at(-1)?.text, "思考内容");
});
