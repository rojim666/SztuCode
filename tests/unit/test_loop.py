from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from pydantic import BaseModel

from sztu_code.core.compact.compactor import Compactor
from sztu_code.core.context import ExecutionContext
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import LlmResponse, ToolCallBlock, UsageStats
from sztu_code.core.loop import AgentLoop
from sztu_code.core.permissions.denial_tracker import DenialTracker
from sztu_code.core.permissions.manager import PermissionManager
from sztu_code.core.permissions.policy import PermissionDecision, ToolPolicy
from sztu_code.core.pricing import ModelPricing, PricingCatalog
from sztu_code.core.subagent.registry import BackgroundTaskRegistry
from sztu_code.core.tools.base import BaseTool, ToolPermission, ToolResult
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


class _CompactingProvider:
    """Returns a high-water tool_use/max_tokens call, a summary call, then end_turn."""

    def __init__(
        self,
        summary_text: str,
        first_stop_reason: str = "tool_use",
        with_tool_call: bool = True,
    ) -> None:
        self._summary_text = summary_text
        self._first_stop_reason = first_stop_reason
        self._with_tool_call = with_tool_call
        self._calls = 0

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
        self._calls += 1
        if self._calls == 1:
            tool_calls = [_tc(inp={"msg": "hi"})] if self._with_tool_call else []
            return LlmResponse(
                stop_reason=self._first_stop_reason,
                tool_calls=tool_calls,
                text="" if tool_calls else "partial",
                usage=UsageStats(
                    input_tokens=100_000,
                    output_tokens=10,
                    context_pct=0.9,
                ),
            )
        if run_id == "compact":
            return LlmResponse(
                stop_reason="end_turn",
                text=self._summary_text,
                usage=UsageStats(input_tokens=100_000, output_tokens=2),
            )
        return LlmResponse(
            stop_reason="end_turn",
            text="done",
            usage=UsageStats(input_tokens=200, output_tokens=10),
        )


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


@dataclass
class _ConcurrencyProbe:
    active: int = 0
    max_active: int = 0
    started: list[str] = field(default_factory=list)
    finished: list[str] = field(default_factory=list)


class _TimedTool(BaseTool):
    description = "Waits for a configured delay"
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "label": {"type": "string"},
            "delay": {"type": "number"},
            "fail": {"type": "boolean"},
        },
        "required": ["label", "delay"],
    }

    # 初始化可声明权限并记录并发行为的测试工具
    def __init__(
        self,
        name: str,
        permission: ToolPermission,
        probe: _ConcurrencyProbe,
    ) -> None:
        self.name = name
        self.required_permission = permission
        self._probe = probe

    # 等待指定时长并返回标签，可按参数产生不可重试失败
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        label = str(params["label"])
        self._probe.active += 1
        self._probe.max_active = max(self._probe.max_active, self._probe.active)
        self._probe.started.append(label)
        try:
            await asyncio.sleep(float(params["delay"]))
            self._probe.finished.append(label)
            if bool(params.get("fail", False)):
                return ToolResult(
                    content=f"failed:{label}",
                    is_error=True,
                    error_type="schema_error",
                )
            return ToolResult(content=f"done:{label}")
        finally:
            self._probe.active -= 1


class _UnknownPermissionTool(_TimedTool):
    # 模拟第三方工具返回框架无法识别的权限能力值
    def classify_permission(self, params: dict[str, object]) -> ToolPermission:
        return cast(ToolPermission, "unknown")


class _StringReadOnlyPermissionTool(_TimedTool):
    """Simulates a malformed third-party permission classifier result."""

    def classify_permission(self, params: dict[str, object]) -> ToolPermission:
        return cast(ToolPermission, "read_only")


class _StringAllowPermissionManager(PermissionManager):
    """Simulates a malformed third-party policy decision result."""

    def evaluate(self, tool_name: str, params: dict[str, object]) -> PermissionDecision:
        return cast(PermissionDecision, "allow")


class _RaisingReadTool(_TimedTool):
    # 模拟工具层异常，验证并发调度会隔离单项异常并继续收集其他结果
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        label = str(params["label"])
        self._probe.started.append(label)
        await asyncio.sleep(float(params.get("delay", 0)))
        raise RuntimeError(f"raised:{label}")


# --- helpers -----------------------------------------------------------------


def _ctx(max_steps: int = 5) -> ExecutionContext:
    return ExecutionContext(run_id="r1", goal="test goal", max_steps=max_steps)


def _tc(name: str = "echo", inp: dict[str, object] | None = None, uid: str = "t1") -> ToolCallBlock:
    return ToolCallBlock(id=uid, name=name, input=inp or {"msg": "hi"})


_SUMMARY = """\
## 1. Original Goal
test goal
## 2. Completed Steps
- echo tool called
## 3. Key Constraints & Discoveries
- none
## 4. Current File State
- none
## 5. Remaining TODOs
- finish
## 6. Critical Data
- none
"""


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


# 用一轮工具调用和结束响应构造并执行调度测试场景
async def _run_tool_batch(
    calls: list[ToolCallBlock],
    tools: list[BaseTool],
    *,
    max_concurrency: int,
    permission_manager: PermissionManager | None = None,
) -> tuple[ExecutionContext, list[BaseModel], float]:
    provider = _MockProvider(
        [
            LlmResponse(stop_reason="tool_use", tool_calls=calls),
            LlmResponse(stop_reason="end_turn", text="done"),
        ]
    )
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    bus = EventBus()
    events = await _events(bus)
    loop = AgentLoop(
        provider,
        registry,
        bus,
        permission_manager=permission_manager,
        tool_max_concurrency=max_concurrency,
    )
    context = _ctx()
    started = time.monotonic()
    await loop.run(context)
    return context, events, time.monotonic() - started


# --- tests -------------------------------------------------------------------


# 功能：验证首轮 end_turn 返回期间到达的 steer 会让 AgentLoop 继续执行下一次模型调用
# 设计：首个 provider 调用把消息放入真实 asyncio.Queue，再断言第二次调用看见该用户消息且最终成功
async def test_steering_received_at_end_turn_continues_loop() -> None:
    steering_queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()

    class _SteeringProvider:
        # 初始化调用记录，供测试检查第二轮输入
        def __init__(self) -> None:
            self.calls: list[list[dict[str, object]]] = []

        # 首轮响应前模拟用户追加指令，第二轮正常结束
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
            self.calls.append([dict(message) for message in messages])
            if len(self.calls) == 1:
                steering_queue.put_nowait({"role": "user", "content": "follow up"})
                return LlmResponse(stop_reason="end_turn", text="first answer")
            return LlmResponse(stop_reason="end_turn", text="final answer")

    provider = _SteeringProvider()
    loop = AgentLoop(
        provider,  # type: ignore[arg-type]
        ToolRegistry(),
        EventBus(),
        steering_queue=steering_queue,
    )
    context = _ctx()

    await loop.run(context)

    assert len(provider.calls) == 2
    assert provider.calls[1][-1] == {"role": "user", "content": "follow up"}
    assert context.status == "success"
    assert context.result == "final answer"


# 功能：验证三个只读工具在并发上限不小于三时于 220ms 内完成
# 设计：每个工具独立等待 100ms，并同时断言探针峰值并发度，避免仅靠宽松耗时阈值产生假阳性
async def test_read_only_batch_runs_concurrently_under_bounded_limit() -> None:
    probe = _ConcurrencyProbe()
    tool = _TimedTool("timed_read", ToolPermission.READ_ONLY, probe)
    calls = [
        _tc("timed_read", {"label": label, "delay": 0.1}, uid=f"read-{label}")
        for label in ("a", "b", "c")
    ]

    _context, _events_seen, elapsed = await _run_tool_batch(
        calls, [tool], max_concurrency=3
    )

    assert elapsed < 0.22
    assert probe.max_active == 3


# 功能：验证并发上限会限制同批只读工具的实际活跃数
# 设计：三个等长调用配置为两个执行槽，断言探针峰值而非仅检查总耗时
async def test_read_only_batch_respects_intermediate_concurrency_limit() -> None:
    probe = _ConcurrencyProbe()
    tool = _TimedTool("timed_read", ToolPermission.READ_ONLY, probe)
    calls = [
        _tc("timed_read", {"label": label, "delay": 0.03}, uid=f"limit-{label}")
        for label in ("a", "b", "c")
    ]

    await _run_tool_batch(calls, [tool], max_concurrency=2)

    assert probe.max_active == 2


# 功能：验证包含写工具的混合批次保持串行且执行顺序与请求顺序一致
# 设计：交替使用只读和写权限元数据并记录开始顺序，锁定整批降级规则而非只隔离单个写调用
async def test_mixed_read_write_batch_stays_serial_in_request_order() -> None:
    probe = _ConcurrencyProbe()
    read_tool = _TimedTool("timed_read", ToolPermission.READ_ONLY, probe)
    write_tool = _TimedTool("timed_write", ToolPermission.WORKSPACE_WRITE, probe)
    calls = [
        _tc("timed_read", {"label": "read-a", "delay": 0.02}, uid="mixed-1"),
        _tc("timed_write", {"label": "write", "delay": 0.02}, uid="mixed-2"),
        _tc("timed_read", {"label": "read-b", "delay": 0.02}, uid="mixed-3"),
    ]

    await _run_tool_batch(calls, [read_tool, write_tool], max_concurrency=3)

    assert probe.max_active == 1
    assert probe.started == ["read-a", "write", "read-b"]


# 功能：验证只读批次中间调用失败时其他调用仍完成且结果按请求顺序写回上下文
# 设计：让第二项最快失败、第三项次快、第一项最慢，故意打乱完成顺序后检查三项完整性及 tool_use_id 顺序
async def test_read_only_failure_is_isolated_and_context_order_is_stable() -> None:
    probe = _ConcurrencyProbe()
    tool = _TimedTool("timed_read", ToolPermission.READ_ONLY, probe)
    calls = [
        _tc("timed_read", {"label": "first", "delay": 0.06}, uid="ordered-1"),
        _tc(
            "timed_read",
            {"label": "second", "delay": 0.01, "fail": True},
            uid="ordered-2",
        ),
        _tc("timed_read", {"label": "third", "delay": 0.03}, uid="ordered-3"),
    ]

    context, events, _elapsed = await _run_tool_batch(
        calls, [tool], max_concurrency=3
    )

    assert probe.max_active == 3
    assert set(probe.finished) == {"first", "second", "third"}
    assert probe.finished != ["first", "second", "third"]
    result_blocks = context.messages[2]["content"]
    assert [block["tool_use_id"] for block in result_blocks] == [
        "ordered-1",
        "ordered-2",
        "ordered-3",
    ]
    assert [block["content"] for block in result_blocks] == [
        "done:first",
        "failed:second",
        "done:third",
    ]
    terminal_ids = [
        event.tool_use_id  # type: ignore[attr-defined]
        for event in events
        if event.type in {"tool.call_finished", "tool.call_failed"}  # type: ignore[attr-defined]
    ]
    assert set(terminal_ids) == {"ordered-1", "ordered-2", "ordered-3"}


# 功能：验证只读工具抛出未捕获异常时不会取消同批其他调用
# 设计：中间工具直接抛异常，前后工具仍应完成，并按请求顺序生成完整 tool_result
async def test_read_only_raised_exception_is_isolated() -> None:
    probe = _ConcurrencyProbe()
    read_tool = _TimedTool("timed_read", ToolPermission.READ_ONLY, probe)
    raising_tool = _RaisingReadTool("raising_read", ToolPermission.READ_ONLY, probe)
    calls = [
        _tc("timed_read", {"label": "first", "delay": 0.02}, uid="raise-1"),
        _tc("raising_read", {"label": "middle", "delay": 0.01}, uid="raise-2"),
        _tc("timed_read", {"label": "last", "delay": 0.02}, uid="raise-3"),
    ]

    context, events, _elapsed = await _run_tool_batch(
        calls, [read_tool, raising_tool], max_concurrency=3
    )

    result_blocks = context.messages[2]["content"]
    assert [block["tool_use_id"] for block in result_blocks] == [
        "raise-1", "raise-2", "raise-3"
    ]
    assert result_blocks[0].get("is_error") is None
    assert result_blocks[1].get("is_error") is True
    assert result_blocks[2].get("is_error") is None
    failed_ids = {
        event.tool_use_id
        for event in events
        if event.type == "tool.call_failed"  # type: ignore[attr-defined]
    }
    assert "raise-2" in failed_ids


# 功能：验证最大并发数为一时全只读批次保持现有串行行为
# 设计：三个声明只读的工具仍只允许一个活跃调用，并核对开始顺序以覆盖兼容性边界
async def test_read_only_batch_with_limit_one_is_serial() -> None:
    probe = _ConcurrencyProbe()
    tool = _TimedTool("timed_read", ToolPermission.READ_ONLY, probe)
    calls = [
        _tc("timed_read", {"label": label, "delay": 0.01}, uid=f"serial-{label}")
        for label in ("a", "b", "c")
    ]

    await _run_tool_batch(calls, [tool], max_concurrency=1)

    assert probe.max_active == 1
    assert probe.started == ["a", "b", "c"]


# 功能：验证未知工具和未知权限能力都不会让批次被错误并发
# 设计：分别混入未注册工具及返回未知权限值的第三方工具，用只读邻居的峰值并发度证明保守降级
@pytest.mark.parametrize("unknown_kind", ["tool", "permission", "string_permission"])
async def test_unknown_tool_or_permission_keeps_batch_serial(unknown_kind: str) -> None:
    probe = _ConcurrencyProbe()
    read_tool = _TimedTool("timed_read", ToolPermission.READ_ONLY, probe)
    unknown_tool = _UnknownPermissionTool(
        "unknown_permission", ToolPermission.READ_ONLY, probe
    )
    string_permission_tool = _StringReadOnlyPermissionTool(
        "string_read_only_permission", ToolPermission.READ_ONLY, probe
    )
    middle_name = {
        "tool": "missing",
        "permission": "unknown_permission",
        "string_permission": "string_read_only_permission",
    }[unknown_kind]
    calls = [
        _tc("timed_read", {"label": "first", "delay": 0.01}, uid="unknown-1"),
        _tc(middle_name, {"label": "middle", "delay": 0.01}, uid="unknown-2"),
        _tc("timed_read", {"label": "last", "delay": 0.01}, uid="unknown-3"),
    ]

    await _run_tool_batch(
        calls,
        [read_tool, unknown_tool, string_permission_tool],
        max_concurrency=3,
    )

    assert probe.max_active == 1
    assert probe.started == [
        "first",
        *([] if unknown_kind == "tool" else ["middle"]),
        "last",
    ]


# 功能：验证裸字符串 allow 不会被视为明确的权限允许，从而错误开启并发
# 设计：模拟不符合 PermissionDecision 合约的权限管理器，断言只读邻居仍被保守串行调度
async def test_non_enum_permission_allow_keeps_batch_serial() -> None:
    probe = _ConcurrencyProbe()
    tool = _TimedTool("timed_read", ToolPermission.READ_ONLY, probe)
    calls = [
        _tc("timed_read", {"label": label, "delay": 0.01}, uid=f"allow-{label}")
        for label in ("first", "second", "last")
    ]

    await _run_tool_batch(
        calls,
        [tool],
        max_concurrency=3,
        permission_manager=_StringAllowPermissionManager(
            {"timed_read": ToolPolicy(default=PermissionDecision.ALLOW)}
        ),
    )

    assert probe.max_active == 1
    assert probe.started == ["first", "second", "last"]


# 功能：验证可能进入审批的只读批次按原顺序串行执行
# 设计：为只读工具配置 ASK 策略并在请求事件中逐一批准，断言不会同时出现多个待审批调用
async def test_read_only_batch_requiring_approval_stays_serial() -> None:
    probe = _ConcurrencyProbe()
    tool = _TimedTool("approval_read", ToolPermission.READ_ONLY, probe)
    manager = PermissionManager(
        {"approval_read": ToolPolicy(default=PermissionDecision.ASK)},
        timeout_s=1,
    )
    pending = 0
    max_pending = 0
    bus = EventBus()

    # 收到权限请求后在下一事件循环拍批准，测量同时待批的调用数
    async def approve(event: BaseModel) -> None:
        nonlocal pending, max_pending
        if event.type != "permission.requested":  # type: ignore[attr-defined]
            return
        pending += 1
        max_pending = max(max_pending, pending)
        await asyncio.sleep(0)
        manager.respond(event.tool_use_id, "allow_once")  # type: ignore[attr-defined]
        pending -= 1

    bus.subscribe(approve)
    provider = _MockProvider(
        [
            LlmResponse(
                stop_reason="tool_use",
                tool_calls=[
                    _tc(
                        "approval_read",
                        {"label": label, "delay": 0.01},
                        uid=f"approval-{label}",
                    )
                    for label in ("a", "b")
                ],
            ),
            LlmResponse(stop_reason="end_turn", text="done"),
        ]
    )
    registry = ToolRegistry()
    registry.register(tool)
    loop = AgentLoop(
        provider,
        registry,
        bus,
        permission_manager=manager,
        tool_max_concurrency=2,
    )

    await loop.run(_ctx())

    assert max_pending == 1
    assert probe.max_active == 1


# 功能：验证工具事件携带批次标识、排队与起止时间及调度模式并保持正确 tool_use_id
# 设计：收集统一 EventBus 事件并按 tool_use_id 配对，直接覆盖 Trace 订阅者会持久化的最小事件元数据
async def test_tool_events_include_batch_scheduling_trace_metadata() -> None:
    probe = _ConcurrencyProbe()
    tool = _TimedTool("timed_read", ToolPermission.READ_ONLY, probe)
    calls = [
        _tc("timed_read", {"label": label, "delay": 0.01}, uid=f"trace-{label}")
        for label in ("a", "b")
    ]

    _context, events, _elapsed = await _run_tool_batch(
        calls, [tool], max_concurrency=2
    )

    started = {
        event.tool_use_id: event  # type: ignore[attr-defined]
        for event in events
        if event.type == "tool.call_started"  # type: ignore[attr-defined]
    }
    terminal = {
        event.tool_use_id: event  # type: ignore[attr-defined]
        for event in events
        if event.type in {"tool.call_finished", "tool.call_failed"}  # type: ignore[attr-defined]
    }
    assert set(started) == {"trace-a", "trace-b"}
    assert set(terminal) == set(started)
    assert len({event.batch_id for event in started.values()}) == 1  # type: ignore[attr-defined]
    for tool_use_id, start_event in started.items():
        finish_event = terminal[tool_use_id]
        assert start_event.scheduler_mode == "concurrent"  # type: ignore[attr-defined]
        assert start_event.queued_at <= start_event.started_at  # type: ignore[attr-defined]
        assert start_event.queue_ms >= 0  # type: ignore[attr-defined]
        assert finish_event.batch_id == start_event.batch_id  # type: ignore[attr-defined]
        assert finish_event.scheduler_mode == "concurrent"  # type: ignore[attr-defined]
        assert finish_event.started_at == start_event.started_at  # type: ignore[attr-defined]
        assert finish_event.finished_at >= finish_event.started_at  # type: ignore[attr-defined]


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
    assert ctx.status == "interrupted"
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


# 功能：验证高水位 tool_use 会触发自动压缩，并将 context 标记为已压缩
# 设计：真实 Compactor + mock provider 返回工具调用和摘要，检查消息被摘要替换且事件发布
async def test_loop_auto_compacts_on_high_water_tool_use(tmp_path: Path) -> None:
    registry = ToolRegistry()
    registry.register(_EchoTool())
    bus = EventBus()
    events = await _events(bus)
    provider = _CompactingProvider(_SUMMARY)
    compactor = Compactor(bus, tmp_path, "sess-1")
    loop = AgentLoop(
        provider,
        registry,
        bus,
        compactor=compactor,
        compact_threshold=0.8,
    )
    ctx = _ctx(max_steps=5)

    await loop.run(ctx)
    # Phase 3a: 异步压缩在后台执行，等待完成
    await asyncio.sleep(0.1)

    assert ctx.compacted is True
    assert ctx.messages[0]["role"] == "user"
    assert "Original Goal" in ctx.messages[0]["content"]
    assert "context.compacting" in [e.type for e in events]  # type: ignore[attr-defined]
    assert "context.compacted" in [e.type for e in events]  # type: ignore[attr-defined]


# 功能：验证非 tool_use 的继续状态（max_tokens）也会触发压缩
async def test_loop_auto_compacts_on_max_tokens(tmp_path: Path) -> None:
    bus = EventBus()
    provider = _CompactingProvider(
        _SUMMARY,
        first_stop_reason="max_tokens",
        with_tool_call=False,
    )
    compactor = Compactor(bus, tmp_path, "sess-1")
    loop = AgentLoop(
        provider,
        ToolRegistry(),
        bus,
        compactor=compactor,
        compact_threshold=0.8,
    )
    ctx = _ctx(max_steps=5)

    await loop.run(ctx)
    # Phase 3a: 等待异步压缩完成
    await asyncio.sleep(0.1)

    assert ctx.compacted is True
    assert ctx.status == "success"


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
    assert ctx.status == "interrupted"
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


# ============================================================
# Claude Code 风格多条件终止测试
# ============================================================


class _RuntimeErrorTool(BaseTool):
    name = "flaky_tool"
    description = "Always raises runtime error"
    input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        return ToolResult(content="something went wrong", is_error=True, error_type="runtime_error")


# 功能：验证同一工具运行时错误 ≥3 次触发 repeated_error 熔断
async def test_repeated_error_termination() -> None:
    tc = _tc("flaky_tool", {}, uid="fe1")
    provider = _MockProvider([
        LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
        LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
        LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
        LlmResponse(stop_reason="end_turn", text="should not reach"),
    ])
    registry = ToolRegistry()
    registry.register(_RuntimeErrorTool())
    loop = AgentLoop(provider, registry, EventBus())
    ctx = _ctx(max_steps=10)
    await loop.run(ctx)
    assert ctx.status == "failed"
    assert ctx.reason == "repeated_error"
    assert ctx.step == 3


# 功能：验证权限拒绝不计入错误累积
async def test_permission_denied_not_accumulated() -> None:
    tc = _tc("deny_tool", {"x": "1"}, uid="pd1")
    provider = _MockProvider([
        LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
        LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
        LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
        LlmResponse(stop_reason="end_turn", text="done"),
    ])
    registry = ToolRegistry()
    registry.register(_PermissionDenyTool())
    loop = AgentLoop(provider, registry, EventBus())
    ctx = _ctx(max_steps=10)
    await loop.run(ctx)
    assert ctx.reason != "repeated_error"


# 功能：验证成功调用重置错误累积
async def test_success_resets_error_accumulator() -> None:
    tc_fail = _tc("flaky_tool", {}, uid="fe2")
    provider = _MockProvider([
        LlmResponse(stop_reason="tool_use", tool_calls=[tc_fail]),
        LlmResponse(stop_reason="tool_use", tool_calls=[tc_fail]),
        LlmResponse(stop_reason="tool_use", tool_calls=[_tc("echo", {"msg": "ok"}, uid="e1")]),
        LlmResponse(stop_reason="tool_use", tool_calls=[tc_fail]),
        LlmResponse(stop_reason="tool_use", tool_calls=[tc_fail]),
        LlmResponse(stop_reason="end_turn", text="done"),
    ])
    registry = ToolRegistry()
    registry.register(_RuntimeErrorTool())
    registry.register(_EchoTool())
    loop = AgentLoop(provider, registry, EventBus())
    ctx = _ctx(max_steps=10)
    await loop.run(ctx)
    assert ctx.status == "success"


# 功能：验证 end_turn 优先级高于 max_turns
async def test_end_turn_wins_over_max_turns() -> None:
    provider = _MockProvider([
        LlmResponse(stop_reason="tool_use", tool_calls=[_tc("echo", {"msg": "1"}, uid="ew1")]),
        LlmResponse(stop_reason="tool_use", tool_calls=[_tc("echo", {"msg": "2"}, uid="ew2")]),
        LlmResponse(stop_reason="end_turn", text="all done"),
    ])
    registry = ToolRegistry()
    registry.register(_EchoTool())
    loop = AgentLoop(provider, registry, EventBus())
    ctx = _ctx(max_steps=3)
    await loop.run(ctx)
    assert ctx.status == "success"
    assert ctx.step == 3


# 功能：验证 context_pct > 98% 触发 blocking_limit
async def test_blocking_limit_termination() -> None:
    provider = _MockProvider([
        LlmResponse(
            stop_reason="tool_use",
            tool_calls=[_tc("echo", {"msg": "hi"}, uid="bl1")],
            usage=UsageStats(input_tokens=100_000, output_tokens=10, context_pct=0.99),
        ),
    ])
    registry = ToolRegistry()
    registry.register(_EchoTool())
    loop = AgentLoop(provider, registry, EventBus())
    ctx = _ctx(max_steps=10)
    await loop.run(ctx)
    assert ctx.status == "interrupted"
    assert ctx.reason == "blocking_limit"


# ============================================================
# Phase 3 — P0 兜底线新增测试
# ============================================================


# 功能：验证累计 Token 不再作为主循环终止条件
# 设计：即使累计 usage 远超旧预算，也继续执行到模型 end_turn
async def test_cumulative_token_budget_does_not_stop_loop() -> None:
    tc = _tc()
    provider = _MockProvider([
        LlmResponse(
            stop_reason="tool_use", tool_calls=[tc],
            usage=UsageStats(input_tokens=100_000, output_tokens=100, context_pct=0.5),
        ),
        LlmResponse(
            stop_reason="end_turn", text="done",
            usage=UsageStats(input_tokens=100_000, output_tokens=100, context_pct=0.5),
        ),
    ])
    registry = ToolRegistry()
    registry.register(_EchoTool())
    loop, _ = _make_loop(provider, registry)
    ctx = _ctx(max_steps=10)
    ctx.max_tokens = 1  # 旧配置值不应再截断主 Agent Run
    await loop.run(ctx)
    assert ctx.status == "success"
    assert ctx.result == "done"


# 功能：验证未知模型价格不会回退旧 3/15 美元默认估价
# 设计：设置足以触发旧估价的 usage 和预算，但不传 catalog，fail-open 下应正常成功
async def test_unknown_pricing_does_not_use_legacy_budget_estimate() -> None:
    provider = _MockProvider([
        LlmResponse(
            stop_reason="end_turn",
            text="ok",
            usage=UsageStats(input_tokens=1_000_000, output_tokens=1_000_000),
        )
    ])
    loop = AgentLoop(
        provider,
        ToolRegistry(),
        EventBus(),
        pricing_provider="unknown",
        pricing_model="unknown",
    )
    ctx = _ctx()
    ctx.max_budget_usd = 1.0

    await loop.run(ctx)

    assert ctx.status == "success"
    assert ctx.reason == "success"


# 功能：验证 loop 使用 pricing catalog 执行 max_budget_usd 判断
# 设计：注入测试价格表让单次 usage 成本超过预算，断言 run 以成本上限中断
async def test_pricing_catalog_budget_stops_loop() -> None:
    provider = _MockProvider([
        LlmResponse(
            stop_reason="tool_use",
            tool_calls=[],
            usage=UsageStats(input_tokens=1_000_000, output_tokens=0),
        )
    ])
    catalog = PricingCatalog([
        ModelPricing(
            provider="test",
            model="priced",
            input_per_million=Decimal("2.00"),
            output_per_million=Decimal("1.00"),
        )
    ])
    loop = AgentLoop(
        provider,
        ToolRegistry(),
        EventBus(),
        pricing_provider="test",
        pricing_model="priced",
        pricing_catalog=catalog,
    )
    ctx = _ctx(max_steps=10)
    ctx.max_budget_usd = 1.0

    await loop.run(ctx)

    assert ctx.status == "interrupted"
    assert ctx.reason == "max_budget_usd"


# 功能：验证墙钟超时在 loop 内正确终止
# 设计：设 max_wall_clock_s=0（已超时），预检应触发中断
async def test_wall_clock_exceeded_stops_loop() -> None:
    provider = _MockProvider([LlmResponse(stop_reason="end_turn", text="ok")])
    loop, _ = _make_loop(provider)
    ctx = _ctx(max_steps=10)
    ctx.max_wall_clock_s = 1
    ctx.started_at = 0.0  # 确保 elapsed_s > 0
    # 模拟已运行超时：elapsed_s 会 >= max_wall_clock_s
    ctx.started_at = time.monotonic() - 10.0  # 10 秒前开始
    await loop.run(ctx)
    # 无 result 时 wall_clock 超时标记为 failed（区别于有结果的中断）
    assert ctx.status == "failed"
    assert ctx.reason == "max_wall_clock_exceeded"


# 功能：验证墙钟超时但有 result 时标记为 interrupted（保留已有结果）
# 设计：先正常完成一个 end_turn 拿到 result，再在下一轮超时
async def test_wall_clock_exceeded_preserves_result() -> None:
    provider = _MockProvider([
        LlmResponse(stop_reason="end_turn", text="final answer"),
    ])
    loop, _ = _make_loop(provider)
    ctx = _ctx(max_steps=10)
    await loop.run(ctx)  # 先正常完成一次 run
    assert ctx.status == "success"
    assert ctx.result == "final answer"
    # 再次 run（模拟 resume），墙钟已超时
    ctx.status = "running"
    ctx.started_at = time.monotonic() - 10.0
    ctx.max_wall_clock_s = 1
    await loop.run(ctx)
    assert ctx.status == "interrupted"  # 有 result，保留
    assert ctx.result == "final answer"


# 功能：验证累计 input tokens 不再单独触发压缩
# 设计：低 context_pct 下即使 input_tokens 很高，也只执行原始任务流程
async def test_auto_compact_by_token_count(tmp_path: Path) -> None:
    compactor = Compactor(EventBus(), tmp_path, "sess-c")
    provider = _MockProvider([
        LlmResponse(
            stop_reason="tool_use",
            tool_calls=[_tc()],
            usage=UsageStats(input_tokens=60_000, output_tokens=10, context_pct=0.3),
        ),
        LlmResponse(stop_reason="end_turn", text="done"),
    ])
    registry = ToolRegistry()
    registry.register(_EchoTool())
    loop = AgentLoop(
        provider, registry, EventBus(),
        compactor=compactor,
        auto_compact_min_tokens=50_000,  # 第一步就超过此阈值
    )
    ctx = _ctx(max_steps=10)
    await loop.run(ctx)
    assert ctx.status == "success"


# 功能：验证步数和 turn 数不再单独触发压缩
# 设计：低 context_pct 下连续多步执行不调用 compactor
async def test_auto_compact_by_step_count(tmp_path: Path) -> None:
    compactor = Compactor(EventBus(), tmp_path, "sess-d")
    provider = _MockProvider([
        LlmResponse(
            stop_reason="tool_use",
            tool_calls=[_tc()],
            # 低 context_pct 不会触发百分比阈值
            usage=UsageStats(input_tokens=1_000, output_tokens=10, context_pct=0.01),
        ),
        LlmResponse(
            stop_reason="tool_use",
            tool_calls=[_tc()],
            usage=UsageStats(input_tokens=1_000, output_tokens=10, context_pct=0.01),
        ),
        LlmResponse(
            stop_reason="tool_use",
            tool_calls=[_tc()],
            usage=UsageStats(input_tokens=1_000, output_tokens=10, context_pct=0.01),
        ),
        LlmResponse(stop_reason="end_turn", text="done"),
    ])
    registry = ToolRegistry()
    registry.register(_EchoTool())
    loop = AgentLoop(
        provider, registry, EventBus(),
        compactor=compactor,
        compact_threshold=0.70,
        auto_compact_min_tokens=1,
        auto_compact_min_steps=1,
    )
    ctx = _ctx(max_steps=10)
    await loop.run(ctx)
    assert ctx.status == "success"


# 功能：验证 wrap_up_on_max_steps 在步数耗尽时触发额外 LLM 调用生成总结
# 设计：max_steps=2，最后一步为 tool_use，wrap_up 会额外调用 LLM
async def test_wrap_up_fires_on_max_steps() -> None:
    """wrap_up 在 max_steps 到达且未自然 end_turn 时生成总结"""
    provider = _MockProvider([
        LlmResponse(
            stop_reason="tool_use",
            tool_calls=[_tc()],
            usage=UsageStats(input_tokens=100, output_tokens=10, context_pct=0.01),
        ),
        LlmResponse(
            stop_reason="tool_use",
            tool_calls=[_tc()],
            usage=UsageStats(input_tokens=100, output_tokens=10, context_pct=0.01),
        ),
        # wrap_up 调用（额外 LLM 调用，无工具）
        LlmResponse(stop_reason="end_turn", text="Task was working on X, file Y modified."),
    ])
    registry = ToolRegistry()
    registry.register(_EchoTool())
    loop = AgentLoop(provider, registry, EventBus(),
                     grace_step_on_max_steps=False)  # 仅测 wrap_up
    ctx = _ctx(max_steps=2)
    await loop.run(ctx)
    assert ctx.status == "interrupted"
    assert ctx.reason == "exceeded_max_steps"
    assert "Task was working on X" in ctx.result


# 功能：验证 grace_step 在最后一步工具成功时追加无工具回合，[COMPLETE] 标记 → success
# 设计：max_steps=2，最后一步为成功 tool_use，conclude 返回 [COMPLETE] 文本
async def test_grace_step_complete_marker_marks_success() -> None:
    provider = _MockProvider([
        LlmResponse(
            stop_reason="tool_use",
            tool_calls=[_tc()],
            usage=UsageStats(input_tokens=100, output_tokens=10, context_pct=0.01),
        ),
        LlmResponse(
            stop_reason="tool_use",
            tool_calls=[_tc()],
            usage=UsageStats(input_tokens=100, output_tokens=10, context_pct=0.01),
        ),
        # grace_step/conclude 调用 → 返回 [COMPLETE] 标记
        LlmResponse(stop_reason="end_turn", text="[COMPLETE] All tasks done."),
    ])
    registry = ToolRegistry()
    registry.register(_EchoTool())
    loop = AgentLoop(provider, registry, EventBus(),
                     wrap_up_on_max_steps=False)  # 仅测 grace_step
    ctx = _ctx(max_steps=2)
    await loop.run(ctx)
    assert ctx.status == "success"


# 功能：验证 grace_step 中 [INCOMPLETE] 标记 → interrupted
# 设计：conclude 返回 [INCOMPLETE] 时保持 interrupted 状态
async def test_grace_step_incomplete_marker_marks_interrupted() -> None:
    provider = _MockProvider([
        LlmResponse(
            stop_reason="tool_use",
            tool_calls=[_tc()],
            usage=UsageStats(input_tokens=100, output_tokens=10, context_pct=0.01),
        ),
        LlmResponse(
            stop_reason="tool_use",
            tool_calls=[_tc()],
            usage=UsageStats(input_tokens=100, output_tokens=10, context_pct=0.01),
        ),
        # grace_step/conclude 调用 → 返回 [INCOMPLETE] 标记
        LlmResponse(stop_reason="end_turn", text="[INCOMPLETE] Still need to test."),
    ])
    registry = ToolRegistry()
    registry.register(_EchoTool())
    loop = AgentLoop(provider, registry, EventBus(),
                     wrap_up_on_max_steps=False)
    ctx = _ctx(max_steps=2)
    await loop.run(ctx)
    assert ctx.status == "interrupted"
    assert ctx.reason == "exceeded_max_steps"
    assert "Still need to test" in ctx.result


# 功能：验证 max_steps=0 在运行时仍然表示不限步数
# 设计：end_turn 正常终止，不受 step 计数限制
async def test_max_steps_zero_runtime_unlimited() -> None:
    """max_steps=0 时 loop 不因步数限制终止，end_turn 正常退出"""
    tc = _tc()
    provider = _MockProvider([
        LlmResponse(
            stop_reason="tool_use",
            tool_calls=[tc],
            usage=UsageStats(input_tokens=100, output_tokens=10, context_pct=0.01),
        ),
        LlmResponse(
            stop_reason="tool_use",
            tool_calls=[tc],
            usage=UsageStats(input_tokens=100, output_tokens=10, context_pct=0.01),
        ),
        LlmResponse(stop_reason="end_turn", text="done"),
    ])
    registry = ToolRegistry()
    registry.register(_EchoTool())
    loop, _ = _make_loop(provider, registry)
    ctx = _ctx(max_steps=0)  # 不限步数
    await loop.run(ctx)
    assert ctx.status == "success"
    assert ctx.step == 3  # 完整运行 3 步
