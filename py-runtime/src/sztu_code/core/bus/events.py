from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Discriminator

from sztu_code.core.bus.commands import UserQuestionItem

ToolSchedulerMode = Literal["serial", "concurrent"]


class CoreStartedEvent(BaseModel):
    type: Literal["core.started"] = "core.started"
    listen_addr: str  # e.g. "127.0.0.1:7437"
    version: str


class RunStartedEvent(BaseModel):
    type: Literal["run.started"] = "run.started"
    run_id: str
    goal: str
    ts: str  # ISO 8601


class RunFinishedEvent(BaseModel):
    type: Literal["run.finished"] = "run.finished"
    run_id: str
    status: str  # "success" | "failed"
    reason: str | None = None  # "exceeded_max_steps" | "cancelled" | "llm_error" | ...
    steps: int
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    cache_read_input_tokens: int = 0
    elapsed_s: float = 0.0
    context_pct: float = 0.0  # 最近一次 LLM 调用的上下文占用百分比
    ts: str


class StepStartedEvent(BaseModel):
    type: Literal["step.started"] = "step.started"
    run_id: str
    step: int
    ts: str


class StepFinishedEvent(BaseModel):
    type: Literal["step.finished"] = "step.finished"
    run_id: str
    step: int
    ts: str


class ToolCallStartedEvent(BaseModel):
    type: Literal["tool.call_started"] = "tool.call_started"
    run_id: str
    tool_use_id: str
    tool_name: str
    params: dict[str, Any]
    # 同一模型回合的工具批次标识；空值代表未经过批次调度的兼容调用
    batch_id: str = ""
    # 供 Trace/TUI 区分调度方式
    scheduler_mode: ToolSchedulerMode = "serial"
    # 从批次入队到实际开始调用的等待时长
    queue_ms: int = 0
    # 工具进入队列与实际开始执行的 UTC 时间戳
    queued_at: str = ""
    started_at: str = ""
    ts: str


class ToolCallFinishedEvent(BaseModel):
    type: Literal["tool.call_finished"] = "tool.call_finished"
    run_id: str
    tool_use_id: str
    tool_name: str
    elapsed_ms: int
    output: str = ""  # tool result content, for TUI display
    batch_id: str = ""
    scheduler_mode: ToolSchedulerMode = "serial"
    queue_ms: int = 0
    queued_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    ts: str


class ToolCallFailedEvent(BaseModel):
    type: Literal["tool.call_failed"] = "tool.call_failed"
    run_id: str
    tool_use_id: str
    tool_name: str
    # "runtime_error" | "timeout" | "schema_error" | "permission_denied" | "rate_limited"
    error_class: str
    error_message: str
    elapsed_ms: int
    attempt: int = 1  # 1=first attempt, 2=first retry, 3=second retry
    retry_decision: Literal["retry", "stop"] = "stop"
    retry_reason: str = ""
    retry_delay_ms: int = 0
    tool_retry_safe: bool = False
    execution_state: str = "completed"
    batch_id: str = ""
    scheduler_mode: ToolSchedulerMode = "serial"
    queue_ms: int = 0
    queued_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    ts: str


class LlmTokenEvent(BaseModel):
    type: Literal["llm.token"] = "llm.token"
    run_id: str
    token: str
    ts: str


class LlmThinkingEvent(BaseModel):
    type: Literal["llm.thinking"] = "llm.thinking"
    run_id: str
    step: int
    thinking: str
    ts: str


class LlmUsageEvent(BaseModel):
    type: Literal["llm.usage"] = "llm.usage"
    run_id: str
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    context_pct: float = 0.0
    model: str = ""  # 当前使用的模型名
    context_window: int = 0
    available_tokens: int = 0
    reserved_output_tokens: int = 0
    system_tokens: int = 0
    summary_tokens: int = 0
    conversation_tokens: int = 0
    tool_tokens: int = 0
    ts: str


class LlmModelSelectedEvent(BaseModel):
    type: Literal["llm.model_selected"] = "llm.model_selected"
    run_id: str
    model: str
    strategy: str  # "static" | "rule_based" | "cost_budget"
    ts: str


class ContextInjectedEvent(BaseModel):
    type: Literal["context.injected"] = "context.injected"
    run_id: str
    # 新事件统一为 system；其余值用于读取旧版分层注入事件。
    source: Literal["system", "global", "project", "session"]
    label: str  # 展示名（当前为 "上下文注入"）
    chars: int = 0  # 注入内容字符数
    preview: str = ""  # 首行预览（前端折叠行摘要）
    text: str = ""  # 完整注入正文（旧事件缺省时前端回退 preview）
    ts: str


class LogLineEvent(BaseModel):
    type: Literal["log.line"] = "log.line"
    run_id: str
    level: str  # "DEBUG" | "INFO" | "WARNING" | "ERROR"
    source: str
    message: str
    ts: str


class SessionCreatedEvent(BaseModel):
    type: Literal["session.created"] = "session.created"
    session_id: str
    mode: str
    ts: str


class SessionMessageReceivedEvent(BaseModel):
    type: Literal["session.message_received"] = "session.message_received"
    session_id: str
    content: str
    ts: str


class SessionWaitingForInputEvent(BaseModel):
    type: Literal["session.waiting_for_input"] = "session.waiting_for_input"
    session_id: str
    last_run_id: str
    ts: str


class SessionResumedEvent(BaseModel):
    type: Literal["session.resumed"] = "session.resumed"
    session_id: str
    ts: str


class SessionClosedEvent(BaseModel):
    type: Literal["session.closed"] = "session.closed"
    session_id: str
    ts: str


class ContextCompactedEvent(BaseModel):
    type: Literal["context.compacted"] = "context.compacted"
    session_id: str
    run_id: str
    original_tokens: int
    summary_tokens: int
    ts: str


class ContextCompactingEvent(BaseModel):
    type: Literal["context.compacting"] = "context.compacting"
    session_id: str
    run_id: str
    ts: str


class PermissionRequestedEvent(BaseModel):
    type: Literal["permission.requested"] = "permission.requested"
    run_id: str
    tool_use_id: str
    tool_name: str
    params: dict[str, Any]
    param_preview: str
    session_id: str
    ts: str


class PermissionGrantedEvent(BaseModel):
    type: Literal["permission.granted"] = "permission.granted"
    run_id: str
    tool_use_id: str
    # "allow_once" | "always_allow" | "auto_allow"
    decision: str
    ts: str


class PermissionDeniedEvent(BaseModel):
    type: Literal["permission.denied"] = "permission.denied"
    run_id: str
    tool_use_id: str
    # "deny_once" | "always_deny" | "auto_deny"
    decision: str
    ts: str


class SessionMessageSteeredEvent(BaseModel):
    type: Literal["session.message_steered"] = "session.message_steered"
    session_id: str
    run_id: str
    content: str
    ts: str


class UserQuestionRequestedEvent(BaseModel):
    type: Literal["question.requested"] = "question.requested"
    rpc_id: str
    session_id: str
    run_id: str
    questions: list[UserQuestionItem]
    ts: str


class UserQuestionResolvedEvent(BaseModel):
    type: Literal["question.resolved"] = "question.resolved"
    rpc_id: str
    session_id: str
    run_id: str
    outcome: Literal["answered", "cancelled"]
    ts: str


class DenialInterventionEvent(BaseModel):
    type: Literal["denial.intervention"] = "denial.intervention"
    run_id: str
    tool_name: str  # 触发熔断的工具名
    consecutive_count: int
    total_denials: int
    message: str  # 注入给 LLM 的干预消息
    ts: str


class StuckLoopEvent(BaseModel):
    type: Literal["stuck.loop"] = "stuck.loop"
    run_id: str
    signature: str  # 触发干预/硬停的工具签名（tool_name:key）
    consecutive_count: int
    total_interventions: int
    message: str  # 注入给 LLM 的干预消息
    ts: str


class PermissionModeChangedEvent(BaseModel):
    type: Literal["permission.mode_changed"] = "permission.mode_changed"
    old_mode: str
    new_mode: str
    ts: str


class SubagentStartedEvent(BaseModel):
    type: Literal["subagent.started"] = "subagent.started"
    run_id: str          # 子 agent run_id
    parent_run_id: str
    description: str
    ts: str


class SubagentFinishedEvent(BaseModel):
    type: Literal["subagent.finished"] = "subagent.finished"
    run_id: str
    parent_run_id: str
    status: str          # "success" | "failed"
    ts: str


class SkillInvokedEvent(BaseModel):
    type: Literal["skill.invoked"] = "skill.invoked"
    skill_name: str
    arguments: str
    run_id: str
    ts: str


class PlanItem(BaseModel):
    id: int
    subject: str
    status: Literal["pending", "in_progress", "completed"]
    blocked_by: list[int]


class PlanUpdatedEvent(BaseModel):
    type: Literal["plan.updated"] = "plan.updated"
    run_id: str
    session_id: str = ""
    items: list[PlanItem]
    ts: str


class TestResultEvent(BaseModel):
    type: Literal["test.result"] = "test.result"
    run_id: str
    tool_use_id: str
    status: Literal["passed", "failed"]
    summary: str
    ts: str


class ChangeAppliedEvent(BaseModel):
    type: Literal["change.applied"] = "change.applied"
    run_id: str
    workspace_path: str
    paths: list[str]
    ts: str


class WorkflowTaskSnapshot(BaseModel):
    id: str
    title: str
    owner: Literal["planner", "coder", "tester", "reviewer"]
    status: Literal[
        "pending",
        "running",
        "succeeded",
        "failed",
        "blocked",
        "cancelled",
        "timed_out",
        "rejected",
    ]
    dependencies: list[str]
    completion_criteria: list[str]
    allowed_paths: list[str]
    attempt: int = 0
    error: str = ""


class WorkflowHandoffSnapshot(BaseModel):
    task_id: str
    role: Literal["planner", "coder", "tester", "reviewer"]
    status: Literal["succeeded", "failed"]
    summary: str
    changed_paths: list[str]
    scope_escalations: list[str]
    commands: list[str]
    output: str
    conclusion: str
    diff_summary: str
    test_summary: str
    security_summary: str
    review_decision: Literal["accept", "return"] | None = None
    tokens: int = 0
    elapsed_s: float = 0.0
    attempt: int = 1
    child_run_id: str = ""


class WorkflowStartedEvent(BaseModel):
    type: Literal["workflow.started"] = "workflow.started"
    run_id: str
    workflow_id: str
    goal: str
    planner_summary: str
    tasks: list[WorkflowTaskSnapshot]
    ts: str


class WorkflowTaskUpdatedEvent(BaseModel):
    type: Literal["workflow.task_updated"] = "workflow.task_updated"
    run_id: str
    workflow_id: str
    task: WorkflowTaskSnapshot
    ts: str


class WorkflowHandoffEvent(BaseModel):
    type: Literal["workflow.handoff"] = "workflow.handoff"
    run_id: str
    workflow_id: str
    artifact: WorkflowHandoffSnapshot
    ts: str


class WorkflowReviewEvent(BaseModel):
    type: Literal["workflow.reviewed"] = "workflow.reviewed"
    run_id: str
    workflow_id: str
    task_id: str
    decision: Literal["accept", "return"]
    diff_summary: str
    test_summary: str
    security_summary: str
    conclusion: str
    ts: str


class WorkflowFinishedEvent(BaseModel):
    type: Literal["workflow.finished"] = "workflow.finished"
    run_id: str
    workflow_id: str
    status: Literal["succeeded", "failed", "cancelled", "timed_out"]
    reason: str
    total_tokens: int
    elapsed_s: float
    ts: str


# 根据 type 字段决定事件类型的判别联合
Event = Annotated[
    CoreStartedEvent
    | RunStartedEvent
    | RunFinishedEvent
    | StepStartedEvent
    | StepFinishedEvent
    | ToolCallStartedEvent
    | ToolCallFinishedEvent
    | ToolCallFailedEvent
    | LlmTokenEvent
    | LlmThinkingEvent
    | LlmUsageEvent
    | LlmModelSelectedEvent
    | ContextInjectedEvent
    | LogLineEvent
    | SessionCreatedEvent
    | SessionMessageReceivedEvent
    | SessionMessageSteeredEvent
    | SessionWaitingForInputEvent
    | SessionResumedEvent
    | SessionClosedEvent
    | ContextCompactingEvent
    | ContextCompactedEvent
    | DenialInterventionEvent
    | StuckLoopEvent
    | PermissionRequestedEvent
    | PermissionGrantedEvent
    | PermissionDeniedEvent
    | UserQuestionRequestedEvent
    | UserQuestionResolvedEvent
    | SubagentStartedEvent
    | SubagentFinishedEvent
    | SkillInvokedEvent
    | PlanUpdatedEvent
    | TestResultEvent
    | ChangeAppliedEvent
    | WorkflowStartedEvent
    | WorkflowTaskUpdatedEvent
    | WorkflowHandoffEvent
    | WorkflowReviewEvent
    | WorkflowFinishedEvent
    | PermissionModeChangedEvent,
    Discriminator("type"),
]
