from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

WorkflowRole = Literal["planner", "coder", "tester", "reviewer"]
WorkflowTaskStatus = Literal[
    "pending",
    "running",
    "succeeded",
    "failed",
    "blocked",
    "cancelled",
    "timed_out",
    "rejected",
]
WorkflowStatus = Literal["succeeded", "failed", "cancelled", "timed_out"]
ReviewDecision = Literal["accept", "return"]


class WorkflowTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    owner: WorkflowRole
    dependencies: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(min_length=1)
    allowed_paths: list[str] = Field(default_factory=list)
    depth: int = Field(default=0, ge=0)
    token_budget: int = Field(default=0, ge=0)
    time_budget_s: float = Field(default=0.0, ge=0.0)
    max_retries: int | None = Field(default=None, ge=0)


class WorkflowGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    planner_summary: str = Field(min_length=1)
    tasks: list[WorkflowTask] = Field(min_length=1)


class WorkflowLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_concurrency: int = Field(default=4, ge=1)
    max_depth: int = Field(default=2, ge=0)
    max_tokens: int = Field(default=0, ge=0)
    max_wall_clock_s: float = Field(default=0.0, ge=0.0)
    max_retries: int = Field(default=1, ge=0)


class HandoffArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    task_id: str
    role: WorkflowRole
    status: Literal["succeeded", "failed"]
    summary: str = Field(min_length=1)
    changed_paths: list[str] = Field(default_factory=list)
    scope_escalations: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    output: str = ""
    conclusion: str = ""
    diff_summary: str = ""
    test_summary: str = ""
    security_summary: str = ""
    review_decision: ReviewDecision | None = None
    tokens: int = Field(default=0, ge=0)
    elapsed_s: float = Field(default=0.0, ge=0.0)
    attempt: int = Field(default=1, ge=1)
    child_run_id: str = ""


class WorkflowTaskResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: WorkflowTask
    status: WorkflowTaskStatus = "pending"
    attempts: int = 0
    artifact: HandoffArtifact | None = None
    error: str = ""
    tokens: int = Field(default=0, ge=0)


class WorkflowResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str
    status: WorkflowStatus
    reason: str = ""
    tasks: list[WorkflowTaskResult]
    total_tokens: int = Field(default=0, ge=0)
    elapsed_s: float = Field(default=0.0, ge=0.0)


class SingleAgentBaseline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    completion_checks: int = Field(default=0, ge=0)
    independent_test_evidence: bool = False
    independent_review_evidence: bool = False
    trace_handoffs: int = Field(default=0, ge=0)
    tokens: int = Field(default=0, ge=0)
    elapsed_s: float = Field(default=0.0, ge=0.0)


class WorkflowComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    workflow_completion_checks: int
    baseline_completion_checks: int
    workflow_has_independent_test: bool
    baseline_has_independent_test: bool
    workflow_has_independent_review: bool
    baseline_has_independent_review: bool
    workflow_trace_handoffs: int
    baseline_trace_handoffs: int
    workflow_tokens: int
    baseline_tokens: int
    workflow_elapsed_s: float
    baseline_elapsed_s: float
