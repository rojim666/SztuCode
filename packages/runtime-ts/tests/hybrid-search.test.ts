import assert from "node:assert/strict";
import test from "node:test";
import { deduplicateBySource, mergeHybridResults } from "../src/retrieval/index.js";
import type { LexicalSearchResult } from "../src/retrieval/lexical-index.js";
import type { SearchResult } from "../src/vector-store/types.js";

function semantic(source: string, chunkIndex: number, score: number, text: string): SearchResult {
  return { score, record: { id: `${source}-${chunkIndex}`, vector: [1], text, metadata: { source, chunk_index: chunkIndex, type: "code" } } };
}

function lexical(source: string, chunkIndex: number, score: number, text: string): LexicalSearchResult {
  return { key: `${source}#${chunkIndex}`, score, text, metadata: { source, chunk_index: chunkIndex, type: "code" } };
}

test("混合排序会用精确关键词命中纠正语义排序", () => {
  const results = mergeHybridResults(
    [semantic("src/generic.ts", 0, 1, "通用请求处理"), semantic("src/auth.ts", 0, 0.8, "checkPermission")],
    [lexical("src/auth.ts", 0, 1, "checkPermission")],
  );
  assert.equal(results[0]!.record.metadata.source, "src/auth.ts");
  assert.ok(results[0]!.lexical_score > 0);
});

test("混合结果按文件去重，只保留最高分块", () => {
  const results = deduplicateBySource([
    { ...mergeHybridResults([semantic("src/auth.ts", 0, 0.8, "one")], []).at(0)!, score: 0.8 },
    { ...mergeHybridResults([semantic("src/auth.ts", 1, 0.9, "two")], []).at(0)!, score: 0.9 },
    { ...mergeHybridResults([semantic("src/context.ts", 0, 0.7, "three")], []).at(0)!, score: 0.7 },
  ], 2);
  assert.deepEqual(results.map((result) => result.record.metadata.source), ["src/auth.ts", "src/context.ts"]);
  assert.equal(results[0]!.record.text, "two");
});
