import type { AssistantMessage, Model, StreamFn, ThinkingLevel } from "@sztucode/ai";
import { Agent, type AgentEvent, type AgentMessage, type AgentTool, type PromptInput } from "@sztucode/agent-core";
import { projectModelContext, type ForkOptions, type NewSessionEntry, type SessionBackend, type SessionEntry, type SessionSnapshot as DomainSessionSnapshot } from "@sztucode/session";
import type { RuntimeEvent } from "@sztucode/protocol";
import type { RunManager } from "./run-manager.js";
import type { Session, SessionStore } from "./session-store.js";
import { AgentLoop, type ChatMessage, type ModelProvider } from "./agent-loop.js";
import type { ToolContext, ToolRegistry as LegacyToolRegistry } from "./tools.js";
import type { PermissionGate as LegacyPermissionGate } from "./permissions.js";
import type { EventBus } from "./event-bus.js";

export interface AgentSessionHost {
  readonly sessions: SessionStore;
  readonly runs: RunManager;
  readonly events: { publish(event: RuntimeEvent): void };
}

export interface ModelRuntime {
  readonly model: Model;
  readonly stream: StreamFn;
  readonly thinkingLevel?: ThinkingLevel;
}

export interface SessionManager {
  load(sessionId: string): Promise<DomainSessionSnapshot>;
  append(sessionId: string, entry: NewSessionEntry): Promise<SessionEntry>;
  fork(sessionId: string, options?: ForkOptions): Promise<DomainSessionSnapshot>;
}

export interface ToolRegistry { list(): AgentTool[]; }

export interface PermissionGate {
  check(context: { tool: AgentTool; args: unknown; permission?: string; signal: AbortSignal }): boolean | Promise<boolean>;
}

export interface ContextCompaction {
  compact(messages: readonly AgentMessage[], options: { focus?: string; signal: AbortSignal }): Promise<{
    messages: AgentMessage[];
    summary: string;
    retainedMessages?: AgentMessage[];
    tokensBefore?: number;
    details?: unknown;
  }>;
}

export interface ResourceLoader { loadSystemPrompt?(context: { sessionId: string }): string | Promise<string>; }
export interface ExtensionRunner { onEvent?(event: AgentEvent, context: { sessionId: string }): void | Promise<void>; }

export interface LegacyAgentSessionOptions {
  id: string;
  backend: SessionBackend;
  provider: ModelProvider;
  tools: LegacyToolRegistry;
  context: ToolContext;
  events: EventBus;
  permissions: LegacyPermissionGate;
  runId: string;
  maxSteps?: number;
  workspaceRoot?: string;
  sessionId?: string;
  parentSessionId?: string;
  extensions?: import("./extensions/registry.js").ExtensionRegistry;
}

interface LegacySessionRuntime {
  prompt(input: PromptInput): Promise<void>;
  abort(): Promise<"cancelling" | "not_running">;
  subscribe(listener: (event: import("@sztucode/protocol").RuntimeEvent) => void): () => void;
  dispose(): void;
  waitForIdle(): Promise<void>;
  getTokens(): number;
  getText(): string;
}

export interface AgentSessionOptions {
  id: string;
  backend: SessionBackend;
  sessionManager?: SessionManager;
  modelRuntime: ModelRuntime;
  tools?: ToolRegistry | AgentTool[];
  permissionGate?: PermissionGate;
  contextCompaction?: ContextCompaction;
  resourceLoader?: ResourceLoader;
  extensions?: ExtensionRunner;
  thinkingLevel?: ThinkingLevel;
  systemPrompt?: string;
}

/** Transport-free coding-agent session. The legacy `(host, id)` constructor remains supported. */
export class AgentSession {
  readonly id: string;
  private readonly legacyHost?: AgentSessionHost;
  private readonly backend?: SessionBackend;
  private readonly manager?: SessionManager;
  private readonly compaction?: ContextCompaction;
  private readonly extensions?: ExtensionRunner;
  private readonly permissionGate?: PermissionGate;
  private readonly resourceLoader?: ResourceLoader;
  private readonly configuredTools?: ToolRegistry | AgentTool[];
  private readonly agent?: Agent;
  private readonly legacyRuntime?: LegacySessionRuntime;
  private disposed = false;
  private unsubscribeAgent?: () => void;

  constructor(host: AgentSessionHost, id: string);
  constructor(options: AgentSessionOptions, agent: Agent);
  constructor(options: LegacyAgentSessionOptions, runtime: LegacySessionRuntime, mode: "legacy");
  constructor(first: AgentSessionHost | AgentSessionOptions | LegacyAgentSessionOptions, second: string | Agent | LegacySessionRuntime, mode?: "legacy") {
    if (typeof second === "string") { this.legacyHost = first as AgentSessionHost; this.id = second; return; }
    if (mode === "legacy") {
      const options = first as LegacyAgentSessionOptions;
      this.id = options.id; this.backend = options.backend; this.manager = createSessionManager(options.backend); this.legacyRuntime = second as LegacySessionRuntime;
      return;
    }
    const options = first as AgentSessionOptions;
    this.id = options.id; this.backend = options.backend; this.compaction = options.contextCompaction; this.extensions = options.extensions; this.permissionGate = options.permissionGate; this.resourceLoader = options.resourceLoader; this.configuredTools = options.tools;
    this.manager = options.sessionManager ?? createSessionManager(options.backend); this.agent = second as Agent;
    this.unsubscribeAgent = this.agent.subscribe((event) => this.handleAgentEvent(event));
  }

  static async open(options: AgentSessionOptions): Promise<AgentSession> {
    const manager = options.sessionManager ?? createSessionManager(options.backend);
    const snapshot = await manager.load(options.id);
    const systemPrompt = options.systemPrompt ?? await options.resourceLoader?.loadSystemPrompt?.({ sessionId: options.id }) ?? "";
    const tools: AgentTool[] = Array.isArray(options.tools) ? options.tools : options.tools?.list() ?? [];
    const agent = new Agent({
      model: options.modelRuntime.model,
      thinkingLevel: options.thinkingLevel ?? options.modelRuntime.thinkingLevel,
      streamFn: options.modelRuntime.stream,
      systemPrompt,
      messages: projectModelContext(snapshot) as AgentMessage[],
      tools,
      checkToolPermission: options.permissionGate ? (context) => options.permissionGate!.check(context) : undefined,
    });
    return new AgentSession({ ...options, sessionManager: manager }, agent);
  }

  /** Creates a SessionRuntime around the legacy provider/tool pipeline. AgentLoop construction stays inside AgentSession. */
  static async openLegacy(options: LegacyAgentSessionOptions): Promise<AgentSession> {
    await options.backend.get(options.id);
    const runtime = new LegacySessionRuntimeImpl(options);
    return new AgentSession(options, runtime, "legacy");
  }

  get state() { this.requireModern(); return this.agent!.state; }
  get agentCore(): Agent { this.requireModern(); return this.agent!; }
  async prompt(input: PromptInput | PromptInput[]): Promise<void> {
    if (this.legacyRuntime) { if (Array.isArray(input)) { for (const item of input) await this.legacyRuntime.prompt(item); } else await this.legacyRuntime.prompt(input); return; }
    this.requireModern(); await this.agent!.prompt(input);
  }
  steer(input: PromptInput): void { this.requireModern(); this.agent!.steer(input); }
  followUp(input: PromptInput): void { this.requireModern(); this.agent!.followUp(input); }
  async abort(): Promise<"cancelling" | "not_running" | void> {
    if (this.legacyHost) { const session = await this.legacyHost.sessions.get(this.id); const runId = session.run_ids.at(-1); return runId ? this.legacyHost.runs.cancel(runId) : "not_running"; }
    if (this.legacyRuntime) return this.legacyRuntime.abort();
    this.requireModern(); this.agent!.abort(); return undefined;
  }
  async compact(focus = ""): Promise<{ summary: string; removedMessages: number }> {
    this.requireModern(); if (!this.compaction) throw new Error("Context compaction is not configured");
    const before = this.agent!.state.messages.length;
    const result = await this.compaction.compact(this.agent!.state.messages, { focus, signal: this.agent!.signal ?? new AbortController().signal });
    this.agent!.replaceMessages(result.messages);
    await this.manager!.append(this.id, { type: "compaction", summary: result.summary, retainedMessages: result.retainedMessages ?? result.messages, tokensBefore: result.tokensBefore, details: result.details });
    return { summary: result.summary, removedMessages: Math.max(0, before - result.messages.length) };
  }
  async fork(options: ForkOptions = {}): Promise<AgentSession> {
    this.requireModern(); const snapshot = await this.manager!.fork(this.id, options); return AgentSession.open({ ...this.modernOptions(), id: snapshot.header.id });
  }
  async snapshot(attached = false): Promise<SessionSnapshot | DomainSessionSnapshot> {
    if (this.legacyHost) { const session = await this.legacyHost.sessions.get(this.id); return legacySnapshot(session, attached); }
    this.requireModern(); return this.backend!.get(this.id);
  }
  subscribe(listener: ((event: AgentEvent) => void | Promise<void>) | ((event: RuntimeEvent) => void)): () => void {
    if (this.legacyHost) return () => undefined;
    if (this.legacyRuntime) return this.legacyRuntime.subscribe(listener as (event: RuntimeEvent) => void);
    this.requireModern(); return this.agent!.subscribe(listener as (event: AgentEvent, signal: AbortSignal) => void | Promise<void>);
  }
  dispose(): void { if (this.disposed) return; this.disposed = true; this.unsubscribeAgent?.(); this.legacyRuntime?.dispose(); if (this.agent?.state.isStreaming) this.agent.abort(); }
  detach(): void { this.dispose(); }

  async get(): Promise<Session | DomainSessionSnapshot> { if (this.legacyHost) return this.legacyHost.sessions.get(this.id); this.requireModern(); return this.backend!.get(this.id); }
  async history(): Promise<Awaited<ReturnType<SessionStore["history"]>> | SessionEntry[]> { if (this.legacyHost) return this.legacyHost.sessions.history(this.id); this.requireModern(); return this.backend!.history(this.id); }
  setModel(model: Model): void { this.requireModern(); this.agent!.setModel(model); }
  setThinkingLevel(level: ThinkingLevel): void { this.requireModern(); this.agent!.setThinkingLevel(level); }
  waitForIdle(): Promise<void> { if (this.legacyRuntime) return this.legacyRuntime.waitForIdle(); this.requireModern(); return this.agent!.waitForIdle(); }
  get usageTokens(): number { return this.legacyRuntime?.getTokens() ?? 0; }
  get outputText(): string { return this.legacyRuntime?.getText() ?? ""; }

  private async handleAgentEvent(event: AgentEvent): Promise<void> {
    if (this.disposed) return;
    if (event.type === "message_end") await this.manager!.append(this.id, { type: "message", message: toModelMessage(event.message) });
    await this.extensions?.onEvent?.(event, { sessionId: this.id });
  }
  private modernOptions(): AgentSessionOptions {
    return { id: this.id, backend: this.backend!, sessionManager: this.manager, modelRuntime: { model: this.agent!.state.model, stream: this.agent!.options.streamFn, thinkingLevel: this.agent!.state.thinkingLevel }, tools: this.configuredTools ?? this.agent!.state.tools, permissionGate: this.permissionGate, resourceLoader: this.resourceLoader, systemPrompt: this.agent!.state.systemPrompt, contextCompaction: this.compaction, extensions: this.extensions };
  }
  private requireModern(): void { if ((!this.agent && !this.legacyRuntime) || !this.backend || !this.manager) throw new Error("This AgentSession is not configured"); if (this.disposed) throw new Error("AgentSession has been disposed"); }
}

class LegacySessionRuntimeImpl implements LegacySessionRuntime {
  private readonly listeners = new Set<(event: import("@sztucode/protocol").RuntimeEvent) => void>();
  private readonly unsubscribeEvents: () => void;
  private readonly loop: AgentLoop;
  private active?: Promise<void>;
  private controller?: AbortController;
  private tokens = 0;
  private text = "";
  private disposed = false;

  constructor(private readonly options: LegacyAgentSessionOptions) {
    this.loop = new AgentLoop(options.provider, options.tools, options.context, options.events, options.permissions, { sessionId: options.sessionId ?? options.id, workspaceRoot: options.workspaceRoot, extensions: options.extensions });
    this.unsubscribeEvents = options.events.subscribe((event) => {
      if (!("run_id" in event) || event.run_id !== options.runId) return;
      for (const listener of this.listeners) { try { listener(event); } catch { /* session observers are isolated */ } }
    });
  }

  async prompt(input: PromptInput): Promise<void> {
    if (this.disposed) throw new Error("SessionRuntime has been disposed");
    if (this.active) throw new Error("SessionRuntime is busy");
    const text = typeof input === "string" ? input : String(input.content ?? "");
    this.controller = new AbortController();
    const signal = this.controller.signal;
    this.active = (async () => {
      const snapshot = await this.options.backend.get(this.options.id);
      const history = projectModelContext(snapshot) as ChatMessage[];
      await this.options.backend.append(this.options.id, { type: "message", message: { role: "user", content: text } });
      const result = await this.loop.run(this.options.runId, text, this.options.maxSteps ?? 20, history, signal);
      this.tokens = result.usage.input_tokens + result.usage.output_tokens;
      this.text = result.text;
      const assistant = result.messages.at(-1);
      if (assistant?.role === "assistant") await this.options.backend.append(this.options.id, { type: "message", message: { role: "assistant", content: assistant.content, ...(assistant.reasoning_content ? { reasoning_content: assistant.reasoning_content } : {}) } });
    })().finally(() => { this.active = undefined; this.controller = undefined; });
    await this.active;
  }

  async abort(): Promise<"cancelling" | "not_running"> {
    if (!this.active) return "not_running";
    this.controller?.abort(new Error("SessionRuntime aborted"));
    this.options.events.publish({ type: "run.finished", run_id: this.options.runId, status: "cancelled", reason: "cancelled", steps: 0, total_input_tokens: 0, total_output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0, elapsed_s: 0, context_pct: 0, ...(this.options.parentSessionId ? { parent_session_id: this.options.parentSessionId } : {}), ts: new Date().toISOString() });
    return "cancelling";
  }

  subscribe(listener: (event: import("@sztucode/protocol").RuntimeEvent) => void): () => void { this.listeners.add(listener); return () => this.listeners.delete(listener); }
  dispose(): void { if (this.disposed) return; this.disposed = true; this.unsubscribeEvents(); }
  waitForIdle(): Promise<void> { return this.active ?? Promise.resolve(); }
  getTokens(): number { return this.tokens; }
  getText(): string { return this.text; }
}

function createSessionManager(backend: SessionBackend): SessionManager { return { load: (id) => backend.get(id), append: (id, entry) => backend.append(id, entry), fork: (id, options) => backend.fork(id, options) }; }

function toModelMessage(message: AgentMessage | AssistantMessage): AgentMessage {
  if (message.role === "assistant" && "text" in message) return { role: "assistant", content: message.text || message.thinkingBlocks || "", ...(message.toolCalls?.length ? { tool_calls: message.toolCalls } : {}), ...(message.reasoningContent ? { reasoning_content: message.reasoningContent } : {}) };
  return { ...message } as AgentMessage;
}

function legacySnapshot(session: Session, attached: boolean): SessionSnapshot { return { session_id: session.id, mode: session.mode, status: session.status, title: session.title, created_at: session.created_at, updated_at: session.updated_at, run_count: session.run_ids.length, archived: session.archived, pinned: session.pinned, workspace_id: session.workspace_id, latest_run_id: session.run_ids.at(-1) ?? null, attached, locked: attached }; }

export type SessionSnapshot = { session_id: string; mode: Session["mode"]; status: Session["status"]; title: string; created_at: string; updated_at: string; run_count: number; archived: boolean; pinned: boolean; workspace_id: string | null; latest_run_id: string | null; attached: boolean; locked: boolean };
