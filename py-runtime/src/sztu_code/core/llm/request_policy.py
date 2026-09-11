"""Deterministic model request policy; task text never changes the cached prefix."""
from __future__ import annotations

import re

_EFFORTS = ("", "low", "medium", "high", "xhigh", "max")


def openai_output_policy(
    model: str, max_tokens: int, effort: str = "",
    temperature: float | None = None, top_p: float | None = None,
) -> dict[str, object]:
    if effort not in _EFFORTS:
        raise ValueError(f"Unsupported reasoning effort: {effort}")
    reasoning = bool(re.match(r"^(?:o[1-9](?:-|$)|gpt-[5-9](?:[.-]|$))", model, re.I))
    deepseek = model.lower().startswith("deepseek")
    suppress_sampling = reasoning or bool(effort) or model.lower().startswith("deepseek-reasoner")
    result: dict[str, object] = {
        "max_completion_tokens" if reasoning else "max_tokens": max_tokens,
    }
    if not suppress_sampling:
        if temperature is not None:
            result["temperature"] = temperature
        if top_p is not None:
            result["top_p"] = top_p
    if effort:
        result["reasoning_effort"] = (
            "high" if deepseek and effort in ("medium", "xhigh") else effort
        )
        if deepseek:
            result["thinking"] = {"type": "enabled"}
    return result


def anthropic_output_policy(max_tokens: int, effort: str = "") -> dict[str, object]:
    if effort not in _EFFORTS:
        raise ValueError(f"Unsupported reasoning effort: {effort}")
    result: dict[str, object] = {"max_tokens": max_tokens}
    if effort:
        if max_tokens < 2048:
            raise ValueError("Thinking requires max_output_tokens >= 2048 (including final output)")
        budgets = {"low": 2048, "medium": 8192, "high": 24576, "xhigh": 32768, "max": 65536}
        result["thinking"] = {
            "type": "enabled", "budget_tokens": min(budgets[effort], max_tokens - 1024),
        }
    return result
