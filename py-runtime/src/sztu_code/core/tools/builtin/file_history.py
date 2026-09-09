from pathlib import Path
import json
from pydantic import BaseModel

from sztu_code.core.file_versions import FileVersions
from sztu_code.core.tools.base import BaseTool, ToolPermission, ToolResult


class FileHistoryParams(BaseModel):
    path: str
    version: str | None = None
    expected_hash: str | None = None


class FileHistoryTool(BaseTool):
    name = "file_history"
    params_model = FileHistoryParams
    description = "List immutable versions from edit_file. Supply a version hash and the current expected_hash to restore that version; restoration records another reversible edit."
    input_schema = {"type": "object", "properties": {"path": {"type": "string"}, "version": {"type": "string"}, "expected_hash": {"type": "string"}}, "required": ["path"]}

    def __init__(self, workspace_root: Path | None = None) -> None:
        self.versions = FileVersions(workspace_root)

    def classify_permission(self, params: dict[str, object]) -> ToolPermission:
        return ToolPermission.WORKSPACE_WRITE if params.get("version") else ToolPermission.READ_ONLY

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = FileHistoryParams.model_validate(params)
        if p.version:
            if not p.expected_hash:
                return ToolResult(content="expected_hash is required to restore a version", is_error=True, error_type="schema_error")
            result = self.versions.restore(p.path, p.version, p.expected_hash)
        else:
            result = self.versions.list(p.path)
        return ToolResult(content=json.dumps(result, ensure_ascii=False))
