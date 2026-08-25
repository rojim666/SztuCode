from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION: Final[Literal["1.0"]] = "1.0"


class TaskCategory(StrEnum):
    LONG_CONTEXT = "long_context"
    CROSS_LANGUAGE = "cross_language"
    SECURITY = "security"
    COLLABORATION = "collaboration"
    GENERAL = "general"


class RunStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    UNSCORED = "unscored"


class FailureReason(StrEnum):
    SETUP_FAILED = "setup_failed"
    RUNNER_FAILED = "runner_failed"
    TIMEOUT = "timeout"
    VALIDATION_FAILED = "validation_failed"
    SCOPE_VIOLATION = "scope_violation"
    INVALID_METRICS = "invalid_metrics"
    UNSUPPORTED_TASK = "unsupported_task"
    INTERNAL_ERROR = "internal_error"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ValidationSpec(StrictModel):
    command: list[str] = Field(min_length=1)
    timeout_seconds: float = Field(default=30.0, gt=0)


class FileChange(StrictModel):
    path: str = Field(min_length=1)
    content: str


class CommonTask(StrictModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]+$")
    title: str = Field(min_length=1)
    category: TaskCategory
    prompt: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class InternalTask(CommonTask):
    source: Literal["internal"] = "internal"
    workspace_files: dict[str, str] = Field(min_length=1)
    validation: ValidationSpec
    expected_modified_files: list[str] = Field(min_length=1)
    reference_changes: list[FileChange] = Field(min_length=1)


class SwebenchLiteTask(CommonTask):
    source: Literal["swebench_lite"] = "swebench_lite"
    repo: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    base_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    instance_id: str = Field(min_length=1)
    fail_to_pass: list[str] = Field(default_factory=list)
    pass_to_pass: list[str] = Field(default_factory=list)


EvaluationTask = Annotated[
    InternalTask | SwebenchLiteTask,
    Field(discriminator="source"),
]


class TaskManifest(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    tasks: list[EvaluationTask] = Field(min_length=1)


class RunMetrics(StrictModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cache_read_input_tokens: int = Field(default=0, ge=0)
    cache_creation_input_tokens: int = Field(default=0, ge=0)
    duration_seconds: float = Field(default=0.0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    modified_files: int = Field(default=0, ge=0)
    steps: int = Field(default=0, ge=0)


class RunRecord(StrictModel):
    task_id: str
    source: Literal["internal", "swebench_lite"]
    category: TaskCategory
    repetition: int = Field(ge=1)
    runner: str
    status: RunStatus
    success: bool | None
    failure_reason: FailureReason | None = None
    error_message: str = ""
    modified_paths: list[str] = Field(default_factory=list)
    unexpected_paths: list[str] = Field(default_factory=list)
    metrics: RunMetrics = Field(default_factory=RunMetrics)
    patch: str = ""
    runner_output: str = ""


class TaskSummary(StrictModel):
    task_id: str
    source: Literal["internal", "swebench_lite"]
    category: TaskCategory
    runs: int = Field(ge=1)
    scored_runs: int = Field(ge=0)
    successes: int = Field(ge=0)
    failures: int = Field(ge=0)
    errors: int = Field(ge=0)
    unscored: int = Field(ge=0)
    success_rate: float | None = Field(default=None, ge=0, le=1)
    pass_at_k: float | None = Field(default=None, ge=0, le=1)
    stability: float | None = Field(default=None, ge=0, le=1)
    duration_mean: float = Field(ge=0)
    duration_stdev: float = Field(ge=0)
    token_mean: float = Field(ge=0)
    tool_calls_mean: float = Field(ge=0)
    modified_files_mean: float = Field(ge=0)


class ReportSummary(StrictModel):
    total_runs: int = Field(ge=0)
    scored_runs: int = Field(ge=0)
    successes: int = Field(ge=0)
    failures: int = Field(ge=0)
    errors: int = Field(ge=0)
    unscored: int = Field(ge=0)
    success_rate: float | None = Field(default=None, ge=0, le=1)
    total_tokens: int = Field(ge=0)
    total_duration_seconds: float = Field(ge=0)
    total_tool_calls: int = Field(ge=0)
    total_modified_files: int = Field(ge=0)
    failure_reasons: dict[str, int] = Field(default_factory=dict)


class EvaluationReport(StrictModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    suite: str
    runner: str
    repetitions: int = Field(ge=1)
    generated_at: datetime
    summary: ReportSummary
    task_summaries: list[TaskSummary]
    runs: list[RunRecord]
