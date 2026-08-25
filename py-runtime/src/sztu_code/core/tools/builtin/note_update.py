from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from sztu_code.core.session.store import SessionStore
from sztu_code.core.tools.base import BaseTool, ToolPermission, ToolResult


class NoteUpdateParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    note_id: str
    content: str


# 更新已有笔记（借鉴 Hy-Memory supersedes 机制）
class NoteUpdateTool(BaseTool):
    params_model = NoteUpdateParams
    name = "note_update"
    required_permission = ToolPermission.WORKSPACE_WRITE
    aliases: ClassVar[list[str]] = []
    description = (
        "更新一条此前保存的笔记。旧笔记归档保留但不显示。"
        "当之前记录的事实发生变化时使用此工具（如技术选型变更），"
        "避免矛盾信息共存。note_id 来自 note_save 的返回值。"
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "note_id": {
                "type": "string",
                "description": "要更新的笔记 ID（来自 note_save 返回值）",
            },
            "content": {
                "type": "string",
                "description": "更新后的笔记内容。",
            },
        },
        "required": ["note_id", "content"],
    }

    # 绑定当前 session 与 run，使工具调用能写入对应 notes.md
    def __init__(self, store: SessionStore, session_id: str, run_id: str) -> None:
        self._store = store
        self._session_id = session_id
        self._run_id = run_id

    # 更新指定 note_id 的笔记：旧版归档，新版写入
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = NoteUpdateParams.model_validate(params)
        content = p.content.strip()
        if not content:
            return ToolResult(
                content="内容不能为空",
                is_error=True,
                error_type="runtime_error",
            )
        new_id = self._store.update_note(
            self._session_id, p.note_id, content, self._run_id,
        )
        if new_id is None:
            return ToolResult(
                content=f"未找到笔记: {p.note_id}。请检查 note_id 是否正确。",
                is_error=True,
                error_type="runtime_error",
            )
        return ToolResult(content=f"已更新 ({p.note_id} → {new_id})。旧笔记已归档。")
