from __future__ import annotations

from sztu_code.core.llm.types import ToolCallBlock
from sztu_code.core.stuck_tracker import StuckLoopTracker, stuck_signature

# ── record_failure / should_intervene ─────────────────────────────────────────

# 功能：验证同一签名连续失败达到阈值时触发干预
# 设计：同一签名失败 2 次，第二次 record_failure 返回 True，snapshot 记录 worst_count
def test_record_failure_increments_consecutive() -> None:
    tracker = StuckLoopTracker()
    sig = ("bash", "pytest test_a")
    assert tracker.record_failure(sig) is False  # 1 次
    assert tracker.record_failure(sig) is True   # 2 次
    snap = tracker.snapshot()
    assert snap["worst_count"] == 2
    assert snap["worst_signature"] == "bash:pytest test_a"


# 功能：验证成功调用后该签名连续失败计数归零
# 设计：失败 2 次后成功，再失败应从 0 重新累积
def test_record_success_resets_consecutive() -> None:
    tracker = StuckLoopTracker()
    sig = ("bash", "pytest test_a")
    tracker.record_failure(sig)
    tracker.record_success(sig)
    assert tracker.record_failure(sig) is False  # 1 次
    assert tracker.record_failure(sig) is True   # 2 次


# 功能：max_failures=0 时关闭软干预
# 设计：失败任意多次 should_intervene 始终为 False
def test_max_failures_zero_disables() -> None:
    tracker = StuckLoopTracker(max_failures=0)
    sig = ("bash", "pytest test_a")
    for _ in range(10):
        tracker.record_failure(sig)
    assert tracker.should_intervene() is False


# 功能：不同签名的失败各自计数，不互相累计
# 设计：cmdA 与 cmdB 各失败一次未触发；cmdA 第二次才触发
def test_distinct_signatures_not_merged() -> None:
    tracker = StuckLoopTracker()
    sig_a = ("bash", "pytest test_a")
    sig_b = ("bash", "pytest test_b")
    tracker.record_failure(sig_a)
    tracker.record_failure(sig_b)
    assert tracker.should_intervene() is False
    assert tracker.record_failure(sig_a) is True


# ── reset_intervention / hard_stop ────────────────────────────────────────────

# 功能：reset_intervention 后 should_intervene 回到 False，且累计干预次数增加
# 设计：触发一次后 reset，再检查应不干预；hard_stop_reached 受 max_total 控制
def test_reset_intervention_clears_cycle() -> None:
    tracker = StuckLoopTracker(max_total=1)
    sig = ("bash", "pytest test_a")
    tracker.record_failure(sig)
    tracker.record_failure(sig)
    tracker.reset_intervention()
    assert tracker.should_intervene() is False
    assert tracker.hard_stop_reached() is True  # interventions=1 >= max_total=1


# 功能：max_total=0 时永不硬停
# 设计：多次 reset 后 hard_stop_reached 始终 False
def test_max_total_zero_never_hard_stops() -> None:
    tracker = StuckLoopTracker(max_total=0)
    sig = ("bash", "pytest test_a")
    for _ in range(5):
        tracker.record_failure(sig)
        tracker.record_failure(sig)
        tracker.reset_intervention()
    assert tracker.hard_stop_reached() is False


# 功能：干预消息包含最严重的工具签名
# 设计：注入消息中应出现工具名与 key，便于 LLM 识别卡死点
def test_intervention_message_names_signature() -> None:
    tracker = StuckLoopTracker()
    sig = ("read_file", "src/foo.py")
    tracker.record_failure(sig)
    tracker.record_failure(sig)
    msg = tracker.intervention_message()
    assert "read_file" in msg
    assert "src/foo.py" in msg


# ── stuck_signature ───────────────────────────────────────────────────────────

# 功能：bash 用完整 command 作签名，保留参数区分不同命令
# 设计：pytest test_a 与 pytest test_b 签名必须不同，防止误合并
def test_signature_bash_uses_full_command() -> None:
    a = stuck_signature(ToolCallBlock(id="1", name="bash", input={"command": "pytest test_a"}))
    b = stuck_signature(ToolCallBlock(id="2", name="bash", input={"command": "pytest test_b"}))
    assert a == ("bash", "pytest test_a")
    assert a != b


# 功能：路径类工具用 path 作签名
# 设计：read_file/write_file 取 path；list_dir 取 path；兼容 file_path 键
def test_signature_path_tools_use_path() -> None:
    assert stuck_signature(
        ToolCallBlock(id="1", name="read_file", input={"path": "a.py"})
    ) == ("read_file", "a.py")
    assert stuck_signature(
        ToolCallBlock(id="2", name="write_file", input={"file_path": "b.py", "content": "x"})
    ) == ("write_file", "b.py")


# 功能：通用工具用稳定 JSON（sort_keys）作签名
# 设计：键顺序不同的两个 dict 应产生相同签名，避免假阴性
def test_signature_generic_stable_json() -> None:
    a = stuck_signature(ToolCallBlock(id="1", name="foo", input={"b": 1, "a": 2}))
    b = stuck_signature(ToolCallBlock(id="2", name="foo", input={"a": 2, "b": 1}))
    assert a == b
    assert a == ("foo", '{"a": 2, "b": 1}')
