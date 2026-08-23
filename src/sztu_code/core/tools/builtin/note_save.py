from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from sztu_code.core.session.store import SessionStore
from sztu_code.core.tools.base import BaseTool, ToolPermission, ToolResult


class NoteSaveParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    content: str


class NoteSaveTool(BaseTool):
    params_model = NoteSaveParams
    name = "note_save"
    required_permission = ToolPermission.WORKSPACE_WRITE
    aliases: ClassVar[list[str]] = []
    description = (
        "Save a concise fact or decision to this session's notes. "
        "These notes are visible in future turns of the same session."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The durable fact or decision to remember.",
            },
        },
        "required": ["content"],
    }

    # 绑定当前 session 与 run，使工具调用能写入对应 notes.md
    def __init__(self, store: SessionStore, session_id: str, run_id: str) -> None:
        self._store = store
        self._session_id = session_id
        self._run_id = run_id

    # 将非空 content 追加到 session notes.md，返回 note_id 供后续更新
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        content = NoteSaveParams.model_validate(params).content.strip()
        if not content:
            return ToolResult(
                content="empty content",
                is_error=True,
                error_type="runtime_error",
            )
        note_id = self._store.append_note(self._session_id, content, self._run_id)
        return ToolResult(content=f"saved ({note_id})")
