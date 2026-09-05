import net from "node:net";
import { TcpNdjsonTransport } from "@sztucode/server";
import { PROTOCOL_CAPABILITIES, PROTOCOL_VERSION, type JsonRpcRequest, type JsonRpcResponse, type EventEnvelope } from "@sztucode/protocol";
import { EventBus } from "./event-bus.js";
import { RunManager } from "./run-manager.js";
import { SessionStore } from "./session-store.js";
import { WorkspaceManager } from "./workspace-manager.js";
import { GitManager } from "./git-manager.js";
import { SettingsStore } from "./settings.js";
import path from "node:path";
import { ConfigurableProvider } from "./providers/configurable.js";
import { ModelProfileStore } from "./model-profiles.js";
import { QuestionManager } from "./questions.js";
import { McpManager } from "./mcp.js";
import type { ModelProvider } from "./agent-loop.js";
import { TraceWriter, TracingProvider } from "./trace.js";
import { NOOP_TELEMETRY_CONTEXT, TraceTelemetryContext, safeStartSpan, type TelemetryContext } from "@sztucode/telemetry";
import { ExtensionRegistry } from "./extensions/registry.js";
import { loadExtensionModules } from "./extensions/loader.js";
import { ServerService, type CodingAgentServices } from "./server-service.js";
import { classifyError, dataRoot, clientId, error, requestRunId, responseRunId, matchesSubscription } from "./server-helpers.js";
import { JsonlSessionBackend } from "@sztucode/session-fs";
import { ArtifactStore } from "./artifact-store.js";
import { OperationStore } from "./operation-store.js";
import { SchedulerStore } from "./scheduler.js";

const PARSE_ERROR = -32700;
const INVALID_REQUEST = -32600;
const MAX_FRAME_BYTES = 64 * 1024 * 1024;

export class RuntimeServer {
  readonly events = new EventBus();
  readonly settings = new SettingsStore();
  readonly questions = new QuestionManager(this.events);
  readonly mcp = new McpManager();
  readonly runs: RunManager;
  readonly sessions = new SessionStore();
  readonly sessionBackend = new JsonlSessionBackend(path.join(dataRoot(), "sessions"));
  readonly artifacts = new ArtifactStore(path.join(dataRoot(), "artifacts"));
  readonly operations = new OperationStore(path.join(dataRoot(), "operations.json"));
  readonly scheduler = new SchedulerStore(path.join(dataRoot(), "scheduled-tasks.json"));
  readonly workspaces = new WorkspaceManager();
  readonly git = new GitManager(this.workspaces);
  readonly models = new ModelProfileStore(this.settings);
  readonly trace: TraceWriter | null;
  readonly telemetry: TelemetryContext;
  readonly extensions = new ExtensionRegistry();
  private readonly provider: ModelProvider;
  private readonly transport: TcpNdjsonTransport;
  private readonly clients = new Set<net.Socket>();
  private readonly handshakenClients = new Set<net.Socket>();
  private readonly subscriptions = new Map<net.Socket, { id: string; topics: string[]; scope: string }>();
  private readonly clientMessageRuns = new Map<string, string>();
  private readonly runSessions = new Map<string, string>();
  private readonly workflows = new Map<string, { controller: AbortController; status: "running" | "completed" | "cancelled" }>();
  readonly service: ServerService;
  private startedAt = Date.now();

  constructor(private readonly host = "127.0.0.1", private readonly port = 7438, provider?: ModelProvider, private readonly maxFrameBytes = MAX_FRAME_BYTES) {
    const traceEnabled = !/^(0|false|no)$/i.test(process.env.SZTU_TRACE_ENABLED ?? "true");
    this.trace = traceEnabled ? new TraceWriter(process.env.SZTU_TRACE_FILE ?? path.join(dataRoot(), "traces", "runtime-ts.jsonl")) : null;
    this.telemetry = this.trace ? new TraceTelemetryContext(this.trace, { includeAttributes: false }) : NOOP_TELEMETRY_CONTEXT;
    const baseProvider = provider ?? new ConfigurableProvider(this.settings);
    this.provider = this.trace ? new TracingProvider(baseProvider, this.trace, /^(1|true|yes)$/i.test(process.env.SZTU_TRACE_INCLUDE_LLM_PAYLOAD ?? "false"), this.telemetry) : baseProvider;
    this.runs = new RunManager(this.events, this.provider, process.cwd(), this.questions, () => this.mcp.listTools(), async () => { const settings = await this.settings.get(); return { contextWindow: settings.context_window, maxOutputTokens: settings.max_output_tokens, streaming: true }; }, this.sessions, this.extensions, this.telemetry, this.operations);
    this.service = new ServerService({ events: this.events, settings: this.settings, sessions: this.sessions, sessionBackend: this.sessionBackend, workspaces: this.workspaces, git: this.git, mcp: this.mcp, models: this.models, questions: this.questions, runs: this.runs, extensions: this.extensions, provider: this.provider, telemetry: this.telemetry, artifacts: this.artifacts, operations: this.operations, scheduler: this.scheduler } satisfies CodingAgentServices);
    this.transport = new TcpNdjsonTransport({ host, port, maxFrameBytes, compatibilityMode: true }, {
      onMessage: (connection, message) => {
        const socket = connection.socket;
        this.clients.add(socket);
        if (message && typeof message === "object" && (message as { type?: unknown }).type === "hello") {
          const version = (message as { version?: unknown }).version;
          if (version !== PROTOCOL_VERSION) {
            this.send(socket, { type: "hello_error", error: { code: -32001, message: `Unsupported protocol version ${String(version)}` } } as never);
            socket.end();
          } else {
            this.handshakenClients.add(socket);
            this.send(socket, { type: "hello", version: PROTOCOL_VERSION, server_version: "ts-0.2.0", capabilities: [...PROTOCOL_CAPABILITIES], connection_id: `${socket.remoteAddress ?? "unknown"}:${socket.remotePort ?? 0}` } as never);
          }
          return;
        }
        void this.handleLine(socket, JSON.stringify(message));
      },
      onClose: (connection) => {
        this.clients.delete(connection.socket);
        this.handshakenClients.delete(connection.socket);
        this.subscriptions.delete(connection.socket);
      },
      onError: (error) => this.trace?.emit({ ts: new Date().toISOString(), direction: "CORE", layer: "ipc", kind: "error", run_id: null, data: { message: error.message } }),
    });
    this.events.subscribe((event) => {
      this.trace?.emit({ ts: new Date().toISOString(), direction: "CORE", layer: "event", kind: "event", run_id: "run_id" in event ? event.run_id : null, data: event.type === "core.started" ? { type: event.type, listen_addr: event.listen_addr, version: event.version } : { type: event.type, session_id: "session_id" in event ? event.session_id : undefined } });
      this.broadcast({ kind: "event", event }); void this.service.persistRunEvent.call(this, event);
    });
  }

  async listen(): Promise<string> {
    // Runs live only in this daemon process. Any persisted active status therefore
    // represents an interrupted run after a restart, not work still in progress.
    await this.sessions.recoverInterruptedSessions();
    await this.mcp.load();
    const mcpStatus = this.mcp.status();
    if (mcpStatus.length) console.log(`MCP servers: ${mcpStatus.map((server) => `${server.name}=${server.connected ? `connected(${server.toolCount} tools)` : `failed(${server.error ?? "unknown"})`}`).join(", ")}`);
    const configuredExtensions = (process.env.SZTU_EXTENSIONS ?? "").split(path.delimiter).map((item) => item.trim()).filter(Boolean);
    if (configuredExtensions.length) await loadExtensionModules(this.extensions, configuredExtensions, "global", process.cwd());
    const workspaceExtensions = (process.env.SZTU_WORKSPACE_EXTENSIONS ?? "").split(path.delimiter).map((item) => item.trim()).filter(Boolean);
    if (workspaceExtensions.length) await loadExtensionModules(this.extensions, workspaceExtensions, "workspace", process.cwd());
    const settings = await this.settings.get();
    this.runs.permissions.setMode(settings.permission_mode);
    const listenAddress = await this.transport.listen();
    this.events.publish({ type: "core.started", listen_addr: listenAddress, version: "ts-0.2.0" });
    return listenAddress;
  }

  async close(): Promise<void> {
    this.runs.cancelAll();
    for (const workflow of this.workflows.values()) if (workflow.status === "running") workflow.controller.abort();
    await this.mcp.close(); await this.transport.close(); await this.extensions.unloadAll(); await this.trace?.flush();
  }

  private async handleLine(socket: net.Socket, line: string): Promise<void> {
    let raw: unknown;
    try { raw = JSON.parse(line); } catch { this.send(socket, error(null, PARSE_ERROR, "Parse error")); return; }
    if (!raw || typeof raw !== "object" || (raw as Record<string, unknown>).jsonrpc !== "2.0" || typeof (raw as Record<string, unknown>).id !== "string" || typeof (raw as Record<string, unknown>).method !== "string") {
      this.send(socket, error(null, INVALID_REQUEST, "Invalid Request")); return;
    }
    const request = raw as JsonRpcRequest;
    this.trace?.emit({ ts: new Date().toISOString(), direction: "CLIENT→CORE", layer: "ipc", kind: "command", run_id: requestRunId(request), client_id: clientId(socket), data: { method: request.method, id: request.id } });
    await safeStartSpan(this.telemetry, { name: "rpc.request", attributes: { method: request.method, client_id: clientId(socket) } }, async (span) => {
      const operationName = request.method.startsWith("session.") ? "session.operation" : request.method === "agent.run" ? "agent.run" : undefined;
      try {
        const response = operationName ? await safeStartSpan(this.telemetry, { name: operationName, attributes: { method: request.method, run_id: requestRunId(request) ?? undefined } }, () => this.dispatch(request, socket)) : await this.dispatch(request, socket);
        this.send(socket, response);
      } catch (cause) {
        span.recordError(cause);
        const classified = classifyError(cause);
        this.send(socket, error(request.id, classified.code, classified.message, classified.data));
      }
    });
  }

  private async dispatch(request: JsonRpcRequest, socket: net.Socket): Promise<JsonRpcResponse> {
    return this.service.dispatch.call(this, request, socket);
  }


  private send(socket: net.Socket, message: JsonRpcResponse | EventEnvelope): void {
    if (socket.destroyed) return;
    socket.write(`${JSON.stringify(message)}\n`);
    if ("kind" in message) {
      const event = message.event;
      this.trace?.emit({ ts: new Date().toISOString(), direction: "CORE→CLIENT", layer: "ipc", kind: "push", run_id: "run_id" in event ? event.run_id : null, client_id: clientId(socket), data: { event_type: event.type } });
      return;
    }
    this.trace?.emit({ ts: new Date().toISOString(), direction: "CORE→CLIENT", layer: "ipc", kind: "error" in message ? "error" : "response", run_id: responseRunId(message), client_id: clientId(socket), data: "error" in message ? { id: message.id, error: { code: message.error.code, message: message.error.message } } : { id: message.id, result: redactTraceValue(message.result) as Record<string, unknown> } });
  }
  private broadcast(message: EventEnvelope): void {
    for (const client of this.clients) {
      const subscription = this.subscriptions.get(client);
      if (subscription && matchesSubscription(message.event, subscription)) this.send(client, message);
    }
  }
}

const redactTraceValue = (value: unknown): unknown => {
  if (Array.isArray(value)) return value.map(redactTraceValue);
  if (!value || typeof value !== "object") return value;
  const output: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    if (/(prompt|content|message|secret|token|key|api|path|file|input|output|params)/i.test(key)) continue;
    output[key] = redactTraceValue(item);
  }
  return output;
};
