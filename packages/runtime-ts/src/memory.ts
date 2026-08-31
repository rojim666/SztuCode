import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import type { Tool } from "./tools.js";
import type { SessionStore } from "./session-store.js";

type MemoryLayer = "global" | "project" | "session";
type MemoryDocument = { name: MemoryLayer; content: string; source: string };
type LiveSources = { sessions?: SessionStore; sessionId?: string; files?: Partial<Record<MemoryLayer, string>> };
const MEMORY_LAYERS: MemoryLayer[] = ["global", "project", "session"];
const LAYER_SOURCES: Record<MemoryLayer, string> = { global: "~/.sztu/context.md", project: ".sztu/context.md", session: "session/notes.md" };
const CONTEXT_MAX_BYTES = 256 * 1024; // project/global context.md 写入上限
const consolidatedPrefix = "## Consolidated notes (";
const todayHeader = () => `${consolidatedPrefix}${new Date().toISOString().slice(0, 10)})`;

export class MemoryCatalog {
  private readonly documents = new Map<MemoryLayer, MemoryDocument>();

  constructor(documents: MemoryDocument[], private readonly inlineChars = 2_000, private readonly live?: LiveSources) {
    for (const document of documents) if (document.content.trim()) this.documents.set(document.name, { ...document, content: document.content.trim() });
  }

  requiresReader(): boolean { return [...this.documents.values()].some((document) => document.content.length > this.inlineChars); }

  // prompt 在每个 run 启动时只渲染一次，此时快照即最新；run 内的可见性由 readLive 负责
  prompt(): string {
    const sections = [...this.documents.values()].map((document) => `## ${capitalize(document.name)} memory\n${this.promptContent(document)}`);
    if (!sections.length) return "";
    return `# Persistent memory\n${sections.join("\n\n")}`;
  }

  read(layer: string, query = "", offset = 0, limit = 1_600): string {
    const document = this.documents.get(layer as MemoryLayer);
    if (!document) throw new Error(`memory layer not found: ${layer}; available: ${[...this.documents.keys()].join(", ") || "none"}`);
    return this.render(document.content, layer, document.source, query, offset, limit);
  }

  // 活读：session 层每次现读 notes，global/project 层每次现读文件，保证 run 内写入与外部编辑立即可见
  async readLive(layer: string, query = "", offset = 0, limit = 1_600): Promise<string> {
    if (!MEMORY_LAYERS.includes(layer as MemoryLayer)) throw new Error(`memory layer not found: ${layer}; available: ${MEMORY_LAYERS.join(", ")}`);
    let content: string;
    if (layer === "session" && this.live?.sessions && this.live.sessionId) content = await this.live.sessions.readNotes(this.live.sessionId);
    else if (layer !== "session" && this.live?.files?.[layer as MemoryLayer]) content = await readText(this.live.files[layer as MemoryLayer]!);
    else content = this.documents.get(layer as MemoryLayer)?.content ?? "";
    return this.render(content.trim(), layer, LAYER_SOURCES[layer as MemoryLayer], query, offset, limit);
  }

  private render(content: string, layer: string, source: string, query: string, offset: number, limit: number): string {
    const safeLimit = Math.min(4_000, Math.max(1, Math.floor(limit)));
    const safeOffset = Math.max(0, Math.floor(offset));
    if (query.trim()) return searchExcerpt(content, query.trim(), safeOffset, safeLimit);
    // 无 query 且 offset 为 0：返回渐进披露目录（标题列表 + 字符数），正文走 query 或 offset 分页
    if (safeOffset === 0) {
      const headings = content.split(/\r?\n/).map((line) => line.trim()).filter((line) => /^#{1,6}\s+/.test(line)).map((line) => line.replace(/^#+\s+/, "").slice(0, 120)).slice(0, 16);
      return `[memory toc: ${layer}, ${content.length} chars, source: ${source}]\n${headings.length ? headings.map((heading) => `- ${heading}`).join("\n") : "(no Markdown headings; use a query or offset paging)"}`;
    }
    const excerpt = content.slice(safeOffset, safeOffset + safeLimit);
    const nextOffset = safeOffset + excerpt.length;
    return `${excerpt}\n\n[memory page: ${layer}, chars ${safeOffset}:${nextOffset}/${content.length}${nextOffset < content.length ? `, next_offset=${nextOffset}` : ", end"}]`;
  }

  private promptContent(document: MemoryDocument): string {
    if (document.content.length <= this.inlineChars) return document.content;
    const headings = document.content.split(/\r?\n/).map((line) => line.trim()).filter((line) => /^#{1,6}\s+/.test(line)).map((line) => line.replace(/^#+\s+/, "").slice(0, 120)).slice(0, 16);
    return `[Progressive memory: ${document.content.length} characters, source: ${document.source}]\nAvailable topics:\n${headings.length ? headings.map((heading) => `- ${heading}`).join("\n") : "- (no Markdown headings; use query search or paged reading)"}\nUse memory_read with layer="${document.name}" and a focused query.`;
  }
}

export async function loadMemoryCatalog(workspaceRoot: string, sessions?: SessionStore, sessionId?: string): Promise<MemoryCatalog> {
  const homeRoot = process.env.USERPROFILE ?? process.env.HOME ?? process.cwd();
  const globalFile = path.join(homeRoot, ".sztu", "context.md"); const projectFile = path.join(workspaceRoot, ".sztu", "context.md");
  const [globalMemory, projectMemory, sessionMemory] = await Promise.all([
    readText(globalFile),
    readText(projectFile),
    sessions && sessionId ? sessions.readNotes(sessionId) : Promise.resolve(""),
  ]);
  return new MemoryCatalog([
    { name: "global", content: globalMemory, source: "~/.sztu/context.md" },
    { name: "project", content: projectMemory, source: ".sztu/context.md" },
    { name: "session", content: sessionMemory, source: "session/notes.md" },
  ], 2_000, { sessions, sessionId, files: { global: globalFile, project: projectFile } });
}

export function createMemoryTools(catalog: MemoryCatalog, sessions?: SessionStore, sessionId?: string, runId = ""): Tool[] {
  const tools: Tool[] = [];
  // 有 session 时也注册：会话笔记在 run 内增长，readLive 保证随时可读
  if (catalog.requiresReader() || Boolean(sessions && sessionId)) tools.push({ name: "memory_read", description: "Read a bounded excerpt from global, project, or session memory", permission: "read_only", schema: { type: "object", properties: { layer: { type: "string", enum: ["global", "project", "session"] }, query: { type: "string" }, offset: { type: "integer", minimum: 0 }, limit: { type: "integer", minimum: 1, maximum: 4000 } }, required: ["layer"] }, async invoke(params) { try { return { ok: true, output: await catalog.readLive(String(params.layer ?? ""), String(params.query ?? ""), Number(params.offset ?? 0), Number(params.limit ?? 1600)) }; } catch (error) { return { ok: false, output: "", error: error instanceof Error ? error.message : String(error), errorType: "runtime_error" }; } } });
  if (sessions && sessionId) {
    tools.push({ name: "note_save", description: "Save a concise durable fact or decision to this session", permission: "workspace_write", schema: { type: "object", properties: { content: { type: "string" } }, required: ["content"] }, async invoke(params) { const content = typeof params.content === "string" ? params.content.trim() : ""; if (!content) return { ok: false, output: "", error: "empty content", errorType: "schema_error" }; try { const noteId = await sessions.appendNote(sessionId, content, runId); return { ok: true, output: `saved (${noteId})` }; } catch (error) { return { ok: false, output: "", error: error instanceof Error ? error.message : String(error), errorType: "schema_error" }; } } });
    tools.push({ name: "note_update", description: "Replace an active session note while preserving its supersedes history", permission: "workspace_write", schema: { type: "object", properties: { note_id: { type: "string" }, content: { type: "string" } }, required: ["note_id", "content"] }, async invoke(params) { const noteId = typeof params.note_id === "string" ? params.note_id.trim() : ""; const content = typeof params.content === "string" ? params.content.trim() : ""; if (!noteId || !content) return { ok: false, output: "", error: "note_id and content are required", errorType: "schema_error" }; try { const nextId = await sessions.updateNote(sessionId, noteId, content, runId); return nextId ? { ok: true, output: `updated (${noteId} -> ${nextId})` } : { ok: false, output: "", error: `note not found: ${noteId}`, errorType: "runtime_error" }; } catch (error) { return { ok: false, output: "", error: error instanceof Error ? error.message : String(error), errorType: "schema_error" }; } } });
    tools.push({ name: "memory_consolidate", description: "Append new active session notes into the project context.md, deduplicated by note id", permission: "workspace_write", schema: { type: "object", properties: {} }, async invoke(_params, context) { try { return await consolidateNotes(sessions, sessionId, path.join(context.workspace.root, ".sztu", "context.md")); } catch (error) { return { ok: false, output: "", error: error instanceof Error ? error.message : String(error), errorType: "runtime_error" }; } } });
  }
  return tools;
}

const readText = async (file: string) => readFile(file, "utf8").then((text) => text.trim()).catch(() => "");
const capitalize = (value: string) => value.charAt(0).toUpperCase() + value.slice(1);

// 分词：按标点/空白切出拉丁数字串与 CJK 连续串，去重并丢弃长度 <2 的词
const tokenize = (text: string): string[] => [...new Set([...text.toLocaleLowerCase().matchAll(/[0-9a-z_]+|[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]+/g)].map((match) => match[0]))].filter((token) => token.length >= 2);

// 行评分：词命中 +1/词，完整短语 +3，全部词命中 +2（合取奖励），标题行整行 ×2
function scoreLine(line: string, tokens: string[], phrase: string): number {
  const lower = line.toLocaleLowerCase(); let score = 0; let matched = 0;
  for (const token of tokens) if (lower.includes(token)) { score += 1; matched += 1; }
  if (!score) return 0;
  if (lower.includes(phrase)) score += 3;
  if (matched === tokens.length) score += 2;
  if (/^#{1,6}\s/.test(line.trimStart())) score *= 2;
  return score;
}

// 评分检索：按分数降序返回命中块，offset 是命中块索引（非字符偏移），保留 ±2 行上下文窗口
function searchExcerpt(content: string, query: string, offset: number, limit: number): string {
  const lines = content.split(/\r?\n/); const tokens = tokenize(query); const phrase = query.toLocaleLowerCase();
  const hits = lines.map((line, index) => ({ index, score: scoreLine(line, tokens, phrase) })).filter((hit) => hit.score > 0).sort((a, b) => b.score - a.score || a.index - b.index);
  if (!hits.length) return `No matches for ${JSON.stringify(query)}.`;
  if (offset >= hits.length) return `No matches for ${JSON.stringify(query)} after match offset ${offset}.`;
  let output = ""; let consumed = 0;
  for (const hit of hits.slice(offset)) {
    const chunk = lines.slice(Math.max(0, hit.index - 2), Math.min(lines.length, hit.index + 3)).join("\n").trim(); const next = `${output ? "\n\n---\n\n" : ""}${chunk}`;
    if (output.length + next.length > limit) { output += next.slice(0, Math.max(0, limit - output.length)); break; }
    output += next; consumed += 1;
  }
  const nextMatch = offset + Math.max(1, consumed);
  return `${output}\n\n[memory search: ${JSON.stringify(query)}, matches ${offset + 1}-${Math.min(nextMatch, hits.length)}/${hits.length}${nextMatch < hits.length ? `, next_offset=${nextMatch}` : ", end"}]`;
}

// 巩固管道：把新增的 active 笔记按 id 去重后并入 project context.md 的当日 Consolidated 段落
async function consolidateNotes(sessions: SessionStore, sessionId: string, contextFile: string): Promise<{ ok: boolean; output: string; error?: string; errorType?: "runtime_error" }> {
  const active = (await sessions.noteBlocks(sessionId)).filter((block) => block.status === "active");
  if (!active.length) return { ok: true, output: "No active session notes to consolidate." };
  let text = await readText(contextFile); let added = 0; let skipped = 0; const entries: string[] = [];
  for (const block of active) {
    // 已存在相同 id 标记（文件内或本批已收）则跳过
    if (text.includes(`### ${block.id}`) || entries.some((entry) => entry.startsWith(`### ${block.id}\n`))) { skipped += 1; continue; }
    entries.push(`### ${block.id}\n${block.raw.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, "").trim()}`); added += 1;
  }
  if (added) {
    text = fitContextBudget(appendConsolidated(text, entries));
    await mkdir(path.dirname(contextFile), { recursive: true });
    const temporary = `${contextFile}.${Date.now()}.tmp`; await writeFile(temporary, text, "utf8"); await rename(temporary, contextFile);
  }
  return { ok: true, output: `Consolidated ${added} note(s) into project context (${skipped} skipped as duplicates).` };
}

// 同日已有段落则追加到段落末尾，否则在文末新建段落
function appendConsolidated(text: string, entries: string[]): string {
  const header = todayHeader(); const joined = entries.join("\n\n");
  if (text.includes(header)) {
    const start = text.indexOf(header) + header.length; const next = text.indexOf("\n## ", start);
    const insertAt = next === -1 ? text.length : next;
    return `${text.slice(0, insertAt).replace(/\s+$/, "")}\n\n${joined}${text.slice(insertAt)}`;
  }
  return `${text.replace(/\s+$/, "")}${text ? "\n\n" : ""}${header}\n\n${joined}\n`;
}

// 超过 256KB 时整段移除最旧的 Consolidated 段落，直到达标或无可移除
function fitContextBudget(text: string): string {
  while (Buffer.byteLength(text, "utf8") > CONTEXT_MAX_BYTES) {
    const next = dropOldestConsolidated(text);
    if (next === text) break;
    text = next;
  }
  return text;
}

function dropOldestConsolidated(text: string): string {
  const start = text.indexOf(consolidatedPrefix);
  if (start === -1) return text;
  const next = text.indexOf("\n## ", start + 1);
  return `${text.slice(0, start)}${text.slice(next === -1 ? text.length : next)}`.replace(/\n{3,}/g, "\n\n").replace(/^\n+/, "");
}
