import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { WorkspaceIndexer } from "../src/indexing/index.js";
import type { Embedder } from "../src/embedding/index.js";
import { MemoryVectorStore } from "../src/vector-store/index.js";
import * as XLSX from "xlsx";

const execFileAsync = promisify(execFile);

function createEmbedder(calls: string[][] = []): Embedder {
  return {
    name: "test",
    dimensions: 2,
    maxTokens: 128,
    async embed(texts) { calls.push(texts); return texts.map((text) => text.includes("权限") ? [1, 0] : [0, 1]); },
    async embedQuery() { return [1, 0]; },
  };
}

test("索引单文件时会分块、携带路径上下文并保存元数据", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-indexer-"));
  try {
    await writeFile(path.join(root, "auth.ts"), "export function checkPermission() {\n  return true;\n}\n", "utf8");
    const calls: string[][] = [];
    const store = new MemoryVectorStore(2);
    const indexer = new WorkspaceIndexer(root, createEmbedder(calls), store);
    const count = await indexer.indexFile("auth.ts");
    assert.equal(count, 1);
    assert.match(calls[0]![0]!, /^auth\.ts\n符号：checkPermission\n符号类型：function\n\n/);
    const result = await store.search([0, 1], 1);
    assert.equal(result[0]!.record.metadata.source, "auth.ts");
    assert.equal(result[0]!.record.metadata.workspace_id, root);
    assert.equal(result[0]!.record.metadata.start_line, 1);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("Office XLSX enters the index with sheet and source version metadata", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-office-indexer-"));
  try {
    const workbook = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(workbook, XLSX.utils.aoa_to_sheet([["地区", "销售额"], ["华东", "180"]]), "汇总");
    await writeFile(path.join(root, "sales.xlsx"), XLSX.write(workbook, { type: "buffer", bookType: "xlsx" }));
    const store = new MemoryVectorStore(2); const indexer = new WorkspaceIndexer(root, createEmbedder(), store);
    assert.equal(await indexer.indexFile("sales.xlsx"), 1);
    const result = await store.search([0, 1], 2); const metadata = result[0]!.record.metadata;
    assert.equal(metadata.source, "sales.xlsx"); assert.equal(metadata.sheet, "汇总"); assert.equal(typeof metadata.source_version, "string"); assert.equal(metadata.block_type, "table");
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("索引完成后通知观察者，嵌入失败时不提前替换观察结果", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-index-observer-"));
  try {
    await writeFile(path.join(root, "auth.ts"), "export function checkPermission() { return true; }", "utf8");
    const observed: Array<[string, number]> = [];
    const store = new MemoryVectorStore(2);
    const indexer = new WorkspaceIndexer(root, createEmbedder(), store, (source, chunks) => observed.push([source, chunks.length]));
    await indexer.indexFile("auth.ts");
    await writeFile(path.join(root, "auth.ts"), "", "utf8");
    await indexer.indexFile("auth.ts");
    assert.deepEqual(observed, [["auth.ts", 1], ["auth.ts", 0]]);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("全量索引过滤噪音目录、扩展名和文件数量，并报告进度", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-index-all-"));
  try {
    await mkdir(path.join(root, "node_modules"));
    await writeFile(path.join(root, "one.ts"), "const one = 1;", "utf8");
    await writeFile(path.join(root, "two.md"), "# two\nbody", "utf8");
    await writeFile(path.join(root, "ignored.bin"), "binary", "utf8");
    await writeFile(path.join(root, "node_modules", "bad.ts"), "const bad = 1;", "utf8");
    const progress: Array<[number, number]> = [];
    const store = new MemoryVectorStore(2);
    const indexer = new WorkspaceIndexer(root, createEmbedder(), store);
    const result = await indexer.indexAll({ extensions: ["ts", "md"], maxFiles: 1, onProgress: (indexed, total) => progress.push([indexed, total]) });
    assert.equal(result.files_indexed, 1);
    assert.equal(await store.count(), 1);
    assert.deepEqual(progress, [[0, 1], [1, 1]]);
    assert.equal(indexer.shouldIndex("node_modules/bad.ts"), false);
    assert.equal(indexer.shouldIndex("ignored.bin"), false);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("全量索引遵守 Git 的 .gitignore 规则", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-index-gitignore-"));
  try {
    await execFileAsync("git", ["init", "--quiet", root]);
    await writeFile(path.join(root, ".gitignore"), "private.ts\nignored-dir/\n", "utf8");
    await mkdir(path.join(root, "ignored-dir"));
    await writeFile(path.join(root, "private.ts"), "const privateValue = 1;", "utf8");
    await writeFile(path.join(root, "public.ts"), "const publicValue = 1;", "utf8");
    await writeFile(path.join(root, "ignored-dir", "nested.ts"), "const nestedValue = 1;", "utf8");
    const store = new MemoryVectorStore(2);
    const indexer = new WorkspaceIndexer(root, createEmbedder(), store);
    const result = await indexer.indexAll();
    assert.equal(result.files_indexed, 1);
    assert.equal((await store.search([0, 1], 5))[0]!.record.metadata.source, "public.ts");
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("重建文件先嵌入后替换旧记录，删除文件时增量更新会清理索引", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-index-update-"));
  try {
    const file = path.join(root, "note.txt");
    await writeFile(file, "旧内容", "utf8");
    const store = new MemoryVectorStore(2);
    const indexer = new WorkspaceIndexer(root, createEmbedder(), store);
    await indexer.indexFile("note.txt");
    assert.equal(await store.count(), 1);
    await writeFile(file, "新内容", "utf8");
    await indexer.updateIndex(["note.txt"]);
    assert.equal(await store.count(), 1);
    assert.equal((await store.search([0, 1], 1))[0]!.record.text, "新内容");
    await rm(file);
    await indexer.updateIndex(["note.txt"]);
    assert.equal(await store.count(), 0);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("索引器拒绝工作区外路径和过大文件", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-index-boundary-"));
  try {
    const indexer = new WorkspaceIndexer(root, createEmbedder(), new MemoryVectorStore(2));
    await assert.rejects(indexer.indexFile("../outside.ts"), /路径不在工作区内|Path escapes workspace/);
    await writeFile(path.join(root, "large.ts"), "x".repeat(1_048_577), "utf8");
    await assert.rejects(indexer.indexFile("large.ts"), /文件过大/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("嵌入失败时保留旧索引，避免索引被替换为空", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-index-failure-"));
  try {
    const file = path.join(root, "stable.ts");
    await writeFile(file, "旧内容", "utf8");
    const store = new MemoryVectorStore(2);
    const working = new WorkspaceIndexer(root, createEmbedder(), store);
    await working.indexFile("stable.ts");
    const failing: Embedder = { ...createEmbedder(), async embed() { throw new Error("模型暂时不可用"); } };
    const failed = new WorkspaceIndexer(root, failing, store);
    await writeFile(file, "新内容", "utf8");
    await assert.rejects(failed.indexFile("stable.ts"), /模型暂时不可用/);
    assert.equal(await store.count(), 1);
    assert.equal((await store.search([0, 1], 1))[0]!.record.text, "旧内容");
  } finally { await rm(root, { recursive: true, force: true }); }
});
