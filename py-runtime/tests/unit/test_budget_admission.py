from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from sztu_code.core.budget import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    MIN_OUTPUT_RESERVE_TOKENS,
    BudgetAdmission,
    CounterInputEstimator,
    evaluate_token_budget,
)
from sztu_code.core.compact.compactor import Compactor
from sztu_code.core.compact.context_usage import IncrementalUsageEstimator
from sztu_code.core.context import ExecutionContext, TerminationReason
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import LlmResponse

# --- stubs -------------------------------------------------------------------


class _FixedEstimator:
    """返回固定估算值的输入估算器，用于确定性准入断言。"""

    def __init__(self, estimate: int) -> None:
        self._estimate = estimate

    def estimate_input_tokens(
        self,
        *,
        messages: list[dict[str, Any]],
        system: str,
        tool_schemas: list[dict[str, Any]],
    ) -> int:
        return self._estimate


class _NoUsageProvider:
    """返回固定响应但 usage=None 的 provider，模拟缺失 usage 的上游。"""

    def __init__(self, responses: list[LlmResponse]) -> None:
        self._responses = iter(responses)
        self.calls = 0

    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
        usage_estimator: object | None = None,
        max_output_tokens: int | None = None,
    ) -> LlmResponse:
        self.calls += 1
        return next(self._responses)


_VALID_SUMMARY = """\
## 1. Original Goal
goal
## 2. Completed Steps
- none
## 3. Key Constraints & Discoveries
- none
## 4. Current File State
- none
## 5. Remaining TODOs
- finish
## 6. Critical Data
- none
"""


class _CountingCompactionProvider:
    """记录压缩请求调用次数的 provider，供压缩准入断言使用。"""

    def __init__(self, summary_text: str) -> None:
        self._summary_text = summary_text
        self.calls = 0

    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
        usage_estimator: object | None = None,
        max_output_tokens: int | None = None,
    ) -> LlmResponse:
        self.calls += 1
        return LlmResponse(stop_reason="end_turn", text=self._summary_text)


# --- 估算器 --------------------------------------------------------------------


# 功能：验证默认估算器随内容增长且对空输入返回正值下界
# 设计：空输入与追加长消息后分别估算，断言单调增长
def test_counter_estimator_grows_with_content() -> None:
    estimator = CounterInputEstimator(IncrementalUsageEstimator())
    empty = estimator.estimate_input_tokens(
        messages=[], system="", tool_schemas=[]
    )
    small = estimator.estimate_input_tokens(
        messages=[{"role": "user", "content": "hello world"}],
        system="sys",
        tool_schemas=[],
    )
    large = estimator.estimate_input_tokens(
        messages=[{"role": "user", "content": "hello world" * 500}],
        system="sys",
        tool_schemas=[],
    )
    assert empty >= 0
    assert small > empty
    assert large > small


# 功能：验证估算器复用同一实例时消息追加只计增量，结果与全量一致
# 设计：同一 estimator 两次估算，第二次仅追加一条消息
def test_counter_estimator_incremental_matches_fresh() -> None:
    incremental = CounterInputEstimator(IncrementalUsageEstimator())
    fresh = CounterInputEstimator(IncrementalUsageEstimator())
    msgs: list[dict[str, Any]] = [{"role": "user", "content": "base " * 100}]
    system = "system prompt"
    first = incremental.estimate_input_tokens(
        messages=msgs, system=system, tool_schemas=[]
    )
    assert first == fresh.estimate_input_tokens(
        messages=msgs, system=system, tool_schemas=[]
    )
    msgs.append({"role": "assistant", "content": [{"type": "text", "text": "more " * 50}]})
    second = incremental.estimate_input_tokens(
        messages=msgs, system=system, tool_schemas=[]
    )
    assert second == fresh.estimate_input_tokens(
        messages=msgs, system=system, tool_schemas=[]
    )
    assert second > first


# --- 准入判定 -------------------------------------------------------------------


# 功能：验证未配置预算（max_tokens=0）时一律放行且不收缩输出上限
# 设计：预算 0 + 高昂估算，断言 action=allow 且 cap=None
def test_admission_allows_when_budget_disabled() -> None:
    admission = _admit(
        spend=0, max_tokens=0, estimate=1_000_000,
    )
    assert admission.action == "allow"
    assert admission.request_max_output_tokens is None
    assert admission.reason == "unlimited"


# 功能：验证余额可容纳估算输入与默认输出上限时按默认放行
# 设计：预算充足，断言 action=allow 且不传 cap
def test_admission_allows_within_budget() -> None:
    admission = _admit(
        spend=100, max_tokens=100_000, estimate=2_000,
    )
    assert admission.action == "allow"
    assert admission.request_max_output_tokens is None
    assert admission.remaining_tokens == 100_000 - 100


# 功能：验证余额可容纳输入但不足默认输出上限时收缩本次请求上限
# 设计：预算=输入+600（低于默认 8192 高于最小预留），cap 应恰好等于剩余输出空间
def test_admission_shrinks_output_cap_to_remaining() -> None:
    estimate = 2_000
    max_tokens = 100 + estimate + 600
    admission = _admit(spend=100, max_tokens=max_tokens, estimate=estimate)
    assert admission.action == "shrink"
    assert admission.request_max_output_tokens == 600
    assert admission.remaining_tokens == max_tokens - 100


# 功能：验证余额连「估算输入 + 最小输出预留」都无法覆盖时阻断请求
# 设计：预算仅比估算输入多 10（低于 256 预留），断言 action=block
def test_admission_blocks_when_reserve_cannot_be_met() -> None:
    estimate = 2_000
    admission = _admit(spend=90, max_tokens=100 + estimate + 10, estimate=estimate)
    assert admission.action == "block"
    assert admission.request_max_output_tokens is None
    assert admission.reason == "insufficient_remaining"


# 功能：验证预算恰好等于估算输入 + 最小输出预留时放行并收缩到预留值
# 设计：边界值下 cap 恰为 MIN_OUTPUT_RESERVE_TOKENS
def test_admission_boundary_exact_reserve() -> None:
    estimate = 500
    max_tokens = 100 + estimate + MIN_OUTPUT_RESERVE_TOKENS
    admission = _admit(spend=100, max_tokens=max_tokens, estimate=estimate)
    assert admission.action == "shrink"
    assert admission.request_max_output_tokens == MIN_OUTPUT_RESERVE_TOKENS


# 功能：验证默认输出上限参数参与收缩判断
# 设计：更小的 default 下同样余额应按默认放行
def test_admission_respects_custom_default_output() -> None:
    estimate = 2_000
    max_tokens = 100 + estimate + 600
    admission = evaluate_token_budget(
        budget_spend_tokens=100,
        max_tokens=max_tokens,
        messages=[],
        system="",
        tool_schemas=[],
        estimator=_FixedEstimator(estimate),
        default_max_output_tokens=256,
    )
    assert admission.action == "allow"
    assert admission.request_max_output_tokens is None


def _admit(*, spend: int, max_tokens: int, estimate: int) -> BudgetAdmission:
    return evaluate_token_budget(
        budget_spend_tokens=spend,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": "goal"}],
        system="sys",
        tool_schemas=[],
        estimator=_FixedEstimator(estimate),
    )


# --- 预算口径（context）--------------------------------------------------------


# 功能：验证预算口径 = 全量 prompt + 输出，缓存部分计入且不减免
# 设计：分别设置 prompt/output/cache 字段，断言 budget_spend_tokens 与耗尽判定
def test_budget_spend_uses_full_prompt_semantics() -> None:
    ctx = ExecutionContext(run_id="r1", goal="g", max_steps=5)
    ctx.total_prompt_tokens = 700
    ctx.total_output_tokens = 200
    assert ctx.budget_spend_tokens() == 900
    ctx.max_tokens = 900
    assert ctx.token_budget_exhausted() is True
    ctx.max_tokens = 901
    assert ctx.token_budget_exhausted() is False
    ctx.max_tokens = 0
    assert ctx.token_budget_exhausted() is False


# 功能：验证 total_tokens 统计口径保持净输入 + 输出（不含缓存），与预算口径区分
# 设计：净输入与缓存分开设置，断言 total_tokens 不含缓存而 budget_spend 含缓存
def test_total_tokens_remains_net_semantics() -> None:
    ctx = ExecutionContext(run_id="r1", goal="g", max_steps=5)
    ctx.total_input_tokens = 100
    ctx.total_cache_read_input_tokens = 900
    ctx.total_output_tokens = 20
    ctx.total_prompt_tokens = 1_000
    assert ctx.total_tokens() == 120
    assert ctx.budget_spend_tokens() == 1_020


# 功能：验证缺失 usage 的 run 在无预算（0=不限）时不影响执行
# 设计：provider 返回 usage=None 的多轮响应，未配置预算，run 正常完成
@pytest.mark.asyncio
async def test_missing_usage_unlimited_budget_unaffected() -> None:
    from sztu_code.core.loop import AgentLoop
    from sztu_code.core.tools.base import BaseTool, ToolResult
    from sztu_code.core.tools.registry import ToolRegistry

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

    responses = [
        LlmResponse(stop_reason="tool_use", usage=None),
        LlmResponse(stop_reason="end_turn", text="done", usage=None),
    ]
    provider = _NoUsageProvider(responses)
    registry = ToolRegistry()
    registry.register(_EchoTool())
    loop = AgentLoop(provider, registry, EventBus())
    ctx = ExecutionContext(run_id="r1", goal="g", max_steps=10)
    await loop.run(ctx)
    assert ctx.status == "success"
    assert ctx.budget_spend_tokens() == 0
    assert provider.calls == 2


# 功能：验证配置预算后连续缺失/全零 usage 触发 fail-closed 熔断（Issue #72）
# 设计：3 次返回 usage=None 的 tool_use 响应后，记账失败计数达阈值，
#       第 4 次请求在准入处被阻断（reason=usage_unavailable），预算不被静默绕过
@pytest.mark.asyncio
async def test_missing_usage_fails_closed_after_streak() -> None:
    from sztu_code.core.bus.events import TokenBudgetAdmissionEvent
    from sztu_code.core.loop import AgentLoop
    from sztu_code.core.tools.base import BaseTool, ToolResult
    from sztu_code.core.tools.registry import ToolRegistry

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

    responses = [
        LlmResponse(stop_reason="tool_use", usage=None),
        LlmResponse(stop_reason="tool_use", usage=None),
        LlmResponse(stop_reason="tool_use", usage=None),
        LlmResponse(stop_reason="end_turn", text="never reached", usage=None),
    ]
    provider = _NoUsageProvider(responses)
    registry = ToolRegistry()
    registry.register(_EchoTool())
    bus = EventBus()
    collected: list[object] = []

    async def _collect(e: object) -> None:
        collected.append(e)

    bus.subscribe(_collect)
    loop = AgentLoop(provider, registry, bus)
    ctx = ExecutionContext(run_id="r1", goal="g", max_steps=10)
    ctx.max_tokens = 1_000_000  # 预算充足，阻断只能来自 usage 熔断
    await loop.run(ctx)
    assert provider.calls == 3
    assert ctx.status == "interrupted"
    assert ctx.reason == TerminationReason.TOKEN_BUDGET_EXHAUSTED
    admissions = [e for e in collected if isinstance(e, TokenBudgetAdmissionEvent)]
    assert admissions
    assert admissions[-1].reason == "usage_unavailable"
    assert admissions[-1].action == "block"


# --- 压缩准入 --------------------------------------------------------------------


# 功能：验证预算不足以覆盖压缩请求时跳过压缩且不调用 provider
# 设计：remaining 低于最小预留，compact_messages 返回失败且 provider 零调用；
#       无预算限制时正常执行压缩请求
@pytest.mark.asyncio
async def test_compaction_skipped_when_budget_insufficient() -> None:
    provider = _CountingCompactionProvider(_VALID_SUMMARY)
    compactor = Compactor(EventBus(), Path(tempfile.mkdtemp()), "sess-1")
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "goal " * 200},
        {"role": "assistant", "content": "reply"},
    ]

    blocked = await compactor.compact_messages(
        messages, provider, remaining_token_budget=MIN_OUTPUT_RESERVE_TOKENS - 1,
    )
    assert provider.calls == 0
    assert blocked is None or (
        isinstance(blocked, tuple) and blocked[0] is None and blocked[1] is None
    )

    allowed = await compactor.compact_messages(
        messages, provider, remaining_token_budget=0,
    )
    assert provider.calls == 1
    assert allowed is not None


# 功能：验证 TerminationReason 包含 Token 预算耗尽原因
# 设计：断言枚举值存在且字符串值稳定（供协议/事件消费）
def test_termination_reason_token_budget_exists() -> None:
    assert TerminationReason.TOKEN_BUDGET_EXHAUSTED == "token_budget_exhausted"
    assert DEFAULT_MAX_OUTPUT_TOKENS > 0
