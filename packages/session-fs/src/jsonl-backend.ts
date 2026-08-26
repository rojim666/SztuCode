import { randomUUID } from "node:crypto";
import { mkdir, readFile, readdir, rename, rm, stat, writeFile, appendFile } from "node:fs/promises";
import path from "node:path";
import type { ModelMessage } from "@sztucode/ai";
import { buildSessionTree, projectModelContext, resolveBranch, SessionValidationError, validateSessionEntry, validateSessionSnapshot, type ForkOptions, type NewSessionEntry, type SessionBackend, type SessionEntry, type SessionHeader, type SessionSnapshot, type SessionTreeNode } from "@sztucode/session";

export interface JsonlSessionBackendOptions { root?: string; onWarning?: (warning: string) => void; }

const now = () => new Date().toISOString();
const safeId = (id: string) => { if (!/^[A-Za-z0-9._-]+$/.test(id)) throw new Error("invalid session id"); return id; };
const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

export class JsonlSessionBackend implements SessionBackend {
  readonly root: string;
  private readonly locks = new Map<string, Promise<unknown>>();
  private readonly warnings: string[] = [];
  private readonly onWarning?: (warning: string) => void;
  constructor(options: JsonlSessionBackendOptions | string = {}) {
    this.root = typeof options === "string" ? options : options.root ?? path.join(process.env.SZTU_DATA_DIR ?? path.join(process.env.USERPROFILE ?? process.cwd(), ".sztu"), "sessions");
    this.onWarning = typeof options === "string" ? undefined : options.onWarning;
  }
  get recoveryWarnings(): readonly string[] { return this.warnings; }
  private warn(message: string): void { this.warnings.push(message); this.onWarning?.(message); }
  private file(id: string): string { return path.join(this.root, `${safeId(id)}.jsonl`); }
  private legacyDir(id: string): string { return path.join(this.root, safeId(id)); }
  private async withLock<T>(id: string, operation: () => Promise<T>): Promise<T> {
    const previous = this.locks.get(id) ?? Promise.resolve();
    const current = previous.then(operation, operation);
    this.locks.set(id, current);
    try { return await current; } finally { if (this.locks.get(id) === current) this.locks.delete(id); }
  }
  async create(header: SessionHeader): Promise<SessionSnapshot> {
    safeId(header.id); if (header.type !== "session" || header.version !== 1) throw new SessionValidationError("unsupported session header");
    await mkdir(this.root, { recursive: true }); const file = this.file(header.id);
    try { await stat(file); throw new Error(`session already exists: ${header.id}`); } catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
    const snapshot: SessionSnapshot = { header: clone(header), entries: [], leafId: null }; await this.atomicWrite(file, `${JSON.stringify(header)}\n`); return snapshot;
  }
  async get(sessionId: string): Promise<SessionSnapshot> {
    safeId(sessionId); const file = this.file(sessionId);
    try { return await this.readNew(file); } catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error; }
    return this.readLegacy(sessionId);
  }
  async list(): Promise<SessionHeader[]> {
    await mkdir(this.root, { recursive: true }); const headers = new Map<string, SessionHeader>();
    for (const entry of await readdir(this.root, { withFileTypes: true })) {
      if (entry.isFile() && entry.name.endsWith(".jsonl")) { try { headers.set(entry.name.slice(0, -6), (await this.readNew(path.join(this.root, entry.name))).header); } catch (error) { this.warn(`unable to read ${entry.name}: ${(error as Error).message}`); } }
      else if (entry.isDirectory()) { try { const snapshot = await this.readLegacy(entry.name); if (!headers.has(entry.name)) headers.set(entry.name, snapshot.header); } catch { /* incomplete legacy directories are ignored */ } }
    }
    return [...headers.values()].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt) || b.id.localeCompare(a.id));
  }
  async append(sessionId: string, input: NewSessionEntry): Promise<SessionEntry> {
    safeId(sessionId); return this.withLock(sessionId, async () => {
      let snapshot: SessionSnapshot;
      try { snapshot = await this.get(sessionId); } catch (error) { throw error; }
      if (!await this.existsNew(sessionId)) { await this.migrateLegacy(sessionId); snapshot = await this.readNew(this.file(sessionId)); }
      const id = input.id ?? randomUUID(); if (snapshot.entries.some((entry) => entry.id === id)) throw new SessionValidationError(`duplicate entry id: ${id}`);
      const parentId = input.parentId === undefined ? snapshot.leafId : input.parentId; if (parentId !== null && !snapshot.entries.some((entry) => entry.id === parentId)) throw new SessionValidationError(`missing parent entry: ${parentId}`);
      const entry = { ...clone(input), id, parentId, sequence: input.sequence ?? (snapshot.entries.at(-1)?.sequence ?? 0) + 1, timestamp: input.timestamp ?? now() } as SessionEntry;
      validateSessionEntry(entry);
      await appendFile(this.file(sessionId), `${JSON.stringify(entry)}\n`, "utf8"); return entry;
    });
  }
  async history(sessionId: string, leafId?: string | null): Promise<SessionEntry[]> { const snapshot = await this.get(sessionId); return resolveBranch(snapshot.entries, leafId === undefined ? snapshot.leafId : leafId); }
  async fork(sessionId: string, options: ForkOptions = {}): Promise<SessionSnapshot> {
    return this.withLock(sessionId, async () => {
      const source = await this.get(sessionId); const branch = resolveBranch(source.entries, options.entryId === undefined ? source.leafId : options.entryId);
      const id = options.id ?? randomUUID(); safeId(id); const ts = now(); const header: SessionHeader = { type: "session", version: 1, id, parentSessionId: source.header.id, createdAt: ts, updatedAt: ts, title: options.title ?? (source.header.title ? `Fork of ${source.header.title}` : `Fork of ${source.header.id}`), workspaceId: options.workspaceId === undefined ? source.header.workspaceId ?? null : options.workspaceId, metadata: options.metadata ?? source.header.metadata };
      if (await this.existsNew(id)) throw new Error(`session already exists: ${id}`);
      const ids = new Map<string, string>(); const entries: SessionEntry[] = branch.map((entry, index) => { const nextId = randomUUID(); ids.set(entry.id, nextId); return { ...clone(entry), id: nextId, parentId: index ? ids.get(entry.parentId!) ?? null : null, sequence: index + 1 }; });
      const snapshot: SessionSnapshot = { header, entries, leafId: entries.at(-1)?.id ?? null }; await this.atomicWrite(this.file(id), [JSON.stringify(header), ...entries.map((entry) => JSON.stringify(entry)), ""].join("\n")); return snapshot;
    });
  }
  async tree(sessionId: string): Promise<SessionTreeNode[]> { const snapshot = await this.get(sessionId); return buildSessionTree(snapshot.entries); }
  async delete(sessionId: string): Promise<void> { safeId(sessionId); await rm(this.file(sessionId), { force: true }); }
  async projectModelContext(sessionId: string, leafId?: string | null): Promise<ModelMessage[]> { return projectModelContext(await this.get(sessionId), leafId); }
  async migrateLegacy(sessionId: string): Promise<SessionSnapshot> {
    return this.withLock(`migrate:${sessionId}`, async () => { const legacy = await this.readLegacy(sessionId); const file = this.file(sessionId); try { await stat(file); return this.readNew(file); } catch { /* write below */ } const lines = [JSON.stringify(legacy.header), ...legacy.entries.map((entry) => JSON.stringify(entry)), ""].join("\n"); await this.atomicWrite(file, lines); return legacy; });
  }
  private async existsNew(id: string): Promise<boolean> { try { await stat(this.file(id)); return true; } catch { return false; } }
  private async atomicWrite(file: string, content: string): Promise<void> { await mkdir(path.dirname(file), { recursive: true }); const temporary = `${file}.${process.pid}.${randomUUID()}.tmp`; await writeFile(temporary, content, "utf8"); await rename(temporary, file); }
  private async readNew(file: string): Promise<SessionSnapshot> {
    const text = await readFile(file, "utf8"); const rows = text.split(/\r?\n/); if (rows.at(-1) === "") rows.pop();
    if (rows.length === 0) throw new SessionValidationError("empty session file");
    const parse = (row: string, line: number): unknown => { try { return JSON.parse(row); } catch { throw new SessionValidationError("invalid JSON in session file", line); } };
    const header = parse(rows[0]!, 1) as SessionHeader; if (header.type !== "session" || header.version !== 1) throw new SessionValidationError("invalid session header", 1);
    const entries: SessionEntry[] = []; for (let index = 1; index < rows.length; index += 1) { const row = rows[index]!; if (!row.trim()) continue; try { const value = parse(row, index + 1); validateSessionEntry(value, index + 1); entries.push(value); } catch (error) { if (index === rows.length - 1 && !text.endsWith("\n")) { this.warn(`ignored incomplete final line in ${path.basename(file)}`); break; } throw error; } }
    const latest = entries.at(-1);
    const snapshot: SessionSnapshot = { header: latest && latest.timestamp > header.updatedAt ? { ...header, updatedAt: latest.timestamp } : header, entries, leafId: latest?.id ?? null };
    validateSessionSnapshot(snapshot); return snapshot;
  }
  private async readLegacy(id: string): Promise<SessionSnapshot> {
    const directory = this.legacyDir(id); const meta = JSON.parse(await readFile(path.join(directory, "meta.json"), "utf8")) as Record<string, unknown>; const header: SessionHeader = { type: "session", version: 1, id: String(meta.id ?? id), parentSessionId: null, createdAt: String(meta.created_at ?? now()), updatedAt: String(meta.updated_at ?? meta.created_at ?? now()), title: String(meta.title ?? ""), workspaceId: meta.workspace_id == null ? null : String(meta.workspace_id), metadata: { legacy: true, mode: meta.mode, status: meta.status, archived: meta.archived, pinned: meta.pinned, run_ids: meta.run_ids, run_stats: meta.run_stats } };
    const entries: SessionEntry[] = []; let parentId: string | null = null; let sequence = 0;
    try { const text = await readFile(path.join(directory, "thread.jsonl"), "utf8"); for (const row of text.split(/\r?\n/).filter(Boolean)) { const message = JSON.parse(row) as ModelMessage & { ts?: string }; const entry: SessionEntry = { type: "message", id: `legacy-${++sequence}`, parentId, sequence, timestamp: message.ts ?? header.updatedAt, message: { role: message.role, content: message.content, ...(message.reasoning_content ? { reasoning_content: message.reasoning_content } : {}) } }; entries.push(entry); parentId = entry.id; } } catch (error) { if ((error as NodeJS.ErrnoException).code !== "ENOENT") this.warn(`unable to read legacy history ${id}: ${(error as Error).message}`); }
    try { const context = JSON.parse(await readFile(path.join(directory, "context.json"), "utf8")); if (Array.isArray(context)) { const entry: SessionEntry = { type: "model_context", id: `legacy-context-${++sequence}`, parentId, sequence, timestamp: header.updatedAt, messages: context as ModelMessage[] }; entries.push(entry); parentId = entry.id; } } catch { /* context is optional in legacy sessions */ }
    return { header, entries, leafId: parentId };
  }
}
