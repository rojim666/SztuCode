import type { Chunk } from "../chunking/index.js";

export interface LexicalSearchFilter {
  pathPrefix?: string;
  fileType?: "code" | "markdown" | "document" | "any";
}

export interface LexicalSearchResult {
  key: string;
  score: number;
  text: string;
  metadata: Record<string, string | number | boolean>;
}

interface LexicalRecord {
  key: string;
  source: string;
  text: string;
  normalizedText: string;
  tokens: Set<string>;
  metadata: Record<string, string | number | boolean>;
}

const CJK_RUN = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+/gu;
const LATIN_TOKEN = /[a-z0-9_$]+/gi;

/**
 * 将自然语言和代码标识符拆成可比较的词元。
 * 同时保留完整标识符和驼峰/下划线拆分结果，避免精确符号查询丢失信息。
 */
export function tokenizeSearchText(text: string): string[] {
  if (typeof text !== "string") return [];
  const normalized = text.normalize("NFKC");
  const tokens = new Set<string>();
  for (const match of normalized.matchAll(CJK_RUN)) {
    const run = match[0]!.toLocaleLowerCase();
    if (run.length >= 2) tokens.add(run);
    for (let index = 0; index + 1 < run.length; index += 1) tokens.add(run.slice(index, index + 2));
  }
  for (const match of normalized.matchAll(LATIN_TOKEN)) {
    const token = match[0]!;
    const lowerToken = token.toLocaleLowerCase();
    if (lowerToken.length >= 2) tokens.add(lowerToken);
    for (const part of token.split(/[_$-]+/u)) {
      const lowerPart = part.toLocaleLowerCase();
      if (lowerPart.length >= 2) tokens.add(lowerPart);
      const camelParts = part.split(/(?<=[a-z0-9])(?=[A-Z])/u).filter((item) => item.length >= 2);
      for (const camelPart of camelParts) tokens.add(camelPart.toLocaleLowerCase());
    }
  }
  return [...tokens];
}

function metadataWithoutUndefined(chunk: Chunk): Record<string, string | number | boolean> {
  return Object.fromEntries(Object.entries(chunk.metadata).filter(([, value]) => value !== undefined)) as Record<string, string | number | boolean>;
}

/** 轻量级倒排式关键词索引，第一阶段使用线性扫描以保持实现简单、结果可解释。 */
export class LexicalIndex {
  private readonly records = new Map<string, LexicalRecord>();

  replace(source: string, chunks: readonly Chunk[]): void {
    this.deleteSource(source);
    for (const chunk of chunks) {
      const metadata = metadataWithoutUndefined(chunk);
      const key = `${source}#${String(metadata.chunk_index ?? this.records.size)}`;
      const searchableText = [
        source,
        metadata.symbol,
        metadata.symbol_kind,
        metadata.section,
        chunk.text,
      ].filter((value): value is string => typeof value === "string" && value.length > 0).join("\n");
      this.records.set(key, {
        key,
        source,
        text: chunk.text,
        normalizedText: searchableText.normalize("NFKC").toLocaleLowerCase(),
        tokens: new Set(tokenizeSearchText(searchableText)),
        metadata,
      });
    }
  }

  deleteSource(source: string): number {
    let deleted = 0;
    for (const [key, record] of this.records) {
      if (record.source === source) {
        this.records.delete(key);
        deleted += 1;
      }
    }
    return deleted;
  }

  count(): number {
    return this.records.size;
  }

  search(query: string, topK: number, filter?: LexicalSearchFilter): LexicalSearchResult[] {
    if (typeof query !== "string" || !query.trim()) throw new Error("关键词查询不能为空");
    if (!Number.isInteger(topK) || topK < 1) return [];
    if (filter?.fileType && !["code", "markdown", "document", "any"].includes(filter.fileType)) throw new Error("fileType 无效");
    const normalizedQuery = query.normalize("NFKC").toLocaleLowerCase().trim();
    const queryTokens = tokenizeSearchText(query);
    const results: Array<LexicalSearchResult & { sequence: number }> = [];
    let sequence = 0;
    for (const record of this.records.values()) {
      if (!this.matchesFilter(record, filter)) continue;
      const score = this.score(record, normalizedQuery, queryTokens);
      if (score <= 0) continue;
      results.push({ key: record.key, score, text: record.text, metadata: { ...record.metadata }, sequence });
      sequence += 1;
    }
    return results.sort((left, right) => right.score - left.score || left.sequence - right.sequence).slice(0, topK).map(({ sequence: _sequence, ...result }) => result);
  }

  private matchesFilter(record: LexicalRecord, filter?: LexicalSearchFilter): boolean {
    const pathPrefix = filter?.pathPrefix?.replaceAll("\\", "/").replace(/^\.\//, "").replace(/\/$/, "") ?? "";
    if (pathPrefix && record.source !== pathPrefix && !record.source.startsWith(`${pathPrefix}/`)) return false;
    const type = String(record.metadata.type ?? "text");
    return !filter?.fileType || filter.fileType === "any" || type === filter.fileType;
  }

  private score(record: LexicalRecord, normalizedQuery: string, queryTokens: readonly string[]): number {
    if (queryTokens.length === 0) return 0;
    const matched = queryTokens.filter((token) => record.tokens.has(token));
    let score = (matched.length / queryTokens.length) * 0.65;
    if (record.normalizedText.includes(normalizedQuery)) score += 0.25;
    const symbol = String(record.metadata.symbol ?? "").toLocaleLowerCase();
    if (symbol && (symbol === normalizedQuery || symbol.includes(normalizedQuery))) score += 0.35;
    const source = record.source.toLocaleLowerCase();
    if (source.includes(normalizedQuery)) score += 0.15;
    return Math.min(1, score);
  }
}
