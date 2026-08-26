import type net from "node:net";

export type MaybePromise<T> = T | Promise<T>;

export type SessionPhase = "idle" | "running" | "steering" | "aborting" | "closed" | string;

export interface SessionSnapshot {
  id: string;
  createdAt: string | number;
  updatedAt: string | number;
  phase: SessionPhase;
  attached: boolean;
  locked: boolean;
  name?: string;
  cwd?: string;
  [key: string]: unknown;
}

export interface SessionMetadata {
  id: string;
  createdAt?: string | number;
  updatedAt?: string | number;
  sessionName?: string;
  cwd?: string;
  [key: string]: unknown;
}

export interface TranscriptProgress {
  [key: string]: unknown;
}

export type ModelRef = string | { provider?: string; id: string; [key: string]: unknown };
export type ThinkingLevel = string;
export type PromptInput = { text: string; [key: string]: unknown };
export type SteerInput = { text: string; [key: string]: unknown };

export type SessionRuntimeEvent =
  | { type: "snapshot" }
  | { type: "progress"; progress: TranscriptProgress }
  | { type: "error"; error: ServerErrorLike };
export type PiSessionRuntimeEvent = SessionRuntimeEvent;

export interface PiSessionRuntime {
  snapshot(): MaybePromise<SessionSnapshot>;
  getPhase(): SessionPhase;
  prompt(input: PromptInput): Promise<void>;
  steer(input: SteerInput): Promise<void>;
  abort(): Promise<void>;
  setModel(model: ModelRef): Promise<void>;
  setThinking(thinkingLevel: ThinkingLevel): Promise<void>;
  subscribe(listener: (event: SessionRuntimeEvent) => void): () => void;
  dispose(): Promise<void>;
}
export type SessionRuntime = PiSessionRuntime;

export interface CreateSessionOptions {
  id: string;
  cwd?: string;
  name?: string;
  model?: ModelRef;
  thinkingLevel?: ThinkingLevel;
  [key: string]: unknown;
}

export interface SessionService {
  listSessions(): Promise<SessionMetadata[]>;
  listModels?(): Promise<unknown[]>;
  createSession(options: CreateSessionOptions): Promise<PiSessionRuntime>;
  openSession(sessionId: string): Promise<PiSessionRuntime>;
}
export type PiServerService = SessionService;

export interface ServerErrorLike {
  code?: string;
  message: string;
  details?: unknown;
}

export interface ConnectionState {
  readonly id: string;
  readonly socket: net.Socket;
  stage: "awaitingHello" | "handshaking" | "ready" | "closing" | "closed";
  handshakeComplete: boolean;
  disconnected: boolean;
  readonly sessionIds: Set<string>;
  readonly subscriptions: Set<string>;
}

export interface RpcRequest {
  jsonrpc: "2.0";
  id: string | number | null;
  method: string;
  params?: unknown;
}

export interface RpcSuccess<T = unknown> {
  jsonrpc: "2.0";
  id: string | number | null;
  result: T;
}

export interface RpcError {
  jsonrpc: "2.0";
  id: string | number | null;
  error: { code: number; message: string; data?: unknown };
}
export type RpcResponse<T = unknown> = RpcSuccess<T> | RpcError;

export interface EventEnvelope<T = unknown> {
  kind: "event";
  event: T;
}

export interface HandshakeHello {
  type: "hello";
  version: number;
  client?: string;
}

export interface HandshakeWelcome {
  type: "hello";
  version: number;
  server_version?: string;
  capabilities?: string[];
  connectionId?: string;
  connection_id?: string;
  snapshot?: unknown;
}

export interface ProtocolHandshake {
  readonly version: number;
  accept(hello: HandshakeHello, connection: ConnectionState): MaybePromise<HandshakeWelcome>;
}

export interface TransportOptions {
  host?: string;
  port?: number;
  maxFrameBytes?: number;
  handshakeTimeoutMs?: number;
  /** Keep compatibility with the existing daemon, whose first frame is JSON-RPC. */
  compatibilityMode?: boolean;
}

export interface Transport {
  readonly connections: ReadonlySet<ConnectionState>;
  listen(): Promise<string>;
  send(connection: ConnectionState, message: unknown): Promise<boolean>;
  closeConnection(connection: ConnectionState): Promise<void>;
  close(): Promise<void>;
}

export interface RpcRouterContext {
  connection: ConnectionState;
}
export type RpcHandler = (params: unknown, context: RpcRouterContext) => MaybePromise<unknown>;
