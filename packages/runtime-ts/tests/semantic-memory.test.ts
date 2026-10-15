import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import type { Embedder } from "../src/embedding/index.js";
import { createMemoryTools, loadMemoryCatalog } from "../src/memory.js";
import { SessionStore } from "../src/session-store.js";
import { Workspace } from "../src/workspace.js";

function embedder(calls: string[][], fail = false): Embedder {
  const vector = (text: string) => /JSONL|持久化|存储|persistence/.test(text) ? [1, 0] : [0, 1];
  return { name: "test-memory", dimensions: 2, maxTokens: 512, async embed(texts) { calls.push(texts); if (fail) throw new Error("模型不可用"); return texts.map(vector); }, async embedQuery(text) { return vector(text); } };
}

test("同工作区跨会话语义查询、重启恢复和笔记更新删除都保持一致", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-semantic-memory-"));
  try {
    const sessions = new SessionStore(path.join(root, "sessions"));
    const first = await sessions.create("chat", "project-a");
    const second = await sessions.create("chat", "project-a");
    const other = await sessions.create("chat", "project-b");
    const original = await sessions.appendNote(first.id, "事件使用 JSONL 存储", "run-a");
    await sessions.appendNote(other.id, "另一项目的秘密 JSONL", "run-private");
    const calls: string[][] = [];
    const catalog = await loadMemoryCatalog(root, sessions, second.id, () => embedder(calls));
    const tools = createMemoryTools(catalog, sessions, second.id, "run-b");
    const read = tools.find((tool) => tool.name === "memory_read")!;
    const context = { workspace: new Workspace(root) };
    const query = { layer: "session", query: "持久化策略", query_mode: "semantic", scope: "workspace" };
    const result = await read.invoke(query, context);
    assert.equal(result.ok, true);
    assert.match(result.output, /事件使用 JSONL 存储/);
    assert.ok(result.output.includes(first.id));
    assert.doesNotMatch(result.output, /秘密/);
    const current = await read.invoke({ ...query, scope: "current" }, context);
    assert.doesNotMatch(current.output, /事件使用 JSONL/);
    const before = calls.length;
    const restored = await loadMemoryCatalog(root, sessions, second.id, () => embedder(calls));
    assert.match(await restored.query("session", "持久化策略", 0, 1600, "hybrid", "workspace"), /JSONL/);
    assert.equal(calls.length, before, "重启后未改动笔记不重复嵌入");
    await sessions.updateNote(first.id, original, "改用 SQLite 存储", "run-a2");
    const updated = await read.invoke(query, context);
    assert.match(updated.output, /SQLite/);
    assert.doesNotMatch(updated.output, /JSONL/);
    await sessions.delete(first.id);
    assert.doesNotMatch((await read.invoke(query, context)).output, /SQLite/);
    const persisted = await readFile(path.join(root, ".sztu/vector/memory-index.jsonl"), "utf8");
    assert.doesNotMatch(persisted, /秘密|JSONL|SQLite/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("混合检索的模型失败会保留关键词结果，纯语义模式明确报错", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-memory-fallback-"));
  try {
    const sessions = new SessionStore(path.join(root, "sessions"));
    const session = await sessions.create("chat", "workspace");
    await sessions.appendNote(session.id, "使用 JSONL 持久化", "run");
    const calls: string[][] = [];
    const catalog = await loadMemoryCatalog(root, sessions, session.id, () => embedder(calls, true));
    const keyword = await catalog.query("session", "JSONL", 0, 1600, "keyword", "workspace");
    assert.match(keyword, /JSONL/);
    assert.equal(calls.length, 0);
    assert.match(await catalog.query("session", "JSONL", 0, 1600, "hybrid", "workspace"), /已返回关键词结果/);
    await assert.rejects(catalog.query("session", "JSONL", 0, 1600, "semantic", "workspace"), /模型不可用/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("语义检索启用后的 note_save 和 note_update 自动更新索引", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-memory-auto-update-"));
  try {
    const sessions = new SessionStore(path.join(root, "sessions"));
    const session = await sessions.create("chat", "workspace");
    const calls: string[][] = [];
    const catalog = await loadMemoryCatalog(root, sessions, session.id, () => embedder(calls));
    const tools = createMemoryTools(catalog, sessions, session.id, "run");
    const context = { workspace: new Workspace(root) };
    await catalog.query("session", "持久化", 0, 1600, "hybrid", "current");
    const saved = await tools.find((tool) => tool.name === "note_save")!.invoke({ content: "使用 JSONL 持久化" }, context);
    assert.equal(saved.ok, true);
    const noteId = saved.output.match(/note-[a-f0-9]+/)![0];
    let stored = await readFile(path.join(root, ".sztu/vector/memory-index.jsonl"), "utf8");
    assert.match(stored, /JSONL/);
    assert.ok(stored.includes(session.id));
    assert.match(stored, /run_id/);
    await tools.find((tool) => tool.name === "note_update")!.invoke({ note_id: noteId, content: "使用 SQLite 存储" }, context);
    stored = await readFile(path.join(root, ".sztu/vector/memory-index.jsonl"), "utf8");
    assert.match(stored, /SQLite/);
    assert.doesNotMatch(stored, /JSONL/);
  } finally { await rm(root, { recursive: true, force: true }); }
});
