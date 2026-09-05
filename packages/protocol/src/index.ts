export type PermissionMode = "normal" | "plan" | "accept_edits" | "auto";
export type PermissionDecision = "allow_once" | "always_allow" | "deny_once" | "always_deny";
export type WorkflowRole = "planner" | "coder" | "tester" | "reviewer";
export type WorkflowTaskStatus = "pending" | "running" | "succeeded" | "failed" | "blocked" | "cancelled" | "timed_out" | "rejected";
export type WorkflowStatus = "succeeded" | "failed" | "cancelled" | "timed_out";

/** Wire contract version. JSON-RPC/NDJSON compatibility is retained within a version. */
export const PROTOCOL_VERSION = 1 as const;
export type ProtocolVersion = typeof PROTOCOL_VERSION;

export const PROTOCOL_CAPABILITIES = [
  "jsonrpc",
  "ndjson",
  "hello",
  "request.cancel",
  "request.idempotency",
  "session.attach",
  "session.detach",
  "session.snapshot",
  "session.command",
  "event.subscribe",
  "artifacts",
] as const;
export type ProtocolCapability = (typeof PROTOCOL_CAPABILITIES)[number];

export const PROTOCOL_METHODS = [
  "core.ping", "core.shutdown", "event.subscribe", "event.unsubscribe",
  "agent.run", "agent.subagent", "run.cancel", "run.get", "run.replay",
  "request.cancel", "$/cancelRequest", "permission.respond", "permission.set_mode",
  "session.create", "session.attach", "session.detach", "session.command", "session.get", "session.list",
  "session.history", "session.get_history", "session.send_message", "session.steer_message",
  "session.archive", "session.close", "session.compact", "session.delete", "session.fork", "session.pin", "session.rename", "session.resume", "session.set_workspace",
  "change.diff", "change.discard", "change.list", "change.revert", "change.stage", "change.unstage",
  "file.read", "file.search", "git.commit", "git.history",
  "artifact.create", "artifact.register", "artifact.get", "artifact.list", "artifact.verify",
  "operation.get", "operation.list", "operation.recover",
  "schedule.create", "schedule.list", "schedule.update", "schedule.pause", "schedule.delete",
  "plugin.catalog", "plugin.catalog_install", "plugin.install", "plugin.list", "plugin.marketplace_add", "plugin.marketplace_refresh", "plugin.marketplace_remove", "plugin.set_enabled", "plugin.uninstall",
  "provider.ccswitch_apply", "provider.ccswitch_list", "provider.model_benchmark", "provider.model_delete", "provider.model_list", "provider.model_save", "provider.model_select", "provider.model_test", "provider.status",
  "question.pending", "question.respond", "settings.get", "settings.update", "skill.install", "skill.list", "skill.set_enabled", "workflow.run",
  "workspace.archive", "workspace.delete", "workspace.list", "workspace.open", "workspace.pin", "workspace.profile", "workspace.rename", "workspace.resume", "workspace.status", "workspace.tree",
] as const;
export type ProtocolMethod = (typeof PROTOCOL_METHODS)[number];

export const JSON_RPC_ERROR_CODES = {
  PARSE_ERROR: -32700,
  INVALID_REQUEST: -32600,
  METHOD_NOT_FOUND: -32601,
  INVALID_PARAMS: -32602,
  INTERNAL_ERROR: -32603,
  VERSION_UNSUPPORTED: -32001,
  NOT_IMPLEMENTED: -32002,
  INVALID_STATE: -32003,
  NOT_FOUND: -32004,
  SESSION_BUSY: -32012,
  REQUEST_CANCELLED: -32013,
  IDEMPOTENCY_CONFLICT: -32014,
} as const;
/** Numeric JSON-RPC code; producers should use JSON_RPC_ERROR_CODES or a reserved extension. */
export type JsonRpcErrorCode = number;
export type IdempotencyKey = string;
export type RequestId = string;

export interface ProtocolError {
  code: JsonRpcErrorCode;
  message: string;
  data?: unknown;
}

export interface ClientHello {
  type: "hello";
  version: ProtocolVersion;
  client?: string;
  capabilities?: ProtocolCapability[];
}

export interface ServerHello {
  type: "hello";
  version: ProtocolVersion;
  server_version: string;
  capabilities: ProtocolCapability[];
  connection_id?: string;
}

export interface ServerHelloError {
  type: "hello_error";
  error: ProtocolError;
}

export interface JsonRpcRequest<P extends Record<string, unknown> = Record<string, unknown>> {
  jsonrpc: "2.0";
  id: RequestId;
  method: string;
  params: P;
  /** Caller supplied key for safe retries of mutating requests. */
  idempotency_key?: IdempotencyKey;
}

export interface JsonRpcSuccess<T = unknown> {
  jsonrpc: "2.0";
  id: string;
  result: T;
}

export interface JsonRpcError {
  jsonrpc: "2.0";
  id: RequestId | null;
  error: ProtocolError;
}

export type JsonRpcResponse<T = unknown> = JsonRpcSuccess<T> | JsonRpcError;

export interface EventEnvelope<E extends RuntimeEvent = RuntimeEvent> {
  kind: "event";
  event: E;
}

export type ClientWireMessage = ClientHello | JsonRpcRequest | JsonRpcNotification;
export type ServerWireMessage = ServerHello | ServerHelloError | JsonRpcResponse | EventEnvelope;

/** JSON-RPC notifications are accepted for cancellation and future server hints. */
export interface JsonRpcNotification<P extends Record<string, unknown> = Record<string, unknown>> {
  jsonrpc: "2.0";
  method: string;
  params: P;
  idempotency_key?: IdempotencyKey;
}

export interface PingParams { type?: "core.ping"; client: string }
export interface AgentRunParams { type?: "agent.run"; goal: string }
export interface RunCancelParams { type?: "run.cancel"; run_id: string }
export interface RunGetParams { type?: "run.get"; run_id: string }
export interface RunReplayParams { type?: "run.replay"; run_id: string; max_events?: number }
export interface RequestCancelParams { type?: "request.cancel" | "$/cancelRequest"; request_id: RequestId; reason?: string }
export interface PermissionRespondParams { type?: "permission.respond"; permission_id: string; decision: PermissionDecision }
export interface WorkspaceOpenParams { type?: "workspace.open"; path: string }
export interface WorkspaceListParams { type?: "workspace.list" }
export interface ArtifactCreateParams { type?: "artifact.create"; workspace_id: string; path: string; artifact_type?: "docx" | "pptx" | "pdf" | "xlsx" | "csv" | "other"; summary?: string; session_id?: string; run_id?: string; input_sources?: Array<{ path: string; version?: string; hash?: string }> }
export interface ArtifactRegisterParams extends Omit<ArtifactCreateParams, "type"> { type?: "artifact.register" }
export interface ArtifactGetParams { type?: "artifact.get"; workspace_id: string; artifact_id: string }
export interface ArtifactListParams { type?: "artifact.list"; workspace_id: string }
export interface ArtifactVerifyParams { type?: "artifact.verify"; workspace_id: string; artifact_id: string; status: "unverified" | "passed" | "failed"; summary?: string }

export interface PongResult { server_version: string; uptime_ms: number; received_at: string; capabilities: string[]; protocol_version?: ProtocolVersion }
export interface AgentRunResult { run_id: string }
export interface RunCancelResult { run_id: string; status: "cancelling" | "not_running" }
export interface RunGetResult { run_id: string; status: "running" | "completed" | "failed" | "cancelled" | "unknown" }
export interface RunReplayResult { run_id: string; events: RuntimeEvent[] }
export interface RequestCancelResult { request_id: RequestId; status: "cancelling" | "not_running" }
export interface WorkspaceSummary { workspace_id: string; path: string; name: string; archived: boolean; pinned?: boolean }
export interface WorkspaceOpenResult { workspace: WorkspaceSummary }
export interface WorkspaceListResult { workspaces: WorkspaceSummary[] }
export interface SessionCreateParams { type?: "session.create"; mode?: "one_shot" | "chat"; title?: string; workspace_id?: string | null }
export interface SessionAttachParams { type?: "session.attach"; session_id: string }
export interface SessionDetachParams { type?: "session.detach"; session_id: string }
export interface SessionForkParams { type?: "session.fork"; session_id: string; title?: string }
export interface SessionGetParams { type?: "session.get"; session_id: string }
export interface SessionListParams { type?: "session.list"; include_archived?: boolean }
export interface SessionHistoryParams { type?: "session.history" | "session.get_history"; session_id: string }
export interface MessageImageBlock { type: "image"; media_type: string; data: string }
export interface SessionSendMessageParams { type?: "session.send_message"; session_id: string; content: string; images?: MessageImageBlock[]; client_message_id?: string }
export interface SessionSteerMessageParams { type?: "session.steer_message"; session_id: string; content: string; images?: MessageImageBlock[] }
export interface SessionPromptParams { type?: "session.prompt"; session_id: string; content: string; client_message_id?: string }
export interface SessionAbortParams { type?: "session.abort"; session_id: string; run_id?: string }
export interface SessionSetModelParams { type?: "session.set_model"; session_id: string; model: string }
export interface SessionSetThinkingParams { type?: "session.set_thinking"; session_id: string; thinking_level: string }
export interface EventSubscribeParams { type?: "event.subscribe"; topics?: string[]; scope?: string }
export interface EventSubscribeResult { subscribed: string[]; scope: string }
export type SessionStatus = "active" | "waiting_for_input" | "closed";
export interface SessionSnapshot {
  session_id: string;
  mode: "one_shot" | "chat";
  status: SessionStatus;
  title: string;
  created_at?: string;
  updated_at: string;
  run_count: number;
  archived: boolean;
  pinned: boolean;
  workspace_id: string | null;
  latest_run_id: string | null;
  attached?: boolean;
  locked?: boolean;
  phase?: "idle" | "running" | "steering" | "aborting" | "closed";
  revision?: number;
}
export interface SessionMetadata {
  session_id: string;
  title?: string;
  mode?: "one_shot" | "chat";
  status?: SessionStatus;
  updated_at?: string;
  archived?: boolean;
  workspace_id?: string | null;
}
export interface ServerSnapshot {
  server_id?: string;
  protocol_version: ProtocolVersion;
  revision: number;
  sessions: SessionMetadata[];
  models?: unknown[];
}
export interface SessionCommandList { command: "list" }
export interface SessionCommandCreate { command: "create"; cwd?: string; name?: string; model?: string; thinkingLevel?: string }
export interface SessionCommandAttach { command: "attach"; sessionId: string }
export interface SessionCommandDetach { command: "detach"; sessionId: string }
export interface SessionCommandPrompt { command: "prompt"; sessionId: string; text: string }
export interface SessionCommandSteer { command: "steer"; sessionId: string; text: string }
export interface SessionCommandAbort { command: "abort"; sessionId: string }
export interface SessionCommandSetModel { command: "set_model"; sessionId: string; model: string }
export interface SessionCommandSetThinking { command: "set_thinking"; sessionId: string; thinkingLevel: string }
export type SessionCommand = SessionCommandList | SessionCommandCreate | SessionCommandAttach | SessionCommandDetach | SessionCommandPrompt | SessionCommandSteer | SessionCommandAbort | SessionCommandSetModel | SessionCommandSetThinking;
export interface SessionCommandParams { type?: "session.command"; command: SessionCommand }
export type SessionCommandResult =
  | { command: "list"; sessions: SessionMetadata[] }
  | { command: "create" | "attach" | "prompt" | "steer" | "abort" | "set_model" | "set_thinking"; session: SessionSnapshot }
  | { command: "detach"; sessionId: string };
export type SessionCommandResultFor<T extends SessionCommand> = Extract<SessionCommandResult, { command: T["command"] }>;
export interface SessionResult { session: SessionSnapshot }
export interface SessionAttachResult { session_id: string; attached: true; session: SessionSnapshot }
export interface SessionDetachResult { session_id: string; attached: false; session?: SessionSnapshot }
export interface SessionListResult { sessions: SessionResult["session"][] }
export interface SessionHistoryResult { messages: Array<{ role: "user" | "assistant"; content: string; ts: string; run_id?: string }> }

export type KnownJsonRpcRequest =
  | { jsonrpc: "2.0"; id: RequestId; method: "core.ping"; params: PingParams; idempotency_key?: IdempotencyKey }
  | { jsonrpc: "2.0"; id: RequestId; method: "agent.run"; params: AgentRunParams; idempotency_key?: IdempotencyKey }
  | { jsonrpc: "2.0"; id: RequestId; method: "run.cancel"; params: RunCancelParams; idempotency_key?: IdempotencyKey }
  | { jsonrpc: "2.0"; id: RequestId; method: "run.get"; params: RunGetParams; idempotency_key?: IdempotencyKey }
  | { jsonrpc: "2.0"; id: RequestId; method: "run.replay"; params: RunReplayParams; idempotency_key?: IdempotencyKey }
  | { jsonrpc: "2.0"; id: RequestId; method: "request.cancel" | "$/cancelRequest"; params: RequestCancelParams; idempotency_key?: IdempotencyKey }
  | { jsonrpc: "2.0"; id: RequestId; method: "session.create"; params: SessionCreateParams; idempotency_key?: IdempotencyKey }
  | { jsonrpc: "2.0"; id: RequestId; method: "session.attach"; params: SessionAttachParams; idempotency_key?: IdempotencyKey }
  | { jsonrpc: "2.0"; id: RequestId; method: "session.detach"; params: SessionDetachParams; idempotency_key?: IdempotencyKey }
  | { jsonrpc: "2.0"; id: RequestId; method: "session.get"; params: SessionGetParams; idempotency_key?: IdempotencyKey }
  | { jsonrpc: "2.0"; id: RequestId; method: "session.list"; params: SessionListParams; idempotency_key?: IdempotencyKey }
  | { jsonrpc: "2.0"; id: RequestId; method: "session.history" | "session.get_history"; params: SessionHistoryParams; idempotency_key?: IdempotencyKey }
  | { jsonrpc: "2.0"; id: RequestId; method: "session.send_message"; params: SessionSendMessageParams; idempotency_key?: IdempotencyKey }
  | { jsonrpc: "2.0"; id: RequestId; method: "session.steer_message"; params: SessionSteerMessageParams; idempotency_key?: IdempotencyKey }
  | { jsonrpc: "2.0"; id: RequestId; method: "session.command"; params: SessionCommandParams; idempotency_key?: IdempotencyKey };

export type KnownRequestParams = KnownJsonRpcRequest["params"];

export interface WorkflowTask {
  id: string; title: string; description: string; owner: WorkflowRole;
  dependencies: string[]; completion_criteria: string[]; allowed_paths: string[];
  depth: number; token_budget: number; time_budget_s: number; max_retries: number | null;
}
export interface WorkflowGraph { workflow_id: string; goal: string; planner_summary: string; tasks: WorkflowTask[]; parent_session_id?: string }
export interface HandoffArtifact {
  workflow_id: string; task_id: string; role: WorkflowRole; status: "succeeded" | "failed";
  summary: string; changed_paths: string[]; scope_escalations: string[]; commands: string[];
  output: string; conclusion: string; diff_summary: string; test_summary: string;
  security_summary: string; review_decision: "accept" | "return" | null;
  tokens: number; elapsed_s: number; attempt: number; child_run_id: string;
  /** Correlation fields for parent/child SessionRuntime execution. */
  parent_run_id?: string; child_session_id?: string;
}
export interface WorkflowTaskResult { task: WorkflowTask; status: WorkflowTaskStatus; attempts: number; artifact: HandoffArtifact | null; error: string; tokens: number; child_session_id?: string; parent_run_id?: string }
export interface WorkflowResult { workflow_id: string; status: WorkflowStatus; reason: string; tasks: WorkflowTaskResult[]; total_tokens: number; elapsed_s: number; parent_run_id?: string }

export interface CoreStartedEvent { type: "core.started"; listen_addr: string; version: string }
export interface RunStartedEvent { type: "run.started"; run_id: string; goal: string; ts: string }
export interface OperationStartedEvent { type: "operation.started"; run_id: string; operation_id: string; goal: string; ts: string }
export interface OperationFinishedEvent { type: "operation.finished"; run_id: string; operation_id: string; status: "completed" | "failed" | "cancelled"; steps: number; ts: string }
export interface RunFinishedEvent { type: "run.finished"; run_id: string; status: "success" | "failed" | "cancelled"; reason?: string; steps: number; total_input_tokens: number; total_output_tokens: number; cache_read_input_tokens: number; cache_creation_input_tokens: number; elapsed_s: number; context_pct: number; parent_session_id?: string; ts: string }
export interface StepStartedEvent { type: "step.started"; run_id: string; step: number; ts: string }
export interface StepFinishedEvent { type: "step.finished"; run_id: string; step: number; ts: string }
/**
 * 一次 run 的执行阶段。粒度刻意做粗——每完成一类动作才推进一次，
 * 避免逐步跳变让调用方看不出「现在在干嘛」。由 daemon 在 agent-loop 里判定并推送。
 */
export type AgentPhase = "understanding" | "executing" | "verifying" | "delivering";
export interface PhaseChangedEvent { type: "phase.changed"; run_id: string; step: number; phase: AgentPhase; previous?: AgentPhase; reason: string; ts: string }
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
export interface SubagentStartedEvent { type: "subagent.started"; run_id: string; parent_run_id: string; parent_session_id?: string; child_session_id?: string; description: string; ts: string }
export interface SubagentFinishedEvent { type: "subagent.finished"; run_id: string; parent_run_id: string; parent_session_id?: string; child_session_id?: string; status: "success" | "failed"; ts: string }
export interface WorkflowTaskSnapshot { id: string; title: string; owner: WorkflowRole; status: WorkflowTaskStatus; dependencies: string[]; completion_criteria: string[]; allowed_paths: string[]; attempt: number; error: string; child_session_id?: string; parent_run_id?: string }
export interface WorkflowStartedEvent { type: "workflow.started"; run_id: string; workflow_id: string; goal: string; planner_summary: string; tasks: WorkflowTaskSnapshot[]; parent_run_id?: string; parent_session_id?: string; ts: string }
export interface WorkflowTaskUpdatedEvent { type: "workflow.task_updated"; run_id: string; workflow_id: string; task: WorkflowTaskSnapshot; parent_run_id?: string; parent_session_id?: string; ts: string }
export interface WorkflowHandoffEvent { type: "workflow.handoff"; run_id: string; workflow_id: string; artifact: HandoffArtifact; parent_run_id?: string; ts: string }
export interface WorkflowReviewedEvent { type: "workflow.reviewed"; run_id: string; workflow_id: string; task_id: string; decision: "accept" | "return"; diff_summary: string; test_summary: string; security_summary: string; conclusion: string; parent_run_id?: string; ts: string }
export interface WorkflowFinishedEvent { type: "workflow.finished"; run_id: string; workflow_id: string; status: WorkflowStatus; reason: string; total_tokens: number; elapsed_s: number; parent_run_id?: string; parent_session_id?: string; ts: string }
export interface SessionLifecycleEvent { type: "session.created" | "session.waiting_for_input" | "session.closed"; session_id: string; mode?: "one_shot" | "chat"; last_run_id?: string; ts: string }
export interface SessionSnapshotEvent { type: "session.snapshot"; session_id: string; snapshot: SessionSnapshot; ts: string }
export interface SessionAttachedEvent { type: "session.attached" | "session.detached"; session_id: string; attached: boolean; ts: string }
export interface SessionMessageSteeredEvent { type: "session.message_steered"; session_id: string; run_id: string; content: string; ts: string }
export interface SkillInvokedEvent { type: "skill.invoked"; skill_name: string; arguments: string; run_id: string; ts: string }
export interface ContextCompactingEvent { type: "context.compacting"; session_id: string; run_id: string; ts: string }
export interface ContextCompactedEvent { type: "context.compacted"; session_id: string; run_id: string; original_tokens: number; summary_tokens: number; ts: string }
export interface PlanItem { id: number; subject: string; status: "pending" | "in_progress" | "completed"; blocked_by: number[] }
export interface PlanUpdatedEvent { type: "plan.updated"; run_id: string; session_id: string; items: PlanItem[]; ts: string }
export interface TestResultEvent { type: "test.result"; run_id: string; tool_use_id: string; status: "passed" | "failed"; summary: string; ts: string }
export interface ChangeAppliedEvent { type: "change.applied"; run_id: string; workspace_path: string; paths: string[]; ts: string }
export interface PermissionModeChangedEvent { type: "permission.mode_changed"; old_mode: PermissionMode; new_mode: PermissionMode; ts: string }

export type RuntimeEvent = CoreStartedEvent | OperationStartedEvent | OperationFinishedEvent | RunStartedEvent | RunFinishedEvent | StepStartedEvent | StepFinishedEvent | PhaseChangedEvent | LlmTokenEvent | LlmThinkingEvent | LlmUsageEvent | PermissionRequestedEvent | PermissionResolvedEvent | PermissionGrantedEvent | PermissionDeniedEvent | DenialInterventionEvent | StuckLoopEvent | ToolCallStartedEvent | ToolCallFinishedEvent | ToolCallFailedEvent | LogLineEvent | ContextInjectedEvent | SessionMessageReceivedEvent | QuestionRequestedEvent | QuestionResolvedEvent | SubagentStartedEvent | SubagentFinishedEvent | WorkflowTaskUpdatedEvent | WorkflowHandoffEvent | WorkflowReviewedEvent | WorkflowFinishedEvent | SessionLifecycleEvent | SessionSnapshotEvent | SessionAttachedEvent | SessionMessageSteeredEvent | SkillInvokedEvent | ContextCompactingEvent | ContextCompactedEvent | PlanUpdatedEvent | TestResultEvent | ChangeAppliedEvent | PermissionModeChangedEvent | WorkflowStartedEvent;

export type ValidationResult<T> =
  | { ok: true; value: T }
  | { ok: false; code: typeof JSON_RPC_ERROR_CODES.INVALID_REQUEST | typeof JSON_RPC_ERROR_CODES.INVALID_PARAMS; message: string; field?: string };

const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const nonEmptyString = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;
const optionalString = (value: unknown): boolean => value === undefined || typeof value === "string";
const optionalBoolean = (value: unknown): boolean => value === undefined || typeof value === "boolean";
const optionalNonNegativeInteger = (value: unknown): boolean => value === undefined || (Number.isInteger(value) && Number(value) >= 0);

function invalidParams(message: string, field?: string): ValidationResult<never> {
  return { ok: false, code: JSON_RPC_ERROR_CODES.INVALID_PARAMS, message, ...(field ? { field } : {}) };
}

function requireId(params: Record<string, unknown>, field: string): ValidationResult<Record<string, unknown>> {
  return nonEmptyString(params[field]) ? { ok: true, value: params } : invalidParams(`${field} must be a non-empty string`, field);
}

/** Validate the known request parameters without rejecting future optional fields. */
export function validateRequestParams(method: string, params: unknown): ValidationResult<Record<string, unknown>> {
  if (!isRecord(params)) return invalidParams("params must be an object");
  const value = params;
  if (value.type !== undefined && value.type !== method) {
    const aliases = method === "session.history" || method === "session.get_history" ? ["session.history", "session.get_history"] : method === "request.cancel" || method === "$/cancelRequest" ? ["request.cancel", "$/cancelRequest"] : [method];
    if (!aliases.includes(String(value.type))) return invalidParams(`params.type must match ${method}`, "type");
  }
  switch (method) {
    case "core.ping": return nonEmptyString(value.client) ? { ok: true, value } : invalidParams("client must be a non-empty string", "client");
    case "agent.run": return nonEmptyString(value.goal) ? { ok: true, value } : invalidParams("goal must be a non-empty string", "goal");
    case "run.cancel": case "run.get": return requireId(value, "run_id");
    case "run.replay": {
      const id = requireId(value, "run_id");
      return !id.ok ? id : optionalNonNegativeInteger(value.max_events) ? { ok: true, value } : invalidParams("max_events must be a non-negative integer", "max_events");
    }
    case "request.cancel": case "$/cancelRequest": return requireId(value, "request_id");
    case "permission.respond": return nonEmptyString(value.permission_id) && ["allow_once", "always_allow", "deny_once", "always_deny"].includes(String(value.decision)) ? { ok: true, value } : invalidParams("permission_id and a valid decision are required");
    case "session.create": return (value.mode === undefined || value.mode === "chat" || value.mode === "one_shot") && optionalString(value.title) && (value.workspace_id === undefined || value.workspace_id === null || nonEmptyString(value.workspace_id)) ? { ok: true, value } : invalidParams("invalid session.create parameters");
    case "session.attach": case "session.detach": case "session.get": case "session.history": case "session.get_history": return requireId(value, "session_id");
    case "session.list": return optionalBoolean(value.include_archived) ? { ok: true, value } : invalidParams("include_archived must be boolean", "include_archived");
    case "session.send_message": case "session.steer_message": return nonEmptyString(value.session_id) && nonEmptyString(value.content) && optionalString(value.client_message_id) && (value.images === undefined || (Array.isArray(value.images) && value.images.every((image) => isRecord(image) && image.type === "image" && nonEmptyString(image.media_type) && nonEmptyString(image.data)))) ? { ok: true, value } : invalidParams("session_id and content are required and images must be valid image blocks");
    default: return { ok: true, value };
  }
}

/** Validate an incoming JSON-RPC request at the wire boundary. */
export function validateJsonRpcRequest(value: unknown): ValidationResult<JsonRpcRequest> {
  if (!isRecord(value) || value.jsonrpc !== "2.0" || !nonEmptyString(value.id) || !nonEmptyString(value.method)) {
    return { ok: false, code: JSON_RPC_ERROR_CODES.INVALID_REQUEST, message: "Invalid Request" };
  }
  if (value.idempotency_key !== undefined && !nonEmptyString(value.idempotency_key)) return invalidParams("idempotency_key must be a non-empty string", "idempotency_key");
  const params = value.params ?? {};
  const checked = validateRequestParams(String(value.method), params);
  if (!checked.ok) return checked;
  return { ok: true, value: { jsonrpc: "2.0", id: String(value.id), method: String(value.method), params: checked.value, ...(value.idempotency_key === undefined ? {} : { idempotency_key: String(value.idempotency_key) }) } };
}

export function isClientHello(value: unknown): value is ClientHello {
  return isRecord(value) && value.type === "hello" && value.version === PROTOCOL_VERSION && (value.client === undefined || typeof value.client === "string") && (value.capabilities === undefined || Array.isArray(value.capabilities));
}

export function isServerHello(value: unknown): value is ServerHello {
  return isRecord(value) && value.type === "hello" && value.version === PROTOCOL_VERSION && nonEmptyString(value.server_version) && Array.isArray(value.capabilities);
}

export function isProtocolError(value: unknown): value is ProtocolError {
  return isRecord(value) && typeof value.code === "number" && Number.isInteger(value.code) && nonEmptyString(value.message);
}

export function isServerHelloError(value: unknown): value is ServerHelloError {
  return isRecord(value) && value.type === "hello_error" && isProtocolError(value.error);
}

export function isJsonRpcRequest(value: unknown): value is JsonRpcRequest {
  return validateJsonRpcRequest(value).ok;
}

export function isEventEnvelope(value: unknown): value is EventEnvelope {
  return isRecord(value) && value.kind === "event" && isRuntimeEvent(value.event);
}

export function isWireMessage(value: unknown): value is ClientWireMessage | ServerWireMessage {
  return isClientHello(value) || isServerHello(value) || isServerHelloError(value) || isJsonRpcRequest(value) || isJsonRpcResponse(value) || isEventEnvelope(value);
}

export function isJsonRpcResponse(value: unknown): value is JsonRpcResponse {
  if (!isRecord(value) || value.jsonrpc !== "2.0" || !(typeof value.id === "string" || value.id === null)) return false;
  const hasResult = "result" in value;
  const hasError = "error" in value;
  return hasResult !== hasError && (!hasError || isProtocolError(value.error));
}

export function isRuntimeEvent(value: unknown): value is RuntimeEvent {
  return !!value && typeof value === "object" && typeof (value as { type?: unknown }).type === "string";
}
