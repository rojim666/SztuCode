from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from sztu_code.core.memory.loader import MemoryCatalog
from sztu_code.core.tools.base import BaseTool, ToolPermission, ToolResult


class MemoryReadParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    layer: str
    query: str = ""
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=1600, ge=1, le=4000)


class MemoryReadTool(BaseTool):
    name = "memory_read"
    required_permission = ToolPermission.READ_ONLY
    aliases: ClassVar[list[str]] = []
    description = (
        "Read a relevant excerpt from progressively disclosed agent memory. "
        "Prefer a specific query; use offset pagination only when exact text is required."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "layer": {
                "type": "string",
                "enum": ["global", "project", "session"],
                "description": "Memory layer named in the system prompt.",
            },
            "query": {
                "type": "string",
                "description": "Case-insensitive text to find. Leave empty for paged reading.",
            },
            "offset": {
                "type": "integer",
                "minimum": 0,
                "description": "Character offset for paging, or match offset when query is set.",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 4000,
                "description": "Maximum excerpt characters; defaults to 1600.",
            },
        },
        "required": ["layer"],
    }
    params_model = MemoryReadParams

    # 绑定本次 run 的不可变记忆快照
    def __init__(self, catalog: MemoryCatalog) -> None:
        self._catalog = catalog

    # 按主题搜索或分页读取记忆片段
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        parsed = MemoryReadParams.model_validate(params)
        try:
            content = self._catalog.read(
                parsed.layer,
                query=parsed.query,
                offset=parsed.offset,
                limit=parsed.limit,
            )
        except KeyError as exc:
            return ToolResult(
                content=str(exc),
                is_error=True,
                error_type="runtime_error",
            )
        return ToolResult(content=content)
