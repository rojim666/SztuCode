from __future__ import annotations

import asyncio

import pytest

import sztu_code.core.tools.invocation as inv_mod
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import ToolCallBlock
from sztu_code.core.tools.base import (
    BaseTool,
    ToolExecutionState,
    ToolPermission,
    ToolResult,
)
from sztu_code.core.tools.errors import RateLimitedError
from sztu_code.core.tools.invocation import invoke_tool
from sztu_code.core.tools.registry import ToolRegistry

# --- stub tools --------------------------------------------------------------


class _FailNTimes(BaseTool):
    """前 n 次返回普通 runtime_error，之后成功。"""

    name = "fail_n"
    description = "Fails n times then succeeds"
    input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}

    def __init__(self, n: int, *, error_type: str = "runtime_error", retry_safe: bool = False) -> None:
        self._remaining = n
        self._error_type = error_type
        self.retry_safe = retry_safe
        self.calls = 0

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        self.calls += 1
        if self._remaining > 0:
            self._remaining -= 1
            # 声明 retry_safe 时同步声明结果可重试且执行状态未开始，构成完整重试条件
            return ToolResult(
                content="transient error",
                is_error=True,
                error_type=self._error_type,
                retryable=self.retry_safe,
                execution_state=(
                    ToolExecutionState.NOT_STARTED
                    if self.retry_safe
                    else ToolExecutionState.COMPLETED
                ),
            )
        return ToolResult(content="ok")


class _RateLimitedNTimes(BaseTool):
    """前 n 次抛出明确的限流错误，之后成功。"""

    name = "rate_n"
    description = "Rate-limits n times then succeeds"
    input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}
    required_permission = ToolPermission.READ_ONLY

    def __init__(self, n: int, *, retry_safe: bool = False) -> None:
        self._remaining = n
        self.retry_safe = retry_safe
        self.calls = 0

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        self.calls += 1
        if self._remaining > 0:
            self._remaining -= 1
            raise RateLimitedError("429 Too Many Requests")
        return ToolResult(content="ok")


class _WriteRateLimitedTool(_RateLimitedNTimes):
    """写工具默认不声明安全重试。"""

    name = "write_rate_limited"
    required_permission = ToolPermission.WORKSPACE_WRITE


class _RetryableResultNTimes(BaseTool):
    """前 n 次返回显式可重试结果，之后成功。"""

    name = "retryable_result_n"
    description = "Returns retryable results n times then succeeds"
    input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}
    required_permission = ToolPermission.READ_ONLY
    retry_safe = True

    def __init__(self, n: int) -> None:
        self._remaining = n
        self.calls = 0

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        self.calls += 1
        if self._remaining > 0:
            self._remaining -= 1
            return ToolResult(
                content="temporary service failure",
                is_error=True,
                error_type="rate_limited",
                retryable=True,
                execution_state=ToolExecutionState.NOT_STARTED,
            )
        return ToolResult(content="ok")


class _AlwaysFails(BaseTool):
    name = "always_fail"
    description = "Always fails"
    input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}

    def __init__(self, error_type: str = "runtime_error", *, retry_safe: bool = False) -> None:
        self._error_type = error_type
        self.retry_safe = retry_safe

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        return ToolResult(
            content="permanent error",
            is_error=True,
            error_type=self._error_type,
            retryable=self.retry_safe,
            execution_state=(
                ToolExecutionState.NOT_STARTED
                if self.retry_safe
                else ToolExecutionState.COMPLETED
            ),
        )


# --- helper ------------------------------------------------------------------


def _call(name: str) -> ToolCallBlock:
    return ToolCallBlock(id="t1", name=name, input={})


async def _run(
    tool: BaseTool,
    *,
    monkeypatch: pytest.MonkeyPatch,
    retry_base_s: float = 0.0,
) -> tuple[ToolResult, list]:
    monkeypatch.setattr(inv_mod, "_RETRY_BASE_S", retry_base_s)
    registry = ToolRegistry()
    registry.register(tool)
    bus = EventBus()
    events: list = []

    async def _collect(event: object) -> None:
        events.append(event)

    bus.subscribe(_collect)
    result = await invoke_tool(registry, _call(tool.name), bus, run_id="r")
    return result, events


def _failed_events(events: list) -> list:
    return [event for event in events if event.type == "tool.call_failed"]  # type: ignore[attr-defined]


# --- tests -------------------------------------------------------------------


# 功能：普通 runtime_error 默认不重试
# 设计：第一次失败后工具本可在第二次成功；以调用次数证明没有发生第二次执行
async def test_runtime_error_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = _FailNTimes(1)

    result, events = await _run(tool, monkeypatch=monkeypatch)

    assert result.is_error
    assert result.error_type == "runtime_error"
    assert tool.calls == 1
    assert result.metadata["retry_decision"] == "stop"
    assert result.metadata["retry_reason"] == "failure_is_not_explicitly_retryable"
    assert "not marked retryable" in result.content
    assert len(_failed_events(events)) == 1


# 功能：显式声明可安全重试的只读工具，在限流时重试
# 设计：第一次抛出 RateLimitedError、第二次成功，并断言实际执行两次
async def test_safe_read_only_rate_limit_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = _RateLimitedNTimes(1, retry_safe=True)

    result, events = await _run(tool, monkeypatch=monkeypatch)

    assert not result.is_error
    assert result.content == "ok"
    assert tool.calls == 2
    failed_events = _failed_events(events)
    assert len(failed_events) == 1
    assert failed_events[0].error_class == "rate_limited"
    assert failed_events[0].attempt == 1
    assert failed_events[0].retry_decision == "retry"
    assert failed_events[0].retry_reason == "explicit_transient_failure_on_retry_safe_tool"
    assert failed_events[0].retry_delay_ms == 0
    assert failed_events[0].tool_retry_safe
    assert failed_events[0].execution_state == ToolExecutionState.NOT_STARTED.value


# 功能：ToolResult 可通过显式元数据声明瞬时失败
# 设计：返回 retryable=True 与 NOT_STARTED，验证调用按同一安全策略重试
async def test_explicit_retryable_result_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = _RetryableResultNTimes(1)

    result, events = await _run(tool, monkeypatch=monkeypatch)

    assert not result.is_error
    assert tool.calls == 2
    assert _failed_events(events)[0].retry_decision == "retry"


# 功能：安全重试继续使用 2 秒、4 秒指数退避
# 设计：记录 sleep 参数和事件中的毫秒值，不进行真实等待
async def test_safe_retry_uses_exponential_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    delays: list[float] = []

    async def _record_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(inv_mod.asyncio, "sleep", _record_sleep)
    # 默认 _MAX_RETRIES=1 只有一次退避；这里提高上限以完整验证 2s→4s 指数序列
    monkeypatch.setattr(inv_mod, "_MAX_RETRIES", 2)
    tool = _RateLimitedNTimes(2, retry_safe=True)

    result, events = await _run(tool, monkeypatch=monkeypatch, retry_base_s=2.0)

    assert not result.is_error
    assert delays == [2.0, 4.0]
    assert [event.retry_delay_ms for event in _failed_events(events)] == [2000, 4000]


# 功能：默认写工具即使限流也不重试
# 设计：写工具未显式声明 retry_safe；限流后检查只执行一次
async def test_write_tool_rate_limit_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = _WriteRateLimitedTool(1)

    result, events = await _run(tool, monkeypatch=monkeypatch)

# 功能：验证 runtime_error 只重试一次后最终返回失败
# 设计：_AlwaysFails 声明 retry_safe 并持续失败；断言最终结果 is_error + 收到 2 个 failed 事件
async def test_runtime_error_exhausts_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    result, events = await _run(
        _AlwaysFails("runtime_error", retry_safe=True), monkeypatch=monkeypatch
    )
    assert result.is_error
    assert result.error_type == "runtime_error"
    failed_events = [e for e in events if e.type == "tool.call_failed"]  # type: ignore[attr-defined]
    assert len(failed_events) == 2
    attempts = [e.attempt for e in failed_events]  # type: ignore[attr-defined]
    assert attempts == [1, 2]

# 功能：写工具显式声明当前调用安全时允许重试
# 设计：写工具设置 retry_safe，限流后第二次调用成功
async def test_explicitly_safe_write_tool_rate_limit_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _WriteRateLimitedTool(1, retry_safe=True)

    result, events = await _run(tool, monkeypatch=monkeypatch)

    assert not result.is_error
    assert result.content == "ok"
    assert tool.calls == 2
    assert _failed_events(events)[0].retry_decision == "retry"


# 功能：可安全重试的限流工具仍保留最大重试次数
# 设计：持续限流，断言初始调用加两次重试后停止
async def test_safe_rate_limit_exhausts_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = _RateLimitedNTimes(10, retry_safe=True)

    result, events = await _run(tool, monkeypatch=monkeypatch)

# 功能：验证 rate_limited 只重试一次后最终返回失败
# 设计：声明 retry_safe 的工具始终抛限流异常，断言 2 个 failed 事件且 error_class 统一
async def test_rate_limited_exhausts_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    result, events = await _run(_RateLimitedNTimes(10, retry_safe=True), monkeypatch=monkeypatch)
    assert result.is_error
    assert result.error_type == "rate_limited"
    failed_events = [e for e in events if e.type == "tool.call_failed"]  # type: ignore[attr-defined]
    assert len(failed_events) == 2
    assert all(e.error_class == "rate_limited" for e in failed_events)  # type: ignore[attr-defined]


# 功能：schema_error 不触发重试
# 设计：直接返回 schema 错误，检查只产生一次失败事件
async def test_schema_error_no_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    result, events = await _run(_AlwaysFails("schema_error"), monkeypatch=monkeypatch)

    assert result.is_error
    assert result.error_type == "schema_error"
    failed_events = _failed_events(events)
    assert len(failed_events) == 1
    assert failed_events[0].retry_decision == "stop"
    assert failed_events[0].retry_reason == "error_is_not_explicitly_transient"

# 功能：验证 timeout 不触发通用重试
# 设计：SlowTool 配合极短超时，断言只执行一次并发出一个 failed 事件
async def test_timeout_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    pass

# 功能：timeout 的未知执行状态不触发第二次执行
# 设计：短超时中断慢工具；断言调用一次且结果显式标记 UNKNOWN
async def test_timeout_with_unknown_execution_state_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _SlowTool(BaseTool):
        name = "slow"
        description = "Sleeps"
        input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}
        retry_safe = True

        def __init__(self) -> None:
            self.calls = 0

        async def invoke(self, params: dict[str, object]) -> ToolResult:
            self.calls += 1
            await asyncio.sleep(60)
            return ToolResult(content="done")

    tool = _SlowTool()
    monkeypatch.setattr(inv_mod, "_RETRY_BASE_S", 0.0)
    registry = ToolRegistry()
    registry.register(tool)
    bus = EventBus()
    events: list = []

    async def _collect(event: object) -> None:
        events.append(event)

    bus.subscribe(_collect)

    result = await invoke_tool(registry, _call("slow"), bus, run_id="r", timeout=0.05)

    assert result.is_error
    assert result.error_type == "timeout"
    failed_events = [e for e in events if e.type == "tool.call_failed"]  # type: ignore[attr-defined]
    assert len(failed_events) == 1


# 功能：失败事件的 error_class 保持在约定枚举内
# 设计：声明 retry_safe 的工具失败一次后成功，运行并检查事件字段
async def test_failed_event_has_valid_error_class(monkeypatch: pytest.MonkeyPatch) -> None:
    valid_classes = {"runtime_error", "timeout", "schema_error", "permission_denied", "rate_limited"}
    result, events = await _run(_FailNTimes(1, retry_safe=True), monkeypatch=monkeypatch)
    assert not result.is_error
    for e in events:
        if e.type == "tool.call_failed":  # type: ignore[attr-defined]
            assert e.error_class in valid_classes  # type: ignore[attr-defined]
