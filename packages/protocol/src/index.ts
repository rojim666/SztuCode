export type PermissionMode = "normal" | "plan" | "accept_edits" | "auto";
export type PermissionDecision = "allow_once" | "always_allow" | "deny_once" | "always_deny";
export type WorkflowRole = "planner" | "coder" | "tester" | "reviewer";
export type WorkflowTaskStatus = "pending" | "running" | "succeeded" | "failed" | "blocked" | "cancelled" | "timed_out" | "rejected";
export type WorkflowStatus = "succeeded" | "failed" | "cancelled" | "timed_out";

export interface JsonRpcRequest<P extends Record<string, unknown> = Record<string, unknown>> {
  jsonrpc: "2.0";
  id: string;
  method: string;
  params: P;
}

export interface JsonRpcSuccess<T = unknown> {
  jsonrpc: "2.0";
  id: string;
  result: T;
}

export interface JsonRpcError {
  jsonrpc: "2.0";
  id: string | null;
  error: { code: number; message: string; data?: unknown };
}

export type JsonRpcResponse<T = unknown> = JsonRpcSuccess<T> | JsonRpcError;

export interface EventEnvelope<E extends RuntimeEvent = RuntimeEvent> {
  kind: "event";
  event: E;
}

export interface PingParams { type?: "core.ping"; client: string }
export interface AgentRunParams { type?: "agent.run"; goal: string }
export interface RunCancelParams { type?: "run.cancel"; run_id: string }
export interface RunGetParams { type?: "run.get"; run_id: string }
export interface RunReplayParams { type?: "run.replay"; run_id: string; max_events?: number }
export interface PermissionRespondParams { type?: "permission.respond"; permission_id: string; decision: PermissionDecision }
export interface WorkspaceOpenParams { type?: "workspace.open"; path: string }
export interface WorkspaceListParams { type?: "workspace.list" }

export interface PongResult { server_version: string; uptime_ms: number; received_at: string; capabilities: string[] }
export interface AgentRunResult { run_id: string }
export interface RunCancelResult { run_id: string; status: "cancelling" | "not_running" }
export interface RunGetResult { run_id: string; status: "running" | "completed" | "cancelled" | "unknown" }
export interface RunReplayResult { run_id: string; events: RuntimeEvent[] }
export interface WorkspaceSummary { workspace_id: string; path: string; name: string; archived: boolean }
export interface WorkspaceOpenResult { workspace: WorkspaceSummary }
export interface WorkspaceListResult { workspaces: WorkspaceSummary[] }
export interface SessionCreateParams { type?: "session.create"; mode?: "one_shot" | "chat"; title?: string; workspace_id?: string | null }
export interface SessionGetParams { type?: "session.get"; session_id: string }
export interface SessionListParams { type?: "session.list"; include_archived?: boolean }
export interface SessionHistoryParams { type?: "session.history" | "session.get_history"; session_id: string }
export interface MessageImageBlock { type: "image"; media_type: string; data: string }
export interface SessionSendMessageParams { type?: "session.send_message"; session_id: string; content: string; images?: MessageImageBlock[]; client_message_id?: string }
export interface SessionSteerMessageParams { type?: "session.steer_message"; session_id: string; content: string; images?: MessageImageBlock[] }
export interface SessionResult { session: { session_id: string; mode: "one_shot" | "chat"; status: "active" | "waiting_for_input" | "closed"; title: string; updated_at: string; run_count: number; archived: boolean; pinned: boolean; workspace_id: string | null; latest_run_id: string | null } }
export interface SessionListResult { sessions: SessionResult["session"][] }
export interface SessionHistoryResult { messages: Array<{ role: "user" | "assistant"; content: string; ts: string; run_id?: string }> }

export interface WorkflowTask {
  id: string; title: string; description: string; owner: WorkflowRole;
  dependencies: string[]; completion_criteria: string[]; allowed_paths: string[];
  depth: number; token_budget: number; time_budget_s: number; max_retries: number | null;
}
export interface WorkflowGraph { workflow_id: string; goal: string; planner_summary: string; tasks: WorkflowTask[] }
export interface HandoffArtifact {
  workflow_id: string; task_id: string; role: WorkflowRole; status: "succeeded" | "failed";
  summary: string; changed_paths: string[]; scope_escalations: string[]; commands: string[];
  output: string; conclusion: string; diff_summary: string; test_summary: string;
  security_summary: string; review_decision: "accept" | "return" | null;
  tokens: number; elapsed_s: number; attempt: number; child_run_id: string;
}
export interface WorkflowTaskResult { task: WorkflowTask; status: WorkflowTaskStatus; attempts: number; artifact: HandoffArtifact | null; error: string; tokens: number }
export interface WorkflowResult { workflow_id: string; status: WorkflowStatus; reason: string; tasks: WorkflowTaskResult[]; total_tokens: number; elapsed_s: number }

export interface CoreStartedEvent { type: "core.started"; listen_addr: string; version: string }
export interface RunStartedEvent { type: "run.started"; run_id: string; goal: string; ts: string }
export interface RunFinishedEvent { type: "run.finished"; run_id: string; status: "success" | "failed" | "cancelled"; reason?: string; verification_status?: string; steps: number; total_input_tokens: number; total_output_tokens: number; cache_read_input_tokens: number; cache_creation_input_tokens: number; elapsed_s: number; context_pct: number; ts: string }
export interface StepStartedEvent { type: "step.started"; run_id: string; step: number; ts: string }
export interface StepFinishedEvent { type: "step.finished"; run_id: string; step: number; ts: string }
export interface LlmTokenEvent { type: "llm.token"; run_id: string; token: string; ts: string }
export interface LlmThinkingEvent { type: "llm.thinking"; run_id: string; step: number; thinking: string; ts: string }
export interface LlmUsageEvent { type: "llm.usage"; run_id: string; input_tokens: number; output_tokens: number; cache_read_input_tokens: number; cache_creation_input_tokens: number; context_pct: number; model: string; context_window: number; available_tokens: number; reserved_output_tokens: number; system_tokens: number; summary_tokens: number; conversation_tokens: number; tool_tokens: number; ts: string }
export interface PermissionRequestedEvent { type: "permission.requested"; run_id: string; permission_id: string; tool_use_id: string; tool_name: string; params: Record<string, unknown>; preview: string; param_preview: string; ts: string }
export interface PermissionResolvedEvent { type: "permission.resolved"; run_id: string; permission_id: string; tool_use_id: string; decision: PermissionDecision; ts: string }
export interface PermissionGrantedEvent { type: "permission.granted"; run_id: string; tool_use_id: string; decision: string; ts: string }
export interface PermissionDeniedEvent { type: "permission.denied"; run_id: string; tool_use_id: string; decision: string; ts: string }
export interface DenialInterventionEvent { type: "denial.intervention"; run_id: string; tool_name: string; consecutive_count: number; total_denials: number; message: string; ts: string }
export interface StuckLoopEvent { type: "stuck.loop"; run_id: string; signature: string; consecutive_count: number; total_interventions: number; message: string; ts: string }
export interface ToolCallStartedEvent { type: "tool.call_started"; run_id: string; tool_use_id: string; tool_name: string; params: Record<string, unknown>; ts: string }
export interface ToolCallFinishedEvent { type: "tool.call_finished"; run_id: string; tool_use_id: string; tool_name: string; elapsed_ms: number; output: string; ts: string }
export interface ToolCallFailedEvent { type: "tool.call_failed"; run_id: string; tool_use_id: string; tool_name: string; error_class: string; error_message: string; elapsed_ms: number; ts: string }
export interface LogLineEvent { type: "log.line"; run_id: string; level: string; source: string; message: string; ts: string }
export interface ContextInjectedEvent { type: "context.injected"; run_id: string; source: "system" | "global" | "project" | "session" | "intervention" | "steering"; label: string; chars: number; preview: string; text: string; ts: string }
export interface SessionMessageReceivedEvent { type: "session.message_received"; session_id: string; content: string; ts: string }
export interface QuestionRequestedEvent { type: "question.requested"; rpc_id: string; session_id: string; run_id: string; questions: Array<Record<string, unknown>>; ts: string }
export interface QuestionResolvedEvent { type: "question.resolved"; rpc_id: string; session_id: string; run_id: string; outcome: "answered" | "cancelled"; ts: string }
export interface SubagentStartedEvent { type: "subagent.started"; run_id: string; parent_run_id: string; description: string; ts: string }
export interface SubagentFinishedEvent { type: "subagent.finished"; run_id: string; parent_run_id: string; status: "success" | "failed"; ts: string }
export interface WorkflowTaskSnapshot { id: string; title: string; owner: WorkflowRole; status: WorkflowTaskStatus; dependencies: string[]; completion_criteria: string[]; allowed_paths: string[]; attempt: number; error: string }
export interface WorkflowStartedEvent { type: "workflow.started"; run_id: string; workflow_id: string; goal: string; planner_summary: string; tasks: WorkflowTaskSnapshot[]; ts: string }
export interface WorkflowTaskUpdatedEvent { type: "workflow.task_updated"; run_id: string; workflow_id: string; task: WorkflowTaskSnapshot; ts: string }
export interface WorkflowHandoffEvent { type: "workflow.handoff"; run_id: string; workflow_id: string; artifact: HandoffArtifact; ts: string }
export interface WorkflowReviewedEvent { type: "workflow.reviewed"; run_id: string; workflow_id: string; task_id: string; decision: "accept" | "return"; diff_summary: string; test_summary: string; security_summary: string; conclusion: string; ts: string }
export interface WorkflowFinishedEvent { type: "workflow.finished"; run_id: string; workflow_id: string; status: WorkflowStatus; reason: string; total_tokens: number; elapsed_s: number; ts: string }
export interface SessionLifecycleEvent { type: "session.created" | "session.waiting_for_input" | "session.closed"; session_id: string; mode?: "one_shot" | "chat"; last_run_id?: string; ts: string }
export interface SessionMessageSteeredEvent { type: "session.message_steered"; session_id: string; run_id: string; content: string; ts: string }
export interface SkillInvokedEvent { type: "skill.invoked"; skill_name: string; arguments: string; run_id: string; ts: string }
export interface ContextCompactingEvent { type: "context.compacting"; session_id: string; run_id: string; ts: string }
export interface ContextCompactedEvent { type: "context.compacted"; session_id: string; run_id: string; original_tokens: number; summary_tokens: number; ts: string }
export interface PlanItem { id: number; subject: string; status: "pending" | "in_progress" | "completed"; blocked_by: number[] }
export interface PlanUpdatedEvent { type: "plan.updated"; run_id: string; session_id: string; items: PlanItem[]; ts: string }
export interface TestResultEvent { type: "test.result"; run_id: string; tool_use_id: string; status: "passed" | "failed"; summary: string; ts: string }
export interface ChangeAppliedEvent { type: "change.applied"; run_id: string; workspace_path: string; paths: string[]; ts: string }
export interface VerificationStartedEvent { type: "verification.started"; run_id: string; condition_count: number; ts: string }
export interface VerificationFinishedEvent { type: "verification.finished"; run_id: string; overall: "verified" | "partial" | "unverified" | "failed" | "env_blocked" | "stale"; results: Array<{ condition_id: string; outcome: string; message: string }>; ts: string }
export interface PermissionModeChangedEvent { type: "permission.mode_changed"; old_mode: PermissionMode; new_mode: PermissionMode; ts: string }

export type RuntimeEvent = CoreStartedEvent | RunStartedEvent | RunFinishedEvent | StepStartedEvent | StepFinishedEvent | LlmTokenEvent | LlmThinkingEvent | LlmUsageEvent | PermissionRequestedEvent | PermissionResolvedEvent | PermissionGrantedEvent | PermissionDeniedEvent | DenialInterventionEvent | StuckLoopEvent | ToolCallStartedEvent | ToolCallFinishedEvent | ToolCallFailedEvent | LogLineEvent | ContextInjectedEvent | SessionMessageReceivedEvent | QuestionRequestedEvent | QuestionResolvedEvent | SubagentStartedEvent | SubagentFinishedEvent | WorkflowTaskUpdatedEvent | WorkflowHandoffEvent | WorkflowReviewedEvent | WorkflowFinishedEvent | SessionLifecycleEvent | SessionMessageSteeredEvent | SkillInvokedEvent | ContextCompactingEvent | ContextCompactedEvent | PlanUpdatedEvent | TestResultEvent | ChangeAppliedEvent | VerificationStartedEvent | VerificationFinishedEvent | PermissionModeChangedEvent | WorkflowStartedEvent;

export function isJsonRpcResponse(value: unknown): value is JsonRpcResponse {
  if (!value || typeof value !== "object") return false;
  const message = value as Record<string, unknown>;
  return message.jsonrpc === "2.0" && (typeof message.id === "string" || message.id === null) && ("result" in message || "error" in message);
}

export function isRuntimeEvent(value: unknown): value is RuntimeEvent {
  return !!value && typeof value === "object" && typeof (value as { type?: unknown }).type === "string";
}
