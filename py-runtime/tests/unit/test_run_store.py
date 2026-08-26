from __future__ import annotations

import json
from pathlib import Path

from sztu_code.core.run_store import RunStore


# 功能：start 写入 running 记录，get 能按 run_id 读回完整字段
# 设计：用临时目录构造 RunStore，断言记录字段完整且状态为 running
def test_start_and_get_roundtrip(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.start("run-1", goal="fix bug", session_id="sess-1")

    record = store.get("run-1")
    assert record is not None
    assert record.run_id == "run-1"
    assert record.status == "running"
    assert record.goal == "fix bug"
    assert record.session_id == "sess-1"
    assert record.started_at


# 功能：finish 把 running 记录推进到终态并持久化
# 设计：先 start 再 finish，重新实例化 RunStore 后仍能读到终态，验证落盘而非仅内存
def test_finish_persists_terminal_status(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.start("run-1")
    store.finish("run-1", status="completed", reason="success", steps=3)

    reloaded = RunStore(tmp_path).get("run-1")
    assert reloaded is not None
    assert reloaded.status == "completed"
    assert reloaded.reason == "success"
    assert reloaded.steps == 3
    assert reloaded.ended_at


# 功能：已终态记录不会被再次覆盖，保证一个 run 只有一个最终结果
# 设计：先 finish 为 completed，再 finish 为 cancelled，断言仍是 completed
def test_finish_is_idempotent_on_terminal(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.start("run-1")
    store.finish("run-1", status="completed")

    store.finish("run-1", status="cancelled", reason="late cancel")
    record = store.get("run-1")
    assert record is not None
    assert record.status == "completed"
    assert record.reason != "late cancel"


# 功能：finish 要求终态，传入非终态状态时报错
# 设计：直接用 running 调用 finish，断言抛出 ValueError，避免误写入非终态
def test_finish_rejects_non_terminal_status(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.start("run-1")
    try:
        store.finish("run-1", status="running")
    except ValueError:
        return
    raise AssertionError("finish should reject a non-terminal status")


# 功能：get 对不存在的 run_id 返回 None
def test_get_unknown_returns_none(tmp_path: Path) -> None:
    assert RunStore(tmp_path).get("missing") is None


# 功能：reconcile 把崩溃遗留的 running 记录标记为 cancelled，且不影响已终态记录
# 设计：预写 running 与 completed 各一条，reconcile 后断言 running→cancelled、completed 不变
def test_reconcile_marks_interrupted_runs_cancelled(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.start("running-1", goal="g")
    store.start("running-2", goal="g")
    store.finish("running-2", status="completed")

    changed = store.reconcile()
    assert {record.run_id for record in changed} == {"running-1"}

    assert store.get("running-1").status == "cancelled"  # type: ignore[union-attr]
    assert store.get("running-1").reason == "daemon_restarted"  # type: ignore[union-attr]
    assert store.get("running-2").status == "completed"  # type: ignore[union-attr]


# 功能：list_running 只返回仍处于 running 状态的记录
def test_list_running_filters_by_status(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.start("a")
    store.start("b")
    store.finish("b", status="cancelled")

    assert {record.run_id for record in store.list_running()} == {"a"}


# 功能：记录文件损坏时 get 返回 None 而不抛异常
# 设计：直接写非法 JSON 到记录路径，get 应优雅降级
def test_get_tolerates_corrupt_record(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    path = store.record_path("bad")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")

    assert store.get("bad") is None


# 功能：运行记录以 JSON 形式落盘，关键字段与内存一致
# 设计：读取 run.json 原始内容，断言 status/run_id/goal 等字段
def test_record_file_is_json(tmp_path: Path) -> None:
    store = RunStore(tmp_path)
    store.start("run-json", goal="hello")

    data = json.loads(store.record_path("run-json").read_text(encoding="utf-8"))
    assert data["run_id"] == "run-json"
    assert data["status"] == "running"
    assert data["goal"] == "hello"
