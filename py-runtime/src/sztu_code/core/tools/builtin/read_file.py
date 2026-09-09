from __future__ import annotations

import asyncio
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from sztu_code.core.documents import SUPPORTED_FORMATS, DocumentError, parse_document
from sztu_code.core.tools.base import BaseTool, ToolPermission, ToolResult
from sztu_code.core.tools.workspace import resolve_workspace_path

_MAX_BYTES = 512 * 1024  # 512 KB


class ReadFileParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: str
    offset: int | None = Field(default=None, ge=0)
    limit: int | None = Field(default=None, ge=1, le=2000)


class ReadFileTool(BaseTool):
    params_model = ReadFileParams
    name = "read_file"
    required_permission = ToolPermission.READ_ONLY
    aliases: ClassVar[list[str]] = ["read", "Read"]
    description = (
        "Read text files or extract text from PDF, DOCX, XLSX and PPTX documents. "
        "Path must be relative to the current working directory. "
        "Text files larger than 512 KB are truncated; documents allow 20 MB and return up to "
        "32K characters. Supply offset (zero-based) or limit for numbered text line pagination. "
        "Scanned PDFs require OCR before reading."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the file (relative to current working directory).",
            },
            "offset": {"type": "integer", "minimum": 0, "description": "Zero-based first line"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 2000},
        },
        "required": ["path"],
    }

    # 绑定可选工作区根目录，使文件读取不依赖 daemon 的进程目录
    def __init__(self, workspace_root: Path | None = None) -> None:
        self._workspace_root = workspace_root

    # 读取文件内容；超 512KB 截断；禁止 .. 路径遍历
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = ReadFileParams.model_validate(params)
        path_str = p.path

        if ".." in Path(path_str).parts:
            raise PermissionError(f"path traversal not allowed: {path_str}")

        path = resolve_workspace_path(self._workspace_root, path_str)
        with path.open("rb") as stream:
            is_pdf = stream.read(5) == b"%PDF-"
        if is_pdf or path.suffix.lower().lstrip(".") in SUPPORTED_FORMATS:
            try:
                document = await asyncio.to_thread(parse_document, path)
                return ToolResult(content=document.text)
            except DocumentError as exc:
                return ToolResult(content=str(exc), is_error=True)
        if p.offset is not None or p.limit is not None:
            return await asyncio.to_thread(self._read_page, path, p.offset or 0, p.limit or 2000)
        with path.open("rb") as stream:
            raw = stream.read(_MAX_BYTES + 1)
        truncated = len(raw) > _MAX_BYTES
        text = raw[:_MAX_BYTES].decode("utf-8", errors="replace")
        if truncated:
            text += "\n[truncated]"

        return ToolResult(content=text)

    @staticmethod
    def _read_page(path: Path, offset: int, limit: int) -> ToolResult:
        # Stream past earlier lines so later pages remain reachable in large files.
        page: list[str] = []
        size = 0
        truncated = False
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            for index, line in enumerate(stream):
                if index < offset:
                    continue
                if len(page) >= limit or size >= _MAX_BYTES:
                    truncated = True
                    break
                text = line.rstrip("\n")
                remaining = _MAX_BYTES - size
                if len(text) > remaining:
                    text = text[:remaining] + " [line truncated]"
                    truncated = True
                page.append(f"{index + 1:6}\t{text}")
                size += len(text)
                if truncated:
                    break
        content = "\n".join(page)
        if truncated:
            content += f"\n\n[truncated; next offset={offset + len(page)}]"
        return ToolResult(content=content)
