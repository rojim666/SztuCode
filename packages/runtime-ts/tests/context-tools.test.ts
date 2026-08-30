import assert from "node:assert/strict";
import test from "node:test";
import { ContextManager, IncrementalContextSanitizer, TokenCounter, microcompactToolResults, truncateText, sanitizeContextMessages } from "../src/context.js";
import { createWorkspaceTools, ToolRegistry } from "../src/tools.js";
import { Workspace } from "../src/workspace.js";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { WorkspaceChangeTracker, activeRunChanges, revertRunChanges } from "../src/changes.js";

test("token counter handles CJK and uses the precise encoder when available", () => { const counter = new TokenCounter(); assert.ok(counter.count("中文") > counter.count("ab")); assert.equal(counter.preciseAvailable, true); });
test("truncateText preserves a bounded result and marker", () => { const result = truncateText("a".repeat(200), 80); assert.ok(result.length <= 80); assert.match(result, /original=200/); });
test("context compaction preserves the initial goal and recent turns", () => { const history = [{ role: "user" as const, content: "original goal" }, ...Array.from({ length: 10 }, (_, index) => ({ role: index % 2 ? "user" as const : "assistant" as const, content: `message-${index}` }))]; const context = new ContextManager(history); const result = context.compact(3); assert.equal(result.removedMessages, 4); assert.equal(context.messages[0]?.content, "original goal"); assert.match(String(context.messages.at(-1)?.content), /message-9/); });
test("context compaction uses a validated model summary and preserves recent turns", async () => {
  const history = Array.from({ length: 10 }, (_, index) => ({ role: index % 2 ? "assistant" as const : "user" as const, content: `message-${index} with important implementation detail` }));
  const context = new ContextManager(history);
  let prompt = "";
  const provider = { complete: async (messages: any[]) => { prompt = String(messages[0].content); return { text: "Goal\nThe user requested a migration.\n\nProgress\nThe runtime is implemented.\n\nOpen Issues\nNone.\n\nNext Steps\nRun the tests.", usage: { output_tokens: 24 }, stop_reason: "end_turn" }; } };
  const result = await context.compactWithProvider(provider, "preserve API contract", 3);
  assert.equal(result.usedModel, true);
  assert.equal(result.removedMessages, 4);
  assert.match(prompt, /preserve API contract/);
  assert.match(String(context.messages.find((message) => typeof message.content === "string" && message.content.includes("Goal"))?.content), /Goal/);
  assert.match(String(context.messages.at(-1)?.content), /message-9/);
});
test("context compaction preserves history when the model returns an invalid summary", async () => {
  const context = new ContextManager(Array.from({ length: 10 }, (_, index) => ({ role: "user" as const, content: `message-${index}` })));
  const result = await context.compactWithProvider({ complete: async () => ({ text: "too short" }) }, "", 3);
  assert.equal(result.usedModel, false);
  assert.equal(result.failed, true);
  assert.equal(result.removedMessages, 0);
  assert.equal(context.messages.length, 10);
  assert.match(String(context.messages.at(-1)?.content), /message-9/);
});
test("automatic compaction threshold uses provider input tokens plus newly added context", () => {
  const context = new ContextManager([{ role: "user", content: "goal" }], { maxTokens: 100, reservedOutputTokens: 10, maxToolResultChars: 8_000 });
  assert.equal(context.needsCompaction(0.70, 60, 9), false);
  assert.equal(context.needsCompaction(0.70, 60, 10), true);
  assert.equal(context.needsCompaction(0, 100, 100), false);
});
test("sliding compaction defers small old turns without dropping history", async () => {
  const history = [{ role: "user" as const, content: "goal" }, ...Array.from({ length: 8 }, (_, index) => ({ role: index % 2 ? "user" as const : "assistant" as const, content: `short-${index}` }))];
  const context = new ContextManager(history); let calls = 0;
  const result = await context.compactWithProvider({ complete: async () => { calls += 1; return { text: "unused" }; } }, "", { slidingWindow: 2, minimumOldTokens: 2_000 });
  assert.equal(result.deferred, true); assert.equal(calls, 0); assert.deepEqual(context.messages, history);
});
test("workspace tools support nested writes and grep", async () => { const root = await mkdtemp(path.join(os.tmpdir(), "sztu-ts-")); try { const tools = createWorkspaceTools(); const context = { workspace: new Workspace(root) }; assert.equal((await tools.get("write_file")!.invoke({ path: "src/a.ts", content: "needle" }, context)).ok, true); const result = await tools.get("grep_search")!.invoke({ pattern: "needle" }, context); assert.match(result.output, /src\/a.ts:1/); assert.equal(await readFile(path.join(root, "src/a.ts"), "utf8"), "needle"); } finally { await rm(root, { recursive: true, force: true }); } });
test("tool registry resolves built-in and tool-declared aliases without advertising duplicates", async () => {
  const tools = createWorkspaceTools();
  for (const [alias, canonical] of Object.entries({ read: "read_file", Read: "read_file", write: "write_file", Write: "write_file", edit: "edit_file", Edit: "edit_file", glob: "glob_search", Glob: "glob_search", grep: "grep_search", Grep: "grep_search", ls: "list_dir", List: "list_dir" })) {
    assert.equal(tools.get(alias)?.name, canonical);
    assert.equal(tools.canonicalName(alias), canonical);
  }
  assert.equal(tools.list().some((tool) => tool.name === "read"), false);
  assert.equal(new ToolRegistry().get("read"), undefined);

  const custom = new ToolRegistry();
  custom.register({ name: "inspect", aliases: ["i", "Inspect"], description: "inspect", permission: "read_only", schema: { type: "object" }, async invoke() { return { ok: true, output: "ok" }; } });
  assert.equal(custom.get("i")?.name, "inspect");
  assert.deepEqual(custom.restrictTo(["Inspect"]).list().map((tool) => tool.name), ["inspect"]);
});
test("run snapshots revert only an unchanged agent result", async () => { const root = await mkdtemp(path.join(os.tmpdir(), "sztu-change-")); const runs = await mkdtemp(path.join(os.tmpdir(), "sztu-runs-")); try { await writeFile(path.join(root, "a.txt"), "before"); const tracker = new WorkspaceChangeTracker(root, "run-1", runs); await tracker.capture(); await writeFile(path.join(root, "a.txt"), "after"); await tracker.finalize(); assert.equal((await activeRunChanges("run-1", root, runs))[0]?.agent_owned, true); await writeFile(path.join(root, "a.txt"), "user edit"); const blocked = await revertRunChanges("run-1", root, ["a.txt"], runs); assert.match(blocked.blocked_paths["a.txt"], /changed since/); await writeFile(path.join(root, "a.txt"), "after"); const reverted = await revertRunChanges("run-1", root, ["a.txt"], runs); assert.deepEqual(reverted.reverted_paths, ["a.txt"]); assert.equal(await readFile(path.join(root, "a.txt"), "utf8"), "before"); } finally { await rm(root, { recursive: true, force: true }); await rm(runs, { recursive: true, force: true }); } });

test("incremental usage snapshot matches full recounts across appends", () => {
  const context = new ContextManager([{ role: "user", content: "goal" }]);
  const counter = context.counter;
  // 全量基准：独立 ContextManager 的首测慢路径（与增量同一计数语义，含每消息开销与 tool_calls 计数）
  const recount = (): number => new ContextManager([...context.messages], undefined, counter).usageSnapshot().conversation;
  const snap = context.usageSnapshot();
  // 初始快照与全量一致
  assert.equal(snap.system, 0);
  assert.equal(snap.conversation, recount());
  assert.equal(snap.tool, 0);

  // 分步追加 assistant + tool + system 消息，逐步验证增量与全量严格相等
  for (let i = 0; i < 12; i += 1) {
    if (i === 3) context.append({ role: "system", content: "base instructions ".repeat(20) });
    context.append({ role: "assistant", content: `analysis step ${i} `, tool_calls: [{ id: `t${i}`, name: "read_file", input: { path: "/x" } }] });
    context.append({ role: "tool", tool_call_id: `t${i}`, content: `result ${i}: ${"data ".repeat(50 + i * 20)}`, is_error: i % 5 === 0 });
    const snap = context.usageSnapshot();
    const expectedSystem = context.messages.filter((m) => m.role === "system").reduce((sum, m) => sum + counter.countJson(m.content), 0);
    const expectedTool = context.messages.filter((m) => m.role === "tool").reduce((sum, m) => sum + counter.countJson(m.content), 0);
    assert.equal(snap.system, expectedSystem);
    assert.equal(snap.tool, expectedTool);
    assert.equal(snap.conversation, recount());
  }
  // tokenEstimate/contextPct 走同一增量路径且数值不变
  assert.equal(context.tokenEstimate(), recount());
  assert.ok(context.availableTokens() >= 0);
});

test("incremental usage snapshot falls back to full recount after message replacement", () => {
  const context = new ContextManager([{ role: "user", content: "goal" }]);
  context.append({ role: "assistant", content: "first tool call", tool_calls: [{ id: "t1", name: "grep_search", input: { pattern: "x" } }] });
  context.append({ role: "tool", tool_call_id: "t1", content: "big output ".repeat(400) });
  context.usageSnapshot();

  // 压缩/截断整体替换消息列表（全部新对象）→ 必须全量重数且结果一致
  const replaced = sanitizeContextMessages(context.messages, 1_000);
  context.messages.splice(0, context.messages.length, ...replaced);
  const snap = context.usageSnapshot();
  const counter = context.counter;
  const recount = (): number => new ContextManager([...context.messages], undefined, counter).usageSnapshot().conversation;
  assert.equal(snap.conversation, recount());
  assert.equal(snap.system, context.messages.filter((m) => m.role === "system").reduce((sum, m) => sum + counter.countJson(m.content), 0));
  assert.equal(snap.tool, context.messages.filter((m) => m.role === "tool").reduce((sum, m) => sum + counter.countJson(m.content), 0));

  // 替换后再追加仍保持增量正确（增量值 = 全量基准；单条 assistant 增量 = 文本计数 + 每消息开销）
  context.append({ role: "assistant", content: "after compaction" });
  const snap2 = context.usageSnapshot();
  assert.equal(snap2.conversation, recount());
  assert.equal(snap2.conversation, snap.conversation + counter.count("after compaction") + 4);
});

test("incremental usage snapshot stays consistent across compact()", () => {
  const history = [{ role: "user" as const, content: "original goal" }, ...Array.from({ length: 10 }, (_, index) => ({ role: index % 2 ? "user" as const : "assistant" as const, content: `message-${index} with details` }))];
  const context = new ContextManager(history);
  context.usageSnapshot();
  const result = context.compact(3);
  assert.equal(result.removedMessages, 4);
  const snap = context.usageSnapshot();
  assert.equal(snap.conversation, new ContextManager([...context.messages], undefined, context.counter).usageSnapshot().conversation);
});

test("incremental sanitizer processes appended tool turns and resets after replacement", () => {
  const sanitizer = new IncrementalContextSanitizer();
  const messages = [{ role: "user" as const, content: "work" }];
  assert.equal(sanitizer.sanitize(messages).length, 1);
  messages.push({ role: "assistant", content: "", tool_calls: [{ id: "t1", name: "read_file", input: {} }] } as any);
  assert.equal(sanitizer.sanitize(messages).length, 1);
  messages.push({ role: "tool", tool_call_id: "t1", content: "done" } as any);
  assert.equal(sanitizer.sanitize(messages).length, 3);
  messages.splice(0, messages.length, { role: "user", content: "replacement" });
  assert.deepEqual(sanitizer.sanitize(messages), messages);
});

test("microcompact shrinks only old tool output without an LLM call", () => {
  const messages = [{ role: "tool" as const, tool_call_id: "old", content: "x".repeat(3_000) }, { role: "tool" as const, tool_call_id: "recent", content: "y".repeat(3_000) }];
  const compacted = microcompactToolResults(messages, 1, 500);
  assert.ok(String(compacted[0]?.content).length <= 500); assert.equal(compacted[1], messages[1]);
});
