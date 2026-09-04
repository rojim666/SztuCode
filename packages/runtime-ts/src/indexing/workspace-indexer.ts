import { readdir, stat, readFile } from "node:fs/promises";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { createChunker, type Chunk } from "../chunking/index.js";
import type { Embedder } from "../embedding/types.js";
import type { VectorStore } from "../vector-store/types.js";
import { ignored, Workspace } from "../workspace.js";

const MAX_FILE_BYTES = 1 * 1024 * 1024;
const DEFAULT_EXTENSIONS = new Set([
  ".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rs", ".java", ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php",
  ".md", ".markdown", ".txt", ".rst", ".adoc", ".json", ".yaml", ".yml", ".toml",
]);
const execFileAsync = promisify(execFile);

export interface IndexAllOptions {
  extensions?: string[];
  maxFiles?: number;
  onProgress?: (indexed: number, total: number) => void;
}

export interface IndexResult {
  files_indexed: number;
  chunks_indexed: number;
}

export type IndexObserver = (source: string, chunks: readonly Chunk[]) => Promise<void> | void;

/** 构造统一的嵌入文本；展示给用户的正文仍保存在 Chunk.text 中。 */
export function formatEmbeddingText(source: string, chunk: Chunk): string {
  const symbol = typeof chunk.metadata.symbol === "string" ? `\n符号：${chunk.metadata.symbol}` : "";
  const kind = typeof chunk.metadata.symbol_kind === "string" ? `\n符号类型：${chunk.metadata.symbol_kind}` : "";
  return `${source}${symbol}${kind}\n\n${chunk.text}`;
}

/** 负责把工作区文件转换成向量记录，不负责注册工具或持久化存储。 */
export class WorkspaceIndexer {
  private readonly workspace: Workspace;
  private readonly workspaceId: string;

  get workspaceRoot(): string { return this.workspace.root; }

  constructor(
    workspaceRoot: string,
    private readonly embedder: Embedder,
    private readonly vectorStore: VectorStore,
    private readonly observer?: IndexObserver,
  ) {
    this.workspace = new Workspace(workspaceRoot);
    this.workspaceId = this.workspace.root;
  }

  async indexFile(relativePath: string): Promise<number> {
    const source = this.normalizeRelativePath(relativePath);
    if (!this.shouldIndex(source)) {
      await this.vectorStore.delete({ source });
      await this.observer?.(source, []);
      return 0;
    }
    const absolute = await this.workspace.resolveExisting(source);
    const fileStat = await stat(absolute);
    if (!fileStat.isFile()) throw new Error(`不是文件：${source}`);
    if (fileStat.size > MAX_FILE_BYTES) throw new Error(`文件过大，超过 ${MAX_FILE_BYTES} 字节：${source}`);
    const buffer = await readFile(absolute);
    if (buffer.includes(0)) throw new Error(`二进制文件不能建立文本索引：${source}`);
    const content = buffer.toString("utf8");
    const chunks = createChunker(source).split(content, { source });
    const vectors = await this.embedder.embed(chunks.map((chunk) => formatEmbeddingText(source, chunk)));
    if (vectors.length !== chunks.length) throw new Error(`嵌入结果数量与分块数量不一致：${source}`);

    // 先完成嵌入，再替换旧记录；模型失败时保留旧索引，避免索引出现空洞。
    await this.vectorStore.delete({ source });
    if (chunks.length === 0) {
      await this.observer?.(source, []);
      return 0;
    }
    await this.vectorStore.add(chunks.map((chunk, index) => ({
      vector: vectors[index]!,
      text: chunk.text,
      metadata: {
        ...chunk.metadata,
        source,
        workspace_id: this.workspaceId,
        mtime_ms: fileStat.mtimeMs,
        file_size: fileStat.size,
      } as Record<string, string | number | boolean>,
    })));
    await this.observer?.(source, chunks);
    return chunks.length;
  }

  async indexAll(options: IndexAllOptions = {}): Promise<IndexResult> {
    const maxFiles = options.maxFiles ?? Number.POSITIVE_INFINITY;
    if (maxFiles !== Number.POSITIVE_INFINITY && (!Number.isInteger(maxFiles) || maxFiles < 1)) throw new Error("maxFiles 必须是正整数");
    const extensions = new Set((options.extensions ?? [...DEFAULT_EXTENSIONS]).map((extension) => extension.startsWith(".") ? extension.toLowerCase() : `.${extension.toLowerCase()}`));
    const allFiles = (await this.listFiles(this.workspace.root)).filter((file) => extensions.has(path.extname(file).toLowerCase()) && this.shouldIndex(file));
    const candidates: string[] = [];
    for (const file of allFiles) {
      if (candidates.length >= maxFiles) break;
      if (await this.isTextFile(file) && !(await this.isGitIgnored(file))) candidates.push(file);
    }
    let filesIndexed = 0;
    let chunksIndexed = 0;
    options.onProgress?.(0, candidates.length);
    for (const file of candidates) {
      try {
        chunksIndexed += await this.indexFile(file);
        filesIndexed += 1;
      } finally {
        options.onProgress?.(filesIndexed, candidates.length);
      }
    }
    return { files_indexed: filesIndexed, chunks_indexed: chunksIndexed };
  }

  /** 扫描当前工作区，返回符合索引规则且未被 Git 忽略的文件。 */
  async discoverFiles(): Promise<string[]> {
    const allFiles = await this.listFiles(this.workspace.root);
    const candidates: string[] = [];
    for (const file of allFiles) {
      if (this.shouldIndex(file) && await this.isTextFile(file) && !(await this.isGitIgnored(file))) candidates.push(file);
    }
    return candidates;
  }

  async updateIndex(changedFiles: string[]): Promise<void> {
    if (!Array.isArray(changedFiles)) throw new TypeError("changedFiles 必须是数组");
    for (const file of changedFiles) {
      const source = this.normalizeRelativePath(file);
      try {
        await this.indexFile(source);
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === "ENOENT") {
          await this.vectorStore.delete({ source });
          await this.observer?.(source, []);
        }
        else throw error;
      }
    }
  }

  shouldIndex(relativePath: string): boolean {
    const normalized = relativePath.replaceAll("\\", "/").replace(/^\.\//, "");
    if (!normalized || normalized.startsWith("/") || normalized.split("/").some((part) => part === ".." || ignored.has(part))) return false;
    const extension = path.posix.extname(normalized).toLowerCase();
    return DEFAULT_EXTENSIONS.has(extension) && !path.posix.basename(normalized).startsWith(".");
  }

  private normalizeRelativePath(relativePath: string): string {
    if (typeof relativePath !== "string" || !relativePath.trim()) throw new Error("relativePath 不能为空");
    const absolute = this.workspace.resolve(relativePath);
    const normalized = path.relative(this.workspace.root, absolute).split(path.sep).join("/");
    if (!this.shouldIndex(normalized) && normalized !== relativePath.replaceAll("\\", "/").replace(/^\.\//, "")) {
      throw new Error(`路径不在工作区内：${relativePath}`);
    }
    return normalized;
  }

  private async listFiles(directory: string): Promise<string[]> {
    const output: string[] = [];
    const walk = async (current: string): Promise<void> => {
      const entries = await readdir(current, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.isDirectory() && ignored.has(entry.name)) continue;
        const absolute = path.join(current, entry.name);
        if (entry.isDirectory()) await walk(absolute);
        else if (entry.isFile()) output.push(path.relative(this.workspace.root, absolute).split(path.sep).join("/"));
      }
    };
    await walk(directory);
    return output.sort();
  }

  private async isTextFile(source: string): Promise<boolean> {
    try {
      const absolute = await this.workspace.resolveExisting(source);
      const fileStat = await stat(absolute);
      if (!fileStat.isFile() || fileStat.size > MAX_FILE_BYTES) return false;
      const sample = await readFile(absolute, { flag: "r" });
      return !sample.subarray(0, Math.min(sample.length, 8_192)).includes(0);
    } catch {
      return false;
    }
  }

  private async isGitIgnored(source: string): Promise<boolean> {
    try {
      await execFileAsync("git", ["-C", this.workspace.root, "check-ignore", "--no-index", "--quiet", "--", source], { timeout: 5_000 });
      return true;
    } catch (error) {
      const code = (error as { code?: number | string }).code;
      return code === 0;
    }
  }
}

export { DEFAULT_EXTENSIONS, MAX_FILE_BYTES };
