import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { mkdir, mkdtemp, readFile, rm, stat, symlink, utimes, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { IndexManager } from "../src/indexing/index-manager.js";
import type { Embedder } from "../src/embedding/index.js";

const exec = promisify(execFile);
function embedding(calls: string[][]): Embedder {
  return { name: "fixed", dimensions: 2, maxTokens: 128, async embed(texts) { calls.push(texts); return texts.map(() => [1, 0]); }, async embedQuery() { return [1, 0]; } };
}

test("索引状态不下载模型；并发搜索只嵌入一次；重启和清除后保持一致", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-index-manager-"));
  try {
    const calls: string[][] = [];
    const manager = new IndexManager(() => embedding(calls));
    await writeFile(path.join(root, "code.ts"), "const value = 1;");
    assert.equal((await manager.status(root)).state, "not_started");
    assert.equal(calls.length, 0);
    await Promise.all([manager.search(root, true, async (state) => state.store.count()), manager.search(root, true, async (state) => state.store.count())]);
    assert.equal(calls.length, 1);
    assert.equal((await manager.status(root)).files, 1);
    const restored = new IndexManager(() => embedding(calls));
    assert.equal((await restored.status(root)).chunks, 1);
    assert.equal(calls.length, 1);
    await restored.clear(root);
    assert.equal((await restored.status(root)).state, "not_started");
    assert.equal(await restored.search(root, false, (state) => state.store.count()), 0);
    await restored.build(root);
    assert.equal((await restored.status(root)).files, 1);
    const persisted = await readFile(path.join(root, ".sztu/vector/semantic-index.jsonl"), "utf8");
    assert.match(persisted, /code.ts/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("变成忽略项、二进制或被删除的文件不再出现在索引里", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-index-invalidated-"));
  try {
    await exec("git", ["init", root]);
    await writeFile(path.join(root, "secret.ts"), "const secret = 1;");
    await writeFile(path.join(root, "code.ts"), "const value = 1;");
    const manager = new IndexManager(() => embedding([]));
    await manager.build(root);
    await writeFile(path.join(root, ".gitignore"), "secret.ts\n");
    await writeFile(path.join(root, "code.ts"), Buffer.from([0, 1, 2]));
    await manager.search(root, true, async (state) => assert.equal(await state.store.count(), 0));
    await manager.update(root, ["secret.ts"]);
    assert.equal((await manager.status(root)).chunks, 0);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("RPC 更新拒绝越界路径；损坏索引可以清除；索引目录不能经符号链接逃逸", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-index-boundary-"));
  const outside = await mkdtemp(path.join(os.tmpdir(), "sztu-index-outside-"));
  try {
    const manager = new IndexManager(() => embedding([]));
    await assert.rejects(manager.update(root, ["../escape.ts"]), /escapes/);
    await mkdir(path.join(root, ".sztu/vector"), { recursive: true });
    await writeFile(path.join(root, ".sztu/vector/semantic-index.jsonl"), "broken");
    const fresh = new IndexManager(() => embedding([]));
    assert.equal((await fresh.status(root)).state, "failed");
    assert.equal((await fresh.clear(root)).state, "not_started");
    await symlink(outside, path.join(root, ".sztu/vector/semantic-index.jsonl"), "junction");
    await assert.rejects(fresh.clear(root), /escapes/);
  } finally { await rm(root, { recursive: true, force: true }); await rm(outside, { recursive: true, force: true }); }
});

test("内容改变但大小和时间戳相同时仍更新；后台模型失败可重试", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-index-retry-"));
  try {
    const file = path.join(root, "code.ts");
    await writeFile(file, "const first = 1;");
    let fail = true;
    const calls: string[][] = [];
    const manager = new IndexManager(() => ({ ...embedding(calls), async embed(texts) { if (fail) throw new Error("model unavailable"); calls.push(texts); return texts.map(() => [1, 0]); } }));
    assert.equal((await manager.startBuild(root)).state, "indexing");
    for (let i = 0; i < 100 && (await manager.status(root)).state === "indexing"; i += 1) await new Promise((resolve) => setTimeout(resolve, 10));
    assert.equal((await manager.status(root)).state, "failed");
    fail = false;
    await manager.build(root);
    const info = await stat(file);
    await writeFile(file, "const other = 2;");
    await utimes(file, info.atime, info.mtime);
    await manager.search(root, true, async (state) => assert.match(state.store.exportRecords()[0]!.text, /other/));
    assert.equal(calls.length, 2);
  } finally { await rm(root, { recursive: true, force: true }); }
});
