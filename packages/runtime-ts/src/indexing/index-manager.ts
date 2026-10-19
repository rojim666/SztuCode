import { readFile, realpath, rm, stat } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import type { SemanticIndexStatus } from "@sztucode/protocol";
import { createTransformersEmbedder, type Embedder } from "../embedding/index.js";
import type { Chunk } from "../chunking/index.js";
import { LexicalIndex } from "../retrieval/index.js";
import { JsonlVectorStore } from "../vector-store/index.js";
import { Workspace } from "../workspace.js";
import { WorkspaceIndexer } from "./workspace-indexer.js";

export interface SemanticIndexState {
  embedder: Embedder;
  indexer: WorkspaceIndexer;
  store: JsonlVectorStore;
  lexical: LexicalIndex;
  status: SemanticIndexStatus;
}

/** 同一工作区的工具和 RPC 共用索引，写入串行执行，状态查询不等待构建完成。 */
export class IndexManager {
  private readonly states = new Map<string, Promise<SemanticIndexState>>();
  private readonly queues = new Map<string, Promise<unknown>>();

  constructor(private readonly createEmbedder: () => Embedder = createTransformersEmbedder) {}

  private async file(root: string): Promise<string> {
    return new Workspace(root).resolveExisting(".sztu/vector/semantic-index.jsonl");
  }

  private getState(root: string): Promise<SemanticIndexState> {
    const existing = this.states.get(root);
    if (existing) return existing;
    const pending = (async () => {
      const file = await this.file(root);
      const embedder = this.createEmbedder();
      const store = await JsonlVectorStore.open(file, embedder.dimensions, "jsonl", { embedderName: embedder.name });
      const lexical = new LexicalIndex();
      const chunks = new Map<string, Chunk[]>();
      for (const record of store.exportRecords()) {
        const source = String(record.metadata.source);
        const group = chunks.get(source) ?? [];
        group.push({ text: record.text, metadata: record.metadata } as Chunk);
        chunks.set(source, group);
      }
      for (const [source, group] of chunks) lexical.replace(source, group);
      const modified = await stat(file).then((value) => value.mtime.toISOString()).catch(() => null);
      return { embedder, store, lexical, indexer: new WorkspaceIndexer(root, embedder, store, (source, next) => lexical.replace(source, next)), status: {
        state: modified ? "ready" : "not_started", files: chunks.size, chunks: await store.count(), processed: 0, total: 0, updated_at: modified, error: null,
      } satisfies SemanticIndexStatus };
    })();
    this.states.set(root, pending);
    void pending.catch(() => { if (this.states.get(root) === pending) this.states.delete(root); });
    return pending;
  }

  private async exclusive<T>(root: string, action: (key: string) => Promise<T>): Promise<T> {
    const key = await realpath(path.resolve(root));
    const previous = this.queues.get(key) ?? Promise.resolve();
    const pending = previous.catch(() => {}).then(() => action(key));
    this.queues.set(key, pending);
    try { return await pending; }
    finally { if (this.queues.get(key) === pending) this.queues.delete(key); }
  }

  async status(root: string): Promise<SemanticIndexStatus> {
    try { return { ...(await this.getState(await realpath(root))).status }; }
    catch (error) { return { state: "failed", files: 0, chunks: 0, processed: 0, total: 0, updated_at: null, error: error instanceof Error ? error.message : String(error) }; }
  }

  private async finish(state: SemanticIndexState): Promise<void> {
    state.status = { ...state.status, state: "ready", files: new Set(state.store.exportRecords().map((record) => record.metadata.source)).size, chunks: await state.store.count(), updated_at: new Date().toISOString(), error: null };
  }

  private async indexing(state: SemanticIndexState, action: () => Promise<void>): Promise<void> {
    state.status = { ...state.status, state: "indexing", processed: 0, total: 0, error: null };
    try { await action(); await this.finish(state); }
    catch (error) {
      state.status = { ...state.status, state: "failed", error: error instanceof Error ? error.message : String(error) };
      throw error;
    }
  }

  private async refresh(state: SemanticIndexState, rebuild = false): Promise<void> {
    const files = new Set(await state.indexer.discoverFiles());
    const sources = new Map(state.store.exportRecords().map((record) => [String(record.metadata.source), record.metadata]));
    const changed: string[] = [];
    for (const [source] of sources) {
      if (!files.has(source)) { await state.store.delete({ source }); state.lexical.replace(source, []); }
    }
    for (const file of files) {
      const absolute = await new Workspace(state.indexer.workspaceRoot).resolveExisting(file);
      const info = await stat(absolute);
      const old = sources.get(file);
      if (rebuild || !old || old.mtime_ms !== info.mtimeMs || old.file_size !== info.size || old.source_version !== createHash("sha256").update(await readFile(absolute)).digest("hex")) changed.push(file);
    }
    state.status.total = changed.length;
    for (const file of changed) { await state.indexer.updateIndex([file]); state.status.processed += 1; }
  }

  async search<T>(root: string, autoIndex: boolean, action: (state: SemanticIndexState) => Promise<T>): Promise<T> {
    return this.exclusive(root, async (key) => {
      await this.file(key);
      const state = await this.getState(key);
      if (autoIndex) await this.indexing(state, () => this.refresh(state));
      return action(state);
    });
  }

  async build(root: string): Promise<SemanticIndexStatus> {
    return this.exclusive(root, async (key) => {
      await this.file(key);
      const state = await this.getState(key);
      await this.indexing(state, () => this.refresh(state, true));
      return { ...state.status };
    });
  }

  async startBuild(root: string): Promise<SemanticIndexStatus> {
    const key = await realpath(root);
    const state = await this.getState(key);
    if (state.status.state !== "indexing") {
      state.status = { ...state.status, state: "indexing", processed: 0, total: 0, error: null };
      // 首次下载模型可能超过 RPC 超时；失败由 status 返回，不作为未处理拒绝泄漏。
      void this.build(key).catch((error) => {
        state.status = { ...state.status, state: "failed", error: error instanceof Error ? error.message : String(error) };
      });
    }
    return { ...state.status };
  }

  async update(root: string, files: string[]): Promise<SemanticIndexStatus> {
    return this.exclusive(root, async (key) => {
      await this.file(key);
      const state = await this.getState(key);
      // 在任何写入之前校验全部路径，避免部分更新后才发现越界参数。
      const workspace = new Workspace(key);
      for (const file of files) await workspace.resolveExisting(file);
      await this.indexing(state, async () => {
        state.status.total = files.length;
        for (const file of files) { await state.indexer.updateIndex([file]); state.status.processed += 1; }
      });
      return { ...state.status };
    });
  }

  async clear(root: string): Promise<SemanticIndexStatus> {
    return this.exclusive(root, async (key) => {
      await rm(await this.file(key), { force: true });
      this.states.delete(key);
      return { ...(await this.getState(key)).status };
    });
  }
}

export const workspaceIndexes = new IndexManager();
