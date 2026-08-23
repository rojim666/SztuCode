from __future__ import annotations

import json
from datetime import UTC, datetime

from sztu_code.core.bus.events import PlanItem, PlanUpdatedEvent
from sztu_code.core.events.bus import EventBus
from sztu_code.core.task.manager import TaskManager
from sztu_code.core.tools.base import BaseTool, ToolResult


class TaskCreateTool(BaseTool):
    name = "task_create"
    description = (
        "Create a new task to track a unit of work. "
        "Use this to break down a complex goal into smaller, trackable steps. "
        "Returns the created task as JSON."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "subject": {
                "type": "string",
                "description": "Short title for the task.",
            },
            "description": {
                "type": "string",
                "description": "Optional longer description of what needs to be done.",
            },
            "blocked_by": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "IDs of tasks that must be completed before this one.",
            },
        },
        "required": ["subject"],
    }

    # 持有 TaskManager 实例，供 invoke 调用
    def __init__(
        self,
        task_manager: TaskManager,
        event_bus: EventBus | None = None,
        run_id: str = "",
        session_id: str = "",
    ) -> None:
        self._manager = task_manager
        self._event_bus = event_bus
        self._run_id = run_id
        self._session_id = session_id

    # 创建任务并返回 JSON 字符串
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        subject = str(params["subject"])
        description = str(params.get("description") or "")
        raw_blocked: list[object] = list(params.get("blocked_by") or [])  # type: ignore[call-overload]
        blocked_by = [int(str(x)) for x in raw_blocked]
        try:
            task = self._manager.create(subject, description, blocked_by)
            await self._publish_plan()
            return ToolResult(content=json.dumps(task.to_dict(), ensure_ascii=False))
        except ValueError as exc:
            return ToolResult(content=str(exc), is_error=True, error_type="runtime_error")

    # 将当前任务列表发布为结构化计划事件，供客户端恢复或实时渲染
    async def _publish_plan(self) -> None:
        if self._event_bus is None or not self._run_id:
            return
        await self._event_bus.publish(
            PlanUpdatedEvent(
                run_id=self._run_id,
                session_id=self._session_id,
                items=[
                    PlanItem(
                        id=task.id,
                        subject=task.subject,
                        status=task.status,
                        blocked_by=task.blocked_by,
                    )
                    for task in self._manager.list_all()
                ],
                ts=datetime.now(UTC).isoformat(),
            )
        )
