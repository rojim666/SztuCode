import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { AgentLoop, type ModelProvider } from "../src/agent-loop.js";
import { EventBus } from "../src/event-bus.js";
import { loadPermissionPolicy, savePermissionPolicy } from "../src/permission-policy.js";
import { PermissionManager } from "../src/permissions.js";
import { createWorkspaceTools } from "../src/tools.js";
import { Workspace } from "../src/workspace.js";

test("read_file adds stable line numbers and paginates by line", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-read-page-"));
  try {
    await writeFile(path.join(root, "sample.txt"), "one\r\ntwo\r\nthree\r\n", "utf8");
    const result = await createWorkspaceTools().get("read_file")!.invoke({ path: "sample.txt", offset: 1, limit: 1 }, { workspace: new Workspace(root) });
    assert.equal(result.ok, true); assert.match(result.output, /^\s+2\ttwo/); assert.match(result.output, /lines 2-2\/3/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("edit_file normalizes CRLF, honors line anchors, and keeps multi-edit atomic", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-edit-lines-"));
  try {
    const target = path.join(root, "sample.txt"); await writeFile(target, "same\r\nsame\r\ntail\r\n", "utf8"); const edit = createWorkspaceTools().get("edit_file")!;
    const result = await edit.invoke({ path: "sample.txt", edits: [{ old_string: "same", new_string: "changed", start_line: 2, end_line: 2 }, { old_string: "tail", new_string: "done" }] }, { workspace: new Workspace(root) });
    assert.equal(result.ok, true); assert.equal(await readFile(target, "utf8"), "same\nchanged\ndone\n");
    const failed = await edit.invoke({ path: "sample.txt", edits: [{ old_string: "same", new_string: "first" }, { old_string: "missing", new_string: "never" }] }, { workspace: new Workspace(root) });
    assert.equal(failed.ok, false); assert.equal(await readFile(target, "utf8"), "same\nchanged\ndone\n"); assert.match(failed.error ?? "", /re-read/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("parameter permission rules round-trip and match only their glob", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-param-policy-")); const policyPath = path.join(root, "policy.toml"); const events = new EventBus(path.join(root, "events.jsonl"));
  try {
    savePermissionPolicy(new Map([["write_file(src/**)", "allow"], ["bash(git diff:*)", "allow"]]), policyPath);
    assert.deepEqual([...loadPermissionPolicy(policyPath)], [["bash(git diff:*)", "allow"], ["write_file(src/**)", "allow"]]);
    const manager = new PermissionManager(events, 5, policyPath);
    assert.equal(await manager.check("r", "1", "write_file", { path: "src/a.ts" }, "workspace_write"), true);
    assert.equal(await manager.check("r", "2", "bash", { command: "git diff --cached" }, "workspace_write"), true);
    assert.equal(await manager.check("r", "3", "write_file", { path: "docs/a.ts" }, "workspace_write"), false);
  } finally { await events.flush(); await rm(root, { recursive: true, force: true }); }
});

test("agent loop coalesces synchronous streaming deltas", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-token-frame-")); const events = new EventBus(path.join(root, "events.jsonl")); const tokens: string[] = [];
  try {
    events.subscribe((event) => { if (event.type === "llm.token") tokens.push(event.token); });
    const provider: ModelProvider = { complete: async (_messages, _tools, _signal, onToken) => { onToken?.("a"); onToken?.("b"); onToken?.("c"); return { text: "abc", tool_calls: [], stop_reason: "end_turn", streamed: true }; } };
    await new AgentLoop(provider, createWorkspaceTools(), { workspace: new Workspace(root) }, events, { check: async () => true }, { streaming: true }).run("frame", "work", 1);
    assert.deepEqual(tokens, ["abc"]);
  } finally { await events.flush(); await rm(root, { recursive: true, force: true }); }
});
