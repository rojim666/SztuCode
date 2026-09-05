import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { JsonlVectorStore, MemoryVectorStore, cosineSimilarity } from "../src/vector-store/index.js";

const records = [
  { vector: [1, 0, 0], text: "认证密码校验", metadata: { source: "auth.ts", workspace_id: "one", kind: "code" } },
  { vector: [0, 1, 0], text: "上下文压缩", metadata: { source: "context.ts", workspace_id: "one", kind: "code" } },
  { vector: [Math.SQRT1_2, Math.SQRT1_2, 0], text: "登录错误处理", metadata: { source: "login.ts", workspace_id: "two", kind: "code" } },
];

test("内存向量库存储、排序和 topK", async () => {
  const store = new MemoryVectorStore(3);
  const ids = await store.add(records);
  assert.equal(ids.length, 3);
  assert.equal(new Set(ids).size, 3);
  assert.equal(await store.count(), 3);

  const results = await store.search([1, 0, 0], 2);
  assert.deepEqual(results.map((result) => result.record.text), ["认证密码校验", "登录错误处理"]);
  assert.equal(results[0]?.score, 1);
  assert.equal(results.length, 2);
  assert.deepEqual(await store.search([1, 0, 0], 0), []);
});

test("元数据过滤在排序前生效，并支持删除和清空", async () => {
  const store = new MemoryVectorStore(3);
  await store.add(records);
  const filtered = await store.search([1, 0, 0], 10, { workspace_id: "one", kind: "code" });
  assert.deepEqual(filtered.map((result) => result.record.text), ["认证密码校验", "上下文压缩"]);
  assert.equal(await store.count({ workspace_id: "two" }), 1);
  assert.equal(await store.delete({ workspace_id: "two" }), 1);
  assert.equal(await store.count(), 2);
  assert.equal(await store.delete(), 2);
  assert.equal(await store.count(), 0);
  await store.add([records[0]!]);
  await store.clear();
  assert.equal(await store.count(), 0);
});

test("向量维度、非有限值和 topK 参数会被明确校验", async () => {
  const store = new MemoryVectorStore(3);
  await assert.rejects(store.add([{ vector: [1, 0], text: "错误", metadata: {} }]), /维度错误/);
  await assert.rejects(store.add([{ vector: [1, Number.NaN, 0], text: "错误", metadata: {} }]), /非有限/);
  await assert.rejects(store.add([{ vector: [1, 0, 0], text: "错误", metadata: { invalid: [] as never } }]), /metadata/);
  await assert.rejects(store.search([1, 0], 1), /维度错误/);
  await assert.rejects(store.search([1, 0, 0], 1.5), /topK/);
});

test("零向量查询不会产生 NaN，分数相同时保持插入顺序", async () => {
  const store = new MemoryVectorStore(3);
  await store.add([
    { vector: [0, 0, 0], text: "先加入", metadata: {} },
    { vector: [0, 0, 0], text: "后加入", metadata: {} },
  ]);
  const results = await store.search([0, 0, 0], 10);
  assert.deepEqual(results.map((result) => result.record.text), ["先加入", "后加入"]);
  assert.ok(results.every((result) => Number.isFinite(result.score)));
  assert.equal(cosineSimilarity([1, 0, 0], [0, 0, 0]), 0);
  assert.ok(Number.isFinite(cosineSimilarity([Number.MAX_VALUE, 0, 0], [Number.MAX_VALUE, 0, 0])));
});

test("JSONL 向量库可以保存、重启恢复并校验模型元数据", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-jsonl-store-"));
  const file = path.join(root, "vectors.jsonl");
  try {
    const first = await JsonlVectorStore.open(file, 3, "jsonl", { embedderName: "test-model" });
    await first.add(records);
    const second = await JsonlVectorStore.open(file, 3, "jsonl", { embedderName: "test-model" });
    assert.equal(await second.count(), 3);
    assert.deepEqual((await second.search([1, 0, 0], 1))[0]!.record.text, "认证密码校验");
    assert.match(await readFile(file, "utf8"), /"format_version":1/);
    await assert.rejects(JsonlVectorStore.open(file, 3, "jsonl", { embedderName: "other-model" }), /模型不匹配/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
