import { createHash } from "node:crypto";
import { realpath } from "node:fs/promises";
import { createChunker, type Chunk } from "./chunking/index.js";
import { createTransformersEmbedder, type Embedder } from "./embedding/index.js";
import { LexicalIndex } from "./retrieval/index.js";
import { JsonlVectorStore } from "./vector-store/index.js";
import type { VectorRecord } from "./vector-store/types.js";
import type { SessionStore } from "./session-store.js";
import { Workspace } from "./workspace.js";

export type MemoryQueryMode = "keyword" | "semantic" | "hybrid";
export type MemoryScope = "current" | "workspace";
type MemorySource = { source: string; text: string; metadata: Record<string, string | number | boolean> };
const queues = new Map<string, Promise<unknown>>();

export class SemanticMemory {
  private readonly embedder: Embedder;
  constructor(private readonly root: string, private readonly sessions: SessionStore | undefined, private readonly sessionId: string | undefined, private readonly readLayer: (layer: string) => Promise<string>, createEmbedder: () => Embedder = createTransformersEmbedder) {
    this.embedder = createEmbedder();
  }

  private async sources(layer: string): Promise<MemorySource[]> {
    if (layer !== "session" || !this.sessions || !this.sessionId) return [{ source: `${layer}/context.md`, text: await this.readLayer(layer), metadata: { layer } }];
    const current = await this.sessions.get(this.sessionId);
    const sessions = current.workspace_id ? (await this.sessions.list(true)).filter((session) => session.workspace_id === current.workspace_id) : [current];
    const output: MemorySource[] = [];
    for (const session of sessions) {
      for (const block of await this.sessions.noteBlocks(session.id)) {
        if (block.status !== "active") continue;
        output.push({ source: `sessions/${session.id}/${block.id}.md`, text: block.raw.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, "").trim(), metadata: {
          layer, session_id: session.id, note_id: block.id, timestamp: block.ts,
          run_id: block.raw.match(/^run_id:\s*(\S+)/m)?.[1] ?? "",
        } });
      }
    }
    return output;
  }

  async search(layer: string, query: string, mode: MemoryQueryMode, scope: MemoryScope, offset: number, limit: number): Promise<string> {
    const root = await realpath(this.root);
    const file = await new Workspace(root).resolveExisting(".sztu/vector/memory-index.jsonl");
    const previous = queues.get(file) ?? Promise.resolve();
    const pending = previous.catch(() => {}).then(async () => {
      const sources = await this.sources(layer);
      const chunks: Chunk[] = sources.flatMap((source) => createChunker(source.source).split(source.text, { source: source.source }).map((chunk) => ({ ...chunk, metadata: { ...chunk.metadata, ...source.metadata, content_hash: createHash("sha256").update(source.text).digest("hex") } })));
      const allowed = chunks.filter((chunk) => layer !== "session" || scope === "workspace" || chunk.metadata.session_id === this.sessionId);
      const lexical = new LexicalIndex();
      for (const source of sources) lexical.replace(source.source, allowed.filter((chunk) => chunk.metadata.source === source.source));
      const keywords = query ? lexical.search(query, Math.max(1, allowed.length)) : [];
      const render = (records: Array<{ text: string; metadata: Record<string, unknown>; score: number }>, warning = "") => {
        const safeLimit = Math.min(4000, Math.max(1, Math.floor(limit)));
        const selected = records.slice(Math.max(0, Math.floor(offset)));
        const text = selected.length ? selected.map((record) => `[${record.metadata.source}; score=${record.score.toFixed(4)}]\n${record.text}`).join("\n\n").slice(0, safeLimit) : `No matches for ${JSON.stringify(query)}.`;
        return `${text}${warning ? `\n\n${warning}` : ""}`;
      };
      if (mode === "keyword") return render(keywords);
      try {
        const store = await JsonlVectorStore.open(file, this.embedder.dimensions, "jsonl", { embedderName: this.embedder.name });
        const existing = store.exportRecords().filter((record) => record.metadata.layer === layer);
        const sourceNames = new Set(sources.map((source) => source.source));
        for (const source of new Set(existing.map((record) => String(record.metadata.source)))) {
          if (!sourceNames.has(source)) await store.delete({ source });
        }
        for (const source of sources) {
          const group = chunks.filter((chunk) => chunk.metadata.source === source.source);
          const old = existing.filter((record) => record.metadata.source === source.source);
          if (group.length && old.length === group.length && old.every((record) => record.metadata.content_hash === group[0]!.metadata.content_hash)) continue;
          const vectors = await this.embedder.embed(group.map((chunk) => chunk.text));
          await store.delete({ source: source.source });
          if (group.length) await store.add(group.map((chunk, index) => ({ text: chunk.text, vector: vectors[index]!, metadata: chunk.metadata as VectorRecord["metadata"] })));
        }
        if (!query) return "Memory index updated.";
        const filter = { layer, ...(layer === "session" && scope === "current" ? { session_id: this.sessionId ?? "" } : {}) };
        const semantic = await store.search(await this.embedder.embedQuery(query), Math.max(1, await store.count(filter)), filter);
        if (mode === "semantic") return render(semantic.map(({ record, score }) => ({ ...record, score })));
        // RRF 只融合排名，避免把关键词分数和余弦相似度误当成同一尺度。
        const ranked = new Map<string, { text: string; metadata: Record<string, unknown>; score: number }>();
        const add = (text: string, metadata: Record<string, unknown>, rank: number) => {
          const key = `${metadata.source}#${metadata.chunk_index}`;
          const current = ranked.get(key);
          ranked.set(key, { text, metadata, score: (current?.score ?? 0) + 1 / (60 + rank + 1) });
        };
        semantic.forEach(({ record }, rank) => add(record.text, record.metadata, rank));
        keywords.forEach((record, rank) => add(record.text, record.metadata, rank));
        return render([...ranked.values()].sort((a, b) => b.score - a.score));
      } catch (error) {
        if (mode === "semantic") throw error;
        return render(keywords, `语义检索暂不可用，已返回关键词结果：${error instanceof Error ? error.message : String(error)}`);
      }
    });
    queues.set(file, pending);
    try { return await pending; }
    finally { if (queues.get(file) === pending) queues.delete(file); }
  }
}
