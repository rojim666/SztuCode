import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { AgentLoop, type ModelProvider } from "../src/agent-loop.js";
import { EventBus } from "../src/event-bus.js";
import { createReadRefTool, OffloadManager } from "../src/offload.js";
import { createWorkspaceTools } from "../src/tools.js";
import { Workspace } from "../src/workspace.js";

test("offload stores complete output and read_ref pages it safely", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-offload-"));
  try {
    const manager = new OffloadManager(root, { forceTools: new Set() });
    const original = "complete output line\n".repeat(200);
    assert.equal(manager.shouldOffload("read_file", original), true);
    const record = await manager.offload("read_file", "tool-1", original, "run-1");
    assert.equal(await manager.readRef(record.ref_path), original);
    assert.match(manager.placeholder(record), /read_ref/);
    const page = await createReadRefTool(manager).invoke({ ref_path: record.ref_path, offset: 100, limit: 200 }, {} as never);
    assert.equal(page.ok, true); assert.match(page.output, /next_offset=300/);
    assert.equal((await createReadRefTool(manager).invoke({ ref_path: "../outside.md" }, {} as never)).ok, false);
    const index = await readFile(path.join(root, "offload", "offload.jsonl"), "utf8"); assert.match(index, /"run_id":"run-1"/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("agent loop offloads tool output and can recover it with read_ref", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-offload-loop-"));
  try {
    const original = "0123456789".repeat(500); await writeFile(path.join(root, "large.txt"), original);
    let call = 0; let refPath = ""; let recovered = "";
    const provider: ModelProvider = { complete: async (messages) => {
      call += 1;
      if (call === 1) return { text: "", tool_calls: [{ id: "read-1", name: "read_file", input: { path: "large.txt" } }], stop_reason: "tool_use" };
      const last = String(messages.at(-1)?.content ?? "");
      if (call === 2) { assert.match(last, /\[上下文卸载:/); refPath = /\[上下文卸载: ([^\]]+)\]/.exec(last)?.[1] ?? ""; return { text: "", tool_calls: [{ id: "ref-1", name: "read_ref", input: { ref_path: refPath, limit: 8000 } }], stop_reason: "tool_use" }; }
      recovered = last; return { text: "done", tool_calls: [], stop_reason: "end_turn" };
    } };
    const loop = new AgentLoop(provider, createWorkspaceTools(), { workspace: new Workspace(root) }, new EventBus(path.join(root, "events.jsonl")), { check: async () => true }, { offloadRoot: path.join(root, "run-data"), offloadMinChars: 100 });
    assert.equal((await loop.run("run-1", "read it", 4)).text, "done");
    assert.ok(refPath.startsWith("refs/")); assert.match(recovered, /0123456789/); assert.match(recovered, /\[ref page:/);
  } finally { await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});

test("disabled offload creates no files", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-offload-disabled-"));
  try { const manager = new OffloadManager(path.join(root, "run"), { enabled: false }); assert.equal(manager.shouldOffload("bash", "large".repeat(1000)), false); await assert.rejects(readFile(path.join(root, "run", "offload", "offload.jsonl"))); }
  finally { await rm(root, { recursive: true, force: true }); }
});

test("agent loop falls back to bounded context when offload storage fails", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-offload-fallback-"));
  try {
    const blocked = path.join(root, "not-a-directory"); await writeFile(blocked, "file");
    let calls = 0; let observed = "";
    const provider: ModelProvider = { complete: async (messages) => { calls += 1; if (calls === 1) return { text: "", tool_calls: [{ id: "large", name: "read_file", input: { path: "large.txt" } }], stop_reason: "tool_use" }; observed = String(messages.at(-1)?.content ?? ""); return { text: "done", tool_calls: [], stop_reason: "end_turn" }; } };
    await writeFile(path.join(root, "large.txt"), "x".repeat(20_000));
    const loop = new AgentLoop(provider, createWorkspaceTools(), { workspace: new Workspace(root) }, new EventBus(path.join(root, "events.jsonl")), { check: async () => true }, { offloadRoot: blocked, offloadMinChars: 100 });
    assert.equal((await loop.run("fallback", "read it", 3)).text, "done");
    assert.match(observed, /chars omitted/); assert.ok(observed.length <= 4_000);
  } finally { await rm(root, { recursive: true, force: true }); }
});
