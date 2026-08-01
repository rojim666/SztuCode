from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from sztu_code.core.context import ExecutionContext
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import LlmResponse, ToolCallBlock, UsageStats
from sztu_code.core.subagent.registry import BackgroundTaskRegistry
from sztu_code.core.subagent.tool import AgentResultTool, SpawnAgentTool


def _make_provider(result_text: str = "child done") -> Any:
    provider = AsyncMock()
    provider.chat = AsyncMock(
        return_value=LlmResponse(
            stop_reason="end_turn",
            tool_calls=[],
            text=result_text,
            usage=UsageStats(
                input_tokens=10,
                output_tokens=5,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
                context_pct=0.01,
            ),
        )
    )
    return provider


def _make_tool(
    tmp_path: Path,
    provider: Any = None,
    depth: int = 0,
    parent_context: ExecutionContext | None = None,
    session: Any = None,
    store: Any = None,
) -> tuple[SpawnAgentTool, BackgroundTaskRegistry, EventBus]:
    bus = EventBus()
    registry = BackgroundTaskRegistry()
    tool = SpawnAgentTool(
        provider=provider or _make_provider(),
        parent_bus=bus,
        parent_run_id="parent-run-01",
        permission_manager=None,
        max_steps=5,
        task_registry=registry,
        runs_dir=tmp_path,
        session_id="sess-test",
        depth=depth,
        parent_context=parent_context,
        session=session,
        store=store,
    )
    return tool, registry, bus


# 功能：前台模式下 spawn_agent 应阻塞直到子 agent 完成并返回其结果
# 设计：使用返回 end_turn 的 mock provider，验证 tool_result.content 包含 provider 返回的文字
@pytest.mark.asyncio
async def test_foreground_returns_result(tmp_path: Path) -> None:
    tool, _, _ = _make_tool(tmp_path, _make_provider("analysis complete"))
    result = await tool.invoke({
        "description": "分析代码",
        "prompt": "分析 src/ 目录",
    })
    assert not result.is_error
    assert "analysis complete" in result.content


# 功能：后台模式应立即返回含 run_id 的消息，不阻塞等待子 agent
# 设计：run_in_background=true 后验证返回消息含 "run_id=" 并且任务注册表已有对应条目
@pytest.mark.asyncio
async def test_background_returns_run_id(tmp_path: Path) -> None:
    tool, registry, _ = _make_tool(tmp_path)
    result = await tool.invoke({
        "description": "后台任务",
        "prompt": "做点事",
        "run_in_background": True,
    })
    assert not result.is_error
    assert "run_id=" in result.content
    # extract run_id from message
    run_id = result.content.split("run_id=")[1].split(".")[0]
    assert registry.get(run_id) is not None


# 功能：后台任务未完成时 agent_result 应返回 "still running"
# 设计：用 Event 阻塞 provider.chat，在未等待任务完成时查询 agent_result
@pytest.mark.asyncio
async def test_agent_result_pending(tmp_path: Path) -> None:
    event = asyncio.Event()

    async def slow_chat(*args: Any, **kwargs: Any) -> LlmResponse:
        await event.wait()
        return LlmResponse(
            stop_reason="end_turn",
            tool_calls=[],
            text="done",
            usage=UsageStats(0, 0, 0, 0, 0.0),
        )

    provider = MagicMock()
    provider.chat = slow_chat

    tool, registry, _ = _make_tool(tmp_path, provider)
    spawn_result = await tool.invoke({
        "description": "slow task",
        "prompt": "do something slow",
        "run_in_background": True,
    })
    run_id = spawn_result.content.split("run_id=")[1].split(".")[0]

    result_tool = AgentResultTool(registry)
    result = await result_tool.invoke({"run_id": run_id})
    assert result.content == "still running"
    assert not result.is_error

    event.set()
    await asyncio.sleep(0.05)


# 功能：后台任务完成后 agent_result 应返回子 agent 的最终文本
# 设计：等待后台任务 task 完成后调用 agent_result，断言返回内容与 provider 结果一致
@pytest.mark.asyncio
async def test_agent_result_done(tmp_path: Path) -> None:
    tool, registry, _ = _make_tool(tmp_path, _make_provider("final answer"))
    spawn_result = await tool.invoke({
        "description": "bg task",
        "prompt": "do it",
        "run_in_background": True,
    })
    run_id = spawn_result.content.split("run_id=")[1].split(".")[0]

    entry = registry.get(run_id)
    assert entry is not None
    task, _ = entry
    await asyncio.wait_for(task, timeout=5.0)

    result_tool = AgentResultTool(registry)
    result = await result_tool.invoke({"run_id": run_id})
    assert not result.is_error
    assert "final answer" in result.content


# 功能：depth=2 时调用 spawn_agent 应返回 is_error=True（嵌套限制）
# 设计：构造 depth=2 的工具，断言 invoke 直接返回错误而不调用 provider
@pytest.mark.asyncio
async def test_nesting_limit(tmp_path: Path) -> None:
    provider = _make_provider()
    tool, _, _ = _make_tool(tmp_path, provider, depth=2)
    result = await tool.invoke({
        "description": "nested",
        "prompt": "do nested work",
    })
    assert result.is_error
    assert "nesting limit" in result.content
    provider.chat.assert_not_called()


# 功能：agent_result 查询不存在的 run_id 应返回 is_error=True
# 设计：空 registry 中查询随机 run_id，验证错误消息含 "Unknown"
@pytest.mark.asyncio
async def test_agent_result_unknown_run_id(tmp_path: Path) -> None:
    registry = BackgroundTaskRegistry()
    tool = AgentResultTool(registry)
    result = await tool.invoke({"run_id": "nonexistent-id"})
    assert result.is_error
    assert "Unknown" in result.content


# 功能：SubagentStartedEvent 应在前台 spawn 时发布到父 bus
# 设计：订阅父 bus 收集所有事件，断言 subagent.started 出现，且 parent_run_id 和 description 正确
@pytest.mark.asyncio
async def test_foreground_publishes_started_event(tmp_path: Path) -> None:
    from sztu_code.core.bus.events import SubagentStartedEvent

    tool, _, bus = _make_tool(tmp_path)
    events: list[Any] = []

    async def _collect(e: Any) -> None:
        events.append(e)

    bus.subscribe(_collect)

    await tool.invoke({
        "description": "test task",
        "prompt": "test prompt",
    })
    started = [e for e in events if isinstance(e, SubagentStartedEvent)]
    assert len(started) == 1
    assert started[0].parent_run_id == "parent-run-01"
    assert started[0].description == "test task"


# 功能：空 subagent_type 默认使用 coder 角色，system prompt 含 coder 标记
# 设计：捕获 provider.chat 的 system 参数，不带 subagent_type spawn，断言含 coder 系统提示关键词
async def test_default_role_is_coder(tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    async def _chat(*args: Any, **kwargs: Any) -> LlmResponse:
        captured["system"] = str(kwargs.get("system", ""))
        return LlmResponse(
            stop_reason="end_turn", tool_calls=[], text="ok",
            usage=UsageStats(0, 0, 0, 0, 0.0),
        )

    provider = MagicMock()
    provider.chat = _chat
    tool, _, _ = _make_tool(tmp_path, provider)
    result = await tool.invoke({"description": "任务", "prompt": "干活"})
    assert not result.is_error
    assert "通用软件工程" in captured["system"]


# 功能：subagent_type 指定角色时 system prompt 使用该角色配置
# 设计：subagent_type="explore"，断言 system 含 explore 的系统提示关键词
async def test_explicit_role_uses_profile(tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    async def _chat(*args: Any, **kwargs: Any) -> LlmResponse:
        captured["system"] = str(kwargs.get("system", ""))
        return LlmResponse(
            stop_reason="end_turn", tool_calls=[], text="ok",
            usage=UsageStats(0, 0, 0, 0, 0.0),
        )

    provider = MagicMock()
    provider.chat = _chat
    tool, _, _ = _make_tool(tmp_path, provider)
    result = await tool.invoke({"description": "任务", "prompt": "探索", "subagent_type": "explore"})
    assert not result.is_error
    assert "代码库探索专家" in captured["system"]


# 功能：spawn 时应用 skill，skill 系统提示合并进子 agent 的 system prompt
# 设计：skill="orchestrate"，断言 system 同时含 coder 与 orchestrate 的标记文本
async def test_skill_merge(tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    async def _chat(*args: Any, **kwargs: Any) -> LlmResponse:
        captured["system"] = str(kwargs.get("system", ""))
        return LlmResponse(
            stop_reason="end_turn", tool_calls=[], text="ok",
            usage=UsageStats(0, 0, 0, 0, 0.0),
        )

    provider = MagicMock()
    provider.chat = _chat
    tool, _, _ = _make_tool(tmp_path, provider)
    result = await tool.invoke({"description": "任务", "prompt": "分析 X", "skill": "orchestrate"})
    assert not result.is_error
    assert "通用软件工程" in captured["system"]  # coder 基础提示
    assert "Multi-agent 协调者" in captured["system"]  # orchestrate 技能提示


# 功能：后台 spawn 会把 child_run_id 登记进父 context 的 pending 集合
# 设计：传入 parent_context，后台 spawn 后断言 run_id 出现在 pending_background_run_ids
async def test_background_tracks_pending_run_id(tmp_path: Path) -> None:
    parent = ExecutionContext(run_id="parent-ctx", goal="g", max_steps=5)
    tool, _, _ = _make_tool(tmp_path, parent_context=parent)
    result = await tool.invoke({
        "description": "后台任务",
        "prompt": "做点事",
        "run_in_background": True,
    })
    assert not result.is_error
    run_id = result.content.split("run_id=")[1].split(".")[0]
    assert run_id in parent.pending_background_run_ids


# 功能：plan 角色（permission_mode=plan）对已注册的写工具自动拒绝且不弹权限请求
# 设计：plan 白名单含 task_create，provider 先调用 task_create 再 end_turn；
#       断言发出 error_class=permission_denied 的 ToolCallFailedEvent 且无 PermissionRequestedEvent
async def test_plan_denies_write_tool(tmp_path: Path) -> None:
    from sztu_code.core.bus.events import PermissionRequestedEvent, ToolCallFailedEvent

    tc = ToolCallBlock(id="w1", name="task_create", input={"subject": "x", "description": "y"})
    resp1 = LlmResponse(stop_reason="tool_use", tool_calls=[tc], text="",
                        usage=UsageStats(0, 0, 0, 0, 0.0))
    resp2 = LlmResponse(stop_reason="end_turn", text="done", tool_calls=[],
                        usage=UsageStats(0, 0, 0, 0, 0.0))
    provider = AsyncMock()
    provider.chat = AsyncMock(side_effect=[resp1, resp2])

    tool, _, bus = _make_tool(tmp_path, provider)
    events: list[Any] = []

    async def _collect(e: Any) -> None:
        events.append(e)

    bus.subscribe(_collect)

    result = await tool.invoke({"description": "规划", "prompt": "做规划", "subagent_type": "plan"})
    assert not result.is_error
    denied = [e for e in events if isinstance(e, ToolCallFailedEvent)
              and e.error_class == "permission_denied"]
    assert len(denied) == 1, f"expected 1 permission_denied, got: {events}"
    requested = [e for e in events if isinstance(e, PermissionRequestedEvent)]
    assert len(requested) == 0


# 功能：plan 角色对只读工具正常放行并成功执行
# 设计：plan 白名单含 list_dir，provider 先调用 list_dir 再 end_turn；断言发出 ToolCallFinishedEvent
async def test_plan_allows_read_tool(tmp_path: Path) -> None:
    from sztu_code.core.bus.events import ToolCallFinishedEvent

    tc = ToolCallBlock(id="r1", name="list_dir", input={"path": "."})
    resp1 = LlmResponse(stop_reason="tool_use", tool_calls=[tc], text="",
                        usage=UsageStats(0, 0, 0, 0, 0.0))
    resp2 = LlmResponse(stop_reason="end_turn", text="done", tool_calls=[],
                        usage=UsageStats(0, 0, 0, 0, 0.0))
    provider = AsyncMock()
    provider.chat = AsyncMock(side_effect=[resp1, resp2])

    tool, _, bus = _make_tool(tmp_path, provider)
    events: list[Any] = []

    async def _collect(e: Any) -> None:
        events.append(e)

    bus.subscribe(_collect)

    result = await tool.invoke({"description": "规划", "prompt": "做规划", "subagent_type": "plan"})
    assert not result.is_error
    finished = [e for e in events if isinstance(e, ToolCallFinishedEvent)]
    assert any(e.tool_name == "list_dir" for e in finished), f"no list_dir finished: {events}"


# 功能：coder 前台子 agent 派发后台孙 agent 时，子 run 会等孙 agent 落定后才回报完成
# 设计：provider 按消息内容分流——child 第一步派发后台孙、第二步 end_turn、孙一步 end_turn；
#       断言 invoke 返回结果含孙 agent 的结果摘要，验证 transitive 等待语义
async def test_foreground_child_waits_for_grandchild(tmp_path: Path) -> None:
    spawn_call = ToolCallBlock(
        id="s1",
        name="spawn_agent",
        input={"description": "孙任务", "prompt": "grandchild work", "run_in_background": True},
    )

    def _end(text: str) -> LlmResponse:
        return LlmResponse(
            stop_reason="end_turn", text=text, tool_calls=[],
            usage=UsageStats(0, 0, 0, 0, 0.0),
        )

    async def _chat(messages: list[dict[str, object]], **kwargs: Any) -> LlmResponse:
        first_user = next(
            (m["content"] for m in messages
             if m["role"] == "user" and isinstance(m["content"], str)),
            "",
        )
        if first_user == "grandchild work":
            return _end("grandchild done")
        if any(
            m["role"] == "assistant"
            and isinstance(m["content"], list)
            and any(isinstance(b, dict) and b.get("name") == "spawn_agent" for b in m["content"])
            for m in messages
        ):
            return _end("child final")
        return LlmResponse(
            stop_reason="tool_use", tool_calls=[spawn_call], text="",
            usage=UsageStats(0, 0, 0, 0, 0.0),
        )

    provider = MagicMock()
    provider.chat = _chat
    tool, _, _ = _make_tool(tmp_path, provider)
    result = await tool.invoke({"description": "子任务", "prompt": "child work"})
    assert not result.is_error
    assert "grandchild done" in result.content
    assert "[subagent" in result.content
