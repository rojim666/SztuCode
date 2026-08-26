from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from sztu_code.core.tools.base import (
    _PERMISSION_GRANT_KEY,
    _PERMISSION_GRANT_TOKEN,
    BaseTool,
    ToolPermission,
    ToolResult,
)
from sztu_code.core.tools.workspace import resolve_workspace_path
from sztu_code.core.workflow.scope import ScopeAuditLog, write_is_outside_scope

_MAX_BYTES = 1 * 1024 * 1024  # 1 MB


class WriteFileParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: str
    content: str


class WriteFileTool(BaseTool):
    params_model = WriteFileParams
    name = "write_file"
    required_permission = ToolPermission.WORKSPACE_WRITE
    aliases: ClassVar[list[str]] = ["write", "Write"]
    description = (
        "Write text content to a file, creating it (and any parent directories) if it "
        "does not exist, or overwriting it if it does. "
        "Path must be relative to the current working directory. "
        "Content size is limited to 1 MB."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the file (relative to current working directory).",
            },
            "content": {
                "type": "string",
                "description": "Text content to write.",
            },
        },
        "required": ["path", "content"],
    }

    # 绑定可选工作区根目录，使写入目标始终受 session 工作区约束
    def __init__(
        self,
        workspace_root: Path | None = None,
        allowed_paths: Sequence[str] | None = None,
        scope_audit: ScopeAuditLog | None = None,
    ) -> None:
        self._workspace_root = workspace_root
        self._allowed_paths = tuple(allowed_paths) if allowed_paths is not None else None
        self._scope_audit = scope_audit

    # 范围内写入使用普通编辑权限，越界写入升级为 full-access 审批
    def classify_permission(self, params: dict[str, object]) -> ToolPermission:
        path = str(params.get("path", ""))
        if write_is_outside_scope(path, self._allowed_paths):
            return ToolPermission.DANGER_FULL_ACCESS
        return ToolPermission.WORKSPACE_WRITE

    # 写入文件内容；超 1MB 拒绝；禁止 .. 路径遍历；自动创建父目录
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = WriteFileParams.model_validate(params)
        path_str = p.path
        content = p.content

        if ".." in Path(path_str).parts:
            raise PermissionError(f"path traversal not allowed: {path_str}")
        outside_scope = write_is_outside_scope(path_str, self._allowed_paths)
        grant = params.get(_PERMISSION_GRANT_KEY)
        if outside_scope and grant is not _PERMISSION_GRANT_TOKEN:
            raise PermissionError(f"write outside assigned scope requires approval: {path_str}")

        encoded = content.encode("utf-8")
        if len(encoded) > _MAX_BYTES:
            return ToolResult(
                content=f"content too large: {len(encoded)} bytes (limit 1 MB)",
                is_error=True,
                error_type="runtime_error",
            )

        path = resolve_workspace_path(self._workspace_root, path_str)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if outside_scope and self._scope_audit is not None:
            self._scope_audit.record(path_str)

        return ToolResult(content=f"wrote {len(encoded)} bytes to {path_str}")
