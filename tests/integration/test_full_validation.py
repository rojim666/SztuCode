"""
Phase 1+2+3 全量验证 —— 无需 API key 的端到端测试
"""
from __future__ import annotations

from pathlib import Path

from sztu_code.core.compact.canvas import TaskCanvas
from sztu_code.core.compact.offload import OffloadManager
from sztu_code.core.context import ContinueReason, ExecutionContext, TerminationReason
from sztu_code.core.session.store import SessionStore

# ============================================================
# Phase 1: OffloadManager
# ============================================================


def test_offload_writes_ref_and_index(tmp_path: Path) -> None:
    """卸载写入 refs/*.md + offload.jsonl 索引"""
    mgr = OffloadManager(tmp_path)
    record = mgr.offload("bash", "tu_1", "output\n" * 300, "run-1")
    assert (tmp_path / record.ref_path).is_file()
    idx = tmp_path / "offload" / "offload.jsonl"
    assert idx.exists()
    lines = idx.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1


def test_offload_placeholder_compact(tmp_path: Path) -> None:
    """占位符远小于原文"""
    mgr = OffloadManager(tmp_path)
    original = "x" * 10000
    record = mgr.offload("grep", "tu_2", original, "run-2")
    ph = mgr.placeholder(record)
    assert len(ph) < 500
    assert record.ref_path in ph
    assert "read_ref" in ph


def test_read_ref_roundtrip(tmp_path: Path) -> None:
    """read_ref 100% 还原"""
    mgr = OffloadManager(tmp_path)
    original = "line of data\n" * 500
    record = mgr.offload("bash", "tu_3", original, "run-3")
    restored = mgr.read_ref(record.ref_path)
    assert restored.rstrip() == original.rstrip()


def test_should_offload_force_tools(tmp_path: Path) -> None:
    """强制卸载工具总是触发"""
    mgr = OffloadManager(tmp_path)
    assert mgr.should_offload("bash", "short") is True
    assert mgr.should_offload("grep", "short") is True


def test_should_offload_disabled(tmp_path: Path) -> None:
    """禁用时不卸载"""
    mgr = OffloadManager(tmp_path, enabled=False)
    assert mgr.should_offload("bash", "x" * 5000) is False


# ============================================================
# Phase 2: TaskCanvas
# ============================================================


def test_canvas_nodes_and_mermaid() -> None:
    """画布节点 + Mermaid 渲染"""
    canvas = TaskCanvas()
    canvas.record_step(label="搜索代码", tool_names=["grep"], summary="找到5文件",
                       refs=["refs/g_001.md"])
    canvas.record_step(label="读取源码", tool_names=["read_file"])
    canvas.record_step(label="运行测试", tool_names=["bash"], status="done",
                       summary="42 passed")

    mermaid = canvas.render_mermaid()
    assert "```mermaid" in mermaid
    assert "搜索代码" in mermaid
    assert "读取源码" in mermaid
    assert "运行测试" in mermaid
    assert "step_01 --> step_02" in mermaid
    assert canvas.node_count == 3
    assert canvas.stats()["done"] >= 1


def test_canvas_running_to_done() -> None:
    """状态转换: running → done/failed"""
    canvas = TaskCanvas()
    canvas.record_step(label="测试", tool_names=["bash"], status="running")
    canvas.finalize_last(label="测试完成", status="done", summary="all passed",
                         refs=["refs/b_001.md"])
    assert canvas.nodes[0].status == "done"

    canvas.record_step(label="修复", tool_names=["edit_file"], status="running")
    canvas.finalize_last(status="failed", summary="error")
    assert canvas.nodes[1].status == "failed"


def test_canvas_folds_old_nodes() -> None:
    """超过 max_visible 折叠旧节点"""
    canvas = TaskCanvas(max_visible_nodes=5)
    for i in range(20):
        canvas.record_step(label=f"Step {i}", status="done")
    output = canvas.render_mermaid()
    assert "15 个更早" in output


# ============================================================
# Phase 3: 终止 + 错误累积 + 预算
# ============================================================


def test_termination_reasons() -> None:
    """TerminationReason 枚举值正确"""
    assert TerminationReason.SUCCESS == "success"
    assert TerminationReason.REPEATED_ERROR == "repeated_error"
    assert TerminationReason.BLOCKING_LIMIT == "blocking_limit"
    assert TerminationReason.MAX_TURNS == "max_turns"
    assert TerminationReason.MAX_BUDGET_USD == "max_budget_usd"


def test_continue_reasons() -> None:
    """ContinueReason 枚举值正确"""
    assert ContinueReason.NEXT_TURN == "next_turn"
    assert ContinueReason.REACTIVE_COMPACT == "reactive_compact"


def test_error_accumulator() -> None:
    """错误累积: 3 次触发, 成功重置"""
    ctx = ExecutionContext(run_id="r1", goal="test", max_steps=10)
    assert not ctx.record_error("bash", "runtime_error")  # 1
    assert not ctx.record_error("bash", "runtime_error")  # 2
    assert ctx.record_error("bash", "runtime_error")       # 3 → 触发
    ctx.record_success()
    assert len(ctx.error_accumulator) == 0


def test_budget_methods() -> None:
    """预算方法"""
    ctx = ExecutionContext(run_id="r1", goal="test", max_steps=10)
    assert ctx.is_at_blocking_limit(0.99) is True
    assert ctx.is_at_blocking_limit(0.50) is False
    assert ctx.is_over_budget() is False  # max_budget_usd=0 → 不限
    ctx.max_budget_usd = 0.01
    ctx.total_input_tokens = 1_000_000
    assert ctx.is_over_budget() is True
    assert ctx.wall_clock_exceeded() is False
    assert ctx.token_budget_exhausted() is False


def test_mark_success_sets_reason() -> None:
    """mark_success 设置 reason"""
    ctx = ExecutionContext(run_id="r1", goal="test", max_steps=5)
    ctx.mark_success()
    assert ctx.status == "success"
    assert ctx.reason == TerminationReason.SUCCESS


def test_mark_interrupted() -> None:
    """mark_interrupted 区别于 failed"""
    ctx = ExecutionContext(run_id="r1", goal="test", max_steps=5)
    ctx.mark_interrupted("max_tokens_exceeded")
    assert ctx.status == "interrupted"
    assert ctx.reason == "max_tokens_exceeded"


# ============================================================
# Phase 3b: 记忆版本化
# ============================================================


def test_note_supersedes_chain(tmp_path: Path) -> None:
    """note_save → note_update → supersedes 链"""
    store = SessionStore(tmp_path / "sessions")
    sid = "sess-note"
    # V1
    v1 = store.append_note(sid, "使用 SQLite", "run-1")
    assert v1.startswith("note-")
    # V2
    v2 = store.update_note(sid, v1, "改用 PostgreSQL", "run-2")
    assert v2 is not None
    assert v2 != v1
    # 只显示最新
    notes = store.read_notes(sid)
    assert "PostgreSQL" in notes
    assert "SQLite" not in notes


def test_read_notes_legacy_format(tmp_path: Path) -> None:
    """旧格式 notes 兼容"""
    d = tmp_path / "sessions" / "sess-old"
    d.mkdir(parents=True)
    (d / "notes.md").write_text("## Note (old)\n旧格式内容\n\n", encoding="utf-8")
    store = SessionStore(tmp_path / "sessions")
    notes = store.read_notes("sess-old")
    assert "旧格式内容" in notes
