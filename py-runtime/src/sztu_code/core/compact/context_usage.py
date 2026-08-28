from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sztu_code.core.compact.token_counter import TokenCounter

# 进程级共享计数器：编码器按名称缓存，避免每次 LLM 调用重复加载 tiktoken
_counter = TokenCounter()


@dataclass(frozen=True)
class ContextUsageBreakdown:
    context_window: int
    available_tokens: int
    reserved_output_tokens: int
    system_tokens: int
    summary_tokens: int
    conversation_tokens: int
    tool_tokens: int


def _count(counter: TokenCounter, value: Any) -> int:
    if value in (None, "", [], {}):
        return 0
    return counter.count_json(value)


def _is_summary_message(message: dict[str, object]) -> bool:
    content = message.get("content")
    if isinstance(content, str):
        return "This session is being continued" in content and "Summary:" in content
    if isinstance(content, list):
        return any(
            isinstance(block, dict)
            and "continue from this summary" in str(block.get("text", "")).lower()
            for block in content
        )
    return False


# 将单条消息的估算计数累加到 raw 上（summary 消息整体计为 summary；
# 其余消息拆分为 tool 块与对话文本两类）
def _accumulate_message(
    counter: TokenCounter,
    message: dict[str, object],
    raw: dict[str, int],
) -> None:
    if _is_summary_message(message):
        raw["summary"] += _count(counter, message)
        return
    content = message.get("content")
    if isinstance(content, list):
        tool_blocks = [
            block
            for block in content
            if isinstance(block, dict) and block.get("type") in {"tool_use", "tool_result"}
        ]
        raw["tools"] += _count(counter, tool_blocks)
        raw["conversation"] += _count(counter, [block for block in content if block not in tool_blocks])
    else:
        raw["conversation"] += _count(counter, content)


# 从零开始对全部内容做分类估算（不含缩放），返回 raw 计数字典
def _count_all(
    counter: TokenCounter,
    messages: list[dict[str, object]],
    system: str,
    tool_schemas: list[dict[str, object]],
) -> dict[str, int]:
    raw: dict[str, int] = {
        "system": _count(counter, system),
        "summary": 0,
        "conversation": 0,
        "tools": _count(counter, tool_schemas),
    }
    for message in messages:
        _accumulate_message(counter, message, raw)
    return raw


class IncrementalUsageEstimator:
    """跨 LLM 调用增量累积 token 分类估算，避免每步对全量上下文重新编码。

    消息列表在每个 step 尾部追加新消息；`truncate_tool_results` 只重建外层
    列表、保留未修改的消息对象身份，因此可以用对象身份（``is``）识别未变化
    前缀，仅对新增尾部做 tiktoken 计数。压缩会整体替换消息列表（全部为新对象），
    此时自动回退到全量重数，保证结果与全量路径一致。
    """

    def __init__(self) -> None:
        self._messages: list[dict[str, object]] = []
        self._system: str | None = None
        self._tools: list[dict[str, object]] | None = None
        self._raw: dict[str, int] = {
            "system": 0,
            "summary": 0,
            "conversation": 0,
            "tools": 0,
        }

    def raw_counts(
        self,
        *,
        messages: list[dict[str, object]],
        system: str,
        tool_schemas: list[dict[str, object]],
    ) -> dict[str, int]:
        counter = _counter
        if system != self._system:
            self._raw["system"] = _count(counter, system)
            self._system = system
        if self._tools is None or tool_schemas != self._tools:
            self._raw["tools"] = _count(counter, tool_schemas)
            # 浅拷贝即可：仅用于内容比较，不持有所有权
            self._tools = list(tool_schemas)

        prev = self._messages
        overlap = 0
        limit = min(len(prev), len(messages))
        while overlap < limit and messages[overlap] is prev[overlap]:
            overlap += 1
        if overlap == len(prev) and len(messages) >= len(prev):
            # 纯追加：仅对新增尾部计数（含空列表的首次调用）
            for message in messages[overlap:]:
                _accumulate_message(counter, message, self._raw)
        else:
            # 消息列表被替换/重排（压缩、截断命中）：全量重数
            self._raw["summary"] = 0
            self._raw["conversation"] = 0
            self._raw["tools"] = _count(counter, tool_schemas)
            for message in messages:
                _accumulate_message(counter, message, self._raw)
        self._messages = list(messages)
        return dict(self._raw)


def estimate_context_usage(
    *,
    messages: list[dict[str, object]],
    tool_schemas: list[dict[str, object]],
    system: str,
    actual_input_tokens: int,
    context_window: int,
    reserved_output_tokens: int,
    incremental: IncrementalUsageEstimator | None = None,
) -> ContextUsageBreakdown:
    """Estimate explainable context categories and reconcile them to provider usage."""
    if incremental is not None:
        raw = incremental.raw_counts(
            messages=messages, system=system, tool_schemas=tool_schemas
        )
    else:
        raw = _count_all(_counter, messages, system, tool_schemas)
    estimated_total = sum(raw.values())
    scale = (
        actual_input_tokens / estimated_total
        if actual_input_tokens > 0 and estimated_total > 0
        else 1.0
    )
    # system/summary/tools 按比例取整；conversation 用残差回填，保证分类总和恒等于实际值
    values: dict[str, int] = {
        key: max(0, round(value * scale)) for key, value in raw.items()
    }
    other = values["system"] + values["summary"] + values["tools"]
    if other >= actual_input_tokens:
        # 其他三类占比过高：conversation 回填为 0，从最大的类中扣减溢出以保持恒等式
        overflow = other - actual_input_tokens
        for key in sorted(("tools", "summary", "system"), key=lambda k: values[k], reverse=True):
            take = min(values[key], overflow)
            values[key] -= take
            overflow -= take
            if overflow == 0:
                break
        values["conversation"] = 0
    else:
        values["conversation"] = actual_input_tokens - other
    reserved = min(
        max(0, reserved_output_tokens), max(0, context_window - actual_input_tokens)
    )
    return ContextUsageBreakdown(
        context_window,
        max(0, context_window - actual_input_tokens - reserved),
        reserved,
        values["system"],
        values["summary"],
        values["conversation"],
        values["tools"],
    )
