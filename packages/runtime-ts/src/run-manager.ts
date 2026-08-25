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
import { buildCompletionContract, buildRepairPrompt, RepairCircuitBreaker, VerificationExecutor, digestsFromChangeRecords, failureSignature, markStaleEvidence, type VerificationResult } from "./verification.js";

type RunState = { runId: string; goal: string; status: "running" | "completed" | "cancelled"; startedAt: number; steps: number; controller: AbortController; usage: { input_tokens: number; output_tokens: number; cache_read_input_tokens: number; cache_creation_input_tokens: number }; contextPct: number; steering: ChatMessage[]; verificationStatus?: string };

export class RunManager {
  private readonly runs = new Map<string, RunState>();
  private readonly sessionRuns = new Map<string, string>();
  readonly permissions: PermissionManager;
  constructor(private readonly events: EventBus, private readonly provider: ModelProvider, workspaceRoot = process.cwd(), private readonly questions?: QuestionManager, private readonly extraTools: () => Tool[] = () => [], private readonly contextConfig: () => Promise<{ contextWindow: number; maxOutputTokens: number; streaming?: boolean }> = async () => ({ contextWindow: 128_000, maxOutputTokens: 8_192 }), private readonly sessions?: SessionStore) {
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
    const root = workspaceRoot ?? process.cwd();
    let result: AgentRunResult;
    let loop: AgentLoop | undefined;
    let verification: VerificationResult | undefined;
    const tracker = workspaceRoot ? new WorkspaceChangeTracker(workspaceRoot, run.runId) : null;
    try {
      const memory = await loadMemoryCatalog(root, this.sessions, sessionId);
      const tools = createWorkspaceTools([...createPlanTools(this.events, run.runId, sessionId), ...createMemoryTools(memory, this.sessions, sessionId, run.runId), ...this.extraTools()]); if (tracker) await tracker.capture();
      if (sessionId && this.questions) registerQuestionTool(tools, (questions) => this.questions!.ask(sessionId, run.runId, questions as never));
      const config = await this.contextConfig();
      const prompt = [await buildSystemPrompt(root, "coder", { permissionMode: this.permissions.getMode(), memoryEnabled: Boolean(sessionId) || memory.requiresReader(), toolNames: tools.list().map((tool) => tool.name), taskText: run.goal }), memory.prompt()].filter(Boolean).join("\n\n");
      const initialHistory = [{ role: "system" as const, content: prompt }, ...history];
      loop = new AgentLoop(this.provider, tools, { workspace: new Workspace(root) }, this.events, this.permissions, { ...config, sessionId, onProgress: (progress) => { run.steps = progress.steps; run.usage = { ...progress.usage }; run.contextPct = progress.contextPct; }, onCompacted: sessionId && this.sessions ? async (messages, summary) => { await this.sessions!.replaceModelHistory(sessionId, messages.filter((message) => message.role !== "system")); if (summary) await this.sessions!.writeSummary(sessionId, summary); } : undefined });
      result = await loop.run(run.runId, run.goal, maxSteps(), initialHistory, run.controller.signal, () => run.steering.splice(0, run.steering.length));
    } catch (error) {
      if (tracker) await tracker.finalize();
      if (run.status !== "running") return;
      run.status = "completed";
      this.sessionRuns.forEach((active, sessionId) => { if (active === run.runId) this.sessionRuns.delete(sessionId); });
      this.emit({ type: "run.finished", run_id: run.runId, status: "failed", reason: error instanceof Error ? error.message : String(error), steps: run.steps, total_input_tokens: run.usage.input_tokens, total_output_tokens: run.usage.output_tokens, cache_read_input_tokens: run.usage.cache_read_input_tokens, cache_creation_input_tokens: run.usage.cache_creation_input_tokens, elapsed_s: elapsed(run.startedAt), context_pct: run.contextPct, ts: now() });
      return;
    }
    run.steps = result.steps;
    run.usage = result.usage;
    run.contextPct = result.contextPct;
    let changes = tracker ? await tracker.finalize() : [];
    if (changes.length) this.emit({ type: "change.applied", run_id: run.runId, workspace_path: path.resolve(workspaceRoot!), paths: changes.map((item) => item.path), ts: now() });
    if (run.status !== "running") return;

    // Verification is opt-in so existing projects without a check contract keep
    // their historical completion semantics. A user checks.toml or project
    // package scripts becomes an independent, permission-free gate when enabled.
    try {
    if (verificationEnabled() && loop) {
      const contract = await buildCompletionContract(run.runId, root);
      if (contract) {
        const executor = new VerificationExecutor(root, runDataRoot(run.runId), verificationTimeoutMs());
        const breaker = new RepairCircuitBreaker(repairAttempts());
        this.emit({ type: "verification.started", run_id: run.runId, condition_count: contract.conditions.length, ts: now() });
        verification = await executor.verify(contract, digestsFromChangeRecords(changes));
        breaker.record(failureSignature(verification));
        for (;;) {
          const stopReason = breaker.stopReason();
          if (verification.overall !== "failed" || stopReason || run.status !== "running") {
            if (stopReason && verification.overall === "failed") this.emit({ type: "log.line", run_id: run.runId, level: "WARN", source: "verification", message: `Repair stopped: ${stopReason}`, ts: now() });
            break;
          }
          breaker.noteAttempt();
          if (tracker) await tracker.capture();
          result = await loop.run(run.runId, buildRepairPrompt(verification, contract), maxSteps(), result.messages, run.controller.signal, () => run.steering.splice(0, run.steering.length));
          changes = tracker ? await tracker.finalize() : changes;
          const current = digestsFromChangeRecords(changes);
          markStaleEvidence(verification, contract, current);
          verification = await executor.verify(contract, current);
          breaker.record(failureSignature(verification));
        }
        run.verificationStatus = verification.overall;
        this.emit({ type: "verification.finished", run_id: run.runId, overall: verification.overall, results: verification.results.map((item) => ({ condition_id: item.condition_id, outcome: item.outcome, message: item.message })), ts: now() });
        if (verification.overall === "failed") {
          if (onComplete) await onComplete(result.messages, run.usage);
          if (sessionId && this.sessions) await this.sessions.replaceModelHistory(sessionId, result.messages.filter((message) => message.role !== "system"));
          run.status = "completed";
          if (sessionId && this.sessionRuns.get(sessionId) === run.runId) this.sessionRuns.delete(sessionId);
          this.emit({ type: "run.finished", run_id: run.runId, status: "failed", reason: "independent verification failed", verification_status: verification.overall, steps: run.steps, total_input_tokens: run.usage.input_tokens, total_output_tokens: run.usage.output_tokens, cache_read_input_tokens: run.usage.cache_read_input_tokens, cache_creation_input_tokens: run.usage.cache_creation_input_tokens, elapsed_s: elapsed(run.startedAt), context_pct: run.contextPct, ts: now() });
          return;
        }
      }
    }
    } catch (error) {
      if (run.status !== "running") return;
      run.status = "completed";
      if (sessionId && this.sessionRuns.get(sessionId) === run.runId) this.sessionRuns.delete(sessionId);
      this.emit({ type: "run.finished", run_id: run.runId, status: "failed", reason: error instanceof Error ? error.message : String(error), ...(verification ? { verification_status: verification.overall } : {}), steps: run.steps, total_input_tokens: run.usage.input_tokens, total_output_tokens: run.usage.output_tokens, cache_read_input_tokens: run.usage.cache_read_input_tokens, cache_creation_input_tokens: run.usage.cache_creation_input_tokens, elapsed_s: elapsed(run.startedAt), context_pct: run.contextPct, ts: now() });
      return;
    }
    if (onComplete) await onComplete(result.messages, run.usage);
    if (sessionId && this.sessions) {
      await this.sessions.replaceModelHistory(sessionId, result.messages.filter((message) => message.role !== "system"));
    }
    await new Promise((resolve) => setTimeout(resolve, 0));
    if (run.status !== "running") return;
    run.status = "completed";
    if (sessionId && this.sessionRuns.get(sessionId) === run.runId) this.sessionRuns.delete(sessionId);
    this.emit({ type: "run.finished", run_id: run.runId, status: "success", ...(run.verificationStatus ? { verification_status: run.verificationStatus } : {}), steps: run.steps, total_input_tokens: run.usage.input_tokens, total_output_tokens: run.usage.output_tokens, cache_read_input_tokens: run.usage.cache_read_input_tokens, cache_creation_input_tokens: run.usage.cache_creation_input_tokens, elapsed_s: elapsed(run.startedAt), context_pct: run.contextPct, ts: now() });
  }

  private emit(event: RuntimeEvent): void { this.events.publish(event); }
}

const now = () => new Date().toISOString();
const elapsed = (startedAt: number) => (Date.now() - startedAt) / 1000;
const maxSteps = (): number => { const value = Number(process.env.SZTU_MAX_STEPS); return Number.isInteger(value) && value >= 0 ? value : 100; };
const verificationEnabled = (): boolean => /^(1|true|yes)$/i.test(process.env.SZTU_REQUIRE_VERIFICATION ?? "");
const verificationTimeoutMs = (): number => { const value = Number(process.env.SZTU_VERIFICATION_TIMEOUT_S); return Number.isFinite(value) && value > 0 ? value * 1_000 : 60_000; };
const repairAttempts = (): number => { const value = Number(process.env.SZTU_MAX_REPAIR_ATTEMPTS); return Number.isInteger(value) && value > 0 ? value : 3; };
const runDataRoot = (runId: string): string => path.join(process.env.SZTU_DATA_DIR ?? path.join(process.env.USERPROFILE ?? process.env.HOME ?? process.cwd(), ".sztu"), "runs", runId);
