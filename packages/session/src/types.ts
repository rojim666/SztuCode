import type { ModelMessage } from "@sztucode/ai";

export interface SessionHeader {
  type: "session";
  version: 1;
  id: string;
  parentSessionId: string | null;
  createdAt: string;
  updatedAt: string;
  title?: string;
  workspaceId?: string | null;
  metadata?: Record<string, unknown>;
}

export interface SessionEntryBase {
  id: string;
  parentId: string | null;
  sequence: number;
  timestamp: string;
}

export type SessionMessageEntry = SessionEntryBase & {
  type: "message";
  message: ModelMessage;
};

export type SessionCompactionEntry = SessionEntryBase & {
  type: "compaction";
  summary: string;
  retainedMessages?: ModelMessage[];
  tokensBefore?: number;
  details?: unknown;
};

export type SessionModelContextEntry = SessionEntryBase & {
  type: "model_context";
  messages: ModelMessage[];
};

export type SessionCustomEntry = SessionEntryBase & {
  type: "custom";
  customType: string;
  data?: unknown;
};

export type SessionEntry = SessionMessageEntry | SessionCompactionEntry | SessionModelContextEntry | SessionCustomEntry;
type EntryWithoutIdentity<T extends SessionEntry> = Omit<T, "id" | "sequence" | "parentId" | "timestamp"> & Partial<Pick<SessionEntryBase, "id" | "sequence" | "parentId" | "timestamp">>;
export type NewSessionEntry = SessionEntry extends infer _Never
  ? EntryWithoutIdentity<SessionMessageEntry> | EntryWithoutIdentity<SessionCompactionEntry> | EntryWithoutIdentity<SessionModelContextEntry> | EntryWithoutIdentity<SessionCustomEntry>
  : never;

export interface SessionSnapshot {
  header: SessionHeader;
  entries: SessionEntry[];
  leafId: string | null;
}

export interface SessionTreeNode {
  entry: SessionEntry;
  children: SessionTreeNode[];
}

export interface ForkOptions {
  entryId?: string | null;
  id?: string;
  title?: string;
  workspaceId?: string | null;
  metadata?: Record<string, unknown>;
}

export interface SessionBackend {
  create(header: SessionHeader): Promise<SessionSnapshot>;
  get(sessionId: string): Promise<SessionSnapshot>;
  list(): Promise<SessionHeader[]>;
  append(sessionId: string, entry: NewSessionEntry): Promise<SessionEntry>;
  history(sessionId: string, leafId?: string | null): Promise<SessionEntry[]>;
  fork(sessionId: string, options?: ForkOptions): Promise<SessionSnapshot>;
  tree(sessionId: string): Promise<SessionTreeNode[]>;
  delete(sessionId: string): Promise<void>;
}
