from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from sztu_code.core.bus.commands import UserQuestionAnswer, UserQuestionItem
from sztu_code.core.config import SztuConfig
from sztu_code.core.events.bus import EventBus
from sztu_code.core.interaction.user_questions import UserQuestionManager
from sztu_code.core.llm.types import ToolCallBlock
from sztu_code.core.permissions.manager import PermissionManager
from sztu_code.core.runner import AgentRunner
from sztu_code.core.task.manager import TaskManager
from sztu_code.core.tools.builtin.ask_user_question import AskUserQuestionTool
from sztu_code.core.tools.invocation import invoke_tool
from sztu_code.core.tools.registry import ToolRegistry


# 功能：验证挂起问题可被完整回答并按 requested/resolved 顺序发布事件
# 设计：用 asyncio.Event 捕获请求到达点，再通过同一 rpc_id 回答，证明 ask Promise 在回答前保持挂起
async def test_question_manager_waits_for_structured_answer() -> None:
    bus = EventBus()
    manager = UserQuestionManager(bus)
    events: list[BaseModel] = []
    requested = asyncio.Event()

    # 收集提问生命周期事件，并在 requested 到达时解除测试等待
    async def collect(event: BaseModel) -> None:
        events.append(event)
        if getattr(event, "type", "") == "question.requested":
            requested.set()

    bus.subscribe(collect)
    question = UserQuestionItem.model_validate(
        {
            "id": "theme",
            "header": "选择主题",
            "question": "使用哪种方案？",
            "options": [
                {"label": "浅色", "description": "保持明亮界面"},
                {"label": "深色", "description": "降低视觉亮度"},
            ],
        }
    )
    task = asyncio.create_task(
        manager.ask(session_id="session-1", run_id="run-1", questions=[question])
    )

    await asyncio.wait_for(requested.wait(), timeout=1)
    pending = manager.list_pending()
    assert len(pending) == 1
    assert task.done() is False

    await manager.respond(
        rpc_id=pending[0].rpc_id,
        session_id="session-1",
        answers=[UserQuestionAnswer(id="theme", selected=["深色"])],
    )

    answers = await asyncio.wait_for(task, timeout=1)
    assert answers[0].selected == ["深色"]
    assert [getattr(event, "type", "") for event in events] == [
        "question.requested",
        "question.resolved",
    ]


# 功能：验证非法选项不会错误恢复挂起工具，取消 run 后挂起项会清理并广播 cancelled
# 设计：先提交请求中不存在的 label 并确认 pending 保留，再取消 ask task 覆盖刷新恢复表的撤销路径
async def test_invalid_answer_keeps_question_pending_until_cancelled() -> None:
    bus = EventBus()
    manager = UserQuestionManager(bus)
    events: list[BaseModel] = []

    # 收集 resolved 事件，确认取消结果能通知所有已连接客户端撤下界面
    async def collect(event: BaseModel) -> None:
        events.append(event)

    bus.subscribe(collect)
    question = UserQuestionItem.model_validate(
        {
            "id": "mode",
            "question": "选择模式",
            "options": [{"label": "安全"}, {"label": "快速"}],
        }
    )
    task = asyncio.create_task(
        manager.ask(session_id="session-1", run_id="run-1", questions=[question])
    )
    while not manager.list_pending():
        await asyncio.sleep(0)
    rpc_id = manager.list_pending()[0].rpc_id

    with pytest.raises(ValueError, match="unknown option"):
        await manager.respond(
            rpc_id=rpc_id,
            session_id="session-1",
            answers=[UserQuestionAnswer(id="mode", selected=["不存在"])],
        )
    assert len(manager.list_pending()) == 1

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert manager.list_pending() == []
    resolved = [event for event in events if getattr(event, "type", "") == "question.resolved"]
    assert resolved[-1].outcome == "cancelled"  # type: ignore[attr-defined]


# 功能：验证 ask_user_question 通过统一 invoke_tool 调用时不受普通工具超时限制
# 设计：给 invoke_tool 传 10ms 超时但延迟 30ms 回答，若交互工具标记失效则结果会错误变成 timeout
async def test_ask_user_question_tool_waits_beyond_normal_tool_timeout() -> None:
    bus = EventBus()
    manager = UserQuestionManager(bus)
    registry = ToolRegistry()
    registry.register(AskUserQuestionTool(manager, "session-1", "run-1"))
    tool_call = ToolCallBlock(
        id="tool-1",
        name="ask_user_question",
        input={
            "questions": [
                {
                    "id": "theme",
                    "question": "使用哪种方案？",
                    "options": [{"label": "浅色"}, {"label": "深色"}],
                }
            ]
        },
    )
    task = asyncio.create_task(
        invoke_tool(
            registry,
            tool_call,
            bus,
            run_id="run-1",
            timeout=0.01,
            permission_manager=PermissionManager(timeout_s=0.01),
            session_id="session-1",
        )
    )
    for _ in range(100):
        if manager.list_pending() or task.done():
            break
        await asyncio.sleep(0)
    assert manager.list_pending(), "interactive questions must bypass permission approval"
    await asyncio.sleep(0.03)
    pending = manager.list_pending()[0]
    await manager.respond(
        rpc_id=pending.rpc_id,
        session_id="session-1",
        answers=[UserQuestionAnswer(id="theme", selected=["深色"])],
    )

    result = await asyncio.wait_for(task, timeout=1)
    assert result.is_error is False
    assert json.loads(result.content) == {
        "answers": [{"id": "theme", "selected": ["深色"]}]
    }


# 功能：验证标准 Agent 工具注册表会为 session run 挂载 ask_user_question
# 设计：直接构建默认 registry 并检查工具实例，避免依赖真实模型调用即可覆盖 preset 等价的挂载边界
def test_standard_runner_registry_mounts_ask_user_question(tmp_path: Path) -> None:
    manager = UserQuestionManager(EventBus())
    runner = AgentRunner(SztuConfig(), user_question_manager=manager)

    registry = runner._build_registry(  # noqa: SLF001
        TaskManager(tmp_path / "tasks"),
        run_id="run-1",
        session_id="session-1",
    )

    assert isinstance(registry.get("ask_user_question"), AskUserQuestionTool)
