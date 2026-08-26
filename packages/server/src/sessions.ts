import { randomUUID } from "node:crypto";
import { ServerError, SessionBusyError, SessionNotFoundError } from "./errors.js";
import type { ConnectionState, EventEnvelope, PiSessionRuntime, SessionMetadata, SessionService, SessionSnapshot } from "./types.js";

interface LiveSession {
  id: string;
  runtime: PiSessionRuntime;
  connections: Set<ConnectionState>;
  unsubscribe: () => void;
  operationCount: number;
  disposing?: Promise<void>;
}

export interface LiveSessionManagerOptions {
  service: SessionService;
  isClosing?: () => boolean;
  sendEvent: (connection: ConnectionState, event: EventEnvelope) => Promise<boolean>;
  onConnectionClose?: (connection: ConnectionState) => Promise<void>;
  onError?: (error: unknown) => void;
}

/** Keeps durable session runtimes alive independently from individual sockets. */
export class LiveSessionManager {
  private readonly liveSessions = new Map<string, LiveSession>();
  private readonly openingSessions = new Map<string, Promise<LiveSession>>();
  private readonly options: LiveSessionManagerOptions;

  constructor(options: LiveSessionManagerOptions) { this.options = options; }

  async listMetadata(): Promise<SessionMetadata[]> {
    const stored = await this.options.service.listSessions();
    const live = await Promise.all([...this.liveSessions.values()].filter((item) => !item.disposing).map(async (item) => [item.id, await this.snapshot(item)] as const));
    const byId = new Map(live);
    const result = stored.map((entry) => {
      const current = byId.get(entry.id);
      if (!current) return entry;
      byId.delete(entry.id);
      return { ...entry, createdAt: current.createdAt, updatedAt: current.updatedAt, sessionName: current.name, cwd: current.cwd };
    });
    for (const current of byId.values()) result.push({ id: current.id, createdAt: current.createdAt, updatedAt: current.updatedAt, sessionName: current.name, cwd: current.cwd });
    return result;
  }

  async create(connection: ConnectionState, options: Omit<Parameters<SessionService["createSession"]>[0], "id">): Promise<SessionSnapshot> {
    const id = randomUUID();
    const live = await this.acquire(id, () => this.options.service.createSession({ ...options, id }));
    await this.attach(connection, live);
    return this.forConnection(await this.broadcastSnapshot(live), connection);
  }

  async attachSession(connection: ConnectionState, sessionId: string): Promise<SessionSnapshot> {
    const live = await this.acquire(sessionId, () => this.options.service.openSession(sessionId));
    await this.attach(connection, live);
    return this.forConnection(await this.broadcastSnapshot(live), connection);
  }

  async detach(connection: ConnectionState, sessionId: string): Promise<void> {
    if (!connection.sessionIds.delete(sessionId)) return;
    const live = this.liveSessions.get(sessionId);
    if (!live) return;
    live.connections.delete(connection);
    await this.maybeDispose(live);
  }

  async execute(connection: ConnectionState, command: { command: string; sessionId?: string; [key: string]: unknown }): Promise<unknown> {
    switch (command.command) {
      case "list": return { command: "list", sessions: await this.listMetadata() };
      case "create": return { command: "create", session: await this.create(connection, command as never) };
      case "attach": return { command: "attach", session: await this.attachSession(connection, String(command.sessionId)) };
      case "detach": await this.detach(connection, String(command.sessionId)); return { command: "detach", sessionId: command.sessionId };
      case "prompt": return { command: "prompt", session: await this.operation(connection, String(command.sessionId), () => this.require(connection, String(command.sessionId)).runtime.prompt({ text: String(command.text ?? "") })) };
      case "steer": return { command: "steer", session: await this.operation(connection, String(command.sessionId), () => this.require(connection, String(command.sessionId)).runtime.steer({ text: String(command.text ?? "") })) };
      case "abort": return { command: "abort", session: await this.operation(connection, String(command.sessionId), () => this.require(connection, String(command.sessionId)).runtime.abort()) };
      case "set_model": return { command: "set_model", session: await this.operation(connection, String(command.sessionId), () => this.require(connection, String(command.sessionId)).runtime.setModel(command.model as never)) };
      case "set_thinking": return { command: "set_thinking", session: await this.operation(connection, String(command.sessionId), () => this.require(connection, String(command.sessionId)).runtime.setThinking(String(command.thinkingLevel))) };
      default: throw new ServerError("invalid_request", `Unknown session command: ${command.command}`);
    }
  }

  async disconnect(connection: ConnectionState): Promise<void> {
    const sessions = [...connection.sessionIds];
    connection.sessionIds.clear();
    for (const id of sessions) this.liveSessions.get(id)?.connections.delete(connection);
    await Promise.all(sessions.map(async (id) => {
      const live = this.liveSessions.get(id);
      if (live) await this.maybeDispose(live);
    }));
  }

  async close(): Promise<void> {
    await Promise.allSettled([...this.openingSessions.values()]);
    const sessions = [...this.liveSessions.values()];
    this.liveSessions.clear();
    await Promise.all(sessions.map(async (live) => {
      live.unsubscribe();
      await live.runtime.dispose();
    }));
  }

  private async acquire(id: string, open: () => Promise<PiSessionRuntime>): Promise<LiveSession> {
    for (;;) {
      const existing = this.liveSessions.get(id);
      if (existing) {
        if (existing.disposing) { await existing.disposing; continue; }
        return existing;
      }
      const pending = this.openingSessions.get(id);
      if (pending) return pending;
      const opening = this.createLive(id, open);
      this.openingSessions.set(id, opening);
      try { return await opening; }
      finally { if (this.openingSessions.get(id) === opening) this.openingSessions.delete(id); }
    }
  }

  private async createLive(id: string, open: () => Promise<PiSessionRuntime>): Promise<LiveSession> {
    const runtime = await open();
    try {
      const snapshot = await runtime.snapshot();
      if (snapshot.id !== id) throw new ServerError("invalid_request", `Runtime session ID changed from ${id} to ${snapshot.id}`);
      const live: LiveSession = { id, runtime, connections: new Set(), unsubscribe: () => {}, operationCount: 0 };
      live.unsubscribe = runtime.subscribe((event) => {
        if (event.type === "error") { this.options.onError?.(event.error); return; }
        if (event.type === "progress") {
          const envelope: EventEnvelope = { kind: "event", event: { type: "session_progress", sessionId: id, progress: event.progress } };
          for (const connection of live.connections) void this.options.sendEvent(connection, envelope);
        } else void this.broadcastSnapshot(live).catch((error) => this.options.onError?.(error));
      });
      this.liveSessions.set(id, live);
      return live;
    } catch (error) {
      await runtime.dispose().catch((disposeError) => this.options.onError?.(disposeError));
      throw error;
    }
  }

  private async attach(connection: ConnectionState, live: LiveSession): Promise<void> {
    if (connection.disconnected || connection.stage === "closing" || connection.stage === "closed") {
      await this.maybeDispose(live);
      throw new ServerError("invalid_request", "Connection is closed");
    }
    connection.sessionIds.add(live.id);
    live.connections.add(connection);
  }

  private require(connection: ConnectionState, id: string): LiveSession {
    if (!connection.sessionIds.has(id)) throw new ServerError("invalid_request", `Connection is not attached to session ${id}`);
    const live = this.liveSessions.get(id);
    if (!live || live.disposing) throw new SessionNotFoundError(`Session is not live: ${id}`);
    return live;
  }

  private async operation(connection: ConnectionState, id: string, action: () => Promise<void>): Promise<SessionSnapshot> {
    const live = this.require(connection, id);
    if (live.operationCount > 0) throw new SessionBusyError(`Session is busy: ${id}`);
    live.operationCount += 1;
    try { await action(); return this.forConnection(await this.broadcastSnapshot(live), connection); }
    finally { live.operationCount -= 1; void this.maybeDispose(live); }
  }

  private async snapshot(live: LiveSession): Promise<SessionSnapshot> {
    const current = await live.runtime.snapshot();
    if (current.id !== live.id) throw new ServerError("invalid_request", "Runtime session ID changed");
    return { ...current, phase: live.runtime.getPhase(), attached: live.connections.size > 0, locked: true };
  }

  private forConnection(snapshot: SessionSnapshot, connection: ConnectionState): SessionSnapshot { return { ...snapshot, attached: connection.sessionIds.has(snapshot.id) }; }

  private async broadcastSnapshot(live: LiveSession): Promise<SessionSnapshot> {
    const snapshot = await this.snapshot(live);
    const event: EventEnvelope = { kind: "event", event: { type: "session_snapshot", snapshot } };
    await Promise.all([...live.connections].map((connection) => this.options.sendEvent(connection, event)));
    return snapshot;
  }

  private async maybeDispose(live: LiveSession): Promise<void> {
    if (this.options.isClosing?.() || live.disposing || live.connections.size || live.operationCount || live.runtime.getPhase() !== "idle") return live.disposing;
    live.disposing = (async () => { try { live.unsubscribe(); await live.runtime.dispose(); } finally { this.liveSessions.delete(live.id); } })();
    await live.disposing;
  }
}

