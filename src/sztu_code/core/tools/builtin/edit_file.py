# 字符串替换编辑工具 —— 类似 Claude Code 的 edit_file
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from sztu_code.core.tools.base import BaseTool, ToolPermission, ToolResult

_MAX_BYTES = 1 * 1024 * 1024  # 1 MB


class EditFileParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: str
    old_string: str
    new_string: str
    replace_all: bool = False


class EditFileTool(BaseTool):
    params_model = EditFileParams
    name = "edit_file"
    required_permission = ToolPermission.WORKSPACE_WRITE
    aliases: ClassVar[list[str]] = ["edit", "Edit"]
    description = (
        "Perform exact string replacement in an existing file. "
        "When editing text, ensure you preserve the exact indentation (tabs/spaces) as it appears "
        "before. ALWAYS prefer editing existing files in the codebase. NEVER write new files unless "
        "explicitly required. Only use emojis if the user explicitly requests it. Avoid adding "
        "emojis to files unless asked. The edit will FAIL if old_string is not unique in the file. "
        "Either provide a larger string with more surrounding context to make it unique. "
        "To create or overwrite a file, prefer using the write_file tool."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the file to edit.",
            },
            "old_string": {
                "type": "string",
                "description": "The exact text to replace.",
            },
            "new_string": {
                "type": "string",
                "description": "The text to replace with (must be different from old_string).",
            },
            "replace_all": {
                "type": "boolean",
                "description": "Replace all occurrences of old_string (default false).",
            },
        },
        "required": ["path", "old_string", "new_string"],
    }

    # 读取文件 → 精确替换 → 写回；old_string 必须唯一（除非 replace_all）
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = EditFileParams.model_validate(params)

        if ".." in Path(p.path).parts:
            raise PermissionError(f"path traversal not allowed: {p.path}")

        if p.old_string == p.new_string:
            return ToolResult(
                content="old_string and new_string are identical — no change needed.",
                is_error=True,
                error_type="schema_error",
            )

        path = Path(p.path)
        if not path.is_file():
            return ToolResult(
                content=f"file not found: {p.path}",
                is_error=True,
                error_type="runtime_error",
            )

        original = path.read_text(encoding="utf-8")
        if len(original.encode("utf-8")) > _MAX_BYTES:
            return ToolResult(
                content=f"file too large: {len(original.encode('utf-8'))} bytes (limit 1 MB)",
                is_error=True,
                error_type="runtime_error",
            )

        count = original.count(p.old_string)
        if count == 0:
            return ToolResult(
                content=(
                    f"old_string not found in {p.path}.\n"
                    f"Tip: make sure the string matches exactly, including whitespace."
                ),
                is_error=True,
                error_type="runtime_error",
            )

        if count > 1 and not p.replace_all:
            return ToolResult(
                content=(
                    f"old_string appears {count} times in {p.path}.\n"
                    f"Add more surrounding context to make it unique, "
                    f"or set replace_all=true to replace all occurrences."
                ),
                is_error=True,
                error_type="schema_error",
            )

        if p.replace_all:
            result = original.replace(p.old_string, p.new_string)
        else:
            result = original.replace(p.old_string, p.new_string, 1)

        path.write_text(result, encoding="utf-8")
        replaced = count if p.replace_all else 1
        return ToolResult(content=f"replaced {replaced} occurrence(s) in {p.path}")
