import net from "node:net";
import { TcpNdjsonTransport } from "@sztucode/server";
import { PROTOCOL_CAPABILITIES, PROTOCOL_VERSION, type JsonRpcRequest, type JsonRpcResponse, type EventEnvelope, type AgentRunParams, type PingParams, type RunCancelParams, type RunGetParams, type RunReplayParams, type PermissionRespondParams, type SessionCreateParams, type SessionForkParams, type SessionGetParams, type SessionListParams, type SessionHistoryParams, type SessionSendMessageParams, type SessionCommand } from "@sztucode/protocol";
import { EventBus } from "./event-bus.js";
import { RunManager } from "./run-manager.js";
import { SessionStore } from "./session-store.js";
import { WorkspaceManager } from "./workspace-manager.js";
import { GitManager } from "./git-manager.js";
import { SettingsStore } from "./settings.js";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { SkillLoader } from "./skills.js";
import { PluginManager } from "./plugins.js";
import { ConfigurableProvider } from "./providers/configurable.js";
import { profileProject } from "./project-profile.js";
import { ContextManager } from "./context.js";
import { ModelProfileStore } from "./model-profiles.js";
import { QuestionManager } from "./questions.js";
import { activeRunChanges, revertRunChanges, runChangeDiff } from "./changes.js";
import { randomUUID } from "node:crypto";
import { listCcswitchProviders } from "./ccswitch.js";
import { McpManager } from "./mcp.js";
import { SubagentManager } from "./subagent.js";
import { MarketplaceManager } from "./marketplaces.js";
import type { ModelProvider } from "./agent-loop.js";
import { TraceWriter, TracingProvider } from "./trace.js";

const PARSE_ERROR = -32700;
const INVALID_REQUEST = -32600;
const METHOD_NOT_FOUND = -32601;
const INVALID_PARAMS = -32602;
const INTERNAL_ERROR = -32603;
const SESSION_BUSY = -32012;
const MAX_FRAME_BYTES = 64 * 1024 * 1024;
const TEXT_READ_LIMIT = 1_000_000;
const IMAGE_READ_LIMIT = 5_000_000;

const MIME_TYPES: Record<string, string> = {
  ".avif": "image/avif", ".bmp": "image/bmp", ".gif": "image/gif", ".ico": "image/x-icon",
  ".jpeg": "image/jpeg", ".jpg": "image/jpeg", ".png": "image/png", ".svg": "image/svg+xml", ".webp": "image/webp",
};

function mimeType(filePath: string): string | null { return MIME_TYPES[path.extname(filePath).toLowerCase()] ?? null; }
function publicSkill(skill: Awaited<ReturnType<SkillLoader["list"]>>[number]): Omit<typeof skill, "system_prompt_template" | "allowed_tools"> {
  const { system_prompt_template: _body, allowed_tools: _tools, ...summary } = skill; return summary;
}

class RpcDispatchError extends Error { constructor(readonly code: number, message: string, readonly data?: unknown) { super(message); } }

export class RuntimeServer {
  readonly events = new EventBus();
  readonly settings = new SettingsStore();
  readonly questions = new QuestionManager(this.events);
  readonly mcp = new McpManager();
  readonly runs: RunManager;
  readonly sessions = new SessionStore();
  readonly workspaces = new WorkspaceManager();
  readonly git = new GitManager(this.workspaces);
  readonly models = new ModelProfileStore(this.settings);
  readonly trace: TraceWriter | null;
  private readonly provider: ModelProvider;
  private readonly transport: TcpNdjsonTransport;
  private readonly clients = new Set<net.Socket>();
  private readonly handshakenClients = new Set<net.Socket>();
  private readonly subscriptions = new Map<net.Socket, { id: string; topics: string[]; scope: string }>();
  private readonly clientMessageRuns = new Map<string, string>();
  private readonly runSessions = new Map<string, string>();
  private readonly workflows = new Map<string, { controller: AbortController; status: "running" | "completed" | "cancelled" }>();
  private startedAt = Date.now();

  constructor(private readonly host = "127.0.0.1", private readonly port = 7438, provider?: ModelProvider, private readonly maxFrameBytes = MAX_FRAME_BYTES) {
    const traceEnabled = !/^(0|false|no)$/i.test(process.env.SZTU_TRACE_ENABLED ?? "true");
    this.trace = traceEnabled ? new TraceWriter(process.env.SZTU_TRACE_FILE ?? path.join(dataRoot(), "traces", "runtime-ts.jsonl")) : null;
    const baseProvider = provider ?? new ConfigurableProvider(this.settings);
    this.provider = this.trace ? new TracingProvider(baseProvider, this.trace, !/^(0|false|no)$/i.test(process.env.SZTU_TRACE_INCLUDE_LLM_PAYLOAD ?? "true")) : baseProvider;
    this.runs = new RunManager(this.events, this.provider, process.cwd(), this.questions, () => this.mcp.listTools(), async () => { const settings = await this.settings.get(); return { contextWindow: settings.context_window, maxOutputTokens: settings.max_output_tokens, streaming: true }; }, this.sessions);
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
      this.trace?.emit({ ts: new Date().toISOString(), direction: "CORE", layer: "event", kind: "event", run_id: "run_id" in event ? event.run_id : null, data: event as unknown as Record<string, unknown> });
      this.broadcast({ kind: "event", event }); void this.persistRunEvent(event);
    });
  }

  async listen(): Promise<string> {
    await this.mcp.load();
    const settings = await this.settings.get();
    this.runs.permissions.setMode(settings.permission_mode);
    const listenAddress = await this.transport.listen();
    this.events.publish({ type: "core.started", listen_addr: listenAddress, version: "ts-0.2.0" });
    return listenAddress;
  }

  async close(): Promise<void> {
    this.runs.cancelAll();
    for (const workflow of this.workflows.values()) if (workflow.status === "running") workflow.controller.abort();
    await this.mcp.close(); await this.transport.close(); await this.trace?.flush();
  }

  private async handleLine(socket: net.Socket, line: string): Promise<void> {
    let raw: unknown;
    try { raw = JSON.parse(line); } catch { this.send(socket, error(null, PARSE_ERROR, "Parse error")); return; }
    if (!raw || typeof raw !== "object" || (raw as Record<string, unknown>).jsonrpc !== "2.0" || typeof (raw as Record<string, unknown>).id !== "string" || typeof (raw as Record<string, unknown>).method !== "string") {
      this.send(socket, error(null, INVALID_REQUEST, "Invalid Request")); return;
    }
    const request = raw as JsonRpcRequest;
    this.trace?.emit({ ts: new Date().toISOString(), direction: "CLIENT→CORE", layer: "ipc", kind: "command", run_id: requestRunId(request), client_id: clientId(socket), data: { method: request.method, id: request.id, params: request.params } });
    try { this.send(socket, await this.dispatch(request, socket)); }
    catch (cause) {
      const classified = classifyError(cause);
      this.send(socket, error(request.id, classified.code, classified.message, classified.data));
    }
  }

  private async dispatch(request: JsonRpcRequest, socket: net.Socket): Promise<JsonRpcResponse> {
    switch (request.method) {
      case "core.ping": {
        const params = request.params as unknown as PingParams;
        if (typeof params.client !== "string") throw new Error("client is required");
        return ok(request.id, { server_version: "ts-0.2.0", uptime_ms: Date.now() - this.startedAt, received_at: new Date().toISOString(), capabilities: ["agent.run", "run.cancel", "run.get", "run.replay", "workspace.*", "session.*", "event.subscribe"] });
      }
      case "core.shutdown": {
        setTimeout(() => { void this.close(); }, 0);
        return ok(request.id, { stopping: true });
      }
      case "session.command": {
        const command = (request.params as { command?: SessionCommand }).command;
        if (!command) throw new Error("command is required");
        if (command.command === "list") return ok(request.id, { command: "list", sessions: (await this.sessions.list(true)).map((session) => toProtocolSessionSnapshot(session)) });
        if (command.command === "create") {
          const session = await this.sessions.create("chat", null, command.name ?? "");
          return ok(request.id, { command: "create", session: toProtocolSessionSnapshot(session) });
        }
        const sessionId = command.sessionId;
        if (command.command === "attach") return ok(request.id, { command: "attach", session: toProtocolSessionSnapshot(await this.sessions.get(sessionId), true) });
        if (command.command === "detach") return ok(request.id, { command: "detach", sessionId });
        if (command.command === "prompt") {
          const params = { session_id: sessionId, content: command.text };
          await this.dispatch({ ...request, method: "session.send_message", params }, socket);
          return ok(request.id, { command: "prompt", session: toProtocolSessionSnapshot(await this.sessions.get(sessionId), true) });
        }
        if (command.command === "steer") {
          const params = { session_id: sessionId, content: command.text };
          await this.dispatch({ ...request, method: "session.steer_message", params }, socket);
          return ok(request.id, { command: "steer", session: toProtocolSessionSnapshot(await this.sessions.get(sessionId), true) });
        }
        if (command.command === "abort") {
          const session = await this.sessions.get(sessionId); const runId = session.run_ids.at(-1); if (runId) this.runs.cancel(runId);
          return ok(request.id, { command: "abort", session: toProtocolSessionSnapshot(await this.sessions.get(sessionId), true) });
        }
        if (command.command === "set_model") { await this.models.select(command.model); return ok(request.id, { command: "set_model", session: toProtocolSessionSnapshot(await this.sessions.get(sessionId), true) }); }
        if (command.command === "set_thinking") { await this.settings.update({ reasoning_effort: command.thinkingLevel as never }); return ok(request.id, { command: "set_thinking", session: toProtocolSessionSnapshot(await this.sessions.get(sessionId), true) }); }
        throw new Error(`Unsupported session command: ${(command as { command: string }).command}`);
      }
      case "agent.run": {
        const params = request.params as unknown as AgentRunParams;
        if (!params.goal?.trim()) throw new Error("goal is required");
        return ok(request.id, { run_id: this.runs.start(params.goal) });
      }
      case "agent.subagent": {
        const params = request.params as { role?: import("@sztucode/protocol").WorkflowRole; goal?: string; workspace_id?: string };
        if (!params.goal?.trim()) throw new Error("goal is required");
        const workspaceRoot = params.workspace_id ? (await this.workspaces.get(params.workspace_id)).path : process.cwd();
        const manager = new SubagentManager(this.provider, workspaceRoot, this.events, this.runs.permissions);
        return ok(request.id, await manager.run(params.role ?? "coder", params.goal));
      }
      case "workflow.run": {
        const params = request.params as { graph?: import("@sztucode/protocol").WorkflowGraph; workspace_id?: string };
        if (!params.graph) throw new Error("graph is required");
        const workspaceRoot = params.workspace_id ? (await this.workspaces.get(params.workspace_id)).path : process.cwd();
        const manager = new SubagentManager(this.provider, workspaceRoot, this.events, this.runs.permissions);
        const runId = randomUUID(); const controller = new AbortController(); const state = { controller, status: "running" as const }; this.workflows.set(runId, state);
        try { const result = await manager.runWorkflow(params.graph, { runId, signal: controller.signal }); this.workflows.set(runId, { controller, status: result.status === "cancelled" ? "cancelled" : "completed" }); return ok(request.id, result); }
        catch (error) { this.workflows.set(runId, { controller, status: controller.signal.aborted ? "cancelled" : "completed" }); throw error; }
      }
      case "session.create": {
        const params = request.params as unknown as SessionCreateParams;
        const session = await this.sessions.create(params.mode ?? "chat", params.workspace_id ?? null, params.title ?? "");
        this.events.publish({ type: "session.created", session_id: session.id, mode: session.mode, ts: new Date().toISOString() });
        return ok(request.id, { session_id: session.id, status: session.status, session: toSessionSummary(session) });
      }
      case "session.get": {
        const params = request.params as unknown as SessionGetParams;
        return ok(request.id, { session: toSessionSummary(await this.sessions.get(params.session_id)) });
      }
      case "session.list": {
        const params = request.params as unknown as SessionListParams;
        return ok(request.id, { sessions: (await this.sessions.list(params.include_archived ?? false)).map(toSessionSummary), next_cursor: null });
      }
      case "session.history":
      case "session.get_history": {
        const params = request.params as unknown as SessionHistoryParams;
        const session = await this.sessions.get(params.session_id);
        return ok(request.id, { messages: await this.sessions.history(params.session_id), run_stats: session.run_stats ?? {}, context_injections: await this.sessions.contextInjections(params.session_id) });
      }
      case "session.send_message": {
        const params = request.params as unknown as SessionSendMessageParams;
        if (!params.session_id || !params.content?.trim()) throw new Error("session_id and content are required");
        if (params.client_message_id) { const existing = this.clientMessageRuns.get(`${params.session_id}:${params.client_message_id}`); if (existing) return ok(request.id, { run_id: existing, session_id: params.session_id }); }
        if (this.runs.hasActiveSession(params.session_id)) throw new RpcDispatchError(SESSION_BUSY, "session busy");
        const modelHistory = await this.sessions.modelHistory(params.session_id);
        const content = params.images?.length ? [{ type: "text", text: params.content }, ...params.images.map((image) => ({ type: "image", source: { media_type: image.media_type, data: image.data } }))] : params.content;
        await this.sessions.appendMessage(params.session_id, { role: "user", content });
        this.events.publish({ type: "session.message_received", session_id: params.session_id, content: params.content, ts: new Date().toISOString() });
        await this.sessions.setStatus(params.session_id, "active");
        const history = modelHistory.map((message) => ({ ...message } as import("./agent-loop.js").ChatMessage));
        const session = await this.sessions.get(params.session_id);
        const workspaceRoot = session.workspace_id ? (await this.workspaces.get(session.workspace_id)).path : undefined;
        let goal = params.content;
        const slash = /^\/([A-Za-z0-9_.-]+)(?:\s+([\s\S]*))?$/.exec(params.content.trim());
        let invokedSkill: { name: string; arguments: string; prompt: string } | null = null;
        if (slash) {
          const skill = (await new SkillLoader(workspaceRoot ?? process.cwd()).list()).find((item) => item.enabled && item.name === slash[1]);
          if (skill) { invokedSkill = { name: skill.name, arguments: slash[2] ?? "", prompt: skill.system_prompt_template }; history.push({ role: "system", content: skill.system_prompt_template }); goal = slash[2] ?? ""; }
        }
        let runId = "";
        runId = this.runs.start(goal, history, async (messages, usage) => {
          const assistant = messages.at(-1);
          if (assistant?.role === "assistant") await this.sessions.appendMessage(params.session_id, { role: "assistant", content: assistant.content, ...(assistant.reasoning_content ? { reasoning_content: assistant.reasoning_content } : {}), run_id: runId });
        }, workspaceRoot, params.session_id, (createdRunId) => this.runSessions.set(createdRunId, params.session_id));
        if (params.client_message_id) this.clientMessageRuns.set(`${params.session_id}:${params.client_message_id}`, runId);
        await this.sessions.attachRun(params.session_id, runId);
        if (invokedSkill) this.events.publish({ type: "skill.invoked", skill_name: invokedSkill.name, arguments: invokedSkill.arguments, run_id: runId, ts: new Date().toISOString() });
        return ok(request.id, { run_id: runId, session_id: params.session_id });
      }
      case "workspace.list": return ok(request.id, { workspaces: await this.workspaces.list() });
      case "workspace.open": { const params = request.params as { path?: string }; if (!params.path) throw new Error("path is required"); return ok(request.id, { workspace: await this.workspaces.open(params.path) }); }
      case "workspace.archive": { const params = request.params as { workspace_id: string }; return ok(request.id, { workspace: await this.workspaces.archive(params.workspace_id) }); }
      case "workspace.resume": { const params = request.params as { workspace_id: string }; return ok(request.id, { workspace: await this.workspaces.resume(params.workspace_id) }); }
      case "workspace.delete": { const params = request.params as { workspace_id: string; confirm?: string }; if (params.confirm !== "delete") throw new Error("confirm=delete is required"); await this.workspaces.delete(params.workspace_id); return ok(request.id, { deleted: true }); }
      case "workspace.status": { const params = request.params as { workspace_id: string }; return ok(request.id, { workspace: await this.workspaces.get(params.workspace_id), ...(await this.workspaces.status(params.workspace_id)) }); }
      case "workspace.profile": { const params = request.params as { workspace_id: string }; const workspace = await this.workspaces.get(params.workspace_id); return ok(request.id, { profile: await profileProject(workspace.path) }); }
      case "workspace.tree": { const params = request.params as { workspace_id: string; path?: string; max_depth?: number; max_entries?: number }; return ok(request.id, { nodes: await this.workspaces.tree(params.workspace_id, params.path, params.max_depth, params.max_entries) }); }
      case "file.search": { const params = request.params as { workspace_id: string; query: string; max_results?: number }; return ok(request.id, { matches: await this.workspaces.search(params.workspace_id, params.query, params.max_results) }); }
      case "file.read": {
        const params = request.params as { workspace_id: string; path: string }; const workspace = await this.workspaces.get(params.workspace_id); const target = path.resolve(workspace.path, params.path); const relative = path.relative(workspace.path, target); if (relative.startsWith("..") || path.isAbsolute(relative)) throw new Error("path escapes workspace");
        const fileMimeType = mimeType(target); const image = fileMimeType?.startsWith("image/") ?? false; const readLimit = image ? IMAGE_READ_LIMIT : TEXT_READ_LIMIT; const file = await readFile(target); const bytes = file.subarray(0, readLimit); const binary = bytes.subarray(0, 8192).includes(0); const previewableImage = binary && image && file.length <= IMAGE_READ_LIMIT;
        return ok(request.id, { content: binary ? "" : bytes.toString("utf8"), encoding: "UTF-8", binary, truncated: file.length > readLimit, media_base64: previewableImage ? bytes.toString("base64") : null, mime_type: previewableImage ? fileMimeType : null });
      }
      case "change.list": { const params = request.params as { workspace_id: string; run_id?: string | null }; const workspace = await this.workspaces.get(params.workspace_id); return ok(request.id, { changes: params.run_id ? await activeRunChanges(params.run_id, workspace.path) : await this.git.list(params.workspace_id) }); }
      case "change.diff": { const params = request.params as { workspace_id: string; path?: string | null; run_id?: string | null }; if (params.run_id && params.path) { const workspace = await this.workspaces.get(params.workspace_id); const snapshotDiff = await runChangeDiff(params.run_id, workspace.path, params.path); if (snapshotDiff !== null) return ok(request.id, { diff: snapshotDiff }); } return ok(request.id, { diff: await this.git.diff(params.workspace_id, params.path) }); }
      case "change.stage": { const params = request.params as { workspace_id: string; paths: string[] }; return ok(request.id, { staged_paths: await this.git.stage(params.workspace_id, params.paths) }); }
      case "change.unstage": { const params = request.params as { workspace_id: string; paths: string[] }; return ok(request.id, { unstaged_paths: await this.git.unstage(params.workspace_id, params.paths) }); }
      case "change.discard": { const params = request.params as { workspace_id: string; paths: string[]; confirm?: string }; if (params.confirm !== "discard") throw new Error("confirm=discard is required"); return ok(request.id, { discarded_paths: await this.git.discard(params.workspace_id, params.paths) }); }
      case "git.commit": { const params = request.params as { workspace_id: string; message: string }; if (!params.message?.trim()) throw new Error("message is required"); return ok(request.id, { commit_hash: await this.git.commit(params.workspace_id, params.message.trim()) }); }
      case "git.history": { const params = request.params as { workspace_id: string; limit?: number; skip?: number }; return ok(request.id, await this.git.history(params.workspace_id, params.limit, params.skip)); }
      case "settings.get": return ok(request.id, { settings: await this.settings.get() });
      case "settings.update": {
        const previous = await this.settings.getProviderConfig();
        const { update, updated } = normalizeSettingsUpdate(request.params as Record<string, unknown>, previous);
        const settings = await this.settings.update(update);
        if (settings.permission_mode !== previous.permission_mode) {
          this.runs.permissions.setMode(settings.permission_mode);
        }
        return ok(request.id, { settings, updated });
      }
      case "permission.set_mode": {
        const params = request.params as { mode: import("@sztucode/protocol").PermissionMode };
        this.runs.permissions.setMode(params.mode);
        const settings = await this.settings.update({ permission_mode: params.mode });
        return ok(request.id, { ok: true, mode: settings.permission_mode });
      }
      case "provider.status": { const settings = await this.settings.get(); const config = await this.settings.getProviderConfig(); const keyConfigured = Boolean(config.keyless || config.api_key || (settings.provider === "openai" ? process.env.OPENAI_API_KEY || process.env.DEEPSEEK_API_KEY : process.env.ANTHROPIC_API_KEY)); const skills = (await new SkillLoader(process.cwd()).list()).map(publicSkill); return ok(request.id, { provider: settings.provider, api_format: settings.api_format, model: settings.model, api_key_configured: keyConfigured, ready_for_next_run: keyConfigured && Boolean(settings.model), skills, mcp_servers: this.mcp.statuses() }); }
      case "skill.list": { const params = request.params as { workspace_id?: string | null }; const root = params.workspace_id ? (await this.workspaces.get(params.workspace_id)).path : process.cwd(); const skills = await new SkillLoader(root).list(); return ok(request.id, { skills: skills.map(publicSkill) }); }
      case "skill.set_enabled": { const params = request.params as { skill_id: string; enabled: boolean; workspace_id?: string | null }; const root = params.workspace_id ? (await this.workspaces.get(params.workspace_id)).path : process.cwd(); const { system_prompt_template: _body, allowed_tools: _tools, ...skill } = await new SkillLoader(root).setEnabled(params.skill_id, params.enabled); return ok(request.id, { skill }); }
      case "skill.install": { const params = request.params as { source_path: string; scope: "personal" | "workspace"; workspace_id?: string | null }; const root = params.workspace_id ? (await this.workspaces.get(params.workspace_id)).path : process.cwd(); const { system_prompt_template: _body, allowed_tools: _tools, ...skill } = await new SkillLoader(root).install(params.source_path, params.scope); return ok(request.id, { skill }); }
      case "plugin.list": { const params = request.params as { workspace_id?: string | null }; const root = params.workspace_id ? (await this.workspaces.get(params.workspace_id)).path : process.cwd(); return ok(request.id, { plugins: await new PluginManager(root).list() }); }
      case "plugin.install": { const params = request.params as { source_path: string; scope: "personal" | "workspace"; workspace_id?: string | null }; const root = params.workspace_id ? (await this.workspaces.get(params.workspace_id)).path : process.cwd(); return ok(request.id, { plugin: await new PluginManager(root).install(params.source_path, params.scope) }); }
      case "plugin.set_enabled": { const params = request.params as { plugin_id: string; enabled: boolean; workspace_id?: string | null }; const root = params.workspace_id ? (await this.workspaces.get(params.workspace_id)).path : process.cwd(); return ok(request.id, { plugin: await new PluginManager(root).setEnabled(params.plugin_id, params.enabled) }); }
      case "plugin.uninstall": { const params = request.params as { plugin_id: string; workspace_id?: string | null; confirm?: string }; if (params.confirm !== "uninstall") throw new Error("confirm=uninstall is required"); const root = params.workspace_id ? (await this.workspaces.get(params.workspace_id)).path : process.cwd(); await new PluginManager(root).uninstall(params.plugin_id); return ok(request.id, { plugin_id: params.plugin_id, uninstalled: true }); }
      case "plugin.catalog": { const params = request.params as { workspace_id?: string | null }; const root = params.workspace_id ? (await this.workspaces.get(params.workspace_id)).path : process.cwd(); return ok(request.id, { ...(await new MarketplaceManager(root).list()), supported: true }); }
      case "plugin.marketplace_add": { const params = request.params as { source: string; git_ref?: string; sparse_paths?: string[]; workspace_id?: string | null }; const root = params.workspace_id ? (await this.workspaces.get(params.workspace_id)).path : process.cwd(); return ok(request.id, { marketplace: await new MarketplaceManager(root).add(params.source, params.git_ref || "", params.sparse_paths || []) }); }
      case "plugin.marketplace_refresh": { const params = request.params as { marketplace_id?: string | null; workspace_id?: string | null }; const root = params.workspace_id ? (await this.workspaces.get(params.workspace_id)).path : process.cwd(); return ok(request.id, { marketplaces: await new MarketplaceManager(root).refresh(params.marketplace_id || undefined) }); }
      case "plugin.marketplace_remove": { const params = request.params as { marketplace_id: string; workspace_id?: string | null; confirm?: string }; if (params.confirm !== "remove") throw new Error("confirm=remove is required"); const root = params.workspace_id ? (await this.workspaces.get(params.workspace_id)).path : process.cwd(); await new MarketplaceManager(root).remove(params.marketplace_id); return ok(request.id, { marketplace_id: params.marketplace_id, removed: true }); }
      case "plugin.catalog_install": { const params = request.params as { catalog_plugin_id: string; scope: "personal" | "workspace"; workspace_id?: string | null }; const root = params.workspace_id ? (await this.workspaces.get(params.workspace_id)).path : process.cwd(); const marketplace = new MarketplaceManager(root); const materialized = await marketplace.materialize(params.catalog_plugin_id); try { return ok(request.id, { plugin: await new PluginManager(root).install(materialized.path, params.scope) }); } finally { await marketplace.cleanupMaterialized(materialized.temporary_root); } }
      case "question.pending": { const params = request.params as { session_id?: string | null }; return ok(request.id, { pending: this.questions.list(params.session_id) }); }
      case "question.respond": { const params = request.params as { rpc_id: string; session_id: string; answers: unknown[] }; const accepted = this.questions.respond(params.rpc_id, params.session_id, params.answers); if (!accepted) throw new Error("unknown or mismatched question request"); return ok(request.id, { ok: true }); }
      case "provider.model_list": return ok(request.id, { models: await this.models.list() });
      case "provider.model_save": return ok(request.id, await this.models.save(request.params as never));
      case "provider.model_select": { const params = request.params as { model_id: string }; const settings = await this.models.select(params.model_id); return ok(request.id, { settings, models: await this.models.list() }); }
      case "provider.model_delete": { const params = request.params as { model_id: string }; return ok(request.id, { models: await this.models.delete(params.model_id) }); }
      case "provider.model_test": return ok(request.id, await probeModel(request.params as Record<string, unknown>));
      case "provider.model_benchmark": return ok(request.id, await benchmarkModel(request.params as Record<string, unknown>));
      case "provider.ccswitch_list": { const providers = await listCcswitchProviders(); return ok(request.id, { providers: providers.map(({ api_key: _secret, ...provider }) => provider) }); }
      case "provider.ccswitch_apply": { const params = request.params as { provider_id: string }; const provider = (await listCcswitchProviders()).find((item) => item.id === params.provider_id); if (!provider) throw new Error(`cc-switch provider not found: ${params.provider_id}`); const saved = await this.models.save({ id: `ccswitch-${provider.id}`, name: provider.name, vendor: "cc-switch", provider: "anthropic", api_format: "anthropic_messages", model: provider.model, base_url: provider.base_url, api_key: provider.api_key }); return ok(request.id, { settings: saved.settings, updated: ["provider", "model", "base_url"] }); }
      case "change.revert": {
        const params = request.params as { workspace_id: string; run_id: string; paths: string[]; confirm?: string };
        if (params.confirm !== "revert") throw new Error("confirm=revert is required");
        const workspace = await this.workspaces.get(params.workspace_id);
        return ok(request.id, await revertRunChanges(params.run_id, workspace.path, params.paths));
      }
      case "event.subscribe": {
        const params = request.params as { topics?: string[]; scope?: string; replay_from_run?: string | null };
        const topics = Array.isArray(params.topics) && params.topics.length ? params.topics.filter((topic) => typeof topic === "string") : ["*"];
        const scope = typeof params.scope === "string" ? params.scope : "global";
        if (scope !== "global" && !scope.startsWith("run:")) throw new Error("scope must be global or run:<run_id>");
        const subscription = { id: `sub-${randomUUID().slice(0, 8)}`, topics, scope };
        this.subscriptions.set(socket, subscription);
        const replay = params.replay_from_run ? this.events.replayRun(params.replay_from_run, 10_000).filter((event) => matchesSubscription(event, subscription)) : [];
        for (const event of replay) this.send(socket, { kind: "event", event });
        return ok(request.id, { subscription_id: subscription.id, replayed_count: replay.length });
      }
      case "run.cancel": {
        const params = request.params as unknown as RunCancelParams;
        const status = this.runs.cancel(params.run_id);
        if (status === "cancelling") return ok(request.id, { run_id: params.run_id, status });
        const workflow = this.workflows.get(params.run_id);
        if (!workflow || workflow.status !== "running") return ok(request.id, { run_id: params.run_id, status: "not_running" });
        workflow.status = "cancelled"; workflow.controller.abort();
        return ok(request.id, { run_id: params.run_id, status: "cancelling" });
      }
      case "run.get": {
        const params = request.params as unknown as RunGetParams;
        const workflow = this.workflows.get(params.run_id);
        return ok(request.id, workflow ? { run_id: params.run_id, status: workflow.status } : this.runs.get(params.run_id));
      }
      case "run.replay": {
        const params = request.params as unknown as RunReplayParams;
        return ok(request.id, { run_id: params.run_id, events: this.events.replayRun(params.run_id, params.max_events) });
      }
      case "permission.respond": {
        const params = request.params as unknown as PermissionRespondParams;
        const permissionId = params.permission_id ?? (request.params as Record<string, unknown>).tool_use_id;
        if (typeof permissionId !== "string") throw new Error("tool_use_id is required");
        const accepted = this.runs.permissions.respond(permissionId, params.decision);
        return ok(request.id, { accepted, ok: accepted });
      }
      case "session.rename": { const params = request.params as { session_id: string; title: string }; return ok(request.id, { session: toSessionSummary(await this.sessions.rename(params.session_id, params.title)) }); }
      case "session.fork": { const params = request.params as unknown as SessionForkParams; if (this.runs.hasActiveSession(params.session_id)) throw new RpcDispatchError(SESSION_BUSY, "session busy"); const forked = await this.sessions.fork(params.session_id, params.title ?? ""); this.events.publish({ type: "session.created", session_id: forked.id, mode: forked.mode, ts: new Date().toISOString() }); return ok(request.id, { session: toSessionSummary(forked) }); }
      case "session.archive": { const params = request.params as { session_id: string }; if (this.runs.hasActiveSession(params.session_id)) throw new RpcDispatchError(SESSION_BUSY, "session busy"); return ok(request.id, { session: toSessionSummary(await this.sessions.setArchived(params.session_id, true)) }); }
      case "session.resume": { const params = request.params as { session_id: string }; if (this.runs.hasActiveSession(params.session_id)) throw new RpcDispatchError(SESSION_BUSY, "session busy"); return ok(request.id, { session: toSessionSummary(await this.sessions.setArchived(params.session_id, false)) }); }
      // Pinning only changes session metadata, so it remains available while a
      // run is active. Archive/close/delete keep their active-run guard.
      case "session.pin": { const params = request.params as { session_id: string; pinned: boolean }; return ok(request.id, { session: toSessionSummary(await this.sessions.setPinned(params.session_id, params.pinned)) }); }
      case "session.close": { const params = request.params as { session_id: string }; if (this.runs.hasActiveSession(params.session_id)) throw new RpcDispatchError(SESSION_BUSY, "session busy"); return ok(request.id, { status: (await this.sessions.close(params.session_id)).status }); }
      case "session.delete": { const params = request.params as { session_id: string }; if (this.runs.hasActiveSession(params.session_id)) throw new RpcDispatchError(SESSION_BUSY, "session busy"); await this.sessions.delete(params.session_id); return ok(request.id, { session_id: params.session_id, deleted: true }); }
      case "session.compact": {
        const params = request.params as { session_id: string; focus?: string };
        const settings = await this.settings.get(); const history = await this.sessions.modelHistory(params.session_id); const context = new ContextManager(history, { maxTokens: settings.context_window, reservedOutputTokens: settings.max_output_tokens, maxToolResultChars: 8_000 });
        this.events.publish({ type: "context.compacting", session_id: params.session_id, run_id: "", ts: new Date().toISOString() });
        const before = context.tokenEstimate(); const result = await context.compactWithProvider(this.provider, params.focus ?? "", 8); const after = context.tokenEstimate();
        if (result.removedMessages > 0) {
          const compactedAt = new Date().toISOString();
          const persisted = context.messages.filter((message): message is typeof message & { role: "user" | "assistant" } => message.role === "user" || message.role === "assistant").map((message) => ({ role: message.role, content: message.content, ts: compactedAt }));
          await this.sessions.replaceHistory(params.session_id, persisted);
          await this.sessions.replaceModelHistory(params.session_id, context.messages);
          if (result.summaryText) await this.sessions.writeSummary(params.session_id, result.summaryText);
        }
        this.events.publish({ type: "context.compacted", session_id: params.session_id, run_id: "", original_tokens: before, summary_tokens: after, ts: new Date().toISOString() });
        return ok(request.id, { summary_tokens: after, saved_tokens: Math.max(0, before - after), removed_messages: result.removedMessages, used_model: result.usedModel });
      }
      case "session.steer_message": { const params = request.params as unknown as import("@sztucode/protocol").SessionSteerMessageParams; if (!params.session_id || !params.content?.trim()) throw new Error("session_id and content are required"); const content = params.images?.length ? [{ type: "text", text: params.content }, ...params.images.map((image) => ({ type: "image", source: { media_type: image.media_type, data: image.data } }))] : params.content; await this.sessions.appendMessage(params.session_id, { role: "user", content }); const runId = this.runs.steer(params.session_id, { role: "user", content }); this.events.publish({ type: "session.message_steered", session_id: params.session_id, run_id: runId, content: params.content, ts: new Date().toISOString() }); return ok(request.id, { run_id: runId, status: "accepted" }); }
      default: return error(request.id, METHOD_NOT_FOUND, `Method not found: ${request.method}`);
    }
  }

  private send(socket: net.Socket, message: JsonRpcResponse | EventEnvelope): void {
    if (socket.destroyed) return;
    socket.write(`${JSON.stringify(message)}\n`);
    if ("kind" in message) {
      const event = message.event;
      this.trace?.emit({ ts: new Date().toISOString(), direction: "CORE→CLIENT", layer: "ipc", kind: "push", run_id: "run_id" in event ? event.run_id : null, client_id: clientId(socket), data: { event_type: event.type } });
      return;
    }
    this.trace?.emit({ ts: new Date().toISOString(), direction: "CORE→CLIENT", layer: "ipc", kind: "error" in message ? "error" : "response", run_id: responseRunId(message), client_id: clientId(socket), data: message as unknown as Record<string, unknown> });
  }
  private async persistRunEvent(event: import("@sztucode/protocol").RuntimeEvent): Promise<void> {
    if (!("run_id" in event)) return;
    const sessionId = this.runSessions.get(event.run_id); if (!sessionId) return;
    await this.sessions.appendRunEvent(sessionId, event as unknown as import("./session-store.js").SessionRunEvent);
    if (event.type !== "run.finished") return;
    await this.sessions.recordRunStats(sessionId, event.run_id, { input_tokens: event.total_input_tokens, output_tokens: event.total_output_tokens, cache_read_input_tokens: event.cache_read_input_tokens, cache_creation_input_tokens: event.cache_creation_input_tokens, elapsed_s: event.elapsed_s, context_pct: event.context_pct });
    const session = await this.sessions.get(sessionId);
    const nextStatus = session.mode === "one_shot" ? "closed" : "waiting_for_input";
    await this.sessions.setStatus(sessionId, nextStatus);
    this.events.publish({ type: nextStatus === "closed" ? "session.closed" : "session.waiting_for_input", session_id: sessionId, last_run_id: event.run_id, ts: new Date().toISOString() });
    this.runSessions.delete(event.run_id);
  }
  private broadcast(message: EventEnvelope): void {
    for (const client of this.clients) {
      const subscription = this.subscriptions.get(client);
      if (subscription && matchesSubscription(message.event, subscription)) this.send(client, message);
    }
  }
}

const ok = <T>(id: string, result: T): JsonRpcResponse<T> => ({ jsonrpc: "2.0", id, result });
const error = (id: string | null, code: number, message: string, data?: unknown): JsonRpcResponse => ({ jsonrpc: "2.0", id, error: { code, message, ...(data === undefined ? {} : { data }) } });
const classifyError = (cause: unknown): { code: number; message: string; data?: unknown } => {
  if (cause instanceof RpcDispatchError) return cause;
  const message = cause instanceof Error ? cause.message : String(cause);
  if (/session busy|steer unavailable/i.test(message)) return { code: SESSION_BUSY, message };
  if (/not found|unknown (session|workspace|plugin|skill|model)/i.test(message) || (cause as NodeJS.ErrnoException | null)?.code === "ENOENT") return { code: -32004, message };
  if (/required|invalid|escapes|must be|confirm=|cannot be|cannot delete|unknown model profile|archived session/i.test(message)) return { code: INVALID_PARAMS, message };
  return { code: INTERNAL_ERROR, message };
};
const toSessionSummary = (session: import("./session-store.js").Session) => { const stats = Object.values(session.run_stats ?? {}); return { session_id: session.id, title: session.title, mode: session.mode, status: session.status, updated_at: session.updated_at, run_count: session.run_ids.length, archived: session.archived, pinned: session.pinned, workspace_id: session.workspace_id, latest_run_id: session.run_ids.at(-1) ?? null, total_input_tokens: stats.reduce((sum, item) => sum + item.input_tokens, 0), total_output_tokens: stats.reduce((sum, item) => sum + item.output_tokens, 0), total_elapsed_s: stats.reduce((sum, item) => sum + item.elapsed_s, 0) }; };
const toProtocolSessionSnapshot = (session: import("./session-store.js").Session, attached = false) => ({ session_id: session.id, mode: session.mode, status: session.status, title: session.title, created_at: session.created_at, updated_at: session.updated_at, run_count: session.run_ids.length, archived: session.archived, pinned: session.pinned, workspace_id: session.workspace_id, latest_run_id: session.run_ids.at(-1) ?? null, attached, locked: attached });

const topicMatches = (type: string, pattern: string): boolean => pattern === "*" || pattern === type || pattern.endsWith("*") && type.startsWith(pattern.slice(0, -1));
const matchesSubscription = (event: import("@sztucode/protocol").RuntimeEvent, subscription: { topics: string[]; scope: string }): boolean => {
  if (!subscription.topics.some((topic) => topicMatches(event.type, topic))) return false;
  if (subscription.scope === "global") return true;
  return "run_id" in event && event.run_id === subscription.scope.slice(4);
};

const dataRoot = (): string => process.env.SZTU_DATA_DIR ?? path.join(process.env.USERPROFILE ?? process.env.HOME ?? process.cwd(), ".sztu");
const clientId = (socket: net.Socket): string => `${socket.remoteAddress ?? "unknown"}:${socket.remotePort ?? 0}`;
const requestRunId = (request: JsonRpcRequest): string | null => typeof request.params?.run_id === "string" ? request.params.run_id : null;
const responseRunId = (response: JsonRpcResponse): string | null => "result" in response && response.result && typeof response.result === "object" && typeof (response.result as { run_id?: unknown }).run_id === "string" ? (response.result as { run_id: string }).run_id : null;

type SettingsUpdateKey = keyof import("./settings.js").RuntimeSettings | "api_key";
type StoredSettingsUpdate = Partial<import("./settings.js").RuntimeSettings> & { api_key?: string; keyless?: boolean };
const SETTINGS_UPDATE_KEYS: SettingsUpdateKey[] = ["provider", "api_format", "model", "base_url", "api_key", "max_output_tokens", "temperature", "top_p", "reasoning_effort", "timeout_s", "max_retries", "context_window", "cache_control", "permission_mode"];

function normalizeSettingsUpdate(input: Record<string, unknown>, current: Awaited<ReturnType<SettingsStore["getProviderConfig"]>>): { update: StoredSettingsUpdate; updated: SettingsUpdateKey[] } {
  const update: StoredSettingsUpdate = {}; const updated: SettingsUpdateKey[] = []; const next = { ...current };
  for (const key of SETTINGS_UPDATE_KEYS) {
    const value = input[key];
    if (value === undefined || value === null) continue;
    validateSetting(key, value);
  }
  if (typeof input.provider === "string" && input.provider !== next.provider) {
    next.provider = input.provider as typeof next.provider; next.api_format = next.provider === "anthropic" ? "anthropic_messages" : "openai_chat_completions";
    update.provider = next.provider; update.api_format = next.api_format; update.keyless = false; updated.push("provider");
  }
  if (typeof input.api_format === "string" && input.api_format !== next.api_format) {
    next.api_format = input.api_format as typeof next.api_format; next.provider = next.api_format === "anthropic_messages" ? "anthropic" : "openai";
    update.api_format = next.api_format; update.provider = next.provider; updated.push("api_format");
  }
  const remaining: SettingsUpdateKey[] = ["model", "base_url", "api_key", "max_output_tokens", "temperature", "top_p", "reasoning_effort", "timeout_s", "max_retries", "context_window", "cache_control", "permission_mode"];
  for (const key of remaining) {
    const value = input[key];
    if (value === undefined || value === null || value === next[key]) continue;
    (next as Record<string, unknown>)[key] = value; (update as Record<string, unknown>)[key] = value; updated.push(key);
  }
  if (updated.some((key) => key === "model" || key === "base_url")) update.keyless = false;
  return { update, updated };
}

function validateSetting(key: SettingsUpdateKey, value: unknown): void {
  const oneOf = (values: readonly unknown[]) => { if (!values.includes(value)) throw new Error(`${key} must be one of: ${values.join(", ")}`); };
  const text = (min: number, max: number) => { if (typeof value !== "string" || value.length < min || value.length > max) throw new Error(`${key} must be a string with length ${min}..${max}`); };
  const number = (min: number, max: number, integer = false, exclusiveMin = false) => {
    const validRange = typeof value === "number" && (exclusiveMin ? value > min : value >= min) && value <= max;
    if (!validRange || !Number.isFinite(value) || integer && !Number.isInteger(value)) throw new Error(`${key} must be ${integer ? "an integer" : "a number"} in range ${exclusiveMin ? "(" : "["}${min}, ${max}]`);
  };
  if (key === "provider") oneOf(["anthropic", "openai"]);
  else if (key === "api_format") oneOf(["openai_chat_completions", "anthropic_messages", "openai_responses"]);
  else if (key === "permission_mode") oneOf(["normal", "accept_edits", "plan", "auto"]);
  else if (key === "reasoning_effort") oneOf(["", "low", "medium", "high", "xhigh", "max"]);
  else if (key === "model") text(1, 200);
  else if (key === "base_url") text(0, 2_000);
  else if (key === "api_key") text(1, 4_000);
  else if (key === "max_output_tokens") number(1, 128_000, true);
  else if (key === "temperature" || key === "top_p") number(0, 1);
  else if (key === "timeout_s") number(0, 600, false, true);
  else if (key === "max_retries") number(0, 10, true);
  else if (key === "context_window") number(0, 10_000_000, true);
  else if (key === "cache_control" && typeof value !== "boolean") throw new Error("cache_control must be a boolean");
}

async function probeModel(input: Record<string, unknown>): Promise<Record<string, unknown>> {
  const started = Date.now(); const apiFormat = String(input.api_format ?? (input.provider === "anthropic" ? "anthropic_messages" : "openai_chat_completions")); const model = String(input.model ?? "").trim();
  if (!model) return { success: false, api_format: apiFormat, model, elapsed_ms: Date.now() - started, input_tokens: 0, output_tokens: 0, error: "model is required" };
  const base = String(input.base_url ?? "").replace(/\/$/, "") || (apiFormat === "anthropic_messages" ? "https://api.anthropic.com/v1" : "https://api.openai.com/v1");
  const headers: Record<string, string> = { "content-type": "application/json" }; const apiKey = typeof input.api_key === "string" ? input.api_key : "";
  if (input.keyless !== true && apiKey) { if (apiFormat === "anthropic_messages") { headers["x-api-key"] = apiKey; headers["anthropic-version"] = "2023-06-01"; } else headers.authorization = `Bearer ${apiKey}`; }
  const url = `${base}/${apiFormat === "anthropic_messages" ? "messages" : apiFormat === "openai_responses" ? "responses" : "chat/completions"}`;
  const body = apiFormat === "anthropic_messages" ? { model, max_tokens: 1, messages: [{ role: "user", content: "Reply OK." }] } : apiFormat === "openai_responses" ? { model, input: "Reply OK.", max_output_tokens: 1 } : { model, messages: [{ role: "user", content: "Reply OK." }], max_completion_tokens: 1 };
  const controller = new AbortController(); const timeout = setTimeout(() => controller.abort(), Math.min(300, Math.max(1, Number(input.timeout_s ?? 30))) * 1000);
  try {
    const response = await fetch(url, { method: "POST", headers, body: JSON.stringify(body), signal: controller.signal });
    if (!response.ok) throw new Error(`Model request failed (${response.status}): ${(await response.text()).slice(0, 500)}`);
    const payload = await response.json() as { usage?: Record<string, unknown> }; const usage = payload.usage ?? {};
    return { success: true, api_format: apiFormat, model, elapsed_ms: Date.now() - started, input_tokens: Number(usage.input_tokens ?? usage.prompt_tokens ?? 0), output_tokens: Number(usage.output_tokens ?? usage.completion_tokens ?? 0), error: null };
  } catch (cause) {
    return { success: false, api_format: apiFormat, model, elapsed_ms: Date.now() - started, input_tokens: 0, output_tokens: 0, error: cause instanceof Error ? cause.message : String(cause) };
  } finally { clearTimeout(timeout); }
}

async function benchmarkModel(input: Record<string, unknown>): Promise<Record<string, unknown>> {
  const samples = Math.min(10, Math.max(1, Number(input.samples ?? 3) || 3));
  const results = await Promise.all(Array.from({ length: samples }, () => probeModel(input)));
  const successful = results.filter((item) => item.success);
  const elapsed = successful.map((item) => Number(item.elapsed_ms || 0)).sort((a, b) => a - b);
  const percentile = (p: number) => elapsed.length ? elapsed[Math.min(elapsed.length - 1, Math.ceil(elapsed.length * p) - 1)] : 0;
  return { api_format: results[0]?.api_format ?? input.api_format ?? "", model: results[0]?.model ?? input.model ?? "", samples, successful: successful.length, failed: results.length - successful.length, min_ms: elapsed[0] ?? 0, median_ms: percentile(0.5), p95_ms: percentile(0.95), max_ms: elapsed.at(-1) ?? 0, average_ttft_ms: elapsed.length ? elapsed.reduce((sum, value) => sum + value, 0) / elapsed.length : 0, errors: results.filter((item) => !item.success).map((item) => item.error).filter(Boolean) };
}
