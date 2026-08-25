import { randomUUID } from "node:crypto";
import path from "node:path";
import type { RunGetResult, RuntimeEvent } from "@sztucode/protocol";
import { EventBus } from "./event-bus.js";
import { AgentLoop, type AgentRunResult } from "./agent-loop.js";
import { createPlanTools, createWorkspaceTools, registerQuestionTool } from "./tools.js";
import { Workspace } from "./workspace.js";
import { PermissionManager } from "./permissions.js";
import type { ChatMessage } from "./agent-loop.js";
import type { ModelProvider } from "./agent-loop.js";
import { QuestionManager } from "./questions.js";
import { WorkspaceChangeTracker } from "./changes.js";
import type { Tool } from "./tools.js";
import { buildSystemPrompt } from "./prompt-loader.js";
import { createMemoryTools, loadMemoryCatalog } from "./memory.js";
import type { SessionStore } from "./session-store.js";
import { ExtensionRegistry } from "./extensions/registry.js";

type RunState = { runId: string; goal: string; status: "running" | "completed" | "cancelled"; startedAt: number; steps: number; controller: AbortController; usage: { input_tokens: number; output_tokens: number; cache_read_input_tokens: number; cache_creation_input_tokens: number }; contextPct: number; steering: ChatMessage[] };

export class RunManager {
  private readonly runs = new Map<string, RunState>();
  private readonly sessionRuns = new Map<string, string>();
  readonly permissions: PermissionManager;
  constructor(private readonly events: EventBus, private readonly provider: ModelProvider, workspaceRoot = process.cwd(), private readonly questions?: QuestionManager, private readonly extraTools: () => Tool[] = () => [], private readonly contextConfig: () => Promise<{ contextWindow: number; maxOutputTokens: number; streaming?: boolean }> = async () => ({ contextWindow: 128_000, maxOutputTokens: 8_192 }), private readonly sessions?: SessionStore, private readonly extensions: ExtensionRegistry = new ExtensionRegistry()) {
    this.permissions = new PermissionManager(events);
  }

  start(goal: string, history: ChatMessage[] = [], onComplete?: (messages: ChatMessage[], usage: RunState["usage"]) => Promise<void>, workspaceRoot?: string, sessionId?: string, onRunCreated?: (runId: string) => void): string {
    const runId = randomUUID();
    const run: RunState = { runId, goal, status: "running", startedAt: Date.now(), steps: 0, controller: new AbortController(), usage: { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 }, contextPct: 0, steering: [] };
    this.runs.set(runId, run);
    if (sessionId) this.sessionRuns.set(sessionId, runId);
    onRunCreated?.(runId);
    this.emit({ type: "run.started", run_id: runId, goal, ts: now() });
    void this.execute(run, history, onComplete, workspaceRoot, sessionId);
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
    run.steering.push(message); return runId!;
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
      const tools = createWorkspaceTools([...createPlanTools(this.events, run.runId, sessionId), ...createMemoryTools(memory, this.sessions, sessionId, run.runId), ...this.extraTools()]);
      for (const tool of this.extensions.toolsForWorkspace(root, new Set(tools.list().map((candidate) => candidate.name)))) { try { tools.register(tool); } catch (error) { this.events.publish({ type: "log.line", run_id: run.runId, level: "WARN", source: "extensions", message: error instanceof Error ? error.message : String(error), ts: now() }); } }
      if (tracker) await tracker.capture();
      if (sessionId && this.questions) registerQuestionTool(tools, (questions) => this.questions!.ask(sessionId, run.runId, questions as never));
      const config = await this.contextConfig();
      const extensionPrompt = (await Promise.all(this.extensions.toolPromptContributions(root).map(async (contribution) => typeof contribution.content === "function" ? contribution.content({ extensionId: "prompt", scope: "global", workspaceRoot: root, sessionId, runId: run.runId }) : contribution.content))).filter(Boolean).join("\n\n");
      const prompt = [await buildSystemPrompt(root, "coder", { permissionMode: this.permissions.getMode(), memoryEnabled: Boolean(sessionId) || memory.requiresReader(), toolNames: tools.list().map((tool) => tool.name), taskText: run.goal }), extensionPrompt, memory.prompt()].filter(Boolean).join("\n\n");
      await this.extensions.dispatch("session_start", { goal: run.goal }, root, { runId: run.runId, sessionId });
      const initialHistory = [{ role: "system" as const, content: prompt }, ...history];
      const loop = new AgentLoop(this.provider, tools, { workspace: new Workspace(root) }, this.events, this.permissions, { ...config, sessionId, workspaceRoot: root, extensions: this.extensions, onProgress: (progress) => { run.steps = progress.steps; run.usage = { ...progress.usage }; run.contextPct = progress.contextPct; }, onCompacted: sessionId && this.sessions ? async (messages, summary) => { await this.sessions!.replaceModelHistory(sessionId, messages.filter((message) => message.role !== "system")); if (summary) await this.sessions!.writeSummary(sessionId, summary); } : undefined });
      result = await loop.run(run.runId, run.goal, maxSteps(), initialHistory, run.controller.signal, () => run.steering.splice(0, run.steering.length));
    } catch (error) {
      if (tracker) await tracker.finalize();
      if (run.status !== "running") return;
      run.status = "completed";
      this.sessionRuns.forEach((active, sessionId) => { if (active === run.runId) this.sessionRuns.delete(sessionId); });
      this.emit({ type: "run.finished", run_id: run.runId, status: "failed", reason: error instanceof Error ? error.message : String(error), steps: run.steps, total_input_tokens: run.usage.input_tokens, total_output_tokens: run.usage.output_tokens, cache_read_input_tokens: run.usage.cache_read_input_tokens, cache_creation_input_tokens: run.usage.cache_creation_input_tokens, elapsed_s: elapsed(run.startedAt), context_pct: run.contextPct, ts: now() });
      await this.extensions.dispatch("agent_end", { goal: run.goal, error }, workspaceRoot ?? process.cwd(), { runId: run.runId, sessionId });
      await this.extensions.dispatch("session_shutdown", { goal: run.goal, error }, workspaceRoot ?? process.cwd(), { runId: run.runId, sessionId });
      return;
    }
    run.steps = result.steps;
    run.usage = result.usage;
    run.contextPct = result.contextPct;
    const changes = tracker ? await tracker.finalize() : [];
    if (changes.length) this.emit({ type: "change.applied", run_id: run.runId, workspace_path: path.resolve(workspaceRoot!), paths: changes.map((item) => item.path), ts: now() });
    if (run.status !== "running") return;
    if (onComplete) await onComplete(result.messages, run.usage);
    if (sessionId && this.sessions) {
      await this.sessions.replaceModelHistory(sessionId, result.messages.filter((message) => message.role !== "system"));
    }
    await new Promise((resolve) => setTimeout(resolve, 0));
    if (run.status !== "running") return;
    run.status = "completed";
    if (sessionId && this.sessionRuns.get(sessionId) === run.runId) this.sessionRuns.delete(sessionId);
    this.emit({ type: "run.finished", run_id: run.runId, status: "success", steps: run.steps, total_input_tokens: run.usage.input_tokens, total_output_tokens: run.usage.output_tokens, cache_read_input_tokens: run.usage.cache_read_input_tokens, cache_creation_input_tokens: run.usage.cache_creation_input_tokens, elapsed_s: elapsed(run.startedAt), context_pct: run.contextPct, ts: now() });
    await this.extensions.dispatch("agent_end", { goal: run.goal, messages: result.messages, result }, workspaceRoot ?? process.cwd(), { runId: run.runId, sessionId });
    await this.extensions.dispatch("session_shutdown", { goal: run.goal, result }, workspaceRoot ?? process.cwd(), { runId: run.runId, sessionId });
  }

  private emit(event: RuntimeEvent): void { this.events.publish(event); }
}

const now = () => new Date().toISOString();
const elapsed = (startedAt: number) => (Date.now() - startedAt) / 1000;
const maxSteps = (): number => { const value = Number(process.env.SZTU_MAX_STEPS); return Number.isInteger(value) && value >= 0 ? value : 100; };
