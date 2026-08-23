from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from sztu_code.evaluation.models import (
    EvaluationTask,
    FailureReason,
    InternalTask,
    RunMetrics,
    RunRecord,
    RunStatus,
    TaskManifest,
)
from sztu_code.evaluation.runners import EvaluationRunner, RunnerOutcome
from sztu_code.evaluation.workspace import (
    changed_snapshot_paths,
    git_changed_paths,
    git_patch,
    prepare_workspace,
    snapshot_workspace,
)

_MAX_OUTPUT_CHARS = 8_000


@dataclass(slots=True)
class ValidationOutcome:
    passed: bool
    output: str


# 将验证命令中的可移植 Python 占位符替换为当前解释器
def _validation_command(task: InternalTask) -> list[str]:
    return [sys.executable if part == "{python}" else part for part in task.validation.command]


# 在隔离工作区中执行内部任务验证命令并保留有界输出
def _validate_internal(task: InternalTask, workspace: Path) -> ValidationOutcome:
    try:
        completed = subprocess.run(
            _validation_command(task),
            cwd=workspace,
            check=False,
            capture_output=True,
            text=True,
            timeout=task.validation.timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return ValidationOutcome(False, "validation timed out")
    output = (completed.stdout + completed.stderr)[-_MAX_OUTPUT_CHARS:]
    return ValidationOutcome(completed.returncode == 0, output)


# 根据 runner 和验证结果确定可比较状态，SWE-bench 未经官方 harness 时保持未评分
def _classify_run(
    task: EvaluationTask,
    outcome: RunnerOutcome,
    unexpected_paths: list[str],
    validation: ValidationOutcome | None,
    patch: str,
) -> tuple[RunStatus, bool | None, FailureReason | None, str]:
    if outcome.failure_reason is not None:
        return RunStatus.ERROR, False, outcome.failure_reason, outcome.error_message
    if unexpected_paths:
        message = f"modified files outside expected scope: {', '.join(unexpected_paths)}"
        return RunStatus.FAILED, False, FailureReason.SCOPE_VIOLATION, message
    if isinstance(task, InternalTask):
        if validation is not None and validation.passed:
            return RunStatus.PASSED, True, None, ""
        return (
            RunStatus.FAILED,
            False,
            FailureReason.VALIDATION_FAILED,
            "internal validation command failed",
        )
    if patch:
        return RunStatus.UNSCORED, None, None, "official SWE-bench harness not run"
    return RunStatus.FAILED, False, FailureReason.VALIDATION_FAILED, "no patch generated"


# 执行一次任务并记录成功、成本、耗时、工具调用、文件范围和失败原因
def _run_once(
    task: EvaluationTask,
    repetition: int,
    runner: EvaluationRunner,
    root: Path,
    timeout_seconds: float,
) -> RunRecord:
    workspace = root / task.id / f"run-{repetition:03d}" / "workspace"
    artifacts = root / task.id / f"run-{repetition:03d}" / "artifacts"
    started = time.perf_counter()
    try:
        prepare_workspace(task, workspace)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        duration = time.perf_counter() - started
        return RunRecord(
            task_id=task.id,
            source=task.source,
            category=task.category,
            repetition=repetition,
            runner=runner.name,
            status=RunStatus.ERROR,
            success=False,
            failure_reason=FailureReason.SETUP_FAILED,
            error_message=str(exc),
            metrics=RunMetrics(duration_seconds=duration),
        )

    before = snapshot_workspace(workspace) if isinstance(task, InternalTask) else {}
    try:
        outcome = runner.run(task, workspace, artifacts, timeout_seconds)
    except Exception as exc:
        outcome = RunnerOutcome(
            failure_reason=FailureReason.INTERNAL_ERROR,
            error_message=f"{type(exc).__name__}: {exc}",
        )
    if isinstance(task, InternalTask):
        modified_paths = changed_snapshot_paths(before, snapshot_workspace(workspace))
        expected = set(task.expected_modified_files)
        unexpected_paths = sorted(set(modified_paths) - expected)
        patch = outcome.patch
        validation = _validate_internal(task, workspace)
    else:
        modified_paths = git_changed_paths(workspace)
        unexpected_paths = []
        patch = outcome.patch or git_patch(workspace)
        validation = None

    duration = time.perf_counter() - started

    status, success, failure_reason, error_message = _classify_run(
        task, outcome, unexpected_paths, validation, patch
    )
    validation_output = validation.output if validation is not None else ""
    runner_output = "\n".join(
        part for part in (outcome.output, validation_output) if part
    )[-_MAX_OUTPUT_CHARS:]
    return RunRecord(
        task_id=task.id,
        source=task.source,
        category=task.category,
        repetition=repetition,
        runner=runner.name,
        status=status,
        success=success,
        failure_reason=failure_reason,
        error_message=error_message,
        modified_paths=modified_paths,
        unexpected_paths=unexpected_paths,
        metrics=RunMetrics(
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            cache_read_input_tokens=outcome.cache_read_input_tokens,
            cache_creation_input_tokens=outcome.cache_creation_input_tokens,
            duration_seconds=duration,
            tool_calls=outcome.tool_calls,
            modified_files=len(modified_paths),
            steps=outcome.steps,
        ),
        patch=patch,
        runner_output=runner_output,
    )


# 在指定根目录顺序运行整个清单并支持同任务重复采样
def _run_in_root(
    manifest: TaskManifest,
    runner: EvaluationRunner,
    repetitions: int,
    root: Path,
    timeout_seconds: float,
) -> list[RunRecord]:
    records: list[RunRecord] = []
    for task in manifest.tasks:
        for repetition in range(1, repetitions + 1):
            records.append(_run_once(task, repetition, runner, root, timeout_seconds))
    return records


# 运行评测清单，默认使用自动清理的临时工作区
def run_manifest(
    manifest: TaskManifest,
    runner: EvaluationRunner,
    repetitions: int,
    timeout_seconds: float,
    workspace_root: Path | None = None,
) -> list[RunRecord]:
    if repetitions < 1:
        raise ValueError("repetitions must be at least 1")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if workspace_root is not None:
        workspace_root.mkdir(parents=True, exist_ok=False)
        return _run_in_root(manifest, runner, repetitions, workspace_root, timeout_seconds)
    with tempfile.TemporaryDirectory(prefix="sztucode-eval-") as raw_root:
        return _run_in_root(
            manifest,
            runner,
            repetitions,
            Path(raw_root),
            timeout_seconds,
        )
