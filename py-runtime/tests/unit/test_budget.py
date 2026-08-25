from __future__ import annotations

import re

from sztu_code.core.compact.budget import truncate_tool_results


# 构造带可选错误标记的 tool_result user 消息
def _make_tool_result_msg(content: str, *, is_error: bool = False) -> dict:
    block = {"type": "tool_result", "tool_use_id": "id1", "content": content}
    if is_error:
        block["is_error"] = True
    return {
        "role": "user",
        "content": [block],
    }


# 检查截断标记包含原始长度、遗漏长度和头尾保留方向
def _assert_marker_metadata(truncated: str, original_length: int) -> None:
    lower = truncated.lower()
    assert str(original_length) in truncated
    assert any(word in lower or word in truncated for word in ("omitted", "遗漏", "省略"))
    assert re.search(
        r"(?:[0-9]+[^\n]{0,20}(?:omitted|遗漏|省略)|"
        r"(?:omitted|遗漏|省略)[^0-9]{0,20}[0-9]+)",
        truncated,
        re.IGNORECASE,
    )
    has_head = any(word in lower or word in truncated for word in ("head", "头部", "前部", "前"))
    has_tail = any(word in lower or word in truncated for word in ("tail", "尾部", "后部", "后"))
    assert has_head and has_tail


# 从结构化截断标记读取遗漏字符数
def _omitted_chars(truncated: str) -> int:
    match = re.search(r"([0-9]+) chars omitted", truncated)
    assert match is not None
    return int(match.group(1))


# 功能：验证 tool_result 内容未超过阈值时原文不变
# 设计：构造 7999 字符内容（刚好低于 8000），断言消息原样返回
def test_short_tool_result_untouched() -> None:
    text = "x" * 7999
    msgs = [_make_tool_result_msg(text)]
    result = truncate_tool_results(msgs, limit=8000, keep=4000)
    assert result[0]["content"][0]["content"] == text


# 功能：验证 tool_result 内容超过阈值时被截断并附加省略标记
# 设计：构造 10000 字符内容，精确核对预算、头尾片段与标记中的长度元数据
def test_long_tool_result_truncated() -> None:
    text = "y" * 10_000
    msgs = [_make_tool_result_msg(text)]
    result = truncate_tool_results(msgs, limit=8000, keep=4000)
    truncated = result[0]["content"][0]["content"]
    assert len(truncated) <= 4000
    _assert_marker_metadata(truncated, len(text))
    marker_start = truncated.index("\n[")
    marker_end = truncated.index("]\n", marker_start) + 2
    omitted = len(text) - marker_start - (len(truncated) - marker_end)
    assert _omitted_chars(truncated) == omitted
    assert truncated.startswith("y" * marker_start)
    assert truncated.endswith("y" * (len(truncated) - marker_end))


# 功能：验证普通日志保留开头上下文和结尾摘要，并在标记中记录方向
# 设计：用明确的头尾哨兵构造日志，断言中间被省略且两端均可见
def test_log_keeps_head_and_tail() -> None:
    text = "HEAD\n" + ("progress\n" * 2000) + "TAIL: done"
    result = truncate_tool_results([_make_tool_result_msg(text)], limit=200, keep=160)
    truncated = result[0]["content"][0]["content"]
    assert len(truncated) <= 160
    assert truncated.startswith("HEAD")
    assert truncated.endswith("TAIL: done")
    _assert_marker_metadata(truncated, len(text))


# 功能：验证错误结果比普通结果为结尾分配更多保留空间
# 设计：用不同字符填充头尾并比较保留计数，避免依赖某个固定分配比例
def test_error_result_biases_tail() -> None:
    text = ("h" * 300) + ("x" * 500) + ("t" * 300)
    normal = truncate_tool_results([_make_tool_result_msg(text)], limit=300, keep=260)
    error = truncate_tool_results(
        [_make_tool_result_msg(text, is_error=True)], limit=300, keep=260
    )
    normal_text = normal[0]["content"][0]["content"]
    error_text = error[0]["content"][0]["content"]
    assert len(normal_text) <= 260
    assert len(error_text) <= 260
    assert error_text.count("t") > normal_text.count("t")
    assert error_text.count("h") < normal_text.count("h")
    _assert_marker_metadata(error_text, len(text))


# 功能：验证极小预算下标记自身也不会超出预算
# 设计：预算小于常规标记长度时仍断言结果严格受限且不抛异常
def test_tiny_budget_is_strictly_bounded() -> None:
    text = "start" + ("中" * 100) + "end"
    for budget in range(0, 80):
        result = truncate_tool_results(
            [_make_tool_result_msg(text)], limit=8, keep=budget
        )
        truncated = result[0]["content"][0]["content"]
        assert len(truncated) <= min(8, budget)


# 功能：验证中文按 Python 字符长度截断时头尾均保持完整字符
# 设计：使用多字节字符和边界预算，检查无编码破坏且长度不越界
def test_chinese_text_keeps_character_boundaries() -> None:
    text = "开头" + ("日志" * 500) + "结尾"
    result = truncate_tool_results([_make_tool_result_msg(text)], limit=120, keep=100)
    truncated = result[0]["content"][0]["content"]
    assert len(truncated) <= 100
    assert truncated.startswith("开头")
    assert truncated.endswith("结尾")
    _assert_marker_metadata(truncated, len(text))


# 功能：验证空字符串工具结果保持原样
# 设计：空结果低于任何有效阈值，断言不会被改写或追加标记
def test_empty_tool_result_untouched() -> None:
    empty = truncate_tool_results([_make_tool_result_msg("")], limit=10, keep=5)
    assert empty[0]["content"][0]["content"] == ""


# 功能：验证单行长文本没有换行也能同时保留头尾
# 设计：以单字符头尾哨兵包住超长正文，断言预算内两端都可见
def test_single_long_line_keeps_head_and_tail() -> None:
    text = "A" + ("x" * 500) + "Z"
    result = truncate_tool_results([_make_tool_result_msg(text)], limit=120, keep=100)
    truncated = result[0]["content"][0]["content"]
    assert len(truncated) <= 100
    assert truncated.startswith("A")
    assert truncated.endswith("Z")
    _assert_marker_metadata(truncated, len(text))


# 功能：验证 pytest 和 stack trace 错误结果优先完整保留末尾失败摘要
# 设计：在超长测试日志末尾放置 traceback 与 summary，错误结果应包含这些诊断信息
def test_pytest_stack_trace_error_keeps_failure_tail() -> None:
    failure_tail = (
        "Traceback (most recent call last):\n"
        "  File \"tests/test_api.py\", line 74, in test_request\n"
        "AssertionError: expected 200, got 500\n"
        "================ 1 failed, 73 passed in 4.20s ================"
    )
    text = "pytest session starts\n" + ("PASSED tests/test_ok.py\n" * 100) + failure_tail
    result = truncate_tool_results(
        [_make_tool_result_msg(text, is_error=True)], limit=360, keep=320
    )
    truncated = result[0]["content"][0]["content"]
    assert len(truncated) <= 320
    assert "pytest session starts" in truncated
    assert truncated.endswith("1 failed, 73 passed in 4.20s ================")
    assert "AssertionError: expected 200, got 500" in truncated
    _assert_marker_metadata(truncated, len(text))


# 功能：验证上下文卸载占位符不会因预算过小而被二次截断
# 设计：构造长度远超预算但含卸载前缀的完整占位符，断言逐字符保持原样
def test_offload_placeholder_never_truncated() -> None:
    placeholder = (
        "[上下文卸载: refs/bash_001.md]\n"
        "摘要: pytest 运行结果 — 1 failed, 73 passed\n"
        "统计: 50000 字符, 800 行\n"
        "使用 read_ref(\"refs/bash_001.md\") 读取完整输出"
    )
    result = truncate_tool_results(
        [_make_tool_result_msg(placeholder)], limit=24, keep=12
    )
    assert result[0]["content"][0]["content"] == placeholder


# 功能：验证 tool_result 内容恰好等于阈值时不截断
# 设计：构造恰好 8000 字符内容，断言原文保持不变
def test_exact_limit_untouched() -> None:
    text = "z" * 8000
    msgs = [_make_tool_result_msg(text)]
    result = truncate_tool_results(msgs, limit=8000, keep=4000)
    assert result[0]["content"][0]["content"] == text


# 功能：验证 text 类型 block 不受截断影响
# 设计：构造含 text block 的 user 消息，内容超过阈值，断言内容原样返回
def test_non_tool_result_block_untouched() -> None:
    long_text = "a" * 20_000
    msgs = [{"role": "user", "content": [{"type": "text", "text": long_text}]}]
    result = truncate_tool_results(msgs, limit=8000, keep=4000)
    assert result[0]["content"][0]["text"] == long_text


# 功能：验证同一 user 消息含多个 tool_result 时各自独立判断截断
# 设计：构造一条消息含两个 tool_result，一短一长，断言只有长的被截断
def test_multiple_tool_results_independent() -> None:
    short = "s" * 100
    long = "l" * 10_000
    msgs = [{
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "a", "content": short},
            {"type": "tool_result", "tool_use_id": "b", "content": long},
        ],
    }]
    result = truncate_tool_results(msgs, limit=8000, keep=4000)
    blocks = result[0]["content"]
    assert blocks[0]["content"] == short
    assert "chars omitted" in blocks[1]["content"]


# 功能：验证 assistant 消息不被截断处理
# 设计：构造超长内容的 assistant 消息，断言原样返回
def test_assistant_message_untouched() -> None:
    text = "a" * 20_000
    msgs = [{"role": "assistant", "content": text}]
    result = truncate_tool_results(msgs, limit=8000, keep=4000)
    assert result[0]["content"] == text
