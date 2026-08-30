import { randomUUID } from "node:crypto";
import path from "node:path";
import type { RunGetResult, RuntimeEvent } from "@sztucode/protocol";
import { EventBus } from "./event-bus.js";
import { AgentLoop, type AgentRunResult } from "./agent-loop.js";
import { createPlanTools, createSkillTool, createSpawnAgentTool, createWorkflowTool, createWorkspaceTools, registerQuestionTool } from "./tools.js";
import { Workspace } from "./workspace.js";
import { PermissionManager } from "./permissions.js";
import type { ChatMessage } from "./agent-loop.js";
import type { ModelProvider } from "./agent-loop.js";
import { QuestionManager } from "./questions.js";
import { WorkspaceChangeTracker } from "./changes.js";
import type { Tool } from "./tools.js";
import { buildDynamicContext, buildSystemPrompt } from "./prompt-loader.js";
import { createMemoryTools, loadMemoryCatalog } from "./memory.js";
import type { SessionStore } from "./session-store.js";
import { ExtensionRegistry } from "./extensions/registry.js";
import { NOOP_TELEMETRY_CONTEXT, safeStartSpan, type TelemetryContext } from "@sztucode/telemetry";
import { SubagentManager } from "./subagent.js";
import { validateWorkflowGraph } from "@sztucode/protocol/workflow";

type RunState = { runId: string; goal: string; status: "running" | "completed" | "failed" | "cancelled"; startedAt: number; steps: number; controller: AbortController; generationController: AbortController; usage: { input_tokens: number; output_tokens: number; cache_read_input_tokens: number; cache_creation_input_tokens: number }; contextPct: number; steering: ChatMessage[] };

/**
 * Compatibility runner for the legacy runtime API.
 * New composition code should use ServerService/AgentSession; this class
 * remains injectable so existing CLI, desktop and tests keep their contract.
 */
export class RunManager {
  private readonly runs = new Map<string, RunState>();
  private readonly sessionRuns = new Map<string, string>();
  private readonly runRoots = new Map<string, string>();
  readonly permissions: PermissionManager;
  constructor(private readonly events: EventBus, private readonly provider: ModelProvider, workspaceRoot = process.cwd(), private readonly questions?: QuestionManager, private readonly extraTools: () => Tool[] = () => [], private readonly contextConfig: () => Promise<{ contextWindow: number; maxOutputTokens: number; streaming?: boolean }> = async () => ({ contextWindow: 128_000, maxOutputTokens: 8_192 }), private readonly sessions?: SessionStore, private readonly extensions: ExtensionRegistry = new ExtensionRegistry(), private readonly telemetry: TelemetryContext = NOOP_TELEMETRY_CONTEXT) {
    this.permissions = new PermissionManager(events, 60_000, undefined, this.telemetry);
    this.events.subscribe((event) => {
      const root = ("workspace_path" in event && typeof event.workspace_path === "string" ? event.workspace_path : undefined) ?? ("run_id" in event ? this.runRoots.get(event.run_id) : undefined) ?? workspaceRoot;
      void this.extensions.emitSessionEvent(event, root, { runId: "run_id" in event ? event.run_id : undefined });
    });
  }

  start(goal: string, history: ChatMessage[] = [], onComplete?: (messages: ChatMessage[], usage: RunState["usage"]) => Promise<void>, workspaceRoot?: string, sessionId?: string, onRunCreated?: (runId: string) => void): string {
    const runId = randomUUID();
    const run: RunState = { runId, goal, status: "running", startedAt: Date.now(), steps: 0, controller: new AbortController(), generationController: new AbortController(), usage: { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 }, contextPct: 0, steering: [] };
    this.runs.set(runId, run);
    this.runRoots.set(runId, workspaceRoot ?? process.cwd());
    if (sessionId) this.sessionRuns.set(sessionId, runId);
    onRunCreated?.(runId);
    this.emit({ type: "operation.started", run_id: runId, operation_id: runId, goal, ts: now() });
    this.emit({ type: "run.started", run_id: runId, goal, ts: now() });
    void safeStartSpan(this.telemetry, { name: "agent.run", attributes: { run_id: runId, session_id: sessionId, workspace: workspaceRoot ? "configured" : "default" } }, (span) => { span.addEvent("agent.started"); return this.execute(run, history, onComplete, workspaceRoot, sessionId); });
    return runId;
  }


  get(runId: string): RunGetResult {
    const run = this.runs.get(runId);
    return { run_id: runId, status: run?.status ?? "unknown" };
  }

  hasActiveSession(sessionId: string): boolean {
    const runId = this.sessionRuns.get(sessionId); const run = runId ? this.runs.get(runId) : undefined;
    return Boolean(run && run.status === "running");
  }

  steer(sessionId: string, message: ChatMessage): string {
    const runId = this.sessionRuns.get(sessionId); const run = runId ? this.runs.get(runId) : undefined;
    if (!run || run.status !== "running") throw new Error("steer unavailable");
    run.steering.push(message); run.generationController.abort(new Error("Generation interrupted by steering")); return runId!;
  }

  cancel(runId: string): "cancelling" | "not_running" {
    const run = this.runs.get(runId);
    if (!run || run.status !== "running") return "not_running";
    run.status = "cancelled";
    run.controller.abort(new Error("Run cancelled"));
    this.permissions.cancelRun(runId);
    this.questions?.cancelRun(runId);
    this.emit({ type: "run.finished", run_id: runId, status: "cancelled", reason: "cancelled", steps: run.steps, total_input_tokens: run.usage.input_tokens, total_output_tokens: run.usage.output_tokens, cache_read_input_tokens: run.usage.cache_read_input_tokens, cache_creation_input_tokens: run.usage.cache_creation_input_tokens, elapsed_s: elapsed(run.startedAt), context_pct: run.contextPct, ts: now() });
      this.sessionRuns.forEach((active, sessionId) => { if (active === runId) this.sessionRuns.delete(sessionId); });
    return "cancelling";
  }

  cancelAll(): number {
    const active = [...this.runs.values()].filter((run) => run.status === "running").map((run) => run.runId);
    for (const runId of active) this.cancel(runId);
    return active.length;
  }

  private async execute(run: RunState, history: ChatMessage[], onComplete?: (messages: ChatMessage[], usage: RunState["usage"]) => Promise<void>, workspaceRoot?: string, sessionId?: string): Promise<void> {
    let result: AgentRunResult;
    const tracker = workspaceRoot ? new WorkspaceChangeTracker(workspaceRoot, run.runId) : null;
    try {
      const root = workspaceRoot ?? process.cwd(); const memory = await loadMemoryCatalog(root, this.sessions, sessionId);
      const subagents = new SubagentManager(this.provider, root, this.events, this.permissions, undefined, undefined, this.telemetry);
      const tools = createWorkspaceTools([...createPlanTools(this.events, run.runId, sessionId), createSkillTool(root), createSpawnAgentTool(async (role, goal, context) => { const result = await subagents.run(role as "planner" | "coder" | "tester" | "reviewer", context ? `${goal}\n\nAdditional context:\n${context}` : goal, [], run.runId, { parentSessionId: sessionId, parentRunId: run.runId }); if (role === "planner") { try { const candidate = JSON.parse(result.text); const errors = validateWorkflowGraph(candidate); if (!errors.length) return { ...result, workflow: candidate }; return { ...result, workflow_error: errors }; } catch { return { ...result, workflow_error: ["planner did not return a valid WorkflowGraph JSON object"] }; } } return result; }), createWorkflowTool(async (graph) => { const candidate = graph as import("@sztucode/protocol").WorkflowGraph; const errors = validateWorkflowGraph(candidate); if (errors.length) throw new Error(errors.join("; ")); return subagents.runWorkflow(candidate, { runId: run.runId, parentRunId: run.runId, parentSessionId: sessionId }); }), ...createMemoryTools(memory, this.sessions, sessionId, run.runId), ...this.extraTools()]);
      for (const tool of this.extensions.toolsForWorkspace(root, new Set(tools.list().map((candidate) => candidate.name)))) { try { tools.register(tool); } catch (error) { this.events.publish({ type: "log.line", run_id: run.runId, level: "WARN", source: "extensions", message: error instanceof Error ? error.message : String(error), ts: now() }); } }
      if (tracker) await tracker.capture();
      if (sessionId && this.questions) registerQuestionTool(tools, (questions) => this.questions!.ask(sessionId, run.runId, questions as never));
      const config = await this.contextConfig();
      const extensionPrompt = (await this.extensions.renderToolPromptContributions(root, { sessionId, runId: run.runId })).filter(Boolean).join("\n\n");
      const prompt = [await buildSystemPrompt(root, "coder", { permissionMode: this.permissions.getMode(), memoryEnabled: Boolean(sessionId) || memory.requiresReader(), toolNames: tools.list().map((tool) => tool.name) }), extensionPrompt].filter(Boolean).join("\n\n");
      const dynamicContext = [await buildDynamicContext(root), memory.prompt()].filter(Boolean).join("\n\n");
      await this.extensions.dispatch("session_start", { goal: run.goal }, root, { runId: run.runId, sessionId });
      const initialHistory = [{ role: "system" as const, content: prompt }, ...(dynamicContext ? [{ role: "user" as const, content: dynamicContext }] : []), ...history];
      const checkpointInterval = positiveEnv("SZTU_CHECKPOINT_INTERVAL", 5);
      const loop = new AgentLoop(this.provider, tools, { workspace: new Workspace(root) }, this.events, this.permissions, { ...config, sessionId, workspaceRoot: root, extensions: this.extensions, telemetry: this.telemetry, onProgress: (progress) => { run.steps = progress.steps; run.usage = { ...progress.usage }; run.contextPct = progress.contextPct; }, onCheckpoint: sessionId && this.sessions ? async (checkpoint) => { if (checkpoint.phase === "tool_batch" && checkpoint.step % checkpointInterval !== 0) return; await this.sessions!.replaceModelHistory(sessionId, checkpoint.messages.filter((message) => message.role !== "system")); await this.sessions!.appendRunEvent(sessionId, { type: "run.checkpoint", run_id: run.runId, operation_id: run.runId, checkpoint_id: `${run.runId}:${checkpoint.sequence}`, sequence: checkpoint.sequence, step: checkpoint.step, phase: checkpoint.phase, input_tokens: checkpoint.usage.input_tokens, output_tokens: checkpoint.usage.output_tokens, ts: new Date().toISOString() }); } : undefined, onCompacted: sessionId && this.sessions ? async (messages, summary) => { await this.sessions!.replaceModelHistory(sessionId, messages.filter((message) => message.role !== "system")); if (summary) await this.sessions!.writeSummary(sessionId, summary); } : undefined });
      result = await loop.run(run.runId, run.goal, maxSteps(), initialHistory, run.controller.signal, () => { const messages = run.steering.splice(0, run.steering.length); if (run.generationController.signal.aborted) run.generationController = new AbortController(); return messages; }, () => run.generationController.signal);
    } catch (error) {
      if (tracker) await tracker.finalize();
      // 失败路径也持久化已积累的对话状态（AgentLoop 会把 partialMessages 挂到错误上），避免多步工作成果蒸发
      const partialMessages = error instanceof Error ? (error as Error & { partialMessages?: ChatMessage[] }).partialMessages : undefined;
      if (sessionId && this.sessions && partialMessages?.length) {
        try { await this.sessions.replaceModelHistory(sessionId, partialMessages.filter((message) => message.role !== "system")); } catch { /* 持久化失败不掩盖原始错误 */ }
      }
      if (run.status !== "running") { await this.extensions.dispatch("agent_end", { goal: run.goal, error: new Error("Run cancelled") }, workspaceRoot ?? process.cwd(), { runId: run.runId, sessionId }); await this.extensions.dispatch("session_shutdown", { goal: run.goal }, workspaceRoot ?? process.cwd(), { runId: run.runId, sessionId }); this.runRoots.delete(run.runId); this.scheduleRunCleanup(run.runId); return; }
      // 失败 run 的状态必须与 run.finished 事件的 status 保持一致，否则 get() 调用方拿到的是谎言
      run.status = "failed";
      this.sessionRuns.forEach((active, sessionId) => { if (active === run.runId) this.sessionRuns.delete(sessionId); });
      this.emit({ type: "operation.finished", run_id: run.runId, operation_id: run.runId, status: "failed", steps: run.steps, ts: now() });
      this.emit({ type: "run.finished", run_id: run.runId, status: "failed", reason: error instanceof Error ? error.message : String(error), steps: run.steps, total_input_tokens: run.usage.input_tokens, total_output_tokens: run.usage.output_tokens, cache_read_input_tokens: run.usage.cache_read_input_tokens, cache_creation_input_tokens: run.usage.cache_creation_input_tokens, elapsed_s: elapsed(run.startedAt), context_pct: run.contextPct, ts: now() });
      await this.extensions.dispatch("agent_end", { goal: run.goal, error }, workspaceRoot ?? process.cwd(), { runId: run.runId, sessionId });
      await this.extensions.dispatch("session_shutdown", { goal: run.goal, error }, workspaceRoot ?? process.cwd(), { runId: run.runId, sessionId });
      this.runRoots.delete(run.runId);
      this.scheduleRunCleanup(run.runId);
      return;
    }
    run.steps = result.steps;
    run.usage = result.usage;
    run.contextPct = result.contextPct;
    const changes = tracker ? await tracker.finalize() : [];
    if (changes.length) this.emit({ type: "change.applied", run_id: run.runId, workspace_path: path.resolve(workspaceRoot!), paths: changes.map((item) => item.path), ts: now() });
    if (run.status !== "running") { await this.extensions.dispatch("agent_end", { goal: run.goal, error: new Error("Run cancelled") }, workspaceRoot ?? process.cwd(), { runId: run.runId, sessionId }); await this.extensions.dispatch("session_shutdown", { goal: run.goal }, workspaceRoot ?? process.cwd(), { runId: run.runId, sessionId }); this.runRoots.delete(run.runId); this.scheduleRunCleanup(run.runId); return; }
    if (onComplete) await onComplete(result.messages, run.usage);
    if (sessionId && this.sessions) {
      await this.sessions.replaceModelHistory(sessionId, result.messages.filter((message) => message.role !== "system"));
    }
    await new Promise((resolve) => setTimeout(resolve, 0));
    if (run.status !== "running") { await this.extensions.dispatch("agent_end", { goal: run.goal, error: new Error("Run cancelled") }, workspaceRoot ?? process.cwd(), { runId: run.runId, sessionId }); await this.extensions.dispatch("session_shutdown", { goal: run.goal }, workspaceRoot ?? process.cwd(), { runId: run.runId, sessionId }); this.runRoots.delete(run.runId); this.scheduleRunCleanup(run.runId); return; }
    run.status = "completed";
    if (sessionId && this.sessionRuns.get(sessionId) === run.runId) this.sessionRuns.delete(sessionId);
    this.emit({ type: "operation.finished", run_id: run.runId, operation_id: run.runId, status: "completed", steps: run.steps, ts: now() });
    this.emit({ type: "run.finished", run_id: run.runId, status: "success", steps: run.steps, total_input_tokens: run.usage.input_tokens, total_output_tokens: run.usage.output_tokens, cache_read_input_tokens: run.usage.cache_read_input_tokens, cache_creation_input_tokens: run.usage.cache_creation_input_tokens, elapsed_s: elapsed(run.startedAt), context_pct: run.contextPct, ts: now() });
    await this.extensions.dispatch("agent_end", { goal: run.goal, messages: result.messages, result }, workspaceRoot ?? process.cwd(), { runId: run.runId, sessionId });
    await this.extensions.dispatch("session_shutdown", { goal: run.goal, result }, workspaceRoot ?? process.cwd(), { runId: run.runId, sessionId });
    this.runRoots.delete(run.runId);
    this.scheduleRunCleanup(run.runId);
  }

  private emit(event: RuntimeEvent): void { this.events.publish(event); }

  /** 终态 run 延迟清理：保留一个窗口供 run.get 轮询拿到真实终态，避免 Map 永久驻留泄漏。 */
  private scheduleRunCleanup(runId: string, delayMs = 60_000): void {
    const timer = setTimeout(() => { this.runs.delete(runId); }, delayMs);
    timer.unref?.();
  }
}

/** @deprecated Use the ServerService-created AgentSession for new callers. */
export const LegacyRunManager = RunManager;

const now = () => new Date().toISOString();
const elapsed = (startedAt: number) => (Date.now() - startedAt) / 1000;
const maxSteps = (): number => { const value = Number(process.env.SZTU_MAX_STEPS); return Number.isInteger(value) && value >= 0 ? value : 100; };
const positiveEnv = (name: string, fallback: number): number => { const value = Number(process.env[name]); return Number.isInteger(value) && value > 0 ? value : fallback; };
