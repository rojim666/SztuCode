from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath


# 将工具相对路径解析到指定工作区并拒绝越界访问
def resolve_workspace_path(workspace_root: Path | None, relative_path: str) -> Path:
    posix_path = PurePosixPath(relative_path)
    windows_path = PureWindowsPath(relative_path)
    if posix_path.is_absolute() or windows_path.anchor or windows_path.drive:
        raise PermissionError(f"path escapes workspace: {relative_path}")
    root = (workspace_root or Path.cwd()).resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise PermissionError(f"path escapes workspace: {relative_path}") from None
    return candidate
