from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath


# 将用户输入路径规范化为工作区相对 POSIX 路径并拒绝绝对路径与目录穿越
def normalize_workspace_relative(path: str) -> str:
    normalized = path.replace("\\", "/").strip()
    candidate = PurePosixPath(normalized)
    windows_candidate = PureWindowsPath(normalized)
    if (
        not normalized
        or candidate.is_absolute()
        or windows_candidate.is_absolute()
        or bool(windows_candidate.drive)
        or ".." in candidate.parts
    ):
        raise PermissionError(f"path must stay inside the assigned workspace scope: {path}")
    return candidate.as_posix().removeprefix("./") or "."


# 判断目标路径是否落在任一显式分配的文件、目录或 glob 范围内
def path_is_allowed(path: str, allowed_paths: Sequence[str]) -> bool:
    normalized = normalize_workspace_relative(path)
    candidate = PurePosixPath(normalized)
    for raw_scope in allowed_paths:
        scope = normalize_workspace_relative(raw_scope)
        if scope == ".":
            return True
        if any(marker in scope for marker in "*?["):
            if candidate.match(scope):
                return True
            continue
        if normalized == scope or normalized.startswith(f"{scope.rstrip('/')}/"):
            return True
    return False


@dataclass
class ScopeAuditLog:
    paths: list[str] = field(default_factory=list)

    # 记录一次已经通过权限系统放行的越界写入，供交接事件和 Reviewer 审计
    def record(self, path: str) -> None:
        normalized = normalize_workspace_relative(path)
        if normalized not in self.paths:
            self.paths.append(normalized)


# 判断目标是否超出角色分配范围；None 表示非工作流旧调用方
def write_is_outside_scope(path: str, allowed_paths: Sequence[str] | None) -> bool:
    if allowed_paths is None:
        return False
    try:
        return not path_is_allowed(path, allowed_paths)
    except PermissionError:
        return True
