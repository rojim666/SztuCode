/** 将文本转换为向量的最小抽象。 */
export interface Embedder {
  readonly name: string;
  readonly dimensions: number;
  readonly maxTokens: number;
  embed(texts: string[]): Promise<number[][]>;
  embedQuery(text: string): Promise<number[]>;
}

/** 本地模型适配器所需的最小模型接口。 */
export interface EmbeddingModel {
  embed(texts: string[]): Promise<number[][]>;
}

export interface LocalEmbedderOptions {
  name: string;
  dimensions: number;
  maxTokens: number;
  loadModel: () => Promise<EmbeddingModel>;
}
