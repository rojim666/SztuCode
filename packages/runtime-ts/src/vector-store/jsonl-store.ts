import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { MemoryVectorStore } from "./memory-store.js";
import type { MetadataValue, SearchResult, VectorRecord, VectorStore } from "./types.js";

const FORMAT_VERSION = 1;

type JsonlHeader = {
  type: "header";
  format_version: number;
  dimensions: number;
  embedder_name?: string;
};

type JsonlLine = JsonlHeader | VectorRecord;

export interface JsonlVectorStoreOptions {
  embedderName?: string;
}

/** 带 JSONL 持久化的线性向量存储，检索仍由内存索引完成。 */
export class JsonlVectorStore implements VectorStore {
  readonly name: string;
  readonly dimensions: number;
  private readonly memory: MemoryVectorStore;
  private readonly filePath: string;
  private readonly embedderName?: string;

  private constructor(filePath: string, dimensions: number, name: string, options: JsonlVectorStoreOptions) {
    this.filePath = path.resolve(filePath);
    this.name = name;
    this.dimensions = dimensions;
    this.embedderName = options.embedderName;
    this.memory = new MemoryVectorStore(dimensions, name);
  }

  static async open(filePath: string, dimensions: number, name = "jsonl", options: JsonlVectorStoreOptions = {}): Promise<JsonlVectorStore> {
    const store = new JsonlVectorStore(filePath, dimensions, name, options);
    try {
      await store.load();
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
    return store;
  }

  async add(records: Omit<VectorRecord, "id">[]): Promise<string[]> {
    const ids = await this.memory.add(records);
    await this.persist();
    return ids;
  }

  async delete(filter?: Partial<Record<string, MetadataValue>>): Promise<number> {
    const deleted = await this.memory.delete(filter);
    if (deleted > 0) await this.persist();
    return deleted;
  }

  search(query: number[], topK: number, filter?: Partial<Record<string, MetadataValue>>): Promise<SearchResult[]> {
    return this.memory.search(query, topK, filter);
  }

  count(filter?: Partial<Record<string, MetadataValue>>): Promise<number> {
    return this.memory.count(filter);
  }

  exportRecords(): VectorRecord[] {
    return this.memory.exportRecords();
  }

  async clear(): Promise<void> {
    await this.memory.clear();
    await this.persist();
  }

  private async load(): Promise<void> {
    const text = await readFile(this.filePath, "utf8");
    const lines = text.split(/\r?\n/u).filter((line) => line.trim());
    if (lines.length === 0) return;
    const header = JSON.parse(lines[0]!) as Partial<JsonlHeader>;
    if (header.type !== "header" || header.format_version !== FORMAT_VERSION || header.dimensions !== this.dimensions) {
      throw new Error(`向量索引格式或维度不匹配：${this.filePath}`);
    }
    if (this.embedderName && header.embedder_name && header.embedder_name !== this.embedderName) {
      throw new Error(`向量索引模型不匹配：文件使用 ${header.embedder_name}，当前使用 ${this.embedderName}`);
    }
    const records = lines.slice(1).map((line) => JSON.parse(line) as VectorRecord);
    this.memory.importRecords(records);
  }

  private async persist(): Promise<void> {
    const directory = path.dirname(this.filePath);
    await mkdir(directory, { recursive: true });
    const header: JsonlHeader = { type: "header", format_version: FORMAT_VERSION, dimensions: this.dimensions, ...(this.embedderName ? { embedder_name: this.embedderName } : {}) };
    const lines = [header, ...this.memory.exportRecords()].map((line: JsonlLine) => JSON.stringify(line));
    const temporaryPath = `${this.filePath}.${process.pid}.${Date.now()}.tmp`;
    await writeFile(temporaryPath, `${lines.join("\n")}\n`, "utf8");
    await rename(temporaryPath, this.filePath);
  }
}
