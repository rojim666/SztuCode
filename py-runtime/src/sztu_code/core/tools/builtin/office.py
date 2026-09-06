from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

from pydantic import ValidationError

from sztu_code.core.documents import DocumentError
from sztu_code.core.office import (
    DESCRIPTIONS,
    CreateDocumentParams,
    EditDocumentParams,
    ReadDocumentParams,
    execute_office_request,
)
from sztu_code.core.tools.base import (
    _PERMISSION_GRANT_KEY,
    _PERMISSION_GRANT_TOKEN,
    BaseTool,
    ToolPermission,
    ToolResult,
)
from sztu_code.core.workflow.scope import ScopeAuditLog, write_is_outside_scope


async def _invoke(name: str, root: Path | None, params: dict[str, object]) -> ToolResult:
    values = {
        key: value
        for key, value in params.items()
        if key not in {"description", _PERMISSION_GRANT_KEY}
    }
    try:
        request = {"tool": name, "workspace": str(root or Path.cwd()), "params": values}
        if len(json.dumps(request).encode()) > 1024 * 1024:
            raise DocumentError("办公请求超过 1MB 限制")
        result = await asyncio.to_thread(execute_office_request, request)
        return ToolResult(content=json.dumps(result, ensure_ascii=False), metadata=result)
    except (DocumentError, ValidationError, OSError, ValueError) as exc:
        return ToolResult(content=str(exc), is_error=True, error_type="runtime_error")


class ReadDocumentTool(BaseTool):
    name = "read_document"
    description = DESCRIPTIONS[name]
    required_permission = ToolPermission.READ_ONLY
    retry_safe = True
    input_schema = ReadDocumentParams.model_json_schema()

    def __init__(self, workspace_root: Path | None = None) -> None:
        self._workspace_root = workspace_root

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        return await _invoke(self.name, self._workspace_root, params)


class CreateDocumentTool(BaseTool):
    # Share the same workflow write-scope enforcement as write_file.
    name = "create_document"
    aliases: ClassVar[list[str]] = []
    params_model = None  # validation occurs after internal permission fields are removed
    description = DESCRIPTIONS[name]
    input_schema = CreateDocumentParams.model_json_schema()

    def __init__(
        self,
        workspace_root: Path | None = None,
        allowed_paths: Sequence[str] | None = None,
        scope_audit: ScopeAuditLog | None = None,
    ) -> None:
        self._workspace_root = workspace_root
        self._allowed_paths = tuple(allowed_paths) if allowed_paths is not None else None
        self._scope_audit = scope_audit

    def classify_permission(self, params: dict[str, object]) -> ToolPermission:
        if write_is_outside_scope(str(params.get("path", "")), self._allowed_paths):
            return ToolPermission.DANGER_FULL_ACCESS
        return ToolPermission.WORKSPACE_WRITE

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        path = str(params.get("path", ""))
        outside = write_is_outside_scope(path, self._allowed_paths)
        if outside and params.get(_PERMISSION_GRANT_KEY) is not _PERMISSION_GRANT_TOKEN:
            raise PermissionError(f"write outside assigned scope requires approval: {path}")
        result = await _invoke(self.name, self._workspace_root, params)
        if outside and not result.is_error and self._scope_audit is not None:
            self._scope_audit.record(path)
        return result


class EditDocumentTool(CreateDocumentTool):
    name = "edit_document"
    description = DESCRIPTIONS[name]
    input_schema = EditDocumentParams.model_json_schema()
