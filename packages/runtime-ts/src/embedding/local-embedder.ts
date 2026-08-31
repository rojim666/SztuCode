import type { Embedder, EmbeddingModel, LocalEmbedderOptions } from "./types.js";

const DEFAULT_MODEL = "Xenova/all-MiniLM-L6-v2";
const DEFAULT_DIMENSIONS = 384;
const DEFAULT_MAX_TOKENS = 512;

interface FeatureExtractionResult {
  data: ArrayLike<number>;
  dims?: readonly number[];
}

interface FeatureExtractionPipeline {
  (texts: string[], options: { pooling: "mean"; normalize: true }): Promise<FeatureExtractionResult>;
}

/**
 * 对本地嵌入模型的轻量适配器。
 * 模型只在第一次真正嵌入时加载，并且并发的第一次调用共享同一个加载 Promise。
 */
export class LocalEmbedder implements Embedder {
  readonly name: string;
  readonly dimensions: number;
  readonly maxTokens: number;

  private readonly loadModel: () => Promise<EmbeddingModel>;
  private modelPromise: Promise<EmbeddingModel> | undefined;

  constructor(options: LocalEmbedderOptions) {
    if (!options.name.trim()) throw new Error("嵌入模型名称不能为空");
    if (!Number.isInteger(options.dimensions) || options.dimensions < 1) throw new Error("嵌入向量维度必须是正整数");
    if (!Number.isInteger(options.maxTokens) || options.maxTokens < 1) throw new Error("嵌入模型 maxTokens 必须是正整数");
    this.name = options.name;
    this.dimensions = options.dimensions;
    this.maxTokens = options.maxTokens;
    this.loadModel = options.loadModel;
  }

  async embed(texts: string[]): Promise<number[][]> {
    if (!Array.isArray(texts)) throw new TypeError("texts 必须是数组");
    if (texts.length === 0) return [];
    for (const text of texts) {
      if (typeof text !== "string" || text.trim().length === 0) throw new Error("嵌入文本不能为空");
    }

    const model = await this.getModel();
    const vectors = await model.embed(texts);
    if (!Array.isArray(vectors) || vectors.length !== texts.length) {
      throw new Error(`嵌入模型返回 ${vectors?.length ?? "非数组"} 个向量，期望 ${texts.length} 个`);
    }
    return vectors.map((vector, index) => this.validateVector(vector, index));
  }

  async embedQuery(text: string): Promise<number[]> {
    const vectors = await this.embed([text]);
    return vectors[0]!;
  }

  private getModel(): Promise<EmbeddingModel> {
    if (!this.modelPromise) {
      const promise = Promise.resolve().then(() => this.loadModel());
      this.modelPromise = promise;
      void promise.catch(() => {
        if (this.modelPromise === promise) this.modelPromise = undefined;
      });
    }
    return this.modelPromise;
  }

  private validateVector(vector: number[], index: number): number[] {
    if (!Array.isArray(vector) || vector.length !== this.dimensions) {
      throw new Error(`第 ${index + 1} 个嵌入向量维度错误：期望 ${this.dimensions}，实际 ${vector?.length ?? "非数组"}`);
    }
    if (!vector.every((value) => typeof value === "number" && Number.isFinite(value))) {
      throw new Error(`第 ${index + 1} 个嵌入向量包含非有限数值`);
    }
    return [...vector];
  }
}

export interface TransformersEmbedderOptions {
  model?: string;
  dimensions?: number;
  maxTokens?: number;
  batchSize?: number;
}

/** 使用 transformers.js 的默认本地嵌入模型。模型在第一次调用时才下载和加载。 */
export function createTransformersEmbedder(options: TransformersEmbedderOptions = {}): LocalEmbedder {
  const modelName = options.model ?? DEFAULT_MODEL;
  const dimensions = options.dimensions ?? DEFAULT_DIMENSIONS;
  const maxTokens = options.maxTokens ?? DEFAULT_MAX_TOKENS;
  const batchSize = options.batchSize ?? 8;
  if (!Number.isInteger(batchSize) || batchSize < 1) throw new Error("嵌入批大小必须是正整数");

  return new LocalEmbedder({
    name: modelName,
    dimensions,
    maxTokens,
    loadModel: async () => {
      const module = await import("@xenova/transformers");
      const pipeline = await module.pipeline("feature-extraction", modelName) as unknown as FeatureExtractionPipeline;
      return {
        embed: async (texts: string[]) => {
          const vectors: number[][] = [];
          for (let start = 0; start < texts.length; start += batchSize) {
            const batch = texts.slice(start, start + batchSize);
            const output = await pipeline(batch, { pooling: "mean", normalize: true });
            const data = Array.from(output.data);
            const expectedLength = batch.length * dimensions;
            if (data.length !== expectedLength) {
              throw new Error(`transformers.js 返回 ${data.length} 个数值，期望 ${expectedLength} 个`);
            }
            for (let index = 0; index < batch.length; index += 1) {
              vectors.push(data.slice(index * dimensions, (index + 1) * dimensions));
            }
          }
          return vectors;
        },
      };
    },
  });
}
