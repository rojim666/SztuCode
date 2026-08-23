from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from sztu_code.core.tools.base import BaseTool, ToolPermission, ToolResult

if TYPE_CHECKING:
    from sztu_code.core.compact.offload import OffloadManager


class ReadRefParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ref_path: str
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=4000, ge=1, le=8000)


# 回读已卸载工具结果的完整内容（TencentDB Agent Memory Level 0 追溯）
class ReadRefTool(BaseTool):
    name = "read_ref"
    required_permission = ToolPermission.READ_ONLY
    aliases: ClassVar[list[str]] = []
    description = (
        "读取已卸载到外部文件的工具调用完整输出。"
        "当上下文中仅有占位符摘要、需要查看完整结果时使用。"
        "ref_path 来自上下文中 `[上下文卸载: refs/xxx.md]` 标记。"
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "ref_path": {
                "type": "string",
                "description": (
                    "卸载文件的相对路径，如 'refs/bash_20260805_001.md'。"
                    "来自上下文中 `[上下文卸载: refs/xxx.md]` 标记。"
                ),
            },
            "offset": {
                "type": "integer",
                "minimum": 0,
                "description": "Character offset for paged reading; defaults to 0.",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 8000,
                "description": "Maximum characters to return; defaults to 4000.",
            },
        },
        "required": ["ref_path"],
    }
    params_model = ReadRefParams

    # 绑定 OffloadManager，使工具能回读 Level 0 原文
    def __init__(self, offload_manager: OffloadManager) -> None:
        self._offload_manager = offload_manager

    # 按 ref_path 读取卸载文件的完整原始内容
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = ReadRefParams.model_validate(params)
        try:
            full_content = self._offload_manager.read_ref(p.ref_path)
        except ValueError as exc:
            return ToolResult(
                content=str(exc),
                is_error=True,
                error_type="runtime_error",
            )
        except FileNotFoundError:
            return ToolResult(
                content=f"卸载文件不存在: {p.ref_path}。该文件可能已被清理。",
                is_error=True,
                error_type="runtime_error",
            )
        content = full_content[p.offset : p.offset + p.limit]
        next_offset = p.offset + len(content)
        suffix = (
            f"\n\n[ref page: chars {p.offset}:{next_offset}/{len(full_content)}"
            + (f", next_offset={next_offset}" if next_offset < len(full_content) else ", end")
            + "]"
        )
        return ToolResult(content=content + suffix)
