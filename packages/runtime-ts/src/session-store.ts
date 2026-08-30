import { mkdir, readFile, readdir, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import type { ContentBlock, ContextMessage } from "./context.js";

export type SessionStatus = "active" | "waiting_for_input" | "closed";
export type SessionMode = "one_shot" | "chat";
export type SessionMessage = { role: "user" | "assistant"; content: string | ContentBlock[]; reasoning_content?: string; ts: string; run_id?: string };
export type SessionRunEvent = { type: string; run_id?: string; [key: string]: unknown };
export type RunStats = { input_tokens: number; output_tokens: number; cache_read_input_tokens: number; cache_creation_input_tokens: number; elapsed_s: number; context_pct: number };
export type Session = { id: string; mode: SessionMode; status: SessionStatus; title: string; created_at: string; updated_at: string; run_ids: string[]; run_stats: Record<string, RunStats>; archived: boolean; pinned: boolean; workspace_id: string | null };

export class SessionStore {
  constructor(private readonly root: string = path.join(process.env.SZTU_DATA_DIR ?? path.join(process.env.USERPROFILE ?? process.cwd(), ".sztu"), "sessions")) {}
  async create(mode: SessionMode = "chat", workspaceId: string | null = null, title = ""): Promise<Session> {
    const id = randomUUID(); const ts = new Date().toISOString();
    const session: Session = { id, mode, status: "active", title: title.trim().slice(0, 200) || "新会话", created_at: ts, updated_at: ts, run_ids: [], run_stats: {}, archived: false, pinned: false, workspace_id: workspaceId };
    await this.save(session); return session;
  }
  // Fork a persisted session: 分配新 ID，复制源 session 的 user/assistant 可见历史，
  // 继承 workspace_id 与 mode，但不复制 run 统计或 active 状态（对齐 Python SessionManager.fork）。
  async fork(sessionId: string, title = ""): Promise<Session> {
    const source = await this.get(sessionId);
    const id = randomUUID(); const ts = new Date().toISOString();
    const forked: Session = { id, mode: source.mode, status: "waiting_for_input", title: title.trim().slice(0, 200) || `Fork of ${source.title || source.id}`, created_at: ts, updated_at: ts, run_ids: [], run_stats: {}, archived: false, pinned: false, workspace_id: source.workspace_id };
    await this.save(forked);
    for (const message of await this.history(sessionId)) {
      if (message.role === "user" || message.role === "assistant") {
        await this.appendMessage(id, { role: message.role, content: message.content });
      }
    }
    return forked;
  }
  async get(id: string): Promise<Session> { return JSON.parse(await readFile(path.join(this.root, id, "meta.json"), "utf8")) as Session; }
  async rename(id: string, title: string): Promise<Session> { const session = await this.get(id); session.title = title.trim().slice(0, 200); session.updated_at = new Date().toISOString(); await this.save(session); return session; }
  async setArchived(id: string, archived: boolean): Promise<Session> { const session = await this.get(id); session.archived = archived; if (archived) session.pinned = false; else if (session.mode === "chat") session.status = "waiting_for_input"; session.updated_at = new Date().toISOString(); await this.save(session); return session; }
  async setPinned(id: string, pinned: boolean): Promise<Session> { const session = await this.get(id); if (pinned && session.archived) throw new Error("archived session cannot be pinned"); session.pinned = pinned; session.updated_at = new Date().toISOString(); await this.save(session); return session; }
  async setWorkspace(id: string, workspaceId: string | null): Promise<Session> { const session = await this.get(id); session.workspace_id = workspaceId; session.updated_at = new Date().toISOString(); await this.save(session); return session; }
  async close(id: string): Promise<Session> { const session = await this.get(id); session.status = "closed"; session.updated_at = new Date().toISOString(); await this.save(session); return session; }
  async setStatus(id: string, status: SessionStatus): Promise<Session> { const session = await this.get(id); session.status = status; session.updated_at = new Date().toISOString(); await this.save(session); return session; }
  /** A daemon restart cancels all in-memory runs, so persisted active sessions must be made resumable. */
  async recoverInterruptedSessions(): Promise<string[]> {
    const recovered: string[] = [];
    for (const session of await this.list(true)) {
      if (session.status !== "active") continue;
      await this.setStatus(session.id, session.mode === "chat" ? "waiting_for_input" : "closed");
      recovered.push(session.id);
    }
    return recovered;
  }
  async delete(id: string): Promise<void> { const { rm } = await import("node:fs/promises"); await rm(path.join(this.root, id), { recursive: true, force: true }); }
  async list(includeArchived = false): Promise<Session[]> {
    await mkdir(this.root, { recursive: true }); const result: Session[] = [];
    for (const entry of await readdir(this.root, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      try { const session = await this.get(entry.name); if (includeArchived || !session.archived) result.push(session); } catch { /* ignore incomplete sessions */ }
    }
    return result.sort((a, b) => Number(b.pinned) - Number(a.pinned) || b.updated_at.localeCompare(a.updated_at) || b.id.localeCompare(a.id));
  }
  async appendMessage(id: string, message: Omit<SessionMessage, "ts"> & { ts?: string }): Promise<void> {
    await mkdir(path.join(this.root, id), { recursive: true });
    const row = { ...message, ts: message.ts ?? new Date().toISOString() };
    await writeFile(path.join(this.root, id, "thread.jsonl"), `${JSON.stringify(row)}\n`, { encoding: "utf8", flag: "a" });
    const session = await this.get(id); session.updated_at = row.ts; if (message.role === "user" && session.title === "新会话") session.title = (typeof message.content === "string" ? message.content : "图片消息").slice(0, 80); await this.save(session);
  }
  async history(id: string): Promise<SessionMessage[]> {
    try { return (await readFile(path.join(this.root, id, "thread.jsonl"), "utf8")).split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line) as SessionMessage); } catch { return []; }
  }
  async modelHistory(id: string): Promise<ContextMessage[]> { try { const value = JSON.parse(await readFile(path.join(this.root, id, "context.json"), "utf8")); if (Array.isArray(value)) return value as ContextMessage[]; } catch { /* use visible history until a model context exists */ } return (await this.history(id)).map((message) => ({ role: message.role, content: message.content })); }
  async replaceModelHistory(id: string, messages: ContextMessage[]): Promise<void> { const directory = path.join(this.root, id); await mkdir(directory, { recursive: true }); const file = path.join(directory, "context.json"); const temporary = `${file}.${process.pid}.${randomUUID()}.tmp`; try { const { copyFile } = await import("node:fs/promises"); await copyFile(file, `${file}.bak`); } catch { /* no existing model context */ } await writeFile(temporary, `${JSON.stringify(messages)}\n`, "utf8"); await rename(temporary, file); }
  async appendRunEvent(id: string, event: SessionRunEvent): Promise<void> { await mkdir(path.join(this.root, id, "runs"), { recursive: true }); await writeFile(path.join(this.root, id, "runs", `${event.run_id ?? "unknown"}.jsonl`), `${JSON.stringify(event)}\n`, { encoding: "utf8", flag: "a" }); }
  async runEvents(id: string, runId: string, maxEvents = 2_000): Promise<SessionRunEvent[]> {
    try {
      const rows = (await readFile(path.join(this.root, id, "runs", `${runId}.jsonl`), "utf8")).split(/\r?\n/).filter(Boolean);
      return rows.slice(-Math.max(1, Math.min(maxEvents, 20_000))).flatMap((line) => { try { return [JSON.parse(line) as SessionRunEvent]; } catch { return []; } });
    } catch { return []; }
  }
  async findRunSession(runId: string): Promise<string | null> {
    for (const session of await this.list(true)) if (session.run_ids.includes(runId)) return session.id;
    return null;
  }
  async contextInjections(id: string): Promise<Array<{ run_id: string; source: string; label: string; chars: number; preview: string; text: string; ts: string }>> {
    const output: Array<{ run_id: string; source: string; label: string; chars: number; preview: string; text: string; ts: string }> = [];
    try { for (const entry of await readdir(path.join(this.root, id, "runs"), { withFileTypes: true })) { if (!entry.isFile() || !entry.name.endsWith(".jsonl")) continue; const lines = (await readFile(path.join(this.root, id, "runs", entry.name), "utf8")).split(/\r?\n/).filter(Boolean); for (const line of lines) { try { const event = JSON.parse(line) as Record<string, unknown>; if (event.type !== "context.injected") continue; const text = String(event.text ?? event.preview ?? ""); output.push({ run_id: String(event.run_id ?? entry.name.slice(0, -6)), source: String(event.source ?? "system"), label: String(event.label ?? "上下文注入"), chars: Number(event.chars ?? text.length), preview: String(event.preview ?? text.slice(0, 160)), text, ts: String(event.ts ?? "") }); } catch { /* ignore corrupt event rows */ } } } } catch { /* no run event directory */ }
    return output.sort((a, b) => a.ts.localeCompare(b.ts));
  }
  async replaceHistory(id: string, messages: Array<Omit<SessionMessage, "ts"> & { ts?: string }>): Promise<void> {
    const session = await this.get(id); const updatedAt = new Date().toISOString(); const file = path.join(this.root, id, "thread.jsonl");
    try { const { copyFile } = await import("node:fs/promises"); await copyFile(file, `${file}.${Date.now()}.bak`); } catch { /* no existing history */ }
    const rows = messages.map((message) => ({ ...message, ts: message.ts ?? updatedAt }));
    await writeFile(file, rows.length ? `${rows.map((row) => JSON.stringify(row)).join("\n")}\n` : "", "utf8");
    session.updated_at = updatedAt; await this.save(session);
  }
  async writeSummary(id: string, text: string): Promise<string> { const directory = path.join(this.root, id); await mkdir(directory, { recursive: true }); const file = path.join(directory, `summary_${compactTimestamp()}_${randomUUID().replace(/-/g, "").slice(0, 8)}.md`); await writeFile(file, text, "utf8"); return file; }
  async attachRun(id: string, runId: string): Promise<void> { const session = await this.get(id); if (!session.run_ids.includes(runId)) session.run_ids.push(runId); session.updated_at = new Date().toISOString(); await this.save(session); }
  async recordRunStats(id: string, runId: string, stats: RunStats): Promise<void> { const session = await this.get(id); session.run_stats ??= {}; session.run_stats[runId] = stats; session.updated_at = new Date().toISOString(); await this.save(session); }
  async readNotes(id: string): Promise<string> {
    let raw = ""; try { raw = await readFile(path.join(this.root, id, "notes.md"), "utf8"); } catch { return ""; }
    if (!raw.includes("---")) return raw.trim();
    const active: string[] = [];
    for (const match of raw.trim().matchAll(/^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*?)(?=\r?\n\r?\n---\r?\n|$)/gm)) {
      if (!/^status:\s*active\s*$/m.test(match[1]!)) continue;
      const runId = match[1]!.match(/^run_id:\s*(\S+)/m)?.[1];
      active.push(`## Note${runId ? ` (${runId})` : ""}\n${match[2]!.trim()}`);
    }
    return active.join("\n\n");
  }
  async appendNote(id: string, content: string, runId: string, supersedes = ""): Promise<string> {
    const noteId = `note-${randomUUID().replace(/-/g, "").slice(0, 12)}`; const directory = path.join(this.root, id); await mkdir(directory, { recursive: true });
    const block = `---\nid: ${noteId}\nstatus: active\nsupersedes: ${supersedes}\nsuperseded_by: \nts: ${new Date().toISOString()}\nrun_id: ${runId}\n---\n${content.trim()}\n\n`;
    await writeFile(path.join(directory, "notes.md"), block, { encoding: "utf8", flag: "a" }); return noteId;
  }
  async updateNote(id: string, noteId: string, content: string, runId: string): Promise<string | null> {
    const file = path.join(this.root, id, "notes.md"); let raw = ""; try { raw = await readFile(file, "utf8"); } catch { return null; }
    const marker = `id: ${noteId}\nstatus: active`; if (!raw.includes(marker)) return null;
    const nextId = `note-${randomUUID().replace(/-/g, "").slice(0, 12)}`;
    const archived = raw.replace(marker, `id: ${noteId}\nstatus: archived`).replace(`id: ${noteId}\nstatus: archived\nsupersedes:`, `id: ${noteId}\nstatus: archived\nsupersedes:`).replace(new RegExp(`(id: ${escapeRegex(noteId)}[\\s\\S]*?superseded_by:)\\s*`), `$1 ${nextId}`);
    const block = `---\nid: ${nextId}\nstatus: active\nsupersedes: ${noteId}\nsuperseded_by: \nts: ${new Date().toISOString()}\nrun_id: ${runId}\n---\n${content.trim()}\n\n`; const temporary = `${file}.${Date.now()}.tmp`;
    await writeFile(temporary, `${archived.trimEnd()}\n\n${block}`, "utf8"); await rename(temporary, file); return nextId;
  }
  private async save(session: Session): Promise<void> {
    const dir = path.join(this.root, session.id); await mkdir(dir, { recursive: true });
    const file = path.join(dir, "meta.json"); const temporary = `${file}.${process.pid}.${randomUUID()}.tmp`;
    await writeFile(temporary, `${JSON.stringify({ ...session, run_stats: session.run_stats ?? {} }, null, 2)}\n`, "utf8");
    await rename(temporary, file);
  }
}

const escapeRegex = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const compactTimestamp = () => new Date().toISOString().replace(/[-:]/g, "").replace("T", "_").slice(0, 15);
