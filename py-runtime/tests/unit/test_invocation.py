from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest
from pydantic import BaseModel

from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import ToolCallBlock
from sztu_code.core.tools.base import BaseTool, ToolExecutionState, ToolResult
from sztu_code.core.tools.invocation import invoke_tool
from sztu_code.core.tools.registry import ToolRegistry

# --- stub tools --------------------------------------------------------------


class _EchoParams(BaseModel):
    msg: str


class _EchoTool(BaseTool):
    name = "echo"
    description = "Echoes the msg param"
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {"msg": {"type": "string"}},
        "required": ["msg"],
    }
    params_model = _EchoParams

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        return ToolResult(content=str(params["msg"]))


class _SlowTool(BaseTool):
    name = "slow"
    description = "Sleeps forever"
    input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        await asyncio.sleep(60)
        return ToolResult(content="done")


class _CountingSlowTool(BaseTool):
    name = "counting_slow"
    description = "Records cancellation of a slow call"
    input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}

    def __init__(self, *, raise_cleanup_error: bool = False) -> None:
        self.calls = 0
        self.cancelled = False
        self.raise_cleanup_error = raise_cleanup_error

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        self.calls += 1
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            self.cancelled = True
            if self.raise_cleanup_error:
                raise RuntimeError("tool cleanup failed")
            raise
        return ToolResult(content="done")


class _CleanupResistingTool(BaseTool):
    name = "cleanup_resisting"
    description = "Delays cancellation cleanup"
    input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}

    def __init__(self) -> None:
        self.cancelled = False
        self.finished = asyncio.Event()

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            self.cancelled = True
            await asyncio.sleep(0.2)
        finally:
            self.finished.set()
        return ToolResult(content="late")


class _ClockAdvancingTool(BaseTool):
    name = "clock_advancing"
    description = "Advances the injected run clock before returning"
    input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}

    def __init__(self, clock: list[float]) -> None:
        self._clock = clock

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        self._clock[0] = 1.0
        return ToolResult(content="late")


class _IndefiniteSlowTool(_CountingSlowTool):
    name = "indefinite_slow"
    allows_indefinite_wait = True


class _ManagedTimeoutSlowTool(_CountingSlowTool):
    name = "managed_timeout_slow"
    manages_timeout = True


class _BrokenTool(BaseTool):
    name = "broken"
    description = "Always raises"
    input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        raise RuntimeError("boom")


class _ReturnedTimeoutTool(BaseTool):
    name = "returned_timeout"
    description = "Returns a timeout result"
    input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        return ToolResult(
            content="inner timeout",
            is_error=True,
            error_type="timeout",
        )


class _BashTestTool(BaseTool):
    name = "bash"
    description = "Returns a test command summary"
    input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        return ToolResult(content="3 passed in 0.12s")


# --- helpers -----------------------------------------------------------------


def _call(name: str, inp: dict[str, object] | None = None, uid: str = "t1") -> ToolCallBlock:
    return ToolCallBlock(id=uid, name=name, input=inp or {})


async def _run(
    registry: ToolRegistry,
    tool_call: ToolCallBlock,
    timeout: float = 5.0,
    remaining_s: float | None = None,
    clock: Callable[[], float] | None = None,
) -> tuple[ToolResult, list[BaseModel]]:
    bus = EventBus()
    events: list[BaseModel] = []

    async def _collect(e: BaseModel) -> None:
        events.append(e)

    bus.subscribe(_collect)
    result = await invoke_tool(
        registry,
        tool_call,
        bus,
        run_id="r1",
        timeout=timeout,
        remaining_s=remaining_s,
        clock=clock,
    )
    return result, events


# --- tests -------------------------------------------------------------------


# 功能：验证正常调用时返回工具内容且发布 started + finished 事件
# 设计：同时检查返回值和事件序列，因为 invoke_tool 的双重职责是"返回结果 + 发布事件"，缺一不可
async def test_success_returns_content_and_finished_event() -> None:
    registry = ToolRegistry()
    registry.register(_EchoTool())
    result, events = await _run(registry, _call("echo", {"msg": "hi"}))
    assert not result.is_error
    assert result.content == "hi"
    types = [e.type for e in events]  # type: ignore[attr-defined]
    assert types[0] == "tool.call_started"
    assert "tool.call_finished" in types
    assert "tool.call_failed" not in types


# 功能：验证调用不存在的工具时返回 runtime_error 并发布 failed 事件而非 finished
# 设计：传入空 registry，确认 error_type 和事件类型同时正确，排除"未知工具却发布了 finished"的情况
async def test_unknown_tool_returns_runtime_error() -> None:
    result, events = await _run(ToolRegistry(), _call("nonexistent"))
    assert result.is_error
    assert result.error_type == "runtime_error"
    assert "unknown tool" in result.content
    types = [e.type for e in events]  # type: ignore[attr-defined]
    assert "tool.call_started" in types
    assert "tool.call_failed" in types
    assert "tool.call_finished" not in types


# 功能：验证缺少必填参数时返回 schema_error 而非 runtime_error
# 设计：注册需要 msg 参数的 EchoTool 但传空 input，确认错误分类准确，schema 错误与运行时错误对 S4 重试策略有不同影响
async def test_missing_required_param_gives_schema_error() -> None:
    registry = ToolRegistry()
    registry.register(_EchoTool())
    result, events = await _run(registry, _call("echo", {}))  # "msg" is required
    assert result.is_error
    assert result.error_type == "schema_error"
    types = [e.type for e in events]  # type: ignore[attr-defined]
    assert "tool.call_failed" in types


# 功能：验证工具执行超时时返回 timeout 类型错误而非 runtime_error
# 设计：使用永久 sleep 的 SlowTool + 极短超时（50ms），测试 asyncio.wait_for 的超时路径，确认超时被正确分类
async def test_timeout_gives_timeout_error() -> None:
    registry = ToolRegistry()
    registry.register(_SlowTool())
    result, events = await _run(registry, _call("slow"), timeout=0.05)
    assert result.is_error
    assert result.error_type == "timeout"
    types = [e.type for e in events]  # type: ignore[attr-defined]
    assert "tool.call_failed" in types


async def test_tool_timeout_remains_inner_boundary_with_remaining_budget() -> None:
    registry = ToolRegistry()
    registry.register(_SlowTool())

    result, _ = await _run(
        registry,
        _call("slow"),
        timeout=0.01,
        remaining_s=1.0,
    )

    assert result.is_error
    assert result.error_type == "timeout"
    assert result.execution_state.value == "unknown"


async def test_returned_timeout_is_unknown_in_failure_event() -> None:
    registry = ToolRegistry()
    registry.register(_ReturnedTimeoutTool())

    result, events = await _run(registry, _call("returned_timeout"))

    assert result.is_error
    assert result.error_type == "timeout"
    assert result.execution_state == ToolExecutionState.UNKNOWN
    failed = [event for event in events if event.type == "tool.call_failed"]  # type: ignore[attr-defined]
    assert len(failed) == 1
    assert failed[0].execution_state == ToolExecutionState.UNKNOWN.value


# 功能：验证 Run 剩余时间比工具 timeout 更短时会取消工具并标记未知状态
# 设计：使用可取消 slow tool，断言只执行一次、收到取消、没有成功事件，避免底层结果迟到后伪装成功
async def test_run_remaining_cancels_slow_tool_without_success_event() -> None:
    tool = _CountingSlowTool()
    registry = ToolRegistry()
    registry.register(tool)

    result, events = await _run(
        registry,
        _call("counting_slow"),
        timeout=5.0,
        remaining_s=0.05,
    )

    assert result.is_error
    assert result.error_type == "deadline_exceeded"
    assert result.execution_state.value == "unknown"
    assert tool.calls == 1
    assert tool.cancelled
    assert not any(event.type == "tool.call_finished" for event in events)  # type: ignore[attr-defined]
    failed = [event for event in events if event.type == "tool.call_failed"]  # type: ignore[attr-defined]
    assert len(failed) == 1
    assert failed[0].error_class == "deadline_exceeded"
    assert failed[0].retry_reason == "run_deadline_exceeded"
    assert failed[0].execution_state == "unknown"


# 功能：验证调用开始前已耗尽 Run 预算时不会执行工具或发布已开始事件
# 设计：用计数工具和零剩余预算覆盖 pre-start gate，区分未开始与执行后超时
async def test_exhausted_run_remaining_skips_tool_before_start() -> None:
    tool = _CountingSlowTool()
    registry = ToolRegistry()
    registry.register(tool)

    result, events = await _run(
        registry,
        _call("counting_slow"),
        remaining_s=0.0,
    )

    assert result.is_error
    assert result.error_type == "deadline_exceeded"
    assert result.execution_state.value == "not_started"
    assert tool.calls == 0
    assert len(events) == 1
    assert events[0].type == "tool.call_failed"  # type: ignore[attr-defined]
    assert events[0].execution_state == ToolExecutionState.NOT_STARTED.value  # type: ignore[attr-defined]
    assert not any(event.type == "tool.call_started" for event in events)  # type: ignore[attr-defined]


async def test_positive_run_remaining_preserves_success() -> None:
    registry = ToolRegistry()
    registry.register(_EchoTool())

    result, events = await _run(
        registry,
        _call("echo", {"msg": "within deadline"}),
        timeout=5.0,
        remaining_s=1.0,
    )

    assert not result.is_error
    assert result.content == "within deadline"
    event_types = [event.type for event in events]  # type: ignore[attr-defined]
    assert event_types[0] == "tool.call_started"
    assert "tool.call_finished" in event_types
    assert "tool.call_failed" not in event_types


@pytest.mark.parametrize("tool_type", [_IndefiniteSlowTool, _ManagedTimeoutSlowTool])
async def test_parent_deadline_applies_to_indefinite_tool_flags(
    tool_type: type[_CountingSlowTool],
) -> None:
    tool = tool_type()
    registry = ToolRegistry()
    registry.register(tool)

    result, _ = await _run(
        registry,
        _call(tool.name),
        timeout=0.01,
        remaining_s=0.05,
    )

    assert result.is_error
    assert result.error_type == "deadline_exceeded"
    assert result.execution_state.value == "unknown"
    assert tool.calls == 1
    assert tool.cancelled


async def test_tool_cleanup_is_bounded_and_remains_unknown() -> None:
    tool = _CleanupResistingTool()
    registry = ToolRegistry()
    registry.register(tool)

    started = asyncio.get_running_loop().time()
    result, events = await _run(
        registry,
        _call("cleanup_resisting"),
        timeout=5.0,
        remaining_s=0.01,
    )
    elapsed = asyncio.get_running_loop().time() - started

    assert elapsed < 0.2
    assert result.is_error
    assert result.error_type == "deadline_exceeded"
    assert result.execution_state.value == "unknown"
    assert tool.cancelled
    await asyncio.wait_for(tool.finished.wait(), timeout=1.0)
    assert not any(event.type == "tool.call_finished" for event in events)  # type: ignore[attr-defined]


async def test_cleanup_crossing_inner_timeout_is_reclassified_as_deadline() -> None:
    tool = _CleanupResistingTool()
    registry = ToolRegistry()
    registry.register(tool)

    result, events = await _run(
        registry,
        _call("cleanup_resisting"),
        timeout=0.01,
        remaining_s=0.05,
    )

    assert result.is_error
    assert result.error_type == "deadline_exceeded"
    assert result.execution_state == ToolExecutionState.UNKNOWN
    failed = [event for event in events if event.type == "tool.call_failed"]  # type: ignore[attr-defined]
    assert len(failed) == 1
    assert failed[0].error_class == "deadline_exceeded"
    await asyncio.wait_for(tool.finished.wait(), timeout=1.0)


async def test_tool_uses_the_run_clock_for_late_result_detection() -> None:
    clock = [0.0]
    tool = _ClockAdvancingTool(clock)
    registry = ToolRegistry()
    registry.register(tool)

    result, events = await _run(
        registry,
        _call("clock_advancing"),
        timeout=5.0,
        remaining_s=1.0,
        clock=lambda: clock[0],
    )

    assert result.is_error
    assert result.error_type == "deadline_exceeded"
    assert result.execution_state.value == "unknown"
    failed = [event for event in events if event.type == "tool.call_failed"]  # type: ignore[attr-defined]
    assert len(failed) == 1
    assert failed[0].error_class == "deadline_exceeded"


async def test_deadline_wins_over_tool_cleanup_error() -> None:
    tool = _CountingSlowTool(raise_cleanup_error=True)
    registry = ToolRegistry()
    registry.register(tool)

    result, _ = await _run(
        registry,
        _call("counting_slow"),
        timeout=5.0,
        remaining_s=0.05,
    )

    assert result.is_error
    assert result.error_type == "deadline_exceeded"
    assert result.execution_state.value == "unknown"
    assert tool.calls == 1
    assert tool.cancelled


async def test_runtime_error_is_not_reclassified_when_run_budget_remains() -> None:
    registry = ToolRegistry()
    registry.register(_BrokenTool())

    result, _ = await _run(
        registry,
        _call("broken"),
        timeout=5.0,
        remaining_s=1.0,
    )

    assert result.is_error
    assert result.error_type == "runtime_error"
    assert result.execution_state.value == "completed"


# 功能：验证工具内部抛出异常时被捕获并转为 runtime_error，错误信息保留原始异常消息
# 设计：工具直接 raise RuntimeError，确认异常不向上传播（invoke_tool 的"不抛异常"契约），error_message 包含 "boom"
async def test_runtime_exception_gives_runtime_error() -> None:
    registry = ToolRegistry()
    registry.register(_BrokenTool())
    result, events = await _run(registry, _call("broken"))
    assert result.is_error
    assert result.error_type == "runtime_error"
    assert "boom" in result.content


# 功能：验证 tool.call_started 始终是第一个被发布的事件，即使工具调用最终失败
# 设计：用不存在的工具触发失败路径，确认即使失败也先发布 started，保证事件流的时序可观测性
async def test_started_event_always_first() -> None:
    result, events = await _run(ToolRegistry(), _call("nonexistent"))
    assert events[0].type == "tool.call_started"  # type: ignore[attr-defined]


# 功能：验证常见测试命令成功后额外发布可回放的 test.result 事件。
# 设计：以名为 bash 的替身返回 pytest 摘要，断言事件包含通过状态与浓缩输出，避免客户端只能从原始终端文本猜测验证结论。
async def test_test_command_publishes_structured_result() -> None:
    registry = ToolRegistry()
    registry.register(_BashTestTool())

    result, events = await _run(registry, _call("bash", {"command": "pytest -q"}, "test-1"))

    assert result.is_error is False
    test_event = next(event for event in events if event.type == "test.result")  # type: ignore[attr-defined]
    assert test_event.status == "passed"  # type: ignore[attr-defined]
    assert test_event.summary == "3 passed in 0.12s"  # type: ignore[attr-defined]

# 功能：验证 started 事件总是包含 description，且元数据不会传入实际工具参数。
# 设计：检查事件参数与 echo 执行结果，确保标题补齐不会破坏已有 params_model。
async def test_started_event_contains_generated_description() -> None:
    registry = ToolRegistry()
    registry.register(_EchoTool())
    result, events = await _run(registry, _call("echo", {"msg": "hello"}))
    started = next(event for event in events if event.type == "tool.call_started")  # type: ignore[attr-defined]
    assert started.params["description"] == "调用 echo"  # type: ignore[attr-defined]
    assert result.content == "hello"
