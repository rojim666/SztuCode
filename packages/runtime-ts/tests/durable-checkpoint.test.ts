import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { EventBus } from "../src/event-bus.js";
import type { ModelProvider } from "../src/agent-loop.js";
import { RunManager } from "../src/run-manager.js";
import { SessionStore } from "../src/session-store.js";

test("run manager durably checkpoints model context after tool batches and completion", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-checkpoint-")); const sessionsRoot = path.join(root, "sessions"); const events = new EventBus(path.join(root, "events.jsonl"));
  try {
    await writeFile(path.join(root, "sample.txt"), "value\n", "utf8"); const sessions = new SessionStore(sessionsRoot); const session = await sessions.create("chat"); let calls = 0;
    const provider: ModelProvider = { complete: async () => ++calls === 1 ? { text: "", tool_calls: [{ id: "read-1", name: "read_file", input: { path: "sample.txt" } }], stop_reason: "tool_use" } : { text: "done", tool_calls: [], stop_reason: "end_turn" } };
    const manager = new RunManager(events, provider, root, undefined, () => [], async () => ({ contextWindow: 128_000, maxOutputTokens: 8_192 }), sessions);
    const finished = new Promise<void>((resolve) => events.subscribe((event) => { if (event.type === "run.finished") resolve(); })); const runId = manager.start("read it", [], undefined, root, session.id); await sessions.attachRun(session.id, runId); await finished;
    const context = await sessions.modelHistory(session.id); assert.ok(context.some((message) => message.role === "tool" && message.tool_call_id === "read-1")); assert.equal(context.at(-1)?.role, "assistant");
    const records = (await readFile(path.join(sessionsRoot, session.id, "runs", `${runId}.jsonl`), "utf8")).trim().split(/\r?\n/).map((line) => JSON.parse(line));
    assert.deepEqual(records.filter((record) => record.type === "run.checkpoint").map((record) => record.phase), ["tool_batch", "completed"]); assert.ok(records.every((record) => record.run_id === runId));
  } finally { await events.flush(); await rm(root, { recursive: true, force: true }); }
});
