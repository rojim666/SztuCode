export type MetadataValue = string | number | boolean;

export interface VectorRecord {
  id: string;
  vector: number[];
  text: string;
  metadata: Record<string, MetadataValue>;
}

export interface SearchResult {
  record: VectorRecord;
  score: number;
}

export interface VectorStore {
  readonly name: string;
  readonly dimensions: number;
  add(records: Omit<VectorRecord, "id">[]): Promise<string[]>;
  delete(filter?: Partial<Record<string, MetadataValue>>): Promise<number>;
  search(query: number[], topK: number, filter?: Partial<Record<string, MetadataValue>>): Promise<SearchResult[]>;
  count(filter?: Partial<Record<string, MetadataValue>>): Promise<number>;
  clear(): Promise<void>;
}
