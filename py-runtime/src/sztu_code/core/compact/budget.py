from __future__ import annotations

from typing import Any

TOOL_RESULT_LIMIT = 8_000
TOOL_RESULT_KEEP = 4_000

# 上下文卸载占位符标记 — 已被卸载的内容不需要再截断
_OFFLOAD_MARKER = "[上下文卸载:"
_NORMAL_HEAD_RATIO = 0.5
_ERROR_HEAD_RATIO = 0.2


# 构造包含精确长度和保留方向的截断标记
def _truncation_marker(original: int, omitted: int, head: int, tail: int) -> str:
    return (
        f"\n[... original={original} chars; {omitted} chars omitted; "
        f"kept=head:{head},tail:{tail} ...]\n"
    )


# 按总预算切分工具输出的头尾，并让错误结果偏向保留尾部
def _truncate_text(text: str, budget: int, *, is_error: bool) -> str:
    original = len(text)
    budget = max(0, budget)
    if budget == 0:
        return ""

    head_ratio = _ERROR_HEAD_RATIO if is_error else _NORMAL_HEAD_RATIO
    retained = min(original - 1, budget)
    while retained > 0:
        head = int(retained * head_ratio)
        tail = retained - head
        marker = _truncation_marker(original, original - retained, head, tail)
        if retained + len(marker) <= budget:
            break
        retained -= 1

    if retained == 0 and budget >= len(_truncation_marker(original, original, 0, 0)):
        marker = _truncation_marker(original, original, 0, 0)
        return marker[:budget]
    if retained == 0:
        # 极小预算无法容纳完整元数据时，优先保留可识别的截断标记前缀
        return _truncation_marker(original, original, 0, 0).lstrip("\n")[:budget]
    return text[:head] + marker + text[original - tail :]


# 计算截断后的目标上限，兼容 keep 小于 limit 的历史配置
def _result_budget(limit: int, keep: int) -> int:
    return max(0, min(limit, keep))


# 对消息列表中超长的 tool_result 内容做内存截断，返回处理后的新列表
# 已被上下文卸载（含 [上下文卸载: 标记）的内容跳过截断
def truncate_tool_results(
    messages: list[dict[str, Any]],
    limit: int = TOOL_RESULT_LIMIT,
    keep: int = TOOL_RESULT_KEEP,
) -> list[dict[str, Any]]:
    result = []
    for msg in messages:
        if msg.get("role") != "user":
            result.append(msg)
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            result.append(msg)
            continue
        new_blocks = []
        changed = False
        for block in content:
            if block.get("type") == "tool_result" and isinstance(block.get("content"), str):
                text = block["content"]
                # 已被上下文卸载的内容 — 占位符很短，不需要截断
                if _OFFLOAD_MARKER in text:
                    new_blocks.append(block)
                    continue
                if len(text) > limit:
                    block = dict(block)
                    block["content"] = _truncate_text(
                        text,
                        _result_budget(limit, keep),
                        is_error=block.get("is_error") is True,
                    )
                    changed = True
            new_blocks.append(block)
        # 未发生截断时保留原消息对象身份，使 IncrementalUsageEstimator
        # 的前缀匹配（is 比较）跨步骤生效，避免每次 LLM 调用全量重数 token
        result.append({**msg, "content": new_blocks} if changed else msg)
    return result
