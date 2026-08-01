from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from sztu_code.core.context import ExecutionContext
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import LlmResponse, ToolCallBlock
from sztu_code.core.loop import AgentLoop
from sztu_code.core.permissions.denial_tracker import DenialTracker
from sztu_code.core.subagent.registry import BackgroundTaskRegistry
from sztu_code.core.tools.base import BaseTool, ToolResult
from sztu_code.core.tools.registry import ToolRegistry

# --- stubs -------------------------------------------------------------------


class _MockProvider:
    """Returns canned responses in order; raises exc immediately if given."""

    def __init__(
        self,
        responses: list[LlmResponse],
        exc: BaseException | None = None,
    ) -> None:
        self._responses = iter(responses)
        self._exc = exc

    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> LlmResponse:
        if self._exc is not None:
            raise self._exc
        return next(self._responses)


class _EchoTool(BaseTool):
    name = "echo"
    description = "Echoes msg"
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {"msg": {"type": "string"}},
        "required": ["msg"],
    }

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        return ToolResult(content=str(params["msg"]))


class _FailTool(BaseTool):
    name = "fail"
    description = "Always raises"
    input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        raise RuntimeError("tool error")


# --- helpers -----------------------------------------------------------------


def _ctx(max_steps: int = 5) -> ExecutionContext:
    return ExecutionContext(run_id="r1", goal="test goal", max_steps=max_steps)


def _tc(name: str = "echo", inp: dict[str, object] | None = None, uid: str = "t1") -> ToolCallBlock:
    return ToolCallBlock(id=uid, name=name, input=inp or {"msg": "hi"})


def _make_loop(
    provider: _MockProvider,
    registry: ToolRegistry | None = None,
    bus: EventBus | None = None,
) -> tuple[AgentLoop, EventBus]:
    b = bus or EventBus()
    return AgentLoop(provider, registry or ToolRegistry(), b), b  # type: ignore[arg-type]


async def _events(bus: EventBus) -> list[BaseModel]:
    collected: list[BaseModel] = []

    async def _h(e: BaseModel) -> None:
        collected.append(e)

    bus.subscribe(_h)
    return collected


# --- tests -------------------------------------------------------------------


# 功能：验证 LLM 返回 end_turn 时 loop 将 context 标记为 success
# 设计：单步 provider 直接返回 end_turn，最简正常路径，确认 loop 的基本终止逻辑
async def test_end_turn_marks_success() -> None:
    provider = _MockProvider([LlmResponse(stop_reason="end_turn", text="done")])
    loop, _ = _make_loop(provider)
    ctx = _ctx()
    await loop.run(ctx)
    assert ctx.status == "success"
    assert ctx.step == 1


# 功能：验证达到 max_steps 时 loop 以 exceeded_max_steps 原因将 context 标记为 failed
# 设计：设置 max_steps=2 + 无限 tool_use provider，同时验证 step 数量和失败原因，确认计数器与终止逻辑联动正确
async def test_max_steps_marks_failed() -> None:
    tc = _tc("unknown", {})
    provider = _MockProvider([LlmResponse(stop_reason="tool_use", tool_calls=[tc])] * 10)
    loop, _ = _make_loop(provider)
    ctx = _ctx(max_steps=2)
    await loop.run(ctx)
    assert ctx.status == "failed"
    assert ctx.reason == "exceeded_max_steps"
    assert ctx.step == 2


# 功能：验证"调工具 → end_turn"的两步路径最终标记为 success
# 设计：provider 返回 [tool_use, end_turn] 序列，注册真实 EchoTool，覆盖最常见的正常工作路径
async def test_tool_use_then_end_turn_marks_success() -> None:
    provider = _MockProvider([
        LlmResponse(stop_reason="tool_use", tool_calls=[_tc()]),
        LlmResponse(stop_reason="end_turn", text="summary"),
    ])
    registry = ToolRegistry()
    registry.register(_EchoTool())
    loop, _ = _make_loop(provider, registry)
    ctx = _ctx()
    await loop.run(ctx)
    assert ctx.status == "success"
    assert ctx.step == 2


# 功能：验证工具结果按 Anthropic 格式（tool_result user 消息）追加到消息历史
# 设计：检查 messages[2]（tool_result 所在位置），断言 tool_use_id 和 content，确认 loop 正确调用了 context.add_tool_result
async def test_tool_result_appended_to_context() -> None:
    provider = _MockProvider([
        LlmResponse(stop_reason="tool_use", tool_calls=[_tc(inp={"msg": "hello"})]),
        LlmResponse(stop_reason="end_turn"),
    ])
    registry = ToolRegistry()
    registry.register(_EchoTool())
    loop, _ = _make_loop(provider, registry)
    ctx = _ctx()
    await loop.run(ctx)
    # messages: [goal, assistant(tool_use), user(tool_result), assistant(end_turn)]
    tool_result_msg = ctx.messages[2]
    assert tool_result_msg["role"] == "user"
    block = tool_result_msg["content"][0]  # type: ignore[index]
    assert block["tool_use_id"] == "t1"
    assert block["content"] == "hello"


# 功能：验证工具失败时 loop 不终止，而是将错误追加上下文让 LLM 重新决策
# 设计：工具始终 raise + provider 第二步返回 end_turn，确认 loop 最终到达 success；这是 agent 区别于普通脚本的核心特性
async def test_tool_failure_loop_continues_to_success() -> None:
    provider = _MockProvider([
        LlmResponse(stop_reason="tool_use", tool_calls=[_tc("fail", {})]),
        LlmResponse(stop_reason="end_turn", text="handled error"),
    ])
    registry = ToolRegistry()
    registry.register(_FailTool())
    loop, _ = _make_loop(provider, registry)
    ctx = _ctx()
    await loop.run(ctx)
    assert ctx.status == "success"
    assert ctx.step == 2


# 功能：验证工具失败的错误信息以 is_error=True 追加进上下文，让 LLM 能感知工具调用失败
# 设计：检查 tool_result block 中的 is_error 标记，与 test_tool_failure_loop_continues_to_success 互补
async def test_tool_failure_result_is_error_in_context() -> None:
    provider = _MockProvider([
        LlmResponse(stop_reason="tool_use", tool_calls=[_tc("fail", {})]),
        LlmResponse(stop_reason="end_turn"),
    ])
    registry = ToolRegistry()
    registry.register(_FailTool())
    loop, _ = _make_loop(provider, registry)
    ctx = _ctx()
    await loop.run(ctx)
    tool_result_msg = ctx.messages[2]
    block = tool_result_msg["content"][0]  # type: ignore[index]
    assert block.get("is_error") is True


# 功能：验证收到 CancelledError 时 loop 将 context 标记为 cancelled 后继续上抛 CancelledError
# 设计：用 pytest.raises 捕获 CancelledError，同时检查 context.status，确认优雅退出行为：先记录状态，再传播取消信号
async def test_cancelled_error_marks_failed_and_reraises() -> None:
    provider = _MockProvider([], exc=asyncio.CancelledError())
    loop, _ = _make_loop(provider)
    ctx = _ctx()
    with pytest.raises(asyncio.CancelledError):
        await loop.run(ctx)
    assert ctx.status == "failed"
    assert ctx.reason == "cancelled"


# 功能：验证 LLM 调用异常被捕获并标记为 llm_error，不向上传播
# 设计：provider 抛 RuntimeError，确认 loop 不崩溃、context 状态为 failed/llm_error，异常被正确吸收
async def test_llm_api_error_marks_failed() -> None:
    provider = _MockProvider([], exc=RuntimeError("api error"))
    loop, _ = _make_loop(provider)
    ctx = _ctx()
    await loop.run(ctx)
    assert ctx.status == "failed"
    assert ctx.reason == "llm_error"


# 功能：验证每个步骤都发布 step.started 和 step.finished 事件
# 设计：注入 bus + 事件收集器，检查事件类型集合，确认步骤级事件的可观测性（S2 TUI 依赖这两个事件显示进度）
async def test_step_started_and_finished_events_published() -> None:
    bus = EventBus()
    events = await _events(bus)
    provider = _MockProvider([LlmResponse(stop_reason="end_turn")])
    loop, _ = _make_loop(provider, bus=bus)
    ctx = _ctx()
    await loop.run(ctx)
    types = [e.type for e in events]  # type: ignore[attr-defined]
    assert "step.started" in types
    assert "step.finished" in types


# 功能：验证多步执行后 step 计数器正确累积到步数总量
# 设计：三步序列 [tool_use, tool_use, end_turn]，确认 step==3，排除计数器初始化错误或某步未递增的情况
async def test_step_counter_increments_across_steps() -> None:
    provider = _MockProvider([
        LlmResponse(stop_reason="tool_use", tool_calls=[_tc()]),
        LlmResponse(stop_reason="tool_use", tool_calls=[_tc()]),
        LlmResponse(stop_reason="end_turn"),
    ])
    registry = ToolRegistry()
    registry.register(_EchoTool())
    loop, _ = _make_loop(provider, registry)
    ctx = _ctx(max_steps=10)
    await loop.run(ctx)
    assert ctx.step == 3
    assert ctx.status == "success"


# 功能：验证 LLM 文本响应以正确的 content block 格式追加到消息历史
# 设计：检查 messages[1] 的 role 和 content block 结构，确认 loop 构造的 assistant 消息符合 Anthropic 格式
async def test_assistant_message_blocks_added_to_context() -> None:
    provider = _MockProvider([LlmResponse(stop_reason="end_turn", text="answer")])
    loop, _ = _make_loop(provider)
    ctx = _ctx()
    await loop.run(ctx)
    assistant_msg = ctx.messages[1]
    assert assistant_msg["role"] == "assistant"
    blocks = assistant_msg["content"]
    assert blocks[0]["type"] == "text"  # type: ignore[index]
    assert blocks[0]["text"] == "answer"  # type: ignore[index]


# ── denial tracker 集成测试 ────────────────────────────────────────────────────


class _PermissionDenyTool(BaseTool):
    """模拟权限被拒绝的工具，返回 permission_denied 错误。"""

    name = "deny_tool"
    description = "Always returns permission_denied"
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {"x": {"type": "string"}},
        "required": ["x"],
    }

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        return ToolResult(
            content="Permission denied by user.",
            is_error=True,
            error_type="permission_denied",
        )


# 功能：验证连续 permission_denied 触发 DenialTracker 注入干预消息到上下文
# 设计：用 _PermissionDenyTool + DenialTracker(max_consecutive=2, max_total=100)，
#       验证第 3 次工具调用前 context.messages 中出现干预消息（以 role=user 且包含 tool name）
async def test_denial_tracker_injects_intervention_message() -> None:
    tc = _tc("deny_tool", {"x": "1"}, uid="td1")
    # 步骤 1-2：tool_use（被拒绝），步骤 3：end_turn
    provider = _MockProvider([
        LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
        LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
        LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
        LlmResponse(stop_reason="end_turn", text="switched strategy"),
    ])
    registry = ToolRegistry()
    registry.register(_PermissionDenyTool())
    bus = EventBus()
    # max_consecutive=2 所以第 2 次拒绝后触发干预
    denial_tracker = DenialTracker(max_consecutive=2, max_total=100)
    loop = AgentLoop(
        provider, registry, bus,
        denial_tracker=denial_tracker,
    )
    ctx = _ctx(max_steps=10)
    await loop.run(ctx)

    # 干预消息应出现在 context.messages 中（role=user, 非 assistant/tool_result）
    intervention_msgs = [
        m for m in ctx.messages
        if m["role"] == "user"
        and isinstance(m["content"], str)
        and "repeatedly rejected" in str(m["content"])
    ]
    assert len(intervention_msgs) >= 1, (
        f"Expected intervention message in context, got messages: {ctx.messages}"
    )
    # 最终应成功
    assert ctx.status == "success"


# 功能：验证 DenialTracker 发布 denial.intervention 事件
# 设计：订阅 bus 收集事件，确认 DenialInterventionEvent 出现在事件流中
async def test_denial_tracker_publishes_intervention_event() -> None:
    tc = _tc("deny_tool", {"x": "1"}, uid="td2")
    provider = _MockProvider([
        LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
        LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
        LlmResponse(stop_reason="end_turn", text="done"),
    ])
    registry = ToolRegistry()
    registry.register(_PermissionDenyTool())
    bus = EventBus()
    events: list[BaseModel] = []

    async def _collect(e: BaseModel) -> None:
        events.append(e)

    bus.subscribe(_collect)

    denial_tracker = DenialTracker(max_consecutive=2, max_total=100)
    loop = AgentLoop(
        provider, registry, bus,
        denial_tracker=denial_tracker,
    )
    ctx = _ctx(max_steps=5)
    await loop.run(ctx)

    intervention_events = [
        e for e in events
        if getattr(e, "type", "") == "denial.intervention"
    ]
    assert len(intervention_events) == 1
    evt = intervention_events[0]
    assert getattr(evt, "tool_name", "") == "deny_tool"
    assert getattr(evt, "total_denials", 0) >= 2


# ── 后台 subagent 等待集成测试 ─────────────────────────────────────────────────


# 功能：end_turn 前若有后台 subagent 未完成，loop 等待其落定后才标记 success
# 设计：注册被 Event 阻塞的后台任务，run_task 异步跑 loop，断言等待期间 run_task 未完成，
#       放行 Event 后 loop 才结束，且 result 含后台子 agent 的结果摘要
async def test_loop_waits_for_background_before_end_turn() -> None:
    gate = asyncio.Event()

    async def _bg() -> None:
        await gate.wait()

    child_ctx = ExecutionContext(run_id="bg-1", goal="bg", max_steps=1, result="bg done")
    registry = BackgroundTaskRegistry()
    registry.register("bg-1", asyncio.create_task(_bg()), child_ctx)

    ctx = _ctx()
    ctx.pending_background_run_ids.add("bg-1")
    provider = _MockProvider([LlmResponse(stop_reason="end_turn", text="done")])
    loop = AgentLoop(provider, ToolRegistry(), EventBus(), task_registry=registry)

    run_task = asyncio.create_task(loop.run(ctx))
    await asyncio.sleep(0.05)
    assert not run_task.done(), "loop must wait for the background task"

    gate.set()
    await asyncio.wait_for(run_task, 2.0)
    assert ctx.status == "success"
    assert "bg done" in ctx.result


# 功能：已完成后台任务不阻塞，end_turn 后立即结束且摘要进入 result
# 设计：预注册已完成的后台任务，断言 loop 不等待、状态为 success、结果含摘要
async def test_loop_background_already_done() -> None:
    async def _bg() -> None:
        return None

    child_ctx = ExecutionContext(run_id="bg-done", goal="bg", max_steps=1, result="already done")
    task = asyncio.create_task(_bg())
    await asyncio.sleep(0.01)  # 让后台任务先完成
    registry = BackgroundTaskRegistry()
    registry.register("bg-done", task, child_ctx)

    ctx = _ctx()
    ctx.pending_background_run_ids.add("bg-done")
    provider = _MockProvider([LlmResponse(stop_reason="end_turn", text="done")])
    loop = AgentLoop(provider, ToolRegistry(), EventBus(), task_registry=registry)

    await asyncio.wait_for(loop.run(ctx), 2.0)
    assert ctx.status == "success"
    assert "already done" in ctx.result


# 功能：max_steps 触发失败时同样等待后台任务落定
# 设计：max_steps=1 + 阻塞后台任务，断言 loop 等后台结束才标记 exceeded_max_steps，摘要仍写入 result
async def test_loop_max_steps_still_waits() -> None:
    gate = asyncio.Event()

    async def _bg() -> None:
        await gate.wait()

    child_ctx = ExecutionContext(run_id="bg-m", goal="bg", max_steps=1, result="bg result")
    registry = BackgroundTaskRegistry()
    registry.register("bg-m", asyncio.create_task(_bg()), child_ctx)

    ctx = _ctx(max_steps=1)
    ctx.pending_background_run_ids.add("bg-m")
    provider = _MockProvider([
        LlmResponse(stop_reason="tool_use", tool_calls=[_tc("unknown", {})]),
    ])
    loop = AgentLoop(provider, ToolRegistry(), EventBus(), task_registry=registry)

    run_task = asyncio.create_task(loop.run(ctx))
    await asyncio.sleep(0.05)
    assert not run_task.done()

    gate.set()
    await asyncio.wait_for(run_task, 2.0)
    assert ctx.status == "failed"
    assert ctx.reason == "exceeded_max_steps"
    assert "bg result" in ctx.result


# 功能：未传入 task_registry 时 pending 集合被忽略，loop 不等待不报错
# 设计：有 pending 但 task_registry=None，断言 loop 正常完成（旧构造点安全）
async def test_loop_no_registry_no_wait() -> None:
    ctx = _ctx()
    ctx.pending_background_run_ids.add("bg-x")
    provider = _MockProvider([LlmResponse(stop_reason="end_turn", text="done")])
    loop = AgentLoop(provider, ToolRegistry(), EventBus())

    await asyncio.wait_for(loop.run(ctx), 2.0)
    assert ctx.status == "success"
