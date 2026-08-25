import type { ModelMessage } from "@sztucode/ai";
import type { ForkOptions, NewSessionEntry, SessionBackend, SessionEntry, SessionHeader, SessionSnapshot, SessionTreeNode } from "@sztucode/session";
import { buildSessionTree, projectModelContext, resolveBranch } from "@sztucode/session";

export interface LegacySessionStoreLike {
  create(mode?: string, workspaceId?: string | null, title?: string): Promise<Record<string, unknown>>;
  get(id: string): Promise<Record<string, unknown>>;
  history(id: string): Promise<Array<{ role: "user" | "assistant"; content: string | unknown[]; reasoning_content?: string; ts?: string }>>;
  modelHistory?(id: string): Promise<ModelMessage[]>;
  appendMessage(id: string, message: { role: "user" | "assistant"; content: string | unknown[]; reasoning_content?: string; ts?: string }): Promise<void>;
  replaceModelHistory?(id: string, messages: ModelMessage[]): Promise<void>;
  fork(id: string, title?: string): Promise<Record<string, unknown>>;
  delete(id: string): Promise<void>;
  list(includeArchived?: boolean): Promise<Array<Record<string, unknown>>>;
}

const headerOf = (value: Record<string, unknown>): SessionHeader => ({ type: "session", version: 1, id: String(value.id), parentSessionId: null, createdAt: String(value.created_at), updatedAt: String(value.updated_at), title: String(value.title ?? ""), workspaceId: value.workspace_id == null ? null : String(value.workspace_id), metadata: { legacy: true, mode: value.mode, status: value.status } });

export class SessionStoreBackendAdapter implements SessionBackend {
  constructor(private readonly store: LegacySessionStoreLike) {}
  async create(header: SessionHeader): Promise<SessionSnapshot> { const created = await this.store.create(String(header.metadata?.mode ?? "chat"), header.workspaceId ?? null, header.title ?? ""); return { header: { ...header, id: String(created.id ?? header.id) }, entries: [], leafId: null }; }
  async get(sessionId: string): Promise<SessionSnapshot> { const session = await this.store.get(sessionId); const messages = await this.store.history(sessionId); let parentId: string | null = null; const entries: SessionEntry[] = messages.map((message, index) => { const entry: SessionEntry = { type: "message", id: `legacy-${index + 1}`, parentId, sequence: index + 1, timestamp: message.ts ?? String(session.updated_at), message: { role: message.role, content: message.content as string | import("@sztucode/ai").ContentBlock[], ...(message.reasoning_content ? { reasoning_content: message.reasoning_content } : {}) } }; parentId = entry.id; return entry; }); return { header: headerOf(session), entries, leafId: parentId }; }
  async list(): Promise<SessionHeader[]> { return (await this.store.list(true)).map(headerOf); }
  async append(sessionId: string, input: NewSessionEntry): Promise<SessionEntry> { if (input.type !== "message") throw new Error("legacy SessionStore only supports message entries"); const current = await this.get(sessionId); const entry: SessionEntry = { ...input, id: input.id ?? `legacy-${Date.now()}`, parentId: input.parentId === undefined ? current.leafId : input.parentId, sequence: input.sequence ?? current.entries.length + 1, timestamp: input.timestamp ?? new Date().toISOString() } as SessionEntry; await this.store.appendMessage(sessionId, { role: input.message.role as "user" | "assistant", content: input.message.content, reasoning_content: input.message.reasoning_content, ts: entry.timestamp }); return entry; }
  async history(sessionId: string, leafId?: string | null): Promise<SessionEntry[]> { const snapshot = await this.get(sessionId); return resolveBranch(snapshot.entries, leafId === undefined ? snapshot.leafId : leafId); }
  async fork(sessionId: string, options: ForkOptions = {}): Promise<SessionSnapshot> { const forked = await this.store.fork(sessionId, options.title ?? ""); const snapshot = await this.get(String(forked.id)); return { ...snapshot, header: { ...snapshot.header, parentSessionId: sessionId } }; }
  async tree(sessionId: string): Promise<SessionTreeNode[]> { return buildSessionTree((await this.get(sessionId)).entries); }
  async delete(sessionId: string): Promise<void> { return this.store.delete(sessionId); }
  async projectModelContext(sessionId: string): Promise<ModelMessage[]> { const snapshot = await this.get(sessionId); if (this.store.modelHistory) return this.store.modelHistory(sessionId); return projectModelContext(snapshot); }
}
