import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createTransformersEmbedder } from "../packages/runtime-ts/src/embedding/index.js";
import { MemoryVectorStore } from "../packages/runtime-ts/src/vector-store/index.js";
import { createChunker } from "../packages/runtime-ts/src/chunking/index.js";

type Sample = { path: string; text: string };
type QueryCase = { query: string; expected: string[] };
type EvalRow = {
  query: string;
  expected: string[];
  results: Array<{ path: string | number | boolean; score: number }>;
  recall_at_1: number;
  recall_at_3: number;
  recall_at_5: number;
  reciprocal_rank: number;
  latency_ms: number;
};

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const samplePaths = [
  "packages/runtime-ts/src/context.ts",
  "packages/runtime-ts/src/permissions.ts",
  "packages/runtime-ts/src/subagent.ts",
  "packages/runtime-ts/src/workflow.ts",
  "packages/runtime-ts/src/tools.ts",
  "packages/runtime-ts/src/memory.ts",
];

const queryCases: QueryCase[] = [
  { query: "上下文压缩在什么条件下触发？", expected: ["packages/runtime-ts/src/context.ts"] },
  { query: "后台子 Agent 如何启动、取消并获取结果？", expected: ["packages/runtime-ts/src/subagent.ts"] },
  { query: "工具调用前如何检查权限并处理拒绝？", expected: ["packages/runtime-ts/src/permissions.ts", "packages/runtime-ts/src/tools.ts"] },
];

async function loadSamples(): Promise<Sample[]> {
  return Promise.all(samplePaths.map(async (relativePath) => ({
    path: relativePath,
    text: await readFile(path.join(repoRoot, relativePath), "utf8"),
  })));
}

function recallAt(results: string[], expected: readonly string[], k: number): number {
  const returned = new Set(results.slice(0, k));
  return expected.some((item) => returned.has(item)) ? 1 : 0;
}

function reciprocalRank(results: string[], expected: readonly string[]): number {
  const expectedSet = new Set(expected);
  const rank = results.findIndex((item) => expectedSet.has(item));
  return rank < 0 ? 0 : 1 / (rank + 1);
}

async function main(): Promise<void> {
  const started = performance.now();
  const samples = await loadSamples();
  const embedder = createTransformersEmbedder();
  const store = new MemoryVectorStore(embedder.dimensions);
  const chunks = samples.flatMap((sample) => createChunker(sample.path, { maxChars: 3_500, overlapLines: 20 }).split(sample.text, { source: sample.path }));
  const vectors = await embedder.embed(chunks.map((chunk) => chunk.text));
  await store.add(chunks.map((chunk, index) => ({
    vector: vectors[index]!,
    text: chunk.text,
    metadata: Object.fromEntries(Object.entries(chunk.metadata).filter(([, value]) => value !== undefined)) as Record<string, string | number | boolean>,
  })));
  const indexMs = performance.now() - started;

  const rows: EvalRow[] = [];
  for (const testCase of queryCases) {
    const queryStarted = performance.now();
    const queryVector = await embedder.embedQuery(testCase.query);
    const chunkResults = await store.search(queryVector, 10);
    const bestBySource = new Map<string, (typeof chunkResults)[number]>();
    for (const result of chunkResults) {
      const source = String(result.record.metadata.source);
      const previous = bestBySource.get(source);
      if (!previous || result.score > previous.score) bestBySource.set(source, result);
    }
    const results = [...bestBySource.values()].sort((left, right) => right.score - left.score).slice(0, 5);
    const queryMs = performance.now() - queryStarted;
    const paths = results.map((result) => String(result.record.metadata.source));
    rows.push({
      query: testCase.query,
      expected: testCase.expected,
      results: results.map((result) => ({ path: result.record.metadata.source, score: Number(result.score.toFixed(4)) })),
      recall_at_1: recallAt(paths, testCase.expected, 1),
      recall_at_3: recallAt(paths, testCase.expected, 3),
      recall_at_5: recallAt(paths, testCase.expected, 5),
      reciprocal_rank: reciprocalRank(paths, testCase.expected),
      latency_ms: Number(queryMs.toFixed(2)),
    });
  }

  const mean = (key: "recall_at_1" | "recall_at_3" | "recall_at_5" | "reciprocal_rank" | "latency_ms") => rows.reduce((sum, row) => sum + row[key], 0) / rows.length;
  console.log(JSON.stringify({
    model: embedder.name,
    dimensions: embedder.dimensions,
    sample_count: samples.length,
    chunk_count: chunks.length,
    index_ms: Number(indexMs.toFixed(2)),
    summary: {
      recall_at_1: Number(mean("recall_at_1").toFixed(4)),
      recall_at_3: Number(mean("recall_at_3").toFixed(4)),
      recall_at_5: Number(mean("recall_at_5").toFixed(4)),
      mrr: Number(mean("reciprocal_rank").toFixed(4)),
      query_latency_ms: Number(mean("latency_ms").toFixed(2)),
    },
    queries: rows,
  }, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
