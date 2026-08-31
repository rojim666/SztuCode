import assert from "node:assert/strict";
import test from "node:test";
import { LocalEmbedder, createTransformersEmbedder, type EmbeddingModel } from "../src/embedding/index.js";

function createEmbedder(loadModel: () => Promise<EmbeddingModel>) {
  return new LocalEmbedder({ name: "test-model", dimensions: 2, maxTokens: 128, loadModel });
}

test("空批次不会加载模型，embedQuery 复用批量接口", async () => {
  let loads = 0;
  const embedder = createEmbedder(async () => {
    loads += 1;
    return { embed: async (texts) => texts.map((text) => [text.length, 1]) };
  });
  assert.deepEqual(await embedder.embed([]), []);
  assert.equal(loads, 0);
  assert.deepEqual(await embedder.embedQuery("abc"), [3, 1]);
  assert.equal(loads, 1);
  await assert.rejects(embedder.embedQuery("   "), /不能为空/);
});

test("并发首次调用只加载一次模型，并校验模型返回的向量", async () => {
  let loads = 0;
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const embedder = createEmbedder(async () => {
    loads += 1;
    await gate;
    return { embed: async (texts) => texts.map(() => [1, 0]) };
  });
  const first = embedder.embed(["a"]);
  const second = embedder.embed(["b"]);
  await Promise.resolve();
  assert.equal(loads, 1);
  release();
  assert.deepEqual(await Promise.all([first, second]), [[[1, 0]], [[1, 0]]]);
});

test("模型加载失败会传递给调用者，后续调用可以重试", async () => {
  let loads = 0;
  const embedder = createEmbedder(async () => {
    loads += 1;
    if (loads === 1) throw new Error("模型加载失败");
    return { embed: async () => [[0, 1]] };
  });
  await assert.rejects(embedder.embed(["第一次"]), /模型加载失败/);
  assert.deepEqual(await embedder.embed(["第二次"]), [[0, 1]]);
  assert.equal(loads, 2);
});

test("模型返回数量、维度或数值非法时失败", async () => {
  const wrongCount = createEmbedder(async () => ({ embed: async () => [] }));
  await assert.rejects(wrongCount.embed(["文本"]), /期望 1 个/);
  const wrongDimension = createEmbedder(async () => ({ embed: async () => [[1]] }));
  await assert.rejects(wrongDimension.embed(["文本"]), /维度错误/);
  const wrongValue = createEmbedder(async () => ({ embed: async () => [[1, Number.NaN]] }));
  await assert.rejects(wrongValue.embed(["文本"]), /非有限/);
});

test("默认 transformers.js 适配器只声明配置，不在创建时下载模型", () => {
  const embedder = createTransformersEmbedder();
  assert.equal(embedder.name, "Xenova/all-MiniLM-L6-v2");
  assert.equal(embedder.dimensions, 384);
  assert.equal(embedder.maxTokens, 512);
  assert.throws(() => createTransformersEmbedder({ batchSize: 0 }), /批大小/);
});
