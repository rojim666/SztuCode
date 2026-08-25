import net from "node:net";
import type { JsonRpcRequest, JsonRpcResponse, AgentRunParams, PingParams, RunCancelParams, RunGetParams, RunReplayParams, PermissionRespondParams, SessionCreateParams, SessionForkParams, SessionGetParams, SessionListParams, SessionHistoryParams, SessionSendMessageParams, SessionCommand } from "@sztucode/protocol";
import { ok, error, RpcDispatchError, toSessionSummary, toProtocolSessionSnapshot, mimeType, publicSkill, matchesSubscription, probeModel, benchmarkModel, normalizeSettingsUpdate } from "./server-helpers.js";
import { SkillLoader } from "./skills.js";
import { PluginManager } from "./plugins.js";
import { ContextManager } from "./context.js";
import { SubagentManager } from "./subagent.js";
import { MarketplaceManager } from "./marketplaces.js";
import { profileProject } from "./project-profile.js";
import { activeRunChanges, revertRunChanges, runChangeDiff } from "./changes.js";
import { listCcswitchProviders } from "./ccswitch.js";
import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { AgentSession } from "./agent-session.js";
import type { EventBus } from "./event-bus.js";
import type { SettingsStore } from "./settings.js";
import type { SessionStore } from "./session-store.js";
import type { WorkspaceManager } from "./workspace-manager.js";
import type { GitManager } from "./git-manager.js";
import type { McpManager } from "./mcp.js";
import type { ModelProfileStore } from "./model-profiles.js";
import type { QuestionManager } from "./questions.js";
import type { RunManager } from "./run-manager.js";
import type { ExtensionRegistry } from "./extensions/registry.js";
import type { SessionBackend } from "@sztucode/session";
import type { TelemetryContext } from "@sztucode/telemetry";

export interface CodingAgentServices {
  readonly events: EventBus;
  readonly settings: SettingsStore;
  readonly sessions: SessionStore;
  readonly sessionBackend: SessionBackend;
  readonly workspaces: WorkspaceManager;
  readonly git: GitManager;
  readonly mcp: McpManager;
  readonly models: ModelProfileStore;
  readonly questions: QuestionManager;
  readonly runs: RunManager;
  readonly extensions: ExtensionRegistry;
  readonly provider: unknown;
  readonly telemetry?: TelemetryContext;
}
const METHOD_NOT_FOUND = -32601;
const SESSION_BUSY = -32012;
const TEXT_READ_LIMIT = 1_000_000;
const IMAGE_READ_LIMIT = 5_000_000;
export class ServerService {
  constructor(readonly services?: CodingAgentServices) {}
  async persistRunEvent(this: any, event: import("@sztucode/protocol").RuntimeEvent): Promise<void> {
    const host = resolveServiceHost(this); if (!("run_id" in event) || !host) return;
    const parentSessionId = "parent_session_id" in event && typeof event.parent_session_id === "string" ? event.parent_session_id : undefined;
    const mappedChildEvent = Boolean(parentSessionId && !host.runSessions.has(event.run_id));
    const sessionId = host.runSessions.get(event.run_id) ?? parentSessionId; if (!sessionId) return;
    if (mappedChildEvent && parentSessionId) {
      try { await host.sessions.get(parentSessionId); } catch { return; }
    }
    await host.sessions.appendRunEvent(sessionId, event as unknown as import("./session-store.js").SessionRunEvent);
    if (event.type !== "run.finished" || mappedChildEvent) return;
    await host.sessions.recordRunStats(sessionId, event.run_id, { input_tokens: event.total_input_tokens, output_tokens: event.total_output_tokens, cache_read_input_tokens: event.cache_read_input_tokens, cache_creation_input_tokens: event.cache_creation_input_tokens, elapsed_s: event.elapsed_s, context_pct: event.context_pct });
    const session = await host.sessions.get(sessionId);
    const nextStatus = session.mode === "one_shot" ? "closed" : "waiting_for_input";
    await host.sessions.setStatus(sessionId, nextStatus);
    host.events.publish({ type: nextStatus === "closed" ? "session.closed" : "session.waiting_for_input", session_id: sessionId, last_run_id: event.run_id, ts: new Date().toISOString() });
    host.runSessions.delete(event.run_id);
  }

  async createSession(this: any, params: { mode?: "chat" | "one_shot"; workspace_id?: string | null; title?: string }): Promise<AgentSession> {
    const host = resolveServiceHost(this); if (!host) throw new Error("ServerService dependencies are not configured");
    const session = await host.sessions.create(params.mode ?? "chat", params.workspace_id ?? null, params.title ?? "");
    host.events.publish({ type: "session.created", session_id: session.id, mode: session.mode, ts: new Date().toISOString() });
    return new AgentSession(host, session.id);
  }

  async openSession(this: any, sessionId: string): Promise<AgentSession> {
    const host = resolveServiceHost(this); if (!host) throw new Error("ServerService dependencies are not configured");
    await host.sessions.get(sessionId);
    return new AgentSession(host, sessionId);
  }

  async dispatch(this: any, request: JsonRpcRequest, socket: net.Socket): Promise<JsonRpcResponse> {
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
        if (command.command === "list") return ok(request.id, { command: "list", sessions: (await this.sessions.list(true)).map((session: import("./session-store.js").Session) => toProtocolSessionSnapshot(session)) });
        if (command.command === "create") {
          const session = await this.service.createSession({ mode: "chat", title: command.name ?? "" });
          return ok(request.id, { command: "create", session: await session.snapshot() });
        }
        const sessionId = command.sessionId;
        if (command.command === "attach") return ok(request.id, { command: "attach", session: await (await this.service.openSession(sessionId)).snapshot(true) });
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
          return ok(request.id, { command: "abort", session: await (await this.service.openSession(sessionId)).snapshot(true) });
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
        const params = request.params as { role?: import("@sztucode/protocol").WorkflowRole; goal?: string; workspace_id?: string; parent_run_id?: string; parent_session_id?: string };
        if (!params.goal?.trim()) throw new Error("goal is required");
        const workspaceRoot = params.workspace_id ? (await this.workspaces.get(params.workspace_id)).path : process.cwd();
        const manager = new SubagentManager(this.provider, workspaceRoot, this.events, this.runs.permissions, this.sessionBackend, undefined, this.telemetry);
        return ok(request.id, await manager.run(params.role ?? "coder", params.goal, [], String(params.parent_run_id ?? ""), { parentSessionId: typeof params.parent_session_id === "string" ? params.parent_session_id : undefined }));
      }
      case "workflow.run": {
        const params = request.params as { graph?: import("@sztucode/protocol").WorkflowGraph; workspace_id?: string; parent_run_id?: string; parent_session_id?: string };
        if (!params.graph) throw new Error("graph is required");
        const workspaceRoot = params.workspace_id ? (await this.workspaces.get(params.workspace_id)).path : process.cwd();
        const manager = new SubagentManager(this.provider, workspaceRoot, this.events, this.runs.permissions, this.sessionBackend, undefined, this.telemetry);
        const runId = randomUUID(); const controller = new AbortController(); const state = { controller, status: "running" as const }; this.workflows.set(runId, state);
        try { const result = await manager.runWorkflow({ ...params.graph, parent_session_id: typeof params.parent_session_id === "string" ? params.parent_session_id : params.graph.parent_session_id }, { runId, signal: controller.signal, parentSessionId: typeof params.parent_session_id === "string" ? params.parent_session_id : undefined, parentRunId: typeof params.parent_run_id === "string" ? params.parent_run_id : undefined }); this.workflows.set(runId, { controller, status: result.status === "cancelled" ? "cancelled" : "completed" }); return ok(request.id, result); }
        catch (error) { this.workflows.set(runId, { controller, status: controller.signal.aborted ? "cancelled" : "completed" }); throw error; }
      }
      case "session.create": {
        const params = request.params as unknown as SessionCreateParams;
        const agentSession = await this.service.createSession(params);
        const session = await agentSession.get();
        return ok(request.id, { session_id: session.id, status: session.status, session: toSessionSummary(session) });
      }
      case "session.get": {
        const params = request.params as unknown as SessionGetParams;
        return ok(request.id, { session: toSessionSummary(await (await this.service.openSession(params.session_id)).get()) });
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
        const history = modelHistory.map((message: import("./context.js").ContextMessage) => ({ ...message } as import("./agent-loop.js").ChatMessage));
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
        runId = this.runs.start(goal, history, async (messages: import("./agent-loop.js").ChatMessage[], usage: { input_tokens: number; output_tokens: number; cache_read_input_tokens: number; cache_creation_input_tokens: number }) => {
          const assistant = messages.at(-1);
          if (assistant?.role === "assistant") await this.sessions.appendMessage(params.session_id, { role: "assistant", content: assistant.content, ...(assistant.reasoning_content ? { reasoning_content: assistant.reasoning_content } : {}), run_id: runId });
        }, workspaceRoot, params.session_id, (createdRunId: string) => this.runSessions.set(createdRunId, params.session_id));
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
        const replay = params.replay_from_run ? this.events.replayRun(params.replay_from_run, 10_000).filter((event: import("@sztucode/protocol").RuntimeEvent) => matchesSubscription(event, subscription)) : [];
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

}

const resolveServiceHost = (value: any): any => value instanceof ServerService ? value.services : value;
