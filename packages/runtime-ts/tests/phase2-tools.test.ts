import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, utimes, writeFile } from "node:fs/promises";
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

test("glob_search sorts matches by modification time, newest first", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-glob-mtime-"));
  try {
    for (let index = 1; index <= 5; index += 1) {
      const file = path.join(root, `a${index}.txt`); await writeFile(file, `file-${index}`);
      // 时间戳单调递增：a5 最新
      const ts = new Date(Date.UTC(2020, 0, index)); await utimes(file, ts, ts);
    }
    const result = await createWorkspaceTools().get("glob_search")!.invoke({ pattern: "a*.txt" }, { workspace: new Workspace(root) });
    assert.equal(result.ok, true);
    assert.deepEqual(result.output.split("\n"), ["a5.txt", "a4.txt", "a3.txt", "a2.txt", "a1.txt"]);
    assert.ok(!result.output.includes("[glob truncated"));
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("glob_search reports a visible truncation marker at the 200-match limit", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-glob-trunc-"));
  try {
    // 201 个命中文件：触发截断
    for (let index = 0; index < 201; index += 1) await writeFile(path.join(root, `f${String(index).padStart(3, "0")}.txt`), "x");
    const result = await createWorkspaceTools().get("glob_search")!.invoke({ pattern: "f*.txt" }, { workspace: new Workspace(root) });
    assert.equal(result.ok, true);
    const lines = result.output.split("\n");
    assert.equal(lines.length, 201); // 200 个命中 + 1 行截断标记
    assert.equal(lines.at(-1), "[glob truncated: 200+ matches; narrow the pattern to continue]");
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("grep_search caps total matches at 200 with a truncation footer", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-grep-trunc-"));
  try {
    // 300 个文件各含一行匹配：全局共享计数到 200 后早停
    for (let index = 0; index < 300; index += 1) await writeFile(path.join(root, `g${String(index).padStart(3, "0")}.txt`), "needle here\n");
    const result = await createWorkspaceTools().get("grep_search")!.invoke({ pattern: "needle" }, { workspace: new Workspace(root) });
    assert.equal(result.ok, true);
    const matches = result.output.split("\n").filter((line) => line.includes(":1: needle here"));
    assert.equal(matches.length, 200);
    assert.match(result.output, /\[search truncated: .*matches=200\+/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("grep_search excludes noise directories in both backends", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-grep-ignored-"));
  try {
    await mkdir(path.join(root, "node_modules", "dep"), { recursive: true });
    await mkdir(path.join(root, ".git"), { recursive: true });
    await writeFile(path.join(root, "node_modules", "dep", "x.txt"), "needle\n");
    await writeFile(path.join(root, ".git", "hidden.txt"), "needle\n");
    await writeFile(path.join(root, "real.txt"), "needle\n");
    const result = await createWorkspaceTools().get("grep_search")!.invoke({ pattern: "needle" }, { workspace: new Workspace(root) });
    assert.equal(result.ok, true);
    assert.match(result.output, /real\.txt:1: needle/);
    assert.ok(!result.output.includes("node_modules"), "node_modules must not be searched");
    assert.ok(!result.output.includes(".git/"), ".git must not be searched");
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("list_dir excludes noise directories like .git and node_modules", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-ls-ignore-"));
  try {
    await mkdir(path.join(root, ".git", "objects"), { recursive: true });
    await mkdir(path.join(root, "node_modules", "dep"), { recursive: true });
    await mkdir(path.join(root, "src"), { recursive: true });
    await writeFile(path.join(root, "main.txt"), "x");
    const result = await createWorkspaceTools().get("list_dir")!.invoke({ path: ".", max_depth: 2 }, { workspace: new Workspace(root) });
    assert.equal(result.ok, true);
    assert.ok(!result.output.includes(".git"), ".git must be hidden");
    assert.ok(!result.output.includes("node_modules"), "node_modules must be hidden");
    assert.match(result.output, /src\//);
    assert.match(result.output, /main\.txt/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("bash background jobs start, report status, stream logs, and can be killed", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-bash-bg-"));
  const dataDir = path.join(root, "data"); const previous = process.env.SZTU_DATA_DIR; process.env.SZTU_DATA_DIR = dataDir;
  try {
    const tools = createWorkspaceTools(); const context = { workspace: new Workspace(root), runId: "bg-run" };
    const started = await tools.get("bash")!.invoke({ command: "sleep 60", background: true }, context);
    assert.equal(started.ok, true);
    const jobMatch = started.output.match(/Started background job (\S+)\./);
    assert.ok(jobMatch, `expected job id in: ${started.output}`);
    const jobId = jobMatch![1]!;
    const listed = await tools.get("bash_status")!.invoke({}, context);
    assert.equal(listed.ok, true);
    assert.match(listed.output, new RegExp(`${jobId}\\s+running`));
    // 终止：SIGTERM 后状态变为 killed
    const killed = await tools.get("bash_kill")!.invoke({ job_id: jobId }, context);
    assert.equal(killed.ok, true);
    const afterKill = await tools.get("bash_status")!.invoke({}, context);
    assert.match(afterKill.output, new RegExp(`${jobId}\\s+killed`));
    assert.equal((await tools.get("bash_kill")!.invoke({ job_id: jobId }, context)).ok, false); // 已终止的任务不能再 kill
    // 快速任务：日志经 bash_output 可读，带分页页脚
    const quick = await tools.get("bash")!.invoke({ command: "echo background-works", background: true }, context);
    const quickId = quick.output.match(/Started background job (\S+)\./)?.[1] ?? "";
    assert.ok(quickId);
    const deadline = Date.now() + 10_000; let output = "";
    do { output = (await tools.get("bash_output")!.invoke({ job_id: quickId }, context)).output; if (!output.includes("background-works")) await new Promise((resolve) => setTimeout(resolve, 100)); } while (!output.includes("background-works") && Date.now() < deadline);
    assert.match(output, /background-works/);
    assert.match(output, /\[log page: job=\S+ status=(finished|running)/);
  } finally { if (previous === undefined) delete process.env.SZTU_DATA_DIR; else process.env.SZTU_DATA_DIR = previous; await rm(root, { recursive: true, force: true }); }
});

test("workspace tools declare tool-level timeouts for filesystem-heavy operations", () => {
  const tools = createWorkspaceTools();
  assert.equal(tools.get("read_file")?.timeoutMs, 30_000);
  assert.equal(tools.get("list_dir")?.timeoutMs, 30_000);
  assert.equal(tools.get("glob_search")?.timeoutMs, 60_000);
  assert.equal(tools.get("grep_search")?.timeoutMs, 60_000);
  assert.equal(tools.get("edit_file")?.timeoutMs, 30_000);
  assert.equal(tools.get("write_file")?.timeoutMs, 30_000);
  assert.equal(tools.get("bash")?.timeoutMs, undefined); // bash 自带进程级超时，不再叠加
});

test("invokeToolWithRetry fails fast with a timeout error when a tool exceeds timeoutMs", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-tool-timeout-race-"));
  const events = new EventBus(path.join(root, "events.jsonl"));
  try {
    let toolCalls = 0;
    const tools = createWorkspaceTools([{ name: "slow_tool", description: "slow", permission: "read_only", timeoutMs: 40, schema: { type: "object" }, async invoke() { toolCalls += 1; await new Promise((resolve) => setTimeout(resolve, 5_000)); return { ok: true, output: "late" }; } }]);
    let messages: Array<{ role: string; content?: unknown; is_error?: boolean }> = []; let calls = 0;
    const provider: ModelProvider = { complete: async (conversation) => { messages = [...conversation] as never; calls += 1; return calls === 1 ? { text: "", tool_calls: [{ id: "slow", name: "slow_tool", input: {} }], stop_reason: "tool_use" } : { text: "observed timeout", tool_calls: [], stop_reason: "end_turn" }; } };
    const loop = new AgentLoop(provider, tools, { workspace: new Workspace(root) }, events, { check: async () => true }, { toolRetryBaseMs: 0, maxWallClockMs: 30_000 });
    const result = await loop.run("timeout-race", "run slow tool", 3);
    assert.equal(result.text, "observed timeout");
    assert.equal(toolCalls, 1); // timeout 错误类型不可重试，只执行一次
    const toolMessage = messages.find((message) => message.role === "tool");
    assert.equal(toolMessage?.is_error, true);
    assert.match(String(toolMessage?.content), /Tool timed out after 40ms/);
  } finally { await events.flush(); await rm(root, { recursive: true, force: true }); } // flush 后再 rm：避免 appendFile 与 rmdir 竞争（CI ENOTEMPTY）
});
