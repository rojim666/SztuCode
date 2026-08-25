from __future__ import annotations

import json
from datetime import UTC, datetime

from sztu_code.core.bus.events import PlanItem, PlanUpdatedEvent
from sztu_code.core.events.bus import EventBus
from sztu_code.core.task.manager import TaskManager
from sztu_code.core.task.model import TaskStatus
from sztu_code.core.tools.base import BaseTool, ToolResult


class TaskUpdateTool(BaseTool):
    name = "task_update"
    description = (
        "Update a task's status or dependency list. "
        "Set status to 'in_progress' when starting work on a task, "
        "'completed' when finished (automatically clears it from other tasks' blocked_by). "
        "Returns the updated task as JSON."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "integer",
                "description": "ID of the task to update.",
            },
            "status": {
                "type": "string",
                "enum": ["pending", "in_progress", "completed"],
                "description": "New status for the task.",
            },
            "add_blocked_by": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Task IDs to add to blocked_by.",
            },
            "remove_blocked_by": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Task IDs to remove from blocked_by.",
            },
        },
        "required": ["task_id"],
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

    # 更新任务并返回 JSON 字符串
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        task_id = int(str(params["task_id"]))
        status: TaskStatus | None = params.get("status")  # type: ignore[assignment]
        raw_add: list[object] = list(params.get("add_blocked_by") or [])  # type: ignore[call-overload]
        raw_rem: list[object] = list(params.get("remove_blocked_by") or [])  # type: ignore[call-overload]
        add_blocked = [int(str(x)) for x in raw_add]
        remove_blocked = [int(str(x)) for x in raw_rem]
        try:
            task = self._manager.update(
                task_id,
                status=status,
                add_blocked_by=add_blocked or None,
                remove_blocked_by=remove_blocked or None,
            )
            await self._publish_plan()
            return ToolResult(content=json.dumps(task.to_dict(), ensure_ascii=False))
        except ValueError as exc:
            return ToolResult(content=str(exc), is_error=True, error_type="runtime_error")

    # 将更新后的任务列表发布为结构化计划事件，供客户端同步完成状态
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
