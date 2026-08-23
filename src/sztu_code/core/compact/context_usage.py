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


def estimate_context_usage(
    *,
    messages: list[dict[str, object]],
    tool_schemas: list[dict[str, object]],
    system: str,
    actual_input_tokens: int,
    context_window: int,
    reserved_output_tokens: int,
) -> ContextUsageBreakdown:
    """Estimate explainable context categories and reconcile them to provider usage."""
    raw = {
        "system": _count(_counter, system),
        "summary": 0,
        "conversation": 0,
        "tools": _count(_counter, tool_schemas),
    }
    for message in messages:
        if _is_summary_message(message):
            raw["summary"] += _count(_counter, message)
            continue
        content = message.get("content")
        if isinstance(content, list):
            tool_blocks = [
                block
                for block in content
                if isinstance(block, dict) and block.get("type") in {"tool_use", "tool_result"}
            ]
            raw["tools"] += _count(_counter, tool_blocks)
            raw["conversation"] += _count(
                _counter, [block for block in content if block not in tool_blocks]
            )
        else:
            raw["conversation"] += _count(_counter, content)
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
