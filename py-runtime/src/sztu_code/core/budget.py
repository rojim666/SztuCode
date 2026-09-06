"""请求级 Token 预算准入（Issue #72）。

预算语义（与配置、统计和文档保持一致）：

- ``context.max_tokens`` 是一次 run 的累计 Token 上限，按「全量 prompt + 输出」
  口径统计（``ExecutionContext.budget_spend_tokens()``）。全量 prompt = 净输入
  + 缓存读 + 缓存写，与上下文占用率（context_pct）同口径：缓存命中部分同样
  占用上下文窗口并按折扣计费，因此不从预算中减免。
- ``max_tokens=0`` 表示不限预算，准入检查直接放行，行为与历史版本一致。
- 每次模型请求前估算输入（system + messages + tool schemas），并至少为模型
  输出预留 ``MIN_OUTPUT_RESERVE_TOKENS``；余额不足以覆盖「估算输入 + 最小
  输出预留」时不再发起普通请求（block），余额可覆盖输入但不足默认输出上限时
  收缩本次请求的输出上限（shrink）。
- 输入估算复用 ``TokenCounter``：tiktoken 可用时为精确计数；不可用时回退到
  CJK 感知的字符估算（中文约 1 token/字符，其他约 4 字符/token）。注意该
  回退并非严格高估：对日文假名、韩文、emoji 和符号密集内容可能低估数倍，
  消耗上限口径因此是「预算 + 单次被放行请求的估算误差」，接入方应据此选择
  预算余量。
- 预算按 run 隔离：``max_tokens`` 是单次 run 的累计上限，父 run 与其派生的
  子 Agent / workflow 任务各自独立计数，不共享预算池。
- 连续多次响应缺失或全零 usage 时无法记账，准入 fail-closed 终止 run
  （见 AgentLoop 的 usage_unavailable 阻断），避免预算被静默绕过。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from sztu_code.core.compact.context_usage import IncrementalUsageEstimator

# 每次请求至少为模型输出预留的 token 数：低于该余数时无法得到有意义的回复，
# 继续请求只会产生截断输出并必然超支
MIN_OUTPUT_RESERVE_TOKENS = 256

# 默认单次请求输出上限，与 LlmConfig.max_output_tokens 的默认值保持一致
DEFAULT_MAX_OUTPUT_TOKENS = 8_192


# 输入估算器接口：不同 Provider 可注入不同的 tokenizer/估算器实现
class InputTokenEstimator(Protocol):
    # 返回一次请求的估算输入 token 数（system + messages + tool schemas）
    def estimate_input_tokens(
        self,
        *,
        messages: list[dict[str, Any]],
        system: str,
        tool_schemas: list[dict[str, Any]],
    ) -> int: ...


# 默认估算器：复用跨调用增量估算器，消息未变化的前缀不重复编码。
# 增量估算器在构造时惰性导入，避免 compact 包与本模块的循环依赖
class CounterInputEstimator:
    def __init__(
        self, incremental: IncrementalUsageEstimator | None = None
    ) -> None:
        if incremental is None:
            from sztu_code.core.compact.context_usage import (
                IncrementalUsageEstimator as _Estimator,
            )
            incremental = _Estimator()
        self._incremental = incremental

    def estimate_input_tokens(
        self,
        *,
        messages: list[dict[str, Any]],
        system: str,
        tool_schemas: list[dict[str, Any]],
    ) -> int:
        raw = self._incremental.raw_counts(
            messages=messages, system=system, tool_schemas=tool_schemas
        )
        return sum(raw.values())


@dataclass(frozen=True)
class BudgetAdmission:
    # "allow"：按 Provider 默认输出上限放行；"shrink"：收缩本次输出上限放行；
    # "block"：余额不足以覆盖估算输入 + 最小输出预留，不发起请求
    action: str
    estimated_input_tokens: int
    remaining_tokens: int
    # 本次请求允许的最大输出 token；None 表示交给 Provider 使用其默认配置
    request_max_output_tokens: int | None
    reason: str = ""


# 纯函数准入判定：max_tokens=0（不限）时仍返回估算值供 Trace 记录，但一律放行
def evaluate_token_budget(
    *,
    budget_spend_tokens: int,
    max_tokens: int,
    messages: list[dict[str, Any]],
    system: str,
    tool_schemas: list[dict[str, Any]],
    estimator: InputTokenEstimator,
    default_max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    min_output_reserve: int = MIN_OUTPUT_RESERVE_TOKENS,
) -> BudgetAdmission:
    estimated_input = estimator.estimate_input_tokens(
        messages=messages, system=system, tool_schemas=tool_schemas
    )
    if max_tokens <= 0:
        return BudgetAdmission(
            action="allow",
            estimated_input_tokens=estimated_input,
            remaining_tokens=0,
            request_max_output_tokens=None,
            reason="unlimited",
        )
    remaining = max_tokens - budget_spend_tokens
    output_room = remaining - estimated_input
    if output_room < min_output_reserve:
        return BudgetAdmission(
            action="block",
            estimated_input_tokens=estimated_input,
            remaining_tokens=remaining,
            request_max_output_tokens=None,
            reason="insufficient_remaining",
        )
    if output_room < default_max_output_tokens:
        return BudgetAdmission(
            action="shrink",
            estimated_input_tokens=estimated_input,
            remaining_tokens=remaining,
            request_max_output_tokens=output_room,
            reason="shrunk_to_remaining",
        )
    return BudgetAdmission(
        action="allow",
        estimated_input_tokens=estimated_input,
        remaining_tokens=remaining,
        request_max_output_tokens=None,
        reason="within_budget",
    )
