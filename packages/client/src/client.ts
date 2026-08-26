import {
  PROTOCOL_CAPABILITIES, PROTOCOL_VERSION, type ClientHello, type EventEnvelope, type EventSubscribeResult,
  type IdempotencyKey, type JsonRpcResponse, type RequestId, type RuntimeEvent, type ServerHello,
  type SessionCommand, type SessionCommandCreate, type SessionCommandResult, type SessionMetadata, type SessionSnapshot,
} from "@sztucode/protocol";
import { ClientClosedError, ClientDisconnectedError, ClientProtocolError, ClientRequestError, ClientTimeoutError } from "./errors.js";
import type { ClientTransport, ClientTransportFactory } from "./transport.js";
import type { ConnectionState, ConnectionStateChange, DaemonClientOptions, EventListener, EventSubscriptionOptions, RequestOptions, Unsubscribe } from "./types.js";

interface Pending<T> { method: string; resolve: (value: T) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout>; }

/** Typed JSON-RPC client. It only talks to daemon endpoints and never owns tools/models. */
export class DaemonClient {
  private readonly options: DaemonClientOptions;
  private readonly listeners = new Set<EventListener>();
  private readonly stateListeners = new Set<(change: ConnectionStateChange) => void>();
  private pending = new Map<string, Pending<unknown>>();
  private transport?: ClientTransport;
  private buffer = "";
  private connection: ConnectionState = "disconnected";
  private disposed = false;
  private sequence = 0;
  private connectPromise?: Promise<ServerHello>;
  private handshakeTimer?: ReturnType<typeof setTimeout>;
  private hello?: ServerHello;
  private eventSequence = 0;

  constructor(options: DaemonClientOptions) { this.options = options; }

  static async connect(options: DaemonClientOptions): Promise<DaemonClient> { const client = new DaemonClient(options); await client.connect(); return client; }
  get connected(): boolean { return this.connection === "connected"; }
  get connectionState(): ConnectionState { return this.connection; }
  get serverHello(): ServerHello | undefined { return this.hello; }

  async connect(): Promise<ServerHello> {
    if (this.disposed) throw new ClientClosedError();
    if (this.connected && this.hello) return this.hello;
    if (this.connectPromise) return this.connectPromise;
    this.connectPromise = this.open();
    try { return await this.connectPromise; } finally { this.connectPromise = undefined; }
  }

  async reconnect(): Promise<ServerHello> {
    if (this.disposed) throw new ClientClosedError();
    if (this.connection !== "disconnected") await this.disconnect(new ClientDisconnectedError("Reconnecting"));
    return this.connect();
  }

  async close(): Promise<void> {
    if (this.disposed) return;
    this.disposed = true;
    this.clearHandshakeTimer();
    const error = new ClientClosedError();
    this.rejectPending(error);
    const transport = this.transport; this.transport = undefined;
    this.setConnection("closed", error);
    await transport?.close();
  }

  async disconnect(reason: Error | string = "Daemon connection is closed"): Promise<void> {
    const error = reason instanceof Error ? reason : new ClientDisconnectedError(reason);
    this.clearHandshakeTimer();
    this.rejectPending(error);
    const transport = this.transport; this.transport = undefined;
    if (this.connection !== "closed") this.setConnection("disconnected", error);
    await transport?.close();
  }

  onEvent(listener: EventListener): Unsubscribe { this.listeners.add(listener); return () => this.listeners.delete(listener); }
  onConnectionStateChange(listener: (change: ConnectionStateChange) => void): Unsubscribe { this.stateListeners.add(listener); return () => this.stateListeners.delete(listener); }
  subscribeEvents(options: EventSubscriptionOptions, listener: EventListener): Promise<Unsubscribe>;
  subscribeEvents(options?: EventSubscriptionOptions): Promise<EventSubscribeResult>;
  subscribeEvents(options: EventSubscriptionOptions = {}, listener?: EventListener): Promise<EventSubscribeResult | Unsubscribe> {
    if (listener) {
      this.listeners.add(listener);
      return this.request<EventSubscribeResult>("event.subscribe", options).then((): Unsubscribe => () => { this.listeners.delete(listener); }) as Promise<Unsubscribe>;
    }
    return this.request<EventSubscribeResult>("event.subscribe", options);
  }

  ping(options?: RequestOptions): Promise<unknown> { return this.request("core.ping", { client: this.options.clientName ?? "@sztucode/client" }, options); }

  async listSessions(options?: RequestOptions): Promise<SessionMetadata[]> {
    const result = await this.sessionCommand({ command: "list" }, options);
    return (result as { sessions: SessionMetadata[] }).sessions.map((item) => normalizeMetadata(item));
  }
  async createSession(options: Omit<SessionCommandCreate, "command"> = {}, requestOptions?: RequestOptions): Promise<SessionSnapshot> { return this.sessionResult({ command: "create", ...options }, requestOptions); }
  async attachSession(sessionId: string, options?: RequestOptions): Promise<SessionSnapshot> { return this.sessionResult({ command: "attach", sessionId }, options); }
  async detachSession(sessionId: string, options?: RequestOptions): Promise<void> { await this.sessionCommand({ command: "detach", sessionId }, options); }
  async prompt(sessionId: string, text: string, options?: RequestOptions): Promise<SessionSnapshot> { return this.sessionResult({ command: "prompt", sessionId, text }, options); }
  async steer(sessionId: string, text: string, options?: RequestOptions): Promise<SessionSnapshot> { return this.sessionResult({ command: "steer", sessionId, text }, options); }
  async abort(sessionId: string, options?: RequestOptions): Promise<SessionSnapshot> { return this.sessionResult({ command: "abort", sessionId }, options); }
  async setModel(sessionId: string, model: string, options?: RequestOptions): Promise<SessionSnapshot> { return this.sessionResult({ command: "set_model", sessionId, model }, options); }
  async setThinking(sessionId: string, thinkingLevel: string, options?: RequestOptions): Promise<SessionSnapshot> { return this.sessionResult({ command: "set_thinking", sessionId, thinkingLevel }, options); }

  private async sessionResult(command: SessionCommand, options?: RequestOptions): Promise<SessionSnapshot> {
    const result = await this.sessionCommand(command, options) as SessionCommandResult;
    if (!("session" in result)) throw new ClientProtocolError(`Session command ${command.command} returned no session`, result);
    return normalizeSnapshot(result.session);
  }
  private sessionCommand(command: SessionCommand, options?: RequestOptions): Promise<SessionCommandResult> { return this.request("session.command", { command }, options); }

  private async open(): Promise<ServerHello> {
    this.buffer = ""; this.setConnection("connecting");
    const factory: ClientTransportFactory = this.options.transportFactory;
    let resolve!: (hello: ServerHello) => void; let reject!: (error: Error) => void;
    const handshake = new Promise<ServerHello>((res, rej) => { resolve = res; reject = rej; });
    this.handshakeResolve = resolve;
    this.handshakeReject = reject;
    const fail = (error: Error) => { this.clearHandshakeTimer(); reject(error); void this.disconnect(error); };
    try {
      const transport = await factory({ onData: (chunk) => this.receive(chunk), onClose: () => fail(new ClientDisconnectedError()), onError: (error) => fail(new ClientDisconnectedError(error.message)) });
      if (this.disposed) { await transport.close(); throw new ClientClosedError(); }
      this.transport = transport;
      const hello: ClientHello = { type: "hello", version: PROTOCOL_VERSION, client: this.options.clientName, capabilities: this.options.capabilities ?? [...PROTOCOL_CAPABILITIES] };
      const timeout = this.options.handshakeTimeoutMs ?? this.options.requestTimeoutMs ?? 10_000;
      this.handshakeTimer = setTimeout(() => fail(new ClientTimeoutError("handshake", "hello", timeout)), timeout);
      this.handshakeTimer.unref?.();
      await transport.send(encode(hello));
    } catch (error) { fail(error instanceof Error ? error : new Error(String(error))); }
    try { const serverHello = await handshake; this.hello = serverHello; this.setConnection("connected"); return serverHello; }
    catch (error) { throw error instanceof Error ? error : new Error(String(error)); }
  }

  private request<T>(method: string, params: Record<string, unknown>, options: RequestOptions = {}): Promise<T> {
    if (this.disposed) return Promise.reject(new ClientClosedError());
    if (!this.connected || !this.transport) return Promise.reject(new ClientDisconnectedError());
    const id = options.requestId ?? `request-${++this.sequence}`;
    const timeout = options.timeoutMs ?? this.options.requestTimeoutMs ?? 20_000;
    const payload = { jsonrpc: "2.0", id, method, params, ...(options.idempotencyKey === undefined ? {} : { idempotency_key: options.idempotencyKey }) };
    let resolve!: (value: T) => void; let reject!: (error: Error) => void;
    const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej; });
    const timer = setTimeout(() => { const entry = this.pending.get(id); if (!entry) return; this.pending.delete(id); reject(new ClientTimeoutError(id, method, timeout)); }, timeout);
    this.pending.set(id, { method, resolve: resolve as (value: unknown) => void, reject, timer });
    try { void Promise.resolve(this.transport.send(encode(payload))).catch((error: unknown) => this.rejectOne(id, error instanceof Error ? error : new Error(String(error)))); }
    catch (error) { this.rejectOne(id, error instanceof Error ? error : new Error(String(error))); }
    return promise;
  }

  private receive(chunk: Uint8Array | string): void {
    this.buffer += typeof chunk === "string" ? chunk : new TextDecoder().decode(chunk);
    let newline = this.buffer.indexOf("\n");
    while (newline >= 0) {
      const line = this.buffer.slice(0, newline).replace(/\r$/, ""); this.buffer = this.buffer.slice(newline + 1); newline = this.buffer.indexOf("\n");
      if (!line) continue;
      let message: unknown; try { message = JSON.parse(line); } catch (error) { this.protocolFailure(new ClientProtocolError("Invalid JSON from daemon", error)); continue; }
      this.handleMessage(message);
    }
  }

  private handleMessage(message: unknown): void {
    if (isHello(message)) { this.clearHandshakeTimer(); this.hello = message; this.resolveHandshake(message); return; }
    if (isHelloError(message)) { this.protocolFailure(new ClientRequestError(message.error)); return; }
    if (isEvent(message)) { this.eventSequence += 1; for (const listener of this.listeners) try { listener(message.event); } catch (error) { this.options.onListenerError?.(error instanceof Error ? error : new Error(String(error))); } return; }
    if (!isResponse(message)) { this.protocolFailure(new ClientProtocolError("Invalid daemon protocol message", message)); return; }
    if (message.id === null) { this.protocolFailure(new ClientProtocolError("Response id must not be null", message)); return; }
    const pending = this.pending.get(message.id);
    if (!pending) { this.protocolFailure(new ClientProtocolError(`Unknown response id ${message.id}`, message)); return; }
    this.pending.delete(message.id); clearTimeout(pending.timer);
    if ("error" in message) pending.reject(new ClientRequestError(message.error)); else pending.resolve(message.result as never);
  }

  private handshakeResolve?: (hello: ServerHello) => void;
  private handshakeReject?: (error: Error) => void;
  private resolveHandshake(hello: ServerHello): void { this.handshakeResolve?.(hello); this.handshakeResolve = undefined; this.handshakeReject = undefined; }
  private protocolFailure(error: Error): void { this.handshakeReject?.(error); this.handshakeReject = undefined; this.handshakeResolve = undefined; void this.disconnect(error); }
  private rejectOne(id: string, error: Error): void { const pending = this.pending.get(id); if (!pending) return; this.pending.delete(id); clearTimeout(pending.timer); pending.reject(error); }
  private rejectPending(error: Error): void { for (const [id, pending] of this.pending) { clearTimeout(pending.timer); pending.reject(error); this.pending.delete(id); } }
  private clearHandshakeTimer(): void { if (this.handshakeTimer) clearTimeout(this.handshakeTimer); this.handshakeTimer = undefined; }
  private setConnection(state: ConnectionState, error?: Error): void { this.connection = state; for (const listener of this.stateListeners) try { listener({ state, ...(error ? { error } : {}) }); } catch (listenerError) { this.options.onListenerError?.(listenerError instanceof Error ? listenerError : new Error(String(listenerError))); } }
}

function encode(value: unknown): Uint8Array { return new TextEncoder().encode(`${JSON.stringify(value)}\n`); }
function isHello(value: unknown): value is ServerHello { return !!value && typeof value === "object" && (value as { type?: unknown }).type === "hello" && (value as { version?: unknown }).version === PROTOCOL_VERSION && typeof (value as { server_version?: unknown }).server_version === "string" && Array.isArray((value as { capabilities?: unknown }).capabilities); }
function isHelloError(value: unknown): value is { type: "hello_error"; error: { code: number; message: string; data?: unknown } } { return !!value && typeof value === "object" && (value as { type?: unknown }).type === "hello_error" && Boolean((value as { error?: unknown }).error); }
function isEvent(value: unknown): value is EventEnvelope { return !!value && typeof value === "object" && (value as { kind?: unknown }).kind === "event" && Boolean((value as { event?: unknown }).event); }
function isResponse(value: unknown): value is JsonRpcResponse { return !!value && typeof value === "object" && (value as { jsonrpc?: unknown }).jsonrpc === "2.0" && typeof (value as { id?: unknown }).id === "string" && ("result" in value || "error" in value); }
function normalizeSnapshot(value: SessionSnapshot | Record<string, unknown>): SessionSnapshot {
  const raw = value as Record<string, unknown>; const id = String(raw.session_id ?? raw.id);
  return { session_id: id, mode: raw.mode === "one_shot" ? "one_shot" : "chat", status: (raw.status as SessionSnapshot["status"]) ?? "active", title: String(raw.title ?? raw.name ?? ""), created_at: raw.created_at as string | undefined ?? String(raw.createdAt ?? new Date().toISOString()), updated_at: String(raw.updated_at ?? raw.updatedAt ?? new Date().toISOString()), run_count: Number(raw.run_count ?? 0), archived: Boolean(raw.archived), pinned: Boolean(raw.pinned), workspace_id: (raw.workspace_id as string | null | undefined) ?? null, latest_run_id: (raw.latest_run_id as string | null | undefined) ?? null, attached: raw.attached as boolean | undefined, locked: raw.locked as boolean | undefined, phase: raw.phase as SessionSnapshot["phase"] | undefined };
}
function normalizeMetadata(value: SessionMetadata | Record<string, unknown>): SessionMetadata { const raw = value as Record<string, unknown>; return { session_id: String(raw.session_id ?? raw.id), title: String(raw.title ?? raw.sessionName ?? ""), mode: raw.mode as SessionMetadata["mode"], status: raw.status as SessionMetadata["status"], updated_at: raw.updated_at as string ?? raw.updatedAt as string, archived: raw.archived as boolean, workspace_id: raw.workspace_id as string | null | undefined }; }
