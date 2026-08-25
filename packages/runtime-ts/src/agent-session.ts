import type { AssistantMessage, Model, StreamFn, ThinkingLevel } from "@sztucode/ai";
import { Agent, type AgentEvent, type AgentMessage, type AgentTool, type PromptInput } from "@sztucode/agent-core";
import { projectModelContext, type ForkOptions, type NewSessionEntry, type SessionBackend, type SessionEntry, type SessionSnapshot as DomainSessionSnapshot } from "@sztucode/session";
import type { RuntimeEvent } from "@sztucode/protocol";
import type { RunManager } from "./run-manager.js";
import type { Session, SessionStore } from "./session-store.js";

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
  private disposed = false;
  private unsubscribeAgent?: () => void;

  constructor(host: AgentSessionHost, id: string);
  constructor(options: AgentSessionOptions, agent: Agent);
  constructor(first: AgentSessionHost | AgentSessionOptions, second: string | Agent) {
    if (typeof second === "string") { this.legacyHost = first as AgentSessionHost; this.id = second; return; }
    const options = first as AgentSessionOptions;
    this.id = options.id; this.backend = options.backend; this.compaction = options.contextCompaction; this.extensions = options.extensions; this.permissionGate = options.permissionGate; this.resourceLoader = options.resourceLoader; this.configuredTools = options.tools;
    this.manager = options.sessionManager ?? createSessionManager(options.backend); this.agent = second;
    this.unsubscribeAgent = this.agent.subscribe((event) => this.handleAgentEvent(event));
  }

  static async open(options: AgentSessionOptions): Promise<AgentSession> {
    const manager = options.sessionManager ?? createSessionManager(options.backend);
    const snapshot = await manager.load(options.id);
    const systemPrompt = options.systemPrompt ?? await options.resourceLoader?.loadSystemPrompt?.({ sessionId: options.id }) ?? "";
    const tools = Array.isArray(options.tools) ? options.tools : options.tools?.list() ?? [];
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

  get state() { this.requireModern(); return this.agent!.state; }
  get agentCore(): Agent { this.requireModern(); return this.agent!; }
  async prompt(input: PromptInput | PromptInput[]): Promise<void> { this.requireModern(); await this.agent!.prompt(input); }
  steer(input: PromptInput): void { this.requireModern(); this.agent!.steer(input); }
  followUp(input: PromptInput): void { this.requireModern(); this.agent!.followUp(input); }
  async abort(): Promise<"cancelling" | "not_running" | void> {
    if (this.legacyHost) { const session = await this.legacyHost.sessions.get(this.id); const runId = session.run_ids.at(-1); return runId ? this.legacyHost.runs.cancel(runId) : "not_running"; }
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
    this.requireModern(); return this.agent!.subscribe(listener as (event: AgentEvent, signal: AbortSignal) => void | Promise<void>);
  }
  dispose(): void { if (this.disposed) return; this.disposed = true; this.unsubscribeAgent?.(); if (this.agent?.state.isStreaming) this.agent.abort(); }
  detach(): void { this.dispose(); }

  async get(): Promise<Session | DomainSessionSnapshot> { if (this.legacyHost) return this.legacyHost.sessions.get(this.id); this.requireModern(); return this.backend!.get(this.id); }
  async history(): Promise<Awaited<ReturnType<SessionStore["history"]>> | SessionEntry[]> { if (this.legacyHost) return this.legacyHost.sessions.history(this.id); this.requireModern(); return this.backend!.history(this.id); }
  setModel(model: Model): void { this.requireModern(); this.agent!.setModel(model); }
  setThinkingLevel(level: ThinkingLevel): void { this.requireModern(); this.agent!.setThinkingLevel(level); }
  waitForIdle(): Promise<void> { this.requireModern(); return this.agent!.waitForIdle(); }

  private async handleAgentEvent(event: AgentEvent): Promise<void> {
    if (this.disposed) return;
    if (event.type === "message_end") await this.manager!.append(this.id, { type: "message", message: toModelMessage(event.message) });
    await this.extensions?.onEvent?.(event, { sessionId: this.id });
  }
  private modernOptions(): AgentSessionOptions {
    return { id: this.id, backend: this.backend!, sessionManager: this.manager, modelRuntime: { model: this.agent!.state.model, stream: this.agent!.options.streamFn, thinkingLevel: this.agent!.state.thinkingLevel }, tools: this.configuredTools ?? this.agent!.state.tools, permissionGate: this.permissionGate, resourceLoader: this.resourceLoader, systemPrompt: this.agent!.state.systemPrompt, contextCompaction: this.compaction, extensions: this.extensions };
  }
  private requireModern(): void { if (!this.agent || !this.backend || !this.manager) throw new Error("This AgentSession uses the legacy runtime adapter"); if (this.disposed) throw new Error("AgentSession has been disposed"); }
}

function createSessionManager(backend: SessionBackend): SessionManager { return { load: (id) => backend.get(id), append: (id, entry) => backend.append(id, entry), fork: (id, options) => backend.fork(id, options) }; }

function toModelMessage(message: AgentMessage | AssistantMessage): AgentMessage {
  if (message.role === "assistant" && "text" in message) return { role: "assistant", content: message.text || message.thinkingBlocks || "", ...(message.toolCalls?.length ? { tool_calls: message.toolCalls } : {}), ...(message.reasoningContent ? { reasoning_content: message.reasoningContent } : {}) };
  return { ...message } as AgentMessage;
}

function legacySnapshot(session: Session, attached: boolean): SessionSnapshot { return { session_id: session.id, mode: session.mode, status: session.status, title: session.title, created_at: session.created_at, updated_at: session.updated_at, run_count: session.run_ids.length, archived: session.archived, pinned: session.pinned, workspace_id: session.workspace_id, latest_run_id: session.run_ids.at(-1) ?? null, attached, locked: attached }; }

export type SessionSnapshot = { session_id: string; mode: Session["mode"]; status: Session["status"]; title: string; created_at: string; updated_at: string; run_count: number; archived: boolean; pinned: boolean; workspace_id: string | null; latest_run_id: string | null; attached: boolean; locked: boolean };
