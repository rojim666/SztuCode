import { randomUUID } from "node:crypto";
import type { MetadataValue, SearchResult, VectorRecord, VectorStore } from "./types.js";

export function cosineSimilarity(left: number[], right: number[]): number {
  if (left.length !== right.length) throw new Error("余弦相似度计算要求向量维度一致");
  if (!left.every((value) => Number.isFinite(value)) || !right.every((value) => Number.isFinite(value))) throw new Error("余弦相似度计算要求向量只包含有限数值");
  const leftScale = Math.max(...left.map((value) => Math.abs(value)));
  const rightScale = Math.max(...right.map((value) => Math.abs(value)));
  if (leftScale === 0 || rightScale === 0) return 0;
  let dot = 0;
  let leftNorm = 0;
  let rightNorm = 0;
  for (let index = 0; index < left.length; index += 1) {
    const normalizedLeft = left[index]! / leftScale;
    const normalizedRight = right[index]! / rightScale;
    dot += normalizedLeft * normalizedRight;
    leftNorm += normalizedLeft ** 2;
    rightNorm += normalizedRight ** 2;
  }
  const denominator = Math.sqrt(leftNorm) * Math.sqrt(rightNorm);
  return denominator === 0 ? 0 : dot / denominator;
}

interface StoredRecord {
  record: VectorRecord;
  sequence: number;
}

/** 适合第一阶段验证契约的线性扫描向量存储。 */
export class MemoryVectorStore implements VectorStore {
  readonly name: string;
  readonly dimensions: number;

  private readonly records = new Map<string, StoredRecord>();
  private nextSequence = 0;

  constructor(dimensions: number, name = "memory") {
    if (!Number.isInteger(dimensions) || dimensions < 1) throw new Error("向量存储维度必须是正整数");
    if (!name.trim()) throw new Error("向量存储名称不能为空");
    this.dimensions = dimensions;
    this.name = name;
  }

  async add(records: Omit<VectorRecord, "id">[]): Promise<string[]> {
    if (!Array.isArray(records)) throw new TypeError("records 必须是数组");
    for (const record of records) this.validateRecord(record);
    const ids: string[] = [];
    for (const input of records) {
      const id = randomUUID();
      this.records.set(id, {
        sequence: this.nextSequence++,
        record: { id, vector: [...input.vector], text: input.text, metadata: { ...input.metadata } },
      });
      ids.push(id);
    }
    return ids;
  }

  async delete(filter?: Partial<Record<string, MetadataValue>>): Promise<number> {
    let deleted = 0;
    for (const [id, stored] of this.records) {
      if (this.matches(stored.record.metadata, filter)) {
        this.records.delete(id);
        deleted += 1;
      }
    }
    return deleted;
  }

  async search(query: number[], topK: number, filter?: Partial<Record<string, MetadataValue>>): Promise<SearchResult[]> {
    this.validateVector(query, "查询");
    if (!Number.isInteger(topK) || !Number.isFinite(topK)) throw new Error("topK 必须是有限整数");
    if (topK < 1) return [];
    return [...this.records.values()]
      .filter((stored) => this.matches(stored.record.metadata, filter))
      .map((stored) => ({ record: this.cloneRecord(stored.record), score: cosineSimilarity(query, stored.record.vector), sequence: stored.sequence }))
      .sort((left, right) => right.score - left.score || left.sequence - right.sequence)
      .slice(0, topK)
      .map(({ record, score }) => ({ record, score }));
  }

  async count(filter?: Partial<Record<string, MetadataValue>>): Promise<number> {
    let count = 0;
    for (const stored of this.records.values()) if (this.matches(stored.record.metadata, filter)) count += 1;
    return count;
  }

  async clear(): Promise<void> {
    this.records.clear();
  }

  /** 导出稳定副本，供持久化存储保存索引内容。 */
  exportRecords(): VectorRecord[] {
    return [...this.records.values()].map(({ record }) => this.cloneRecord(record));
  }

  /** 从持久化文件恢复记录；恢复前会清空当前内容。 */
  importRecords(records: readonly VectorRecord[]): void {
    this.records.clear();
    this.nextSequence = 0;
    for (const record of records) {
      this.validateRecord(record);
      this.records.set(record.id, { sequence: this.nextSequence++, record: this.cloneRecord(record) });
    }
  }

  private matches(metadata: Record<string, MetadataValue>, filter?: Partial<Record<string, MetadataValue>>): boolean {
    if (!filter) return true;
    return Object.entries(filter).every(([key, value]) => metadata[key] === value);
  }

  private validateRecord(record: Omit<VectorRecord, "id">): void {
    if (!record || typeof record.text !== "string") throw new Error("向量记录的 text 必须是字符串");
    if (!record.metadata || typeof record.metadata !== "object" || Array.isArray(record.metadata)) throw new Error("向量记录的 metadata 必须是对象");
    for (const value of Object.values(record.metadata)) {
      if (!((typeof value === "string") || (typeof value === "boolean") || (typeof value === "number" && Number.isFinite(value)))) throw new Error("向量记录的 metadata 只能包含字符串、有限数字或布尔值");
    }
    this.validateVector(record.vector, "记录");
  }

  private validateVector(vector: number[], label: string): void {
    if (!Array.isArray(vector) || vector.length !== this.dimensions) throw new Error(`${label}向量维度错误：期望 ${this.dimensions}，实际 ${vector?.length ?? "非数组"}`);
    if (!vector.every((value) => typeof value === "number" && Number.isFinite(value))) throw new Error(`${label}向量包含非有限数值`);
  }

  private cloneRecord(record: VectorRecord): VectorRecord {
    return { id: record.id, vector: [...record.vector], text: record.text, metadata: { ...record.metadata } };
  }
}
