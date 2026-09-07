import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { EventBus } from "../src/event-bus.js";

test("event bus flushes buffered stream events in publication order", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-event-bus-"));
  const tracePath = path.join(root, "nested", "events.jsonl");
  const events = new EventBus(tracePath);
  try {
    for (let index = 0; index < 250; index += 1) {
      events.publish({ type: "llm.token", run_id: "run-1", token: String(index), ts: `t-${index}` });
    }
    events.publish({ type: "step.finished", run_id: "run-1", step: 1, ts: "done" });
    await events.flush();

    const rows = (await readFile(tracePath, "utf8")).trim().split(/\r?\n/).map((row) => JSON.parse(row));
    assert.equal(rows.length, 251);
    assert.deepEqual(rows.slice(0, 250).map((event) => event.token), Array.from({ length: 250 }, (_, index) => String(index)));
    assert.equal(rows.at(-1)?.type, "step.finished");
  } finally {
    await events.flush();
    await rm(root, { recursive: true, force: true });
  }
});

test("event bus flush writes a stream-only trace without waiting for the timer", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-event-bus-flush-"));
  const tracePath = path.join(root, "events.jsonl");
  const events = new EventBus(tracePath);
  try {
    events.publish({ type: "llm.thinking", run_id: "run-2", step: 3, thinking: "checking", ts: "now" });
    await events.flush();
    const rows = (await readFile(tracePath, "utf8")).trim().split(/\r?\n/).map((row) => JSON.parse(row));
    assert.deepEqual(rows.map((event) => event.type), ["llm.thinking"]);
  } finally {
    await events.flush();
    await rm(root, { recursive: true, force: true });
  }
});
