from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

from sztu_code.evaluation.models import (
    EvaluationTask,
    InternalTask,
    SwebenchLiteTask,
    TaskManifest,
)

_TASKS_DIR = Path(__file__).with_name("tasks")
_DEFAULT_MANIFESTS = {
    "internal": _TASKS_DIR / "internal-v1.json",
    "swebench-lite": _TASKS_DIR / "swebench-lite-smoke.json",
}


# 将任务文件中的 POSIX 相对路径解析为安全路径并拒绝越界片段
def safe_relative_path(raw_path: str) -> PurePosixPath:
    if "\\" in raw_path:
        raise ValueError(f"task paths must use forward slashes: {raw_path}")
    path = PurePosixPath(raw_path)
    if path.is_absolute() or not path.parts or ".." in path.parts or "." in path.parts:
        raise ValueError(f"unsafe task path: {raw_path}")
    return path


# 返回随包分发的默认任务清单路径
def default_manifest_path(suite: str) -> Path:
    try:
        return _DEFAULT_MANIFESTS[suite]
    except KeyError as exc:
        choices = ", ".join(sorted(_DEFAULT_MANIFESTS))
        raise ValueError(f"unknown suite {suite!r}; choose one of: {choices}") from exc


# 校验清单中的任务标识与工作区路径不重复且不越界
def _validate_manifest(manifest: TaskManifest) -> None:
    ids = [task.id for task in manifest.tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("task ids must be unique")

    instance_ids = [
        task.instance_id for task in manifest.tasks if isinstance(task, SwebenchLiteTask)
    ]
    if len(instance_ids) != len(set(instance_ids)):
        raise ValueError("SWE-bench instance ids must be unique")

    for task in manifest.tasks:
        if not isinstance(task, InternalTask):
            continue
        workspace_paths = {str(safe_relative_path(path)) for path in task.workspace_files}
        expected_paths = {str(safe_relative_path(path)) for path in task.expected_modified_files}
        reference_paths = {
            str(safe_relative_path(change.path)) for change in task.reference_changes
        }
        if expected_paths != reference_paths:
            raise ValueError(
                f"{task.id}: expected_modified_files must match reference_changes"
            )
        if not expected_paths <= workspace_paths:
            missing = sorted(expected_paths - workspace_paths)
            raise ValueError(f"{task.id}: changed paths missing from workspace: {missing}")


# 从版本化 JSON 文件加载并完整校验评测任务清单
def load_manifest(path: Path) -> TaskManifest:
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    manifest = TaskManifest.model_validate(raw)
    _validate_manifest(manifest)
    return manifest


# 按任务标识和数量筛选清单，同时保留原始清单元数据
def select_tasks(
    manifest: TaskManifest,
    task_ids: set[str] | None = None,
    max_tasks: int | None = None,
) -> TaskManifest:
    tasks: list[EvaluationTask] = list(manifest.tasks)
    if task_ids:
        available = {task.id for task in tasks}
        unknown = sorted(task_ids - available)
        if unknown:
            raise ValueError(f"unknown task ids: {', '.join(unknown)}")
        tasks = [task for task in tasks if task.id in task_ids]
    if max_tasks is not None:
        if max_tasks < 1:
            raise ValueError("max_tasks must be at least 1")
        tasks = tasks[:max_tasks]
    if not tasks:
        raise ValueError("task selection is empty")
    return manifest.model_copy(update={"tasks": tasks})


# 生成可交给外部 Agent 的公开任务负载并移除参考答案
def public_task_payload(task: EvaluationTask) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": task.id,
        "source": task.source,
        "title": task.title,
        "category": task.category.value,
        "prompt": task.prompt,
        "tags": list(task.tags),
    }
    if isinstance(task, InternalTask):
        payload["expected_modified_files"] = list(task.expected_modified_files)
    else:
        payload.update(
            {
                "instance_id": task.instance_id,
                "repo": task.repo,
                "base_commit": task.base_commit,
                "fail_to_pass": list(task.fail_to_pass),
                "pass_to_pass": list(task.pass_to_pass),
            }
        )
    return payload
