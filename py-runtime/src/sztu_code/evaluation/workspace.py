from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from sztu_code.evaluation.models import EvaluationTask, InternalTask, SwebenchLiteTask
from sztu_code.evaluation.tasks import safe_relative_path

_IGNORED_PARTS = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__"}


# 将清单相对路径约束在本次评测工作区内
def workspace_path(root: Path, raw_path: str) -> Path:
    relative = safe_relative_path(raw_path)
    target = root.joinpath(*relative.parts)
    resolved_root = root.resolve()
    resolved_target = target.resolve(strict=False)
    if not resolved_target.is_relative_to(resolved_root):
        raise ValueError(f"task path escapes workspace: {raw_path}")
    return target


# 在隔离目录中写入内部任务的初始破损工作区
def seed_internal_workspace(task: InternalTask, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=False)
    for raw_path, content in task.workspace_files.items():
        target = workspace_path(root, raw_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")


# 克隆 SWE-bench 仓库并检出任务指定的不可变基线提交
def clone_swebench_workspace(task: SwebenchLiteTask, root: Path) -> None:
    root.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "git",
            "clone",
            "--quiet",
            "--filter=blob:none",
            "--no-checkout",
            f"https://github.com/{task.repo}.git",
            str(root),
        ],
        check=True,
        timeout=600,
    )
    subprocess.run(
        ["git", "checkout", "--quiet", "--detach", task.base_commit],
        cwd=root,
        check=True,
        timeout=120,
    )


# 根据任务来源准备内部 fixture 或 SWE-bench 仓库
def prepare_workspace(task: EvaluationTask, root: Path) -> None:
    if isinstance(task, InternalTask):
        seed_internal_workspace(task, root)
        return
    clone_swebench_workspace(task, root)


# 对内部工作区文件计算内容哈希以识别新增、修改和删除
def snapshot_workspace(root: Path) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in _IGNORED_PARTS for part in relative.parts):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        snapshot[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


# 比较工作区前后快照并返回稳定排序的变更路径
def changed_snapshot_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    all_paths = set(before) | set(after)
    return sorted(path for path in all_paths if before.get(path) != after.get(path))


# 从 Git 状态中提取 SWE-bench 工作区的修改路径
def git_changed_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    paths: list[str] = []
    entries = [entry for entry in result.stdout.split("\0") if entry]
    index = 0
    while index < len(entries):
        entry = entries[index]
        status = entry[:2]
        path = entry[3:]
        if "R" in status or "C" in status:
            index += 1
            if index < len(entries):
                path = entries[index]
        paths.append(path.replace("\\", "/"))
        index += 1
    return sorted(set(paths))


# 获取包含已跟踪与未跟踪文件的 unified diff 供 SWE-bench harness 使用
def git_patch(root: Path) -> str:
    tracked = subprocess.run(
        ["git", "diff", "--binary", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    untracked = sorted(
        entry[3:] for entry in status.split("\0") if entry.startswith("?? ")
    )
    additions: list[str] = []
    for raw_path in untracked:
        diff = subprocess.run(
            ["git", "diff", "--no-index", "--binary", "--", "/dev/null", raw_path],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if diff.returncode not in (0, 1):
            raise RuntimeError(diff.stderr.strip() or f"cannot diff {raw_path}")
        additions.append(diff.stdout)
    return tracked + "".join(additions)


# 应用内部基准随清单提供的参考修改以验证评测管线本身
def apply_reference_changes(task: InternalTask, root: Path) -> None:
    for change in task.reference_changes:
        target = workspace_path(root, change.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(change.content, encoding="utf-8", newline="\n")
