from __future__ import annotations

from pathlib import Path

from sztu_code.core.compact.budget import truncate_tool_results
from sztu_code.core.compact.offload import OffloadManager, OffloadRecord, _make_summary
from sztu_code.core.tools.builtin.read_ref import ReadRefTool

# ============================================================
# _make_summary 摘要生成
# ============================================================


# 功能：验证 bash 测试输出能提取末尾的测试结果摘要
# 设计：使用 pytest 风格的测试输出，断言摘要包含 passed/failed 统计行
def test_make_summary_bash_pytest() -> None:
    output = "\n".join([
        "============================= test session starts ====",
        "collected 45 items",
        "tests/test_a.py::test_x PASSED",
        "tests/test_b.py::test_y FAILED",
        "========================= 42 passed, 3 failed ====",
    ])
    summary = _make_summary("bash", output)
    assert "42 passed" in summary or "3 failed" in summary


# 功能：验证 bash 空输出返回标记
def test_make_summary_bash_empty() -> None:
    assert "(empty output)" in _make_summary("bash", "")


# 功能：验证 read_file 摘要展示统计信息
def test_make_summary_read_file() -> None:
    output = "line1\nline2\nline3\n"
    summary = _make_summary("read_file", output)
    assert "3 行" in summary or "3 lines" in summary


# 功能：验证 grep 摘要展示结果数量
def test_make_summary_grep() -> None:
    output = "src/auth.py:15:def login()\nsrc/auth.py:32:def logout()\n"
    summary = _make_summary("grep", output)
    assert "2" in summary


# ============================================================
# OffloadManager 核心功能
# ============================================================


# 功能：验证 should_offload 对大输出返回 True
# 设计：构造超过 2000 字符的字符串，断言触发卸载
def test_should_offload_large_content(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    assert mgr.should_offload("bash", "x" * 3000) is True


# 功能：验证 should_offload 对小输出返回 False（非强制卸载工具）
# 设计：使用 read_file（非 force_tools），短内容不触发卸载
def test_should_offload_small_content(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path, force_tools=frozenset())  # 清空强制工具列表
    assert mgr.should_offload("read_file", "short") is False


# 功能：验证强制卸载工具（bash/grep/glob）不管输出大小都卸载
# 设计：短的 bash 命令输出也触发强制卸载
def test_should_offload_force_tools(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    assert mgr.should_offload("bash", "short") is True
    assert mgr.should_offload("grep", "short") is True
    assert mgr.should_offload("glob", "short") is True


# 功能：验证 disabling 卸载管理器后 should_offload 永远返回 False
def test_should_offload_disabled(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path, enabled=False)
    assert mgr.should_offload("bash", "x" * 5000) is False


# 功能：验证禁用卸载时不创建 refs/ 和 offload/ 空目录（Bug5 回归测试）
def test_disabled_offload_manager_creates_no_dirs(tmp_path: Path) -> None:
    OffloadManager(tmp_path, enabled=False)
    assert not (tmp_path / "refs").exists()
    assert not (tmp_path / "offload").exists()


# 功能：验证禁用卸载时 enabled 属性返回 False（Bug2 回归测试）
def test_disabled_offload_manager_enabled_property(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path, enabled=False)
    assert mgr.enabled is False


# 功能：验证 offload 方法写入 refs/*.md 文件
# 设计：调用 offload 后检查 refs 目录下是否产生 .md 文件
def test_offload_writes_ref_file(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    content = "line1\nline2\nline3\n" * 100  # ~2000 chars
    record = mgr.offload("bash", "toolu_001", content, "run-1")
    ref_full = tmp_path / record.ref_path
    assert ref_full.is_file()
    assert "line1" in ref_full.read_text(encoding="utf-8")


# 功能：验证 offload 方法追加 offload.jsonl 索引记录
# 设计：多次调用 offload 后，检查 offload.jsonl 中的记录数量
def test_offload_writes_index(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    mgr.offload("bash", "toolu_001", "x" * 3000, "run-1")
    mgr.offload("grep", "toolu_002", "y" * 3000, "run-1")
    index = tmp_path / "offload" / "offload.jsonl"
    lines = index.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


# 功能：验证 OffloadRecord 包含正确的元数据
# 设计：构造卸载记录并检查各字段
def test_offload_record_fields(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    record = mgr.offload("bash", "toolu_003", "z" * 3000, "run-2", is_error=True)
    assert record.tool_name == "bash"
    assert record.tool_use_id == "toolu_003"
    assert record.run_id == "run-2"
    assert record.is_error is True
    assert record.char_count == 3000
    assert record.ref_path.startswith("refs/bash_")


# 功能：验证 placeholder 方法生成的占位符包含关键元素
# 设计：检查占位符含有卸载标记、ref_path、摘要和 read_ref 提示
def test_placeholder_contains_key_elements(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    record = mgr.offload("bash", "toolu_004", "x" * 3000, "run-3")
    ph = mgr.placeholder(record)
    assert "[上下文卸载:" in ph
    assert record.ref_path in ph
    assert "read_ref" in ph
    assert record.summary in ph


# ============================================================
# read_ref 回读功能
# ============================================================


# 功能：验证 read_ref 能完整回读卸载文件的原始内容
# 设计：先 offload，再 read_ref，断言内容完全一致（使用 ASCII 避免平台编码差异）
def test_read_ref_roundtrip(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    original = "line of output content\n" * 200
    record = mgr.offload("bash", "toolu_005", original, "run-4")
    restored = mgr.read_ref(record.ref_path)
    assert restored.rstrip() == original.rstrip()


# 功能：验证 read_ref 正确处理以空行开头的内容（Bug1 回归测试）
# 设计：构造以空行开头的原始内容，确保头部分离不会被内容内的 \n\n 误导
def test_read_ref_content_starts_with_blank_lines(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    original = "\n\n\nactual content starts here\nmore content\n"
    record = mgr.offload("bash", "toolu_008", original, "run-6")
    restored = mgr.read_ref(record.ref_path)
    assert restored.rstrip() == original.rstrip()


# 功能：验证 read_ref 对不存在文件抛出 FileNotFoundError
def test_read_ref_missing(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    try:
        mgr.read_ref("refs/nonexistent.md")
        assert False, "应抛出异常"
    except FileNotFoundError:
        pass


# 功能：验证 read_ref 阻止路径遍历攻击
def test_read_ref_path_traversal(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    try:
        mgr.read_ref("refs/../../../etc/passwd")
        assert False, "应抛出异常"
    except ValueError:
        pass


# ============================================================
# ReadRefTool 集成测试
# ============================================================


# 功能：验证 ReadRefTool 通过 offload_manager 正确回读文件
# 设计：先 offload 一条记录，再通过 ReadRefTool.invoke 读取
async def test_read_ref_tool_invoke(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    original = "test content\n" * 100
    record = mgr.offload("bash", "toolu_006", original, "run-5")
    tool = ReadRefTool(mgr)
    result = await tool.invoke({"ref_path": record.ref_path})
    assert result.is_error is False
    assert original.strip() in result.content


# 功能：验证 read_ref 工具分页返回超长外部结果，避免完整内容重新灌入上下文
# 设计：卸载 10K 字符后限制读取 500 字符，断言返回游标且不含完整原文
async def test_read_ref_tool_pages_large_result(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    record = mgr.offload("bash", "toolu_page", "x" * 10_000, "run-page")
    result = await ReadRefTool(mgr).invoke(
        {"ref_path": record.ref_path, "offset": 500, "limit": 500}
    )
    assert result.is_error is False
    assert "next_offset=1000" in result.content
    assert len(result.content) < 600


# 功能：验证 ReadRefTool 对不存在文件返回错误
async def test_read_ref_tool_missing(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    tool = ReadRefTool(mgr)
    result = await tool.invoke({"ref_path": "refs/does_not_exist.md"})
    assert result.is_error is True


# 功能：验证 ReadRefTool 阻止路径遍历
async def test_read_ref_tool_traversal(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    tool = ReadRefTool(mgr)
    result = await tool.invoke({"ref_path": "../outside.md"})
    assert result.is_error is True


# ============================================================
# list_by_run 查询功能
# ============================================================


# 功能：验证 list_by_run 按 run_id 正确过滤记录
# 设计：写入 3 条记录（2 条 run-A, 1 条 run-B），按 run_id 查询
def test_list_by_run_filtering(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    mgr.offload("bash", "t1", "a" * 3000, "run-A")
    mgr.offload("grep", "t2", "b" * 3000, "run-A")
    mgr.offload("glob", "t3", "c" * 3000, "run-B")

    run_a = mgr.list_by_run("run-A")
    run_b = mgr.list_by_run("run-B")
    run_c = mgr.list_by_run("run-C")

    assert len(run_a) == 2
    assert len(run_b) == 1
    assert len(run_c) == 0


# ============================================================
# OffloadRecord 序列化
# ============================================================


# 功能：验证 OffloadRecord 的 to_dict / from_dict 往返一致性
# 设计：构造一条完整记录，dict 序列化后反序列化，断言所有字段一致
def test_offload_record_roundtrip() -> None:
    original = OffloadRecord(
        id="off_001",
        run_id="run-X",
        tool_name="bash",
        tool_use_id="toolu_007",
        ref_path="refs/bash_001.md",
        summary="测试摘要",
        char_count=5000,
        line_count=120,
        is_error=False,
        ts="2026-08-05T12:00:00Z",
    )
    restored = OffloadRecord.from_dict(original.to_dict())
    assert restored.id == original.id
    assert restored.run_id == original.run_id
    assert restored.tool_name == original.tool_name
    assert restored.tool_use_id == original.tool_use_id
    assert restored.ref_path == original.ref_path
    assert restored.summary == original.summary
    assert restored.char_count == original.char_count
    assert restored.line_count == original.line_count
    assert restored.is_error == original.is_error


# ============================================================
# budget.py 与 offload 协调
# ============================================================


# 功能：验证 truncate_tool_results 不截断已卸载的占位符内容
# 设计：构造含卸载标记的 tool_result，断言即使内容超过阈值也不截断
def test_truncate_skips_offloaded_content() -> None:
    offloaded = (
        "[上下文卸载: refs/bash_001.md]\n"
        "摘要: test summary\n"
        "统计: 50000 字符, 800 行\n"
        "使用 read_ref(\"refs/bash_001.md\") 读取完整输出"
    )
    msgs = [{
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "id1", "content": offloaded}],
    }]
    result = truncate_tool_results(msgs)
    assert result[0]["content"][0]["content"] == offloaded


# 功能：验证 truncate_tool_results 仍然截断未卸载的超长内容（fallback）
# 设计：构造不含卸载标记的超长 tool_result，断言仍然被截断
def test_truncate_still_works_for_non_offloaded() -> None:
    long_text = "z" * 10_000
    msgs = [{
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "id2", "content": long_text}],
    }]
    result = truncate_tool_results(msgs, limit=8000, keep=4000)
    truncated = result[0]["content"][0]["content"]
    assert "chars omitted" in truncated
    assert len(truncated) < len(long_text)


# ============================================================
# 多行触发卸载
# ============================================================


# 功能：验证超过 min_lines 行数时触发卸载（即使字符数不大）
# 设计：构造短行但行数超标的输出，断言触发卸载
def test_should_offload_many_lines(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path, force_tools=frozenset())  # 关闭强制工具
    content = "short\n" * 60  # 60 行，每行 6 字符 = 360 字符
    # 行数超过 min_lines=50 但字符数 << min_chars=2000
    assert mgr.should_offload("read_file", content) is True


# 功能：验证小于 min_lines 和 min_chars 时不触发卸载（非强制工具）
def test_should_not_offload_small(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path, force_tools=frozenset())
    assert mgr.should_offload("read_file", "hello world") is False


# ============================================================
# 边缘情况与鲁棒性测试
# ============================================================


# 功能：验证超长单行内容触发卸载（无换行但字符数超限）
def test_should_offload_long_single_line(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path, force_tools=frozenset())
    assert mgr.should_offload("read_file", "x" * 5000) is True


# 功能：验证恰好等于 min_chars 不触发卸载（边界值）
def test_should_offload_exact_min_chars_boundary(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path, force_tools=frozenset(), min_chars=2000)
    assert mgr.should_offload("read_file", "x" * 2000) is False


# 功能：验证恰好等于 min_chars+1 触发卸载（边界值）
def test_should_offload_one_over_min_chars(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path, force_tools=frozenset(), min_chars=2000)
    assert mgr.should_offload("read_file", "x" * 2001) is True


# 功能：验证自定义 force_tools 生效
def test_custom_force_tools(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path, force_tools=frozenset({"bash"}))
    assert mgr.should_offload("bash", "short") is True
    assert mgr.should_offload("grep", "short") is False  # grep 不在自定义列表中


# 功能：验证空字符串不触发卸载（强制工具除外）
def test_empty_string_offload(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path, force_tools=frozenset())
    assert mgr.should_offload("read_file", "") is False


# 功能：验证 bash 空输出也会因强制工具而卸载
def test_force_tool_empty_output(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    assert mgr.should_offload("bash", "") is True


# 功能：验证回读工具结果不会再次卸载，避免读取与卸载互相循环
# 设计：即使返回内容超过阈值，也断言 memory_read/read_ref 均不触发卸载
def test_readback_tools_are_never_reoffloaded(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path, force_tools=frozenset({"read_ref", "memory_read"}))
    assert mgr.should_offload("read_ref", "x" * 10_000) is False
    assert mgr.should_offload("memory_read", "x" * 10_000) is False


# 功能：验证 offload 对 error 结果正确标记
def test_offload_error_result(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    record = mgr.offload("bash", "toolu_err", "command not found", "run-1", is_error=True)
    assert record.is_error is True
    assert "command not found" in mgr.read_ref(record.ref_path)


# 功能：验证占位符 compact 模式下不展示 id 和 tool 字段
def test_placeholder_compact_mode(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    record = mgr.offload("bash", "toolu_cpt", "x" * 3000, "run-1")
    ph = mgr.placeholder(record, compact=True)
    assert "id:" not in ph
    assert "tool:" not in ph
    assert "read_ref" in ph


# 功能：验证占位符完整模式下展示所有字段
def test_placeholder_full_mode(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    record = mgr.offload("bash", "toolu_full", "x" * 3000, "run-1")
    ph = mgr.placeholder(record, compact=False)
    assert "id:" in ph
    assert "tool:" in ph


# 功能：验证多次 offload 产生的文件名互不相同
def test_offload_unique_filenames(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    r1 = mgr.offload("bash", "t1", "a" * 3000, "run-1")
    r2 = mgr.offload("bash", "t2", "b" * 3000, "run-1")
    assert r1.ref_path != r2.ref_path
    assert r1.id != r2.id


# 功能：验证 read_ref 对大文件也能正确回读
def test_read_ref_large_file(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    original = "large content line\n" * 500  # ~10K chars
    record = mgr.offload("bash", "toolu_large", original, "run-1")
    restored = mgr.read_ref(record.ref_path)
    assert restored.rstrip() == original.rstrip()


# 功能：验证 _make_summary 对未知工具类型仍产生有效输出
def test_make_summary_unknown_tool() -> None:
    from sztu_code.core.compact.offload import _make_summary
    summary = _make_summary("unknown_tool", "output line 1\noutput line 2")
    assert len(summary) > 0
    assert "output line 1" in summary


# 功能：验证 bash 摘要在没有关键标记行时回退到最后有意义的一行
def test_make_summary_bash_fallback() -> None:
    from sztu_code.core.compact.offload import _make_summary
    # 内容不含 pytest/test/error 等标记
    output = "line a\nline b\n" + ("x" * 15) + "\nlast meaningful line here\n"
    summary = _make_summary("bash", output)
    assert len(summary) > 0


# 功能：验证 _make_summary 对超过 max_chars 的摘要行正确截断
def test_make_summary_truncates_long_line() -> None:
    from sztu_code.core.compact.offload import _make_summary
    long_line = "=" * 50 + " 42 passed, 3 failed " + "=" * 500
    summary = _make_summary("bash", long_line, max_chars=50)
    assert len(summary) <= 50 or summary.endswith("...")


# 功能：验证多工具结果卸载后 list_by_run 能全部找回
def test_list_by_run_many_records(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path)
    for i in range(10):
        mgr.offload("bash", f"t{i}", f"output {i}\n" * 100, "run-batch")
    records = mgr.list_by_run("run-batch")
    assert len(records) == 10


# 功能：验证 disabled 模式的 OffloadManager 调用 offload 仍可写入
# 设计：should_offload 阻断正常流程，但直接调用 offload 应仍能工作
def test_offload_direct_call_when_disabled(tmp_path: Path) -> None:
    mgr = OffloadManager(tmp_path, enabled=False)
    record = mgr.offload("bash", "t_direct", "x" * 3000, "run-direct")
    assert (tmp_path / record.ref_path).is_file()
