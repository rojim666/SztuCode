import type { HandoffArtifact, WorkflowGraph, WorkflowResult, WorkflowTask, WorkflowTaskResult } from "@sztucode/protocol";
import { readyTaskIds, validateWorkflowGraph } from "@sztucode/protocol/workflow";
import { normalizeWorkflowPath, workflowPathIsAllowed } from "./workflow-scope.js";

export type WorkflowTaskExecution = {
  attempt: number;
  completed: ReadonlyMap<string, HandoffArtifact>;
  signal: AbortSignal;
};

export type WorkflowTaskExecutor = (task: WorkflowTask, execution: WorkflowTaskExecution) => Promise<HandoffArtifact>;

export type WorkflowOrchestratorHooks = {
  onTaskUpdated?: (result: WorkflowTaskResult) => void | Promise<void>;
  onHandoff?: (artifact: HandoffArtifact) => void | Promise<void>;
};

class WorkflowTimeoutError extends Error {
  constructor(taskId: string) { super(`task timed out: ${taskId}`); this.name = "WorkflowTimeoutError"; }
}

class WorkflowCancelledError extends Error {
  constructor() { super("workflow cancelled"); this.name = "WorkflowCancelledError"; }
}

export class WorkflowOrchestrator {
  private readonly maxConcurrency: number;

  constructor(private readonly executeTask: WorkflowTaskExecutor, maxConcurrency = 4, private readonly hooks: WorkflowOrchestratorHooks = {}) {
    this.maxConcurrency = Math.max(1, Math.floor(maxConcurrency));
  }

  async run(graph: WorkflowGraph, signal?: AbortSignal): Promise<WorkflowResult> {
    const errors = validateWorkflowGraph(graph);
    if (errors.length) throw new Error(errors.join("; "));

    const startedAt = Date.now();
    const results = new Map<string, WorkflowTaskResult>();
    const completed = new Map<string, HandoffArtifact>();
    for (const task of graph.tasks) results.set(task.id, { task, status: "pending", attempts: 0, artifact: null, error: "", tokens: 0 });

    while ([...results.values()].some((result) => result.status === "pending" || result.status === "running")) {
      if (signal?.aborted) { await this.cancelUnfinished(results); break; }
      const ready = readyTaskIds([...results.values()].map((result) => ({ id: result.task.id, dependencies: result.task.dependencies, status: result.status }))).slice(0, this.maxConcurrency);
      if (!ready.length) {
        for (const result of results.values()) {
          if (result.status !== "pending") continue;
          result.status = "blocked";
          result.error = "dependency failed or workflow stalled";
          await this.notify(result);
        }
        break;
      }
      await Promise.all(ready.map((id) => this.runTask(graph.workflow_id, results.get(id)!, completed, signal)));
    }

    const values = [...results.values()];
    const status = workflowStatus(values);
    return {
      workflow_id: graph.workflow_id,
      status,
      reason: status === "succeeded" ? "" : status === "cancelled" ? "workflow cancelled" : "one or more tasks did not succeed",
      tasks: values,
      total_tokens: values.reduce((sum, result) => sum + result.tokens, 0),
      elapsed_s: (Date.now() - startedAt) / 1000,
    };
  }

  private async runTask(workflowId: string, result: WorkflowTaskResult, completed: Map<string, HandoffArtifact>, parentSignal?: AbortSignal): Promise<void> {
    const task = result.task;
    const maximumAttempts = 1 + (task.max_retries ?? 0);

    for (let attempt = 1; attempt <= maximumAttempts; attempt += 1) {
      if (parentSignal?.aborted) { result.status = "cancelled"; result.error = "workflow cancelled"; await this.notify(result); return; }
      result.status = "running";
      result.attempts = attempt;
      result.error = "";
      await this.notify(result);

      const controller = new AbortController();
      const cancel = () => controller.abort(new WorkflowCancelledError());
      parentSignal?.addEventListener("abort", cancel, { once: true });
      try {
        const artifact = await this.executeWithTimeout(task, { attempt, completed, signal: controller.signal }, controller, parentSignal);
        const normalized = { ...artifact, attempt };
        result.artifact = normalized;
        result.tokens += Math.max(0, normalized.tokens);
        validateHandoff(workflowId, task, normalized);
        await this.hooks.onHandoff?.(normalized);

        if (task.token_budget > 0 && result.tokens > task.token_budget) {
          result.status = "rejected";
          result.error = `token budget exceeded: used ${result.tokens}, budget ${task.token_budget}`;
          await this.notify(result);
          return;
        }
        if (normalized.status === "succeeded" && normalized.review_decision !== "return") {
          result.status = "succeeded";
          completed.set(task.id, normalized);
          await this.notify(result);
          return;
        }

        result.status = normalized.review_decision === "return" ? "rejected" : "failed";
        result.error = normalized.review_decision === "return" ? normalized.conclusion || "reviewer returned the task" : normalized.summary || "task failed";
        if (result.status === "rejected") { await this.notify(result); return; }
      } catch (error) {
        const timedOut = error instanceof WorkflowTimeoutError;
        const cancelled = error instanceof WorkflowCancelledError || parentSignal?.aborted;
        result.status = cancelled ? "cancelled" : timedOut ? "timed_out" : "failed";
        result.error = error instanceof Error ? error.message : String(error);
      } finally {
        parentSignal?.removeEventListener("abort", cancel);
        controller.abort();
      }

      await this.notify(result);
      if (result.status === "cancelled") return;
      if (task.token_budget > 0 && result.tokens >= task.token_budget) {
        result.status = "rejected";
        result.error = `token budget exhausted: used ${result.tokens}, budget ${task.token_budget}`;
        await this.notify(result);
        return;
      }
      if (attempt === maximumAttempts) return;
    }
  }

  private async executeWithTimeout(task: WorkflowTask, execution: WorkflowTaskExecution, controller: AbortController, parentSignal?: AbortSignal): Promise<HandoffArtifact> {
    let cancel: (() => void) | undefined;
    const cancellation = new Promise<never>((_resolve, reject) => {
      if (parentSignal?.aborted) reject(new WorkflowCancelledError());
      else if (parentSignal) { cancel = () => reject(new WorkflowCancelledError()); parentSignal.addEventListener("abort", cancel, { once: true }); }
    });
    let timer: NodeJS.Timeout | undefined;
    const timeout = task.time_budget_s > 0 ? new Promise<never>((_resolve, reject) => {
      timer = setTimeout(() => { const error = new WorkflowTimeoutError(task.id); controller.abort(error); reject(error); }, task.time_budget_s * 1000);
    }) : new Promise<never>(() => {});
    try {
      return await Promise.race([this.executeTask(task, execution), timeout, cancellation]);
    } finally {
      if (timer) clearTimeout(timer);
      if (cancel) parentSignal?.removeEventListener("abort", cancel);
    }
  }

  private async notify(result: WorkflowTaskResult): Promise<void> {
    await this.hooks.onTaskUpdated?.({ ...result });
  }

  private async cancelUnfinished(results: Map<string, WorkflowTaskResult>): Promise<void> {
    for (const result of results.values()) {
      if (result.status !== "pending" && result.status !== "running") continue;
      result.status = "cancelled";
      result.error = "workflow cancelled";
      await this.notify(result);
    }
  }
}

function validateHandoff(workflowId: string, task: WorkflowTask, artifact: HandoffArtifact): void {
  if (artifact.workflow_id !== workflowId || artifact.task_id !== task.id) throw new Error("handoff artifact does not match workflow task identity");
  if (artifact.role !== task.owner) throw new Error("handoff artifact role does not match task owner");
  if (!artifact.summary.trim()) throw new Error("handoff artifact requires a summary");
  if (!Number.isFinite(artifact.tokens) || artifact.tokens < 0) throw new Error("handoff artifact has invalid token usage");
  if (!Number.isFinite(artifact.elapsed_s) || artifact.elapsed_s < 0) throw new Error("handoff artifact has invalid elapsed time");
  if (task.owner === "coder") {
    const changed = artifact.changed_paths.map(normalizeWorkflowPath);
    const outside = changed.filter((value) => !workflowPathIsAllowed(value, task.allowed_paths)).sort();
    const escalations = artifact.scope_escalations.map(normalizeWorkflowPath).sort();
    if (!sameValues(outside, escalations)) throw new Error("coder scope escalation evidence does not match actual changed paths");
  }
  if (task.owner === "tester" && (!artifact.commands.length || !artifact.output.trim() || !artifact.conclusion.trim())) throw new Error("tester handoff requires commands, output, and conclusion");
  if (task.owner === "reviewer") {
    if (!artifact.review_decision) throw new Error("reviewer handoff requires accept or return decision");
    if (![artifact.diff_summary, artifact.test_summary, artifact.security_summary, artifact.conclusion].every((value) => value.trim())) throw new Error("reviewer handoff requires diff, test, security, and conclusion evidence");
  }
}

const sameValues = (left: string[], right: string[]) => left.length === right.length && left.every((value, index) => value === right[index]);

function workflowStatus(results: WorkflowTaskResult[]): WorkflowResult["status"] {
  if (results.every((result) => result.status === "succeeded")) return "succeeded";
  if (results.some((result) => result.status === "timed_out")) return "timed_out";
  if (results.some((result) => result.status === "cancelled")) return "cancelled";
  return "failed";
}
