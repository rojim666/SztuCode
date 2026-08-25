import { randomUUID } from "node:crypto";
import { RpcRouter, isRpcRequest, INVALID_REQUEST } from "./router.js";
import { ServerError } from "./errors.js";
import { LiveSessionManager } from "./sessions.js";
import { TcpNdjsonTransport } from "./transport.js";
import type { ConnectionState, EventEnvelope, HandshakeHello, HandshakeWelcome, PiServerService, RpcRequest, TransportOptions } from "./types.js";

export interface ServerOptions extends TransportOptions {
  serverId?: string;
  /** Require a hello frame before JSON-RPC. Defaults to true for the new server package. */
  requireHandshake?: boolean;
  snapshot?: () => unknown | Promise<unknown>;
  onError?: (error: Error) => void;
}

const PROTOCOL_VERSION = 1;

/** Transport/session server. Runtime creation belongs to the injected service. */
export class Server {
  readonly id: string;
  readonly transport: TcpNdjsonTransport;
  readonly router: RpcRouter;
  readonly sessions: LiveSessionManager;
  private readonly options: ServerOptions;
  private closing = false;
  private closePromise?: Promise<void>;

  constructor(service: PiServerService, options: ServerOptions = {}) {
    this.options = options;
    this.id = options.serverId ?? randomUUID();
    this.router = new RpcRouter();
    this.transport = new TcpNdjsonTransport(options, {
      onMessage: (connection, message) => void this.receive(connection, message),
      onClose: (connection) => this.disconnect(connection),
      onError: (error) => this.reportError(error),
    });
    this.sessions = new LiveSessionManager({
      service,
      isClosing: () => this.closing,
      sendEvent: (connection, event) => this.transport.send(connection, event),
      onError: (error) => this.reportError(error),
    });
    this.registerSessionRoutes();
  }

  get address(): string | undefined { return this.transport.address; }

  register(method: string, handler: Parameters<RpcRouter["register"]>[1]): this { this.router.register(method, handler); return this; }

  async listen(): Promise<string> { return this.transport.listen(); }

  publish(event: unknown): void {
    const envelope: EventEnvelope = { kind: "event", event };
    for (const connection of this.transport.connections) {
      if (connection.stage !== "ready" || !this.matchesSubscription(connection, event)) continue;
      void this.transport.send(connection, envelope).catch((error) => this.reportError(error));
    }
  }

  async close(): Promise<void> {
    if (this.closePromise) return this.closePromise;
    this.closing = true;
    this.closePromise = (async () => {
      await this.transport.close();
      await this.sessions.close();
    })();
    return this.closePromise;
  }

  private async receive(connection: ConnectionState, value: unknown): Promise<void> {
    if (this.closing || connection.disconnected) return;
    if (!connection.handshakeComplete) {
      if (this.options.requireHandshake !== false && !this.isHello(value)) {
        await this.failHandshake(connection, "The first frame must be hello");
        return;
      }
      if (this.isHello(value)) {
        await this.handshake(connection, value);
        return;
      }
      connection.handshakeComplete = true;
      connection.stage = "ready";
    }
    if (!isRpcRequest(value)) {
      await this.transport.send(connection, { jsonrpc: "2.0", id: null, error: { code: INVALID_REQUEST, message: "Invalid Request" } });
      return;
    }
    const response = await this.router.dispatch(value, connection);
    await this.transport.send(connection, response);
  }

  private async handshake(connection: ConnectionState, hello: HandshakeHello): Promise<void> {
    connection.stage = "handshaking";
    if (hello.version !== PROTOCOL_VERSION) { await this.failHandshake(connection, `Unsupported protocol version ${hello.version}; expected ${PROTOCOL_VERSION}`); return; }
    const welcome: HandshakeWelcome = { type: "hello", version: PROTOCOL_VERSION, server_version: "server-0.1.0", capabilities: ["jsonrpc", "ndjson", "hello", "request.idempotency", "session.command", "event.subscribe"], connectionId: connection.id, connection_id: connection.id, snapshot: await this.options.snapshot?.() };
    await this.transport.send(connection, welcome);
    connection.handshakeComplete = true;
    connection.stage = "ready";
  }

  private async failHandshake(connection: ConnectionState, message: string): Promise<void> {
    await this.transport.send(connection, { type: "hello_error", error: { code: "invalid_request", message } });
    await this.transport.closeConnection(connection);
  }

  private async disconnect(connection: ConnectionState): Promise<void> {
    if (connection.sessionIds.size) await this.sessions.disconnect(connection);
    connection.subscriptions.clear();
  }

  private registerSessionRoutes(): void {
    this.register("session.command", async (params, context) => {
      if (!params || typeof params !== "object" || typeof (params as { command?: unknown }).command !== "string") throw new ServerError("invalid_request", "command is required");
      return this.sessions.execute(context.connection, params as { command: string; [key: string]: unknown });
    });
    this.register("session.list", (_params) => this.sessions.listMetadata());
    this.register("event.subscribe", (params, context) => {
      const input = params && typeof params === "object" ? params as { topics?: unknown; scope?: unknown } : {};
      const topics = Array.isArray(input.topics) ? input.topics.filter((item): item is string => typeof item === "string") : ["*"];
      context.connection.subscriptions.clear(); topics.forEach((topic) => context.connection.subscriptions.add(topic));
      return { subscribed: topics, scope: typeof input.scope === "string" ? input.scope : "global" };
    });
    this.register("event.unsubscribe", (_params, context) => { context.connection.subscriptions.clear(); return { unsubscribed: true }; });
    this.register("core.ping", (params) => ({ server_version: "server-0.1.0", received_at: new Date().toISOString(), client: params && typeof params === "object" ? (params as { client?: string }).client ?? null : null }));
    this.register("core.shutdown", () => { setTimeout(() => void this.close(), 0); return { stopping: true }; });
  }

  private matchesSubscription(connection: ConnectionState, event: unknown): boolean {
    if (!connection.subscriptions.size) return false;
    const type = event && typeof event === "object" && typeof (event as { type?: unknown }).type === "string" ? (event as { type: string }).type : "";
    return [...connection.subscriptions].some((pattern) => pattern === "*" || pattern === type || (pattern.endsWith("*") && type.startsWith(pattern.slice(0, -1))));
  }

  private isHello(value: unknown): value is HandshakeHello { return !!value && typeof value === "object" && (value as { type?: unknown }).type === "hello" && typeof (value as { version?: unknown }).version === "number"; }
  private reportError(error: unknown): void { try { this.options.onError?.(error instanceof Error ? error : new Error(String(error))); } catch { /* observer errors must not affect transport */ } }
}

export class PiServer extends Server {}

export type { ConnectionState } from "./types.js";
