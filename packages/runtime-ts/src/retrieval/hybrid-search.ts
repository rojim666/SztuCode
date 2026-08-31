import type { LexicalSearchResult } from "./lexical-index.js";
import type { SearchResult, VectorRecord } from "../vector-store/types.js";

export interface HybridSearchResult {
  key: string;
  score: number;
  semantic_score: number;
  lexical_score: number;
  record: VectorRecord;
}

/** 使用 source 和 chunk_index 建立跨向量/关键词索引稳定一致的记录键。 */
export function searchRecordKey(metadata: Record<string, string | number | boolean>): string {
  return `${String(metadata.source ?? "")}#${String(metadata.chunk_index ?? "")}`;
}

/** 合并两路召回结果；分数保持在 0～1，便于向调用方解释和设置阈值。 */
export function mergeHybridResults(
  semanticResults: readonly SearchResult[],
  lexicalResults: readonly LexicalSearchResult[],
  semanticWeight = 0.7,
  lexicalWeight = 0.3,
): HybridSearchResult[] {
  if (!Number.isFinite(semanticWeight) || !Number.isFinite(lexicalWeight) || semanticWeight < 0 || lexicalWeight < 0 || semanticWeight + lexicalWeight <= 0) {
    throw new Error("混合检索权重必须是非负数且总和大于 0");
  }
  const totalWeight = semanticWeight + lexicalWeight;
  const lexicalByKey = new Map(lexicalResults.map((result) => [result.key, result]));
  const merged = new Map<string, HybridSearchResult>();
  for (const result of semanticResults) {
    const key = searchRecordKey(result.record.metadata);
    const lexical = lexicalByKey.get(key);
    const semanticScore = Math.max(0, Math.min(1, result.score));
    const lexicalScore = lexical?.score ?? 0;
    merged.set(key, {
      key,
      score: (semanticScore * semanticWeight + lexicalScore * lexicalWeight) / totalWeight,
      semantic_score: semanticScore,
      lexical_score: lexicalScore,
      record: result.record,
    });
  }
  // 关键词索引通常来自同一批向量记录，但保留这条分支可防止两个索引短暂不同步时丢失精确命中。
  for (const lexical of lexicalResults) {
    if (merged.has(lexical.key)) continue;
    merged.set(lexical.key, {
      key: lexical.key,
      score: (lexical.score * lexicalWeight) / totalWeight,
      semantic_score: 0,
      lexical_score: lexical.score,
      record: {
        id: lexical.key,
        vector: [],
        text: lexical.text,
        metadata: lexical.metadata,
      },
    });
  }
  return [...merged.values()].sort((left, right) => right.score - left.score || right.lexical_score - left.lexical_score || right.semantic_score - left.semantic_score);
}

/** 每个文件只保留综合分数最高的代码块，避免重叠分块占满结果。 */
export function deduplicateBySource(results: readonly HybridSearchResult[], limit: number): HybridSearchResult[] {
  if (!Number.isInteger(limit) || limit < 1) return [];
  const best = new Map<string, HybridSearchResult>();
  for (const result of results) {
    const source = String(result.record.metadata.source ?? result.key);
    const previous = best.get(source);
    if (!previous || result.score > previous.score) best.set(source, result);
  }
  return [...best.values()].sort((left, right) => right.score - left.score || String(left.record.metadata.source).localeCompare(String(right.record.metadata.source))).slice(0, limit);
}
