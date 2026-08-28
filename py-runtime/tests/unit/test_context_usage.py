from sztu_code.core.compact.context_usage import (
    IncrementalUsageEstimator,
    _count_all,
    estimate_context_usage,
)
from sztu_code.core.compact.token_counter import TokenCounter


def test_context_usage_categories_reconcile_to_provider_input() -> None:
    usage = estimate_context_usage(
        messages=[
            {"role": "user", "content": "This session is being continued from a previous conversation.\nSummary:\nDone."},
            {"role": "assistant", "content": [{"type": "text", "text": "Working"}, {"type": "tool_use", "name": "read", "input": {"path": "a.py"}}]},
            {"role": "user", "content": [{"type": "tool_result", "content": "file body"}]},
        ],
        tool_schemas=[{"name": "read", "description": "Read a file"}],
        system="You are an agent.",
        actual_input_tokens=1200,
        context_window=4000,
        reserved_output_tokens=500,
    )

    categorized = usage.system_tokens + usage.summary_tokens + usage.conversation_tokens + usage.tool_tokens
    assert categorized == 1200
    assert usage.summary_tokens > 0
    assert usage.tool_tokens > 0
    assert usage.reserved_output_tokens == 500
    assert usage.available_tokens == 2300


def test_context_usage_never_reports_negative_available_capacity() -> None:
    usage = estimate_context_usage(
        messages=[{"role": "user", "content": "hello"}],
        tool_schemas=[],
        system="system",
        actual_input_tokens=990,
        context_window=1000,
        reserved_output_tokens=200,
    )
    assert usage.reserved_output_tokens == 10
    assert usage.available_tokens == 0


# 功能：验证估算不可整除时分类总和仍恒等于实际 input tokens
# 设计：raw 估算与 actual 的比例缩放必然产生舍入残差，残差必须由 conversation 回填，
#      否则事件统计与 provider usage 对不上账
def test_context_usage_categories_always_reconcile_when_uneven() -> None:
    cases = [
        ([{"role": "user", "content": "你好，这是一个中文消息" * 30}], 1),
        (
            [
                {"role": "assistant", "content": [{"type": "text", "text": "block"}, {"type": "tool_use", "name": "read", "input": {"path": "a.py"}}]},
                {"role": "user", "content": [{"type": "tool_result", "content": "content " * 50}]},
            ],
            2,
        ),
        ([], 0),
    ]
    for messages, _ in cases:
        usage = estimate_context_usage(
            messages=messages,
            tool_schemas=[{"name": "read", "description": "Read a file"}],
            system="system prompt " * 10,
            actual_input_tokens=7777,
            context_window=100_000,
            reserved_output_tokens=8192,
        )
        categorized = (
            usage.system_tokens
            + usage.summary_tokens
            + usage.conversation_tokens
            + usage.tool_tokens
        )
        assert categorized == 7777
        assert all(
            v >= 0
            for v in (
                usage.system_tokens,
                usage.summary_tokens,
                usage.conversation_tokens,
                usage.tool_tokens,
            )
        )
        assert usage.available_tokens == 100_000 - 7777 - 8192


# 功能：验证增量估算与全量重数在逐步追加消息时结果一致
# 设计：模拟 AgentLoop 每步追加 assistant + tool_result，断言增量结果与
#      从头全量重数完全一致（否则用量分类统计会偏离）
def test_incremental_matches_full_recount_across_steps() -> None:
    counter = TokenCounter()
    estimator = IncrementalUsageEstimator()
    system = "You are an agent."
    tools = [{"name": "read", "description": "Read a file"}]

    msgs: list[dict[str, object]] = [
        {"role": "user", "content": "goal"},
        {"role": "assistant", "content": [{"type": "text", "text": "plan"}]},
    ]
    assert estimator.raw_counts(
        messages=msgs, system=system, tool_schemas=tools
    ) == _count_all(counter, msgs, system, tools)

    for i in range(3):
        msgs.append(
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": f"t{i}",
                        "name": "read",
                        "input": {"path": "a.py"},
                    }
                ],
            }
        )
        msgs.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": f"t{i}",
                        "content": f"body {i} " * 200,
                    }
                ],
            }
        )
    assert estimator.raw_counts(
        messages=msgs, system=system, tool_schemas=tools
    ) == _count_all(counter, msgs, system, tools)


# 功能：验证消息整体替换（压缩/截断命中）时增量估算自动回退全量重数
# 设计：第二步消息列表元素全部为新对象，身份前缀无重叠，结果必须等于全量重数
def test_incremental_falls_back_on_message_replacement() -> None:
    counter = TokenCounter()
    estimator = IncrementalUsageEstimator()
    system = "s"
    tools: list[dict[str, object]] = []

    step1 = [{"role": "user", "content": "hello world"}]
    estimator.raw_counts(messages=step1, system=system, tool_schemas=tools)

    step2 = [
        {
            "role": "user",
            "content": "This session is being continued from a previous conversation.\nSummary:\nWorked.",
        },
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "Understood, I will continue."}],
        },
    ]
    assert estimator.raw_counts(
        messages=step2, system=system, tool_schemas=tools
    ) == _count_all(counter, step2, system, tools)
