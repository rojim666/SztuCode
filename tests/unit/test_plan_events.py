from __future__ import annotations

from pathlib import Path

from sztu_code.core.events.bus import EventBus
from sztu_code.core.task.manager import TaskManager
from sztu_code.core.tools.builtin.task_create import TaskCreateTool
from sztu_code.core.tools.builtin.task_update import TaskUpdateTool


# 功能：验证创建和更新任务都会发布带 run/session 关联的完整计划快照。
# 设计：使用真实 TaskManager 与内存 EventBus 串联两个工具，断言第二个快照包含已完成状态，覆盖客户端实时计划面板所依赖的完整事件契约。
async def test_task_tools_publish_structured_plan_updates(tmp_path: Path) -> None:
    events: list[object] = []
    bus = EventBus()

    async def collect(event: object) -> None:
        events.append(event)

    bus.subscribe(collect)
    manager = TaskManager(tmp_path / ".tasks")
    create = TaskCreateTool(manager, bus, "run-plan", "sess-plan")
    update = TaskUpdateTool(manager, bus, "run-plan", "sess-plan")

    await create.invoke({"subject": "inspect implementation"})
    await update.invoke({"task_id": 1, "status": "completed"})

    assert [event.type for event in events] == ["plan.updated", "plan.updated"]  # type: ignore[attr-defined]
    latest = events[-1]
    assert latest.run_id == "run-plan"  # type: ignore[attr-defined]
    assert latest.session_id == "sess-plan"  # type: ignore[attr-defined]
    assert latest.items[0].status == "completed"  # type: ignore[attr-defined]
