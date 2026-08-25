from __future__ import annotations

import json
import statistics
from collections import Counter
from datetime import UTC, datetime
from math import comb
from pathlib import Path

from sztu_code.evaluation.models import (
    EvaluationReport,
    ReportSummary,
    RunRecord,
    RunStatus,
    SwebenchLiteTask,
    TaskManifest,
    TaskSummary,
)


# 计算有限重复样本下至少一次成功的无偏 pass@k 估计
def pass_at_k(total: int, successes: int, k: int) -> float:
    if total < 1 or k < 1 or k > total:
        raise ValueError("pass@k requires 1 <= k <= total")
    if successes < 0 or successes > total:
        raise ValueError("successes must be between 0 and total")
    failures = total - successes
    if failures < k:
        return 1.0
    return 1.0 - (comb(failures, k) / comb(total, k))


# 对空序列返回零并统一保留六位小数
def _mean(values: list[float]) -> float:
    return round(statistics.mean(values), 6) if values else 0.0


# 只有至少两个样本时计算样本标准差
def _stdev(values: list[float]) -> float:
    return round(statistics.stdev(values), 6) if len(values) > 1 else 0.0


# 聚合同一任务的成功率、pass@k、稳定性与资源指标
def _task_summary(task_id: str, records: list[RunRecord], repetitions: int) -> TaskSummary:
    first = records[0]
    scored = [record for record in records if record.success is not None]
    successes = sum(record.success is True for record in scored)
    failures = sum(record.status == RunStatus.FAILED for record in records)
    errors = sum(record.status == RunStatus.ERROR for record in records)
    unscored = sum(record.status == RunStatus.UNSCORED for record in records)
    scored_count = len(scored)
    success_rate = successes / scored_count if scored_count else None
    selected_k = min(repetitions, scored_count)
    pass_k = pass_at_k(scored_count, successes, selected_k) if selected_k else None
    stability = None
    if scored_count:
        stability = max(successes, scored_count - successes) / scored_count
    durations = [record.metrics.duration_seconds for record in records]
    tokens = [
        float(record.metrics.input_tokens + record.metrics.output_tokens)
        for record in records
    ]
    return TaskSummary(
        task_id=task_id,
        source=first.source,
        category=first.category,
        runs=len(records),
        scored_runs=scored_count,
        successes=successes,
        failures=failures,
        errors=errors,
        unscored=unscored,
        success_rate=success_rate,
        pass_at_k=pass_k,
        stability=stability,
        duration_mean=_mean(durations),
        duration_stdev=_stdev(durations),
        token_mean=_mean(tokens),
        tool_calls_mean=_mean([float(record.metrics.tool_calls) for record in records]),
        modified_files_mean=_mean(
            [float(record.metrics.modified_files) for record in records]
        ),
    )


# 从全部运行记录生成版本化 JSON 报告模型
def build_report(
    manifest: TaskManifest,
    runner_name: str,
    repetitions: int,
    records: list[RunRecord],
) -> EvaluationReport:
    grouped: dict[str, list[RunRecord]] = {task.id: [] for task in manifest.tasks}
    for record in records:
        if record.task_id not in grouped:
            raise ValueError(f"run references unknown task: {record.task_id}")
        grouped[record.task_id].append(record)
    if any(not task_records for task_records in grouped.values()):
        missing = [task_id for task_id, task_records in grouped.items() if not task_records]
        raise ValueError(f"tasks have no runs: {', '.join(missing)}")

    task_summaries = [
        _task_summary(task.id, grouped[task.id], repetitions) for task in manifest.tasks
    ]
    scored = [record for record in records if record.success is not None]
    successes = sum(record.success is True for record in scored)
    failure_counter = Counter(
        record.failure_reason.value
        for record in records
        if record.failure_reason is not None
    )
    summary = ReportSummary(
        total_runs=len(records),
        scored_runs=len(scored),
        successes=successes,
        failures=sum(record.status == RunStatus.FAILED for record in records),
        errors=sum(record.status == RunStatus.ERROR for record in records),
        unscored=sum(record.status == RunStatus.UNSCORED for record in records),
        success_rate=successes / len(scored) if scored else None,
        total_tokens=sum(
            record.metrics.input_tokens + record.metrics.output_tokens for record in records
        ),
        total_duration_seconds=round(
            sum(record.metrics.duration_seconds for record in records), 6
        ),
        total_tool_calls=sum(record.metrics.tool_calls for record in records),
        total_modified_files=sum(record.metrics.modified_files for record in records),
        failure_reasons=dict(sorted(failure_counter.items())),
    )
    return EvaluationReport(
        suite=manifest.name,
        runner=runner_name,
        repetitions=repetitions,
        generated_at=datetime.now(UTC),
        summary=summary,
        task_summaries=task_summaries,
        runs=records,
    )


# 将可选比例格式化为报告中的百分数或未评分标记
def _format_rate(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


# 生成人类可读 Markdown 汇总并明确区分未评分 SWE-bench 结果
def render_markdown(report: EvaluationReport) -> str:
    summary = report.summary
    lines = [
        "# SztuCode Evaluation Report",
        "",
        f"- Suite: `{report.suite}`",
        f"- Runner: `{report.runner}`",
        f"- Repetitions: {report.repetitions}",
        f"- Generated at: {report.generated_at.isoformat()}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Total runs | {summary.total_runs} |",
        f"| Scored runs | {summary.scored_runs} |",
        f"| Successes | {summary.successes} |",
        f"| Success rate | {_format_rate(summary.success_rate)} |",
        f"| Failures | {summary.failures} |",
        f"| Errors | {summary.errors} |",
        f"| Unscored | {summary.unscored} |",
        f"| Tokens | {summary.total_tokens} |",
        f"| Duration (s) | {summary.total_duration_seconds:.3f} |",
        f"| Tool calls | {summary.total_tool_calls} |",
        f"| Modified files | {summary.total_modified_files} |",
        "",
        "## Per-task stability",
        "",
        "| Task | Source | Runs | Success | pass@k | Stability | "
        "Tokens avg | Tools avg | Files avg |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in report.task_summaries:
        lines.append(
            "| "
            f"`{item.task_id}` | {item.source} | {item.runs} | "
            f"{_format_rate(item.success_rate)} | {_format_rate(item.pass_at_k)} | "
            f"{_format_rate(item.stability)} | {item.token_mean:.1f} | "
            f"{item.tool_calls_mean:.1f} | {item.modified_files_mean:.1f} |"
        )
    lines.extend(["", "## Failure reasons", ""])
    if summary.failure_reasons:
        lines.extend(["| Reason | Count |", "| --- | ---: |"])
        for reason, count in summary.failure_reasons.items():
            lines.append(f"| `{reason}` | {count} |")
    else:
        lines.append("No scored run failed.")
    if summary.unscored:
        lines.extend(
            [
                "",
                "> SWE-bench runs that only generated patches are marked `unscored`. ",
                "> Use the official Docker harness before treating them as resolved tasks.",
            ]
        )
    lines.append("")
    return "\n".join(lines)


# 同时写出机器可读 JSON 与人类可读 Markdown 报告
def write_report(report: EvaluationReport, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "report.json"
    markdown_path = output_dir / "summary.md"
    json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    return json_path, markdown_path


# 将指定重复轮次的 SWE-bench patch 导出为官方 harness 预测格式
def export_swebench_predictions(
    report: EvaluationReport,
    manifest: TaskManifest,
    output_path: Path,
    model_name: str,
    repetition: int = 1,
) -> int:
    instances = {
        task.id: task
        for task in manifest.tasks
        if isinstance(task, SwebenchLiteTask)
    }
    predictions: list[dict[str, str]] = []
    for record in report.runs:
        task = instances.get(record.task_id)
        if task is None or record.repetition != repetition:
            continue
        predictions.append(
            {
                "instance_id": task.instance_id,
                "model_name_or_path": model_name,
                "model_patch": record.patch,
            }
        )
    if not predictions:
        raise ValueError("report contains no SWE-bench predictions for that repetition")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in predictions),
        encoding="utf-8",
    )
    return len(predictions)
