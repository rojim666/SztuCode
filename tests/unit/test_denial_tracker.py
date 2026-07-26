from __future__ import annotations

from sztu_code.core.permissions.denial_tracker import DenialTracker


# ── record_denial ──────────────────────────────────────────────────────────────

# 功能：验证同工具连续拒绝时计数器递增
# 设计：连续 record_denial("bash") 三次，每次返回值和计数器都应递增
def test_record_denial_increments_consecutive() -> None:
    tracker = DenialTracker()
    assert tracker.record_denial("bash") is False   # 1 次，未达阈值
    assert tracker.record_denial("bash") is False   # 2 次，未达阈值
    assert tracker.record_denial("bash") is True    # 3 次，触发干预
    snap = tracker.snapshot()
    assert snap["consecutive"]["bash"] == 3
    assert snap["total"] == 3


# ── record_success ─────────────────────────────────────────────────────────────

# 功能：验证成功调用后对应工具的连续拒绝计数归零
# 设计：record_denial 两次后 record_success，再 record_denial 应从头计数
def test_record_success_resets_consecutive() -> None:
    tracker = DenialTracker()
    tracker.record_denial("bash")
    tracker.record_denial("bash")      # consecutive=2
    tracker.record_success("bash")     # reset → 0
    # 再次拒绝应从 0 开始累积
    assert tracker.record_denial("bash") is False  # 1 次
    assert tracker.record_denial("bash") is False  # 2 次
    assert tracker.record_denial("bash") is True   # 3 次


# ── should_intervene ───────────────────────────────────────────────────────────

# 功能：验证连续拒绝达到阈值（默认 3）时 should_intervene 返回 True
# 设计：默认 max_consecutive=3，两次拒绝不应触发，第三次触发
def test_should_intervene_at_threshold() -> None:
    tracker = DenialTracker(max_consecutive=3)
    tracker.record_denial("bash")
    tracker.record_denial("bash")
    assert tracker.should_intervene() is False
    tracker.record_denial("bash")
    assert tracker.should_intervene() is True


# 功能：验证总拒绝数达到 max_total（默认 20）时触发干预
# 设计：20 个不同工具各被拒一次，不触发连续阈值但触发总量阈值
def test_should_intervene_at_total_limit() -> None:
    tracker = DenialTracker(max_total=5, max_consecutive=10)
    for i in range(4):
        tracker.record_denial(f"tool_{i}")
    assert tracker.should_intervene() is False
    tracker.record_denial("tool_4")
    assert tracker.should_intervene() is True
    assert tracker.snapshot()["total"] == 5


# 功能：验证不同工具独立计数，A 被拒 3 次不因 B 成功而重置
# 设计：bash 被拒 2 次、write_file 成功 1 次不应重置 bash 的计数
def test_different_tools_separate_counters() -> None:
    tracker = DenialTracker()
    tracker.record_denial("bash")
    tracker.record_denial("bash")          # bash=2
    tracker.record_success("write_file")   # 不影响 bash
    snap = tracker.snapshot()
    assert snap["consecutive"]["bash"] == 2
    # bash 再次被拒应触发
    assert tracker.record_denial("bash") is True


# ── intervention_message ──────────────────────────────────────────────────────

# 功能：验证干预消息包含被拒工具名和次数
# 设计：向两个不同工具注入拒绝记录，消息中应出现二者名称和次数
def test_intervention_message_names_tools() -> None:
    tracker = DenialTracker()
    tracker.record_denial("bash")
    tracker.record_denial("bash")
    tracker.record_denial("bash")          # bash=3
    tracker.record_denial("write_file")    # write_file=1
    msg = tracker.intervention_message()
    assert "bash" in msg
    assert "3 times" in msg
    assert "write_file" in msg
    assert "1 time" in msg


# ── reset_intervention ─────────────────────────────────────────────────────────

# 功能：验证 reset_intervention 后 should_intervene 返回 False，防止重复注入
# 设计：触发干预 → reset → should_intervene 返回 False，但之后新的拒绝可再次触发
def test_reset_intervention_prevents_double_injection() -> None:
    tracker = DenialTracker(max_consecutive=3)
    tracker.record_denial("bash")
    tracker.record_denial("bash")
    tracker.record_denial("bash")
    assert tracker.should_intervene() is True
    tracker.reset_intervention()
    assert tracker.should_intervene() is False
    # 重置后连续计数器已清零，需要重新累积 3 次才能再次触发
    assert tracker.record_denial("bash") is False


# 功能：验证自定义阈值生效
# 设计：max_consecutive=5 时，4 次被拒不触发，5 次触发
def test_custom_thresholds() -> None:
    tracker = DenialTracker(max_consecutive=5)
    for _ in range(4):
        assert tracker.record_denial("bash") is False
    assert tracker.record_denial("bash") is True
