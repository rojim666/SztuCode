import { randomUUID } from "node:crypto";
import type { HandoffArtifact, WorkflowGraph, WorkflowRole, WorkflowTask } from "@sztucode/protocol";
import type { ChatMessage, ModelProvider } from "./agent-loop.js";
import { EventBus } from "./event-bus.js";
import { PermissionManager } from "./permissions.js";
import { createPlanTools, createWorkspaceTools } from "./tools.js";
import { Workspace } from "./workspace.js";
import { WorkflowOrchestrator } from "./workflow.js";
import { buildSystemPrompt, loadAgentProfile } from "./prompt-loader.js";
import type { PermissionGate } from "./permissions.js";
import type { ToolPermission } from "./tools.js";
import { normalizeWorkflowPath, workflowPathIsAllowed } from "./workflow-scope.js";
import { AgentSession } from "./agent-session.js";
import { JsonlSessionBackend } from "@sztucode/session-fs";
import type { SessionBackend, SessionHeader, SessionSnapshot } from "@sztucode/session";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { NOOP_TELEMETRY_CONTEXT, safeStartSpan, type TelemetryContext } from "@sztucode/telemetry";

const roleNames: Record<WorkflowRole, string> = { planner: "planner", coder: "coder", tester: "tester", reviewer: "reviewer" };
const workflowCoderTools = ["read_file", "write_file", "edit_file", "list_dir", "grep_search", "glob_search"];
export type SubagentRunOptions = { signal?: AbortSignal; parentSessionId?: string; parentRunId?: string; allowedPaths?: string[]; changedPaths?: Set<string>; scopeEscalations?: Set<string> };

export interface ChildSessionInfo { runId: string; sessionId: string; parentRunId: string; parentSessionId: string | null; role: WorkflowRole; runtime: AgentSession }

export interface PersistedWorkflowState {
  workflow_id: string;
  run_id: string;
  parent_session_id: string | null;
  status: "running" | "succeeded" | "failed" | "cancelled" | "timed_out";
  graph: WorkflowGraph;
  tasks: import("@sztucode/protocol").WorkflowTaskResult[];
  updated_at: string;
}

export class SubagentManager {
  private readonly children = new Map<string, ChildSessionInfo>();
  private readonly workflowRoot: string;
  private workflowWrite = Promise.resolve();
  constructor(private readonly provider: ModelProvider, private readonly workspaceRoot: string, private readonly events: EventBus, private readonly permissions: PermissionManager, private readonly sessionBackend: SessionBackend = new JsonlSessionBackend(), workflowRoot = path.join(process.env.SZTU_DATA_DIR ?? path.join(process.env.USERPROFILE ?? process.cwd(), ".sztu"), "workflows"), private readonly telemetry: TelemetryContext = NOOP_TELEMETRY_CONTEXT) { this.workflowRoot = workflowRoot; }
  async run(role: WorkflowRole, goal: string, history: ChatMessage[] = [], parentRunId = "", options: SubagentRunOptions = {}): Promise<{ runId: string; sessionId: string; text: string; tokens: number }> {
    return safeStartSpan(this.telemetry, { name: "subagent.run", attributes: { role, parent_run_id: options.parentRunId ?? parentRunId, parent_session_id: options.parentSessionId } }, (span) => { span.addEvent("subagent.started"); return this.runInternal(role, goal, history, parentRunId, options); });
  }
  private async runInternal(role: WorkflowRole, goal: string, history: ChatMessage[] = [], parentRunId = "", options: SubagentRunOptions = {}): Promise<{ runId: string; sessionId: string; text: string; tokens: number }> {
    if (options.signal?.aborted) throw options.signal.reason ?? new Error("subagent cancelled");
    const runId = randomUUID(); const sessionId = randomUUID(); const effectiveParentRunId = options.parentRunId ?? parentRunId; const ts = new Date().toISOString();
    const profile = await loadAgentProfile(this.workspaceRoot, roleNames[role]);
    const rolePrompt = profile.systemPrompt || `Act as the ${role} role for this task.`;
    const tools = createWorkspaceTools(createPlanTools(this.events, runId, sessionId));
    if (profile.allowedTools?.length) tools.restrictTo(profile.allowedTools);
    if (options.allowedPaths) tools.restrictTo(workflowCoderTools);
    const basePermissions = profile.permissionMode ? this.permissions.scoped(profile.permissionMode) : this.permissions;
    const permissions = options.allowedPaths ? scopedWorkflowPermissions(basePermissions, options.allowedPaths) : basePermissions;
    const basePrompt = await buildSystemPrompt(this.workspaceRoot, role, { permissionMode: profile.permissionMode ?? this.permissions.getMode(), toolNames: tools.list().map((tool) => tool.name) });
    const context = { workspace: new Workspace(this.workspaceRoot), onFileChanged: (relativePath: string) => { const normalized = normalizeWorkflowPath(relativePath); options.changedPaths?.add(normalized); if (options.allowedPaths && !workflowPathIsAllowed(normalized, options.allowedPaths)) options.scopeEscalations?.add(normalized); } };
    const runtime = await this.createChildSession({ runId, sessionId, role, parentRunId: effectiveParentRunId, parentSessionId: options.parentSessionId ?? null, profile, tools, context, permissions, history });
    this.children.set(sessionId, { runId, sessionId, parentRunId: effectiveParentRunId, parentSessionId: options.parentSessionId ?? null, role, runtime });
    this.events.publish({ type: "subagent.started", run_id: runId, parent_run_id: effectiveParentRunId, ...(options.parentSessionId ? { parent_session_id: options.parentSessionId } : {}), child_session_id: sessionId, description: `${role}: ${goal.slice(0, 200)}`, ts });
    const stopOnParentAbort = () => { void runtime.abort(); };
    options.signal?.addEventListener("abort", stopOnParentAbort, { once: true });
    try {
      if (options.signal?.aborted) { await runtime.abort(); throw options.signal.reason ?? new Error("subagent cancelled"); }
      await runtime.prompt(`${basePrompt}\n\n# Role instructions\n${rolePrompt}\n\n${goal}`);
      const text = runtime.outputText;
      this.events.publish({ type: "subagent.finished", run_id: runId, parent_run_id: effectiveParentRunId, ...(options.parentSessionId ? { parent_session_id: options.parentSessionId } : {}), child_session_id: sessionId, status: "success", ts: new Date().toISOString() });
      return { runId, sessionId, text, tokens: runtime.usageTokens };
    } catch (error) {
      this.events.publish({ type: "subagent.finished", run_id: runId, parent_run_id: effectiveParentRunId, ...(options.parentSessionId ? { parent_session_id: options.parentSessionId } : {}), child_session_id: sessionId, status: "failed", ts: new Date().toISOString() });
      throw error;
    } finally {
      options.signal?.removeEventListener("abort", stopOnParentAbort);
      this.children.delete(sessionId); runtime.dispose();
    }
  }

  getChildSession(sessionId: string): ChildSessionInfo | undefined { return this.children.get(sessionId); }
  async abortChildSession(sessionId: string): Promise<"cancelling" | "not_running"> { const result = await this.children.get(sessionId)?.runtime.abort(); return result === "cancelling" ? result : "not_running"; }
  async snapshotChildSession(sessionId: string): Promise<SessionSnapshot> { return this.sessionBackend.get(sessionId); }
  subscribeChildEvents(sessionId: string, listener: (event: import("@sztucode/protocol").RuntimeEvent) => void): () => void {
    const child = this.children.get(sessionId);
    if (!child) throw new Error(`child session is not active: ${sessionId}`);
    return child.runtime.subscribe(listener);
  }

  private async createChildSession(input: { runId: string; sessionId: string; role: WorkflowRole; parentRunId: string; parentSessionId: string | null; profile: Awaited<ReturnType<typeof loadAgentProfile>>; tools: import("./tools.js").ToolRegistry; context: import("./tools.js").ToolContext; permissions: PermissionGate; history: ChatMessage[] }): Promise<AgentSession> {
    const now = new Date().toISOString();
    const header: SessionHeader = { type: "session", version: 1, id: input.sessionId, parentSessionId: input.parentSessionId, createdAt: now, updatedAt: now, title: `${input.role}: ${input.profile.name ?? input.role}`, workspaceId: this.workspaceRoot, metadata: { parentRunId: input.parentRunId, childRunId: input.runId, role: input.role } };
    await this.sessionBackend.create(header);
    for (const message of input.history) await this.sessionBackend.append(input.sessionId, { type: "message", message: message as never });
    return AgentSession.openLegacy({ id: input.sessionId, backend: this.sessionBackend, provider: this.provider, tools: input.tools, context: input.context, events: this.events, permissions: input.permissions, runId: input.runId, maxSteps: input.profile.maxSteps || 20, workspaceRoot: this.workspaceRoot, sessionId: input.sessionId, parentSessionId: input.parentSessionId ?? undefined, telemetry: this.telemetry });
  }
  async runWorkflow(graph: WorkflowGraph, options: { runId?: string; signal?: AbortSignal; parentSessionId?: string; parentRunId?: string } = {}): Promise<import("@sztucode/protocol").WorkflowResult> {
    const workflowRunId = options.runId ?? randomUUID(); const parentSessionId = options.parentSessionId ?? graph.parent_session_id ?? null; const parentRunId = options.parentRunId ?? ""; const started = new Date().toISOString();
    const taskResults = new Map<string, import("@sztucode/protocol").WorkflowTaskResult>();
    for (const task of graph.tasks) taskResults.set(task.id, { task, status: "pending", attempts: 0, artifact: null, error: "", tokens: 0, parent_run_id: workflowRunId });
    await this.persistWorkflow({ workflow_id: graph.workflow_id, run_id: workflowRunId, parent_session_id: parentSessionId, status: "running", graph, tasks: [...taskResults.values()], updated_at: started });
    this.events.publish({ type: "workflow.started", run_id: workflowRunId, workflow_id: graph.workflow_id, goal: graph.goal, planner_summary: graph.planner_summary, tasks: graph.tasks.map((task) => snapshot(task, "pending", 0, "", undefined, workflowRunId)), parent_run_id: parentRunId, ...(parentSessionId ? { parent_session_id: parentSessionId } : {}), ts: started });
    const orchestrator = new WorkflowOrchestrator(
      (task, execution) => this.executeTask(graph.workflow_id, task, execution.completed, workflowRunId, execution.attempt, execution.signal, parentSessionId),
      4,
      {
        onTaskUpdated: async (result) => { const withParent = { ...result, parent_run_id: workflowRunId, ...(result.artifact?.child_session_id ? { child_session_id: result.artifact.child_session_id } : {}) }; taskResults.set(result.task.id, withParent); await this.persistWorkflow({ workflow_id: graph.workflow_id, run_id: workflowRunId, parent_session_id: parentSessionId, status: "running", graph, tasks: [...taskResults.values()], updated_at: new Date().toISOString() }); this.events.publish({ type: "workflow.task_updated", run_id: workflowRunId, workflow_id: graph.workflow_id, task: snapshot(result.task, result.status, result.attempts, result.error, result.artifact?.child_session_id, workflowRunId), parent_run_id: parentRunId, ...(parentSessionId ? { parent_session_id: parentSessionId } : {}), ts: new Date().toISOString() }); },
        onHandoff: (artifact) => {
          this.events.publish({ type: "workflow.handoff", run_id: workflowRunId, workflow_id: graph.workflow_id, artifact, parent_run_id: parentRunId, ts: new Date().toISOString() });
          if (artifact.role === "reviewer") this.events.publish({ type: "workflow.reviewed", run_id: workflowRunId, workflow_id: graph.workflow_id, task_id: artifact.task_id, decision: artifact.review_decision ?? "return", diff_summary: artifact.diff_summary, test_summary: artifact.test_summary, security_summary: artifact.security_summary, conclusion: artifact.conclusion, parent_run_id: parentRunId, ts: new Date().toISOString() });
        },
      },
    );
    const result = { ...(await orchestrator.run(graph, options.signal)), parent_run_id: parentRunId }; await this.persistWorkflow({ workflow_id: graph.workflow_id, run_id: workflowRunId, parent_session_id: parentSessionId, status: result.status, graph, tasks: result.tasks, updated_at: new Date().toISOString() }); this.events.publish({ type: "workflow.finished", run_id: workflowRunId, workflow_id: graph.workflow_id, status: result.status, reason: result.reason, total_tokens: result.total_tokens, elapsed_s: result.elapsed_s, parent_run_id: parentRunId, ...(parentSessionId ? { parent_session_id: parentSessionId } : {}), ts: new Date().toISOString() }); return result;
  }
  async loadWorkflow(runId: string): Promise<PersistedWorkflowState> { return JSON.parse(await (await import("node:fs/promises")).readFile(path.join(this.workflowRoot, `${runId}.json`), "utf8")) as PersistedWorkflowState; }
  private async persistWorkflow(state: PersistedWorkflowState): Promise<void> {
    const write = async () => { await mkdir(this.workflowRoot, { recursive: true }); await writeFile(path.join(this.workflowRoot, `${state.run_id}.json`), `${JSON.stringify(state, null, 2)}\n`, "utf8"); };
    this.workflowWrite = this.workflowWrite.then(write, write); await this.workflowWrite;
  }
  private async executeTask(workflowId: string, task: WorkflowTask, completed: ReadonlyMap<string, HandoffArtifact>, parentRunId: string, attempt: number, signal: AbortSignal, parentSessionId: string | null): Promise<HandoffArtifact> {
    const dependencyArtifacts = task.dependencies.map((id) => completed.get(id)).filter((artifact): artifact is HandoffArtifact => Boolean(artifact)); const started = Date.now(); const changedPaths = new Set<string>(); const scopeEscalations = new Set<string>();
    try {
      const result = await this.run(task.owner, workflowPrompt(workflowId, task, dependencyArtifacts, attempt), [], parentRunId, { signal, ...(parentSessionId ? { parentSessionId } : {}), ...(task.owner === "coder" ? { allowedPaths: task.allowed_paths, changedPaths, scopeEscalations } : {}) });
      try { return artifactFromText(workflowId, task, result, attempt, started, [...changedPaths].sort(), [...scopeEscalations].sort(), parentRunId); }
      catch (error) { return failedArtifact(workflowId, task, error, attempt, started, [...changedPaths].sort(), [...scopeEscalations].sort(), result.tokens, result.runId, result.sessionId, parentRunId); }
    } catch (error) {
      if (signal.aborted) throw signal.reason ?? error;
      return failedArtifact(workflowId, task, error, attempt, started, [...changedPaths].sort(), [...scopeEscalations].sort(), 0, "", "", parentRunId);
    }
  }
}

type RolePayload = Partial<Pick<HandoffArtifact, "status" | "summary" | "commands" | "output" | "conclusion" | "diff_summary" | "test_summary" | "security_summary" | "review_decision">>;

function workflowPrompt(workflowId: string, task: WorkflowTask, dependencies: HandoffArtifact[], attempt: number): string {
  const contracts: Record<WorkflowRole, Record<string, unknown>> = {
    planner: { status: "succeeded|failed", summary: "planning result", conclusion: "completion assessment" },
    coder: { status: "succeeded|failed", summary: "what was implemented", conclusion: "completion assessment" },
    tester: { status: "succeeded|failed", summary: "verification scope", commands: ["exact command"], output: "key raw output", conclusion: "pass/fail conclusion", test_summary: "concise evidence" },
    reviewer: { status: "succeeded|failed", summary: "review scope", diff_summary: "actual diff findings", test_summary: "tester evidence assessment", security_summary: "security evidence or limitation", review_decision: "accept|return", conclusion: "arbitration reason" },
  };
  const rules: Record<WorkflowRole, string> = {
    planner: "Analyze only and do not modify files.",
    coder: "Only modify files under allowed_paths using write_file/edit_file. Do not run tests; the independent Tester owns verification.",
    tester: "Run checks yourself, do not modify files, and preserve exact commands and real output.",
    reviewer: "Inspect actual files and dependency evidence. Return work when any completion, test, or security gate is unsatisfied. Do not modify files.",
  };
  return `Execute this delegated workflow task.\nContext: ${JSON.stringify({ workflow_id: workflowId, task, attempt, dependency_evidence: dependencies })}\nRole rule: ${rules[task.owner]}\nFinish with exactly one JSON object and no Markdown fence.\nRequired contract: ${JSON.stringify(contracts[task.owner])}`;
}

export function parseRolePayload(text: string, role: WorkflowRole): RolePayload {
  const trimmed = text.trim();
  if (role === "coder" && !trimmed.startsWith("{") && !trimmed.startsWith("```")) return { status: "succeeded", summary: trimmed || "coder completed without summary", conclusion: trimmed };
  const match = trimmed.match(/(?:```(?:json)?\s*)?(\{[\s\S]*\})(?:\s*```)?/i);
  if (!match) throw new Error(`${role} must return a JSON handoff object`);
  let value: unknown;
  try { value = JSON.parse(match[1]!); } catch { throw new Error(`${role} returned invalid JSON handoff`); }
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`${role} must return a JSON handoff object`);
  return value as RolePayload;
}

function artifactFromText(workflowId: string, task: WorkflowTask, result: { runId: string; sessionId: string; text: string; tokens: number }, attempt: number, started: number, changedPaths: string[], scopeEscalations: string[], parentRunId: string): HandoffArtifact {
  const payload = parseRolePayload(result.text, task.owner);
  const status = payload.status === "failed" ? "failed" : "succeeded";
  const decision = payload.review_decision === "accept" || payload.review_decision === "return" ? payload.review_decision : null;
  return {
    workflow_id: workflowId, task_id: task.id, role: task.owner, status,
    summary: stringValue(payload.summary) || `${task.title} completed`, changed_paths: changedPaths, scope_escalations: scopeEscalations,
    commands: Array.isArray(payload.commands) ? payload.commands.filter((item): item is string => typeof item === "string") : [], output: stringValue(payload.output), conclusion: stringValue(payload.conclusion),
    diff_summary: stringValue(payload.diff_summary), test_summary: stringValue(payload.test_summary), security_summary: stringValue(payload.security_summary), review_decision: decision,
    tokens: result.tokens, elapsed_s: (Date.now() - started) / 1000, attempt, child_run_id: result.runId, child_session_id: result.sessionId, parent_run_id: parentRunId,
  };
}

const stringValue = (value: unknown): string => typeof value === "string" ? value : "";

function failedArtifact(workflowId: string, task: WorkflowTask, error: unknown, attempt: number, started: number, changedPaths: string[], scopeEscalations: string[], tokens = 0, childRunId = "", childSessionId = "", parentRunId = ""): HandoffArtifact {
  return { workflow_id: workflowId, task_id: task.id, role: task.owner, status: "failed", summary: error instanceof Error ? error.message : String(error), changed_paths: changedPaths, scope_escalations: scopeEscalations, commands: [], output: "", conclusion: "failed", diff_summary: "", test_summary: "", security_summary: "", review_decision: null, tokens, elapsed_s: (Date.now() - started) / 1000, attempt, child_run_id: childRunId, child_session_id: childSessionId, parent_run_id: parentRunId };
}

export function scopedWorkflowPermissions(base: PermissionGate, allowedPaths: string[]): PermissionGate {
  return { check: (runId, permissionId, toolName, params, permission, signal) => {
    const effective: ToolPermission = (toolName === "write_file" || toolName === "edit_file") && typeof params.path === "string" && !workflowPathIsAllowed(params.path, allowedPaths) ? "danger_full_access" : permission;
    return base.check(runId, permissionId, toolName, params, effective, signal);
  } };
}

function snapshot(task: WorkflowTask, status: import("@sztucode/protocol").WorkflowTaskStatus, attempt: number, error: string, childSessionId?: string, parentRunId?: string): import("@sztucode/protocol").WorkflowTaskSnapshot { return { id: task.id, title: task.title, owner: task.owner, status, dependencies: task.dependencies, completion_criteria: task.completion_criteria, allowed_paths: task.allowed_paths, attempt, error, ...(childSessionId ? { child_session_id: childSessionId } : {}), ...(parentRunId ? { parent_run_id: parentRunId } : {}) }; }
