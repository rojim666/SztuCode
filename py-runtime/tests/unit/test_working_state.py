from __future__ import annotations

from datetime import UTC, datetime

from sztu_code.core.context import ExecutionContext
from sztu_code.core.memory.working_state import WorkingState
from sztu_code.core.verification.models import EvidenceKind, VerificationOutcome


# 功能：验证带硬证据的 VERIFIED 观察被吸收进 verified_facts
# 设计：TEST_OUTPUT 属于硬证据（非模型自述），吸收后应出现在 verified_facts 中
def test_verified_hard_evidence_is_absorbed() -> None:
    ws = WorkingState(goals=["实现功能"])

    absorbed = ws.absorb("pytest 全部通过", VerificationOutcome.VERIFIED, EvidenceKind.TEST_OUTPUT)

    assert absorbed is True
    assert ws.verified_facts == ["pytest 全部通过"]


# 功能：验证模型自述永不通过证据门（AC-2 核心）
# 设计：即使 outcome=VERIFIED，MODEL_ASSERTION 也必须被拒绝——模型不能自评自证
def test_model_assertion_never_passes_gate() -> None:
    ws = WorkingState(goals=["实现功能"])

    absorbed = ws.absorb("我完成了任务", VerificationOutcome.VERIFIED, EvidenceKind.MODEL_ASSERTION)

    assert absorbed is False
    assert ws.verified_facts == []


# 功能：验证未验证观察不改变工作状态
# 设计：UNVERIFIED 观察被拒绝，verified_facts 与 unresolved 均不变
def test_unverified_observation_leaves_state_unchanged() -> None:
    ws = WorkingState(goals=["实现功能"])

    absorbed = ws.absorb("应该没问题", VerificationOutcome.UNVERIFIED, EvidenceKind.MODEL_ASSERTION)

    assert absorbed is False
    assert ws.verified_facts == []
    assert ws.unresolved == []


# 功能：验证过期与被环境阻塞的证据不被吸收
# 设计：STALE/ENV_BLOCKED 的证据已失效或不可用，不得进入 verified_facts
def test_stale_and_env_blocked_are_rejected() -> None:
    ws = WorkingState(goals=["实现功能"])

    assert ws.absorb("旧证据", VerificationOutcome.STALE, EvidenceKind.TEST_OUTPUT) is False
    assert ws.absorb("环境受限", VerificationOutcome.ENV_BLOCKED, EvidenceKind.COMMAND_EXIT_CODE) is False
    assert ws.verified_facts == []


# 功能：验证 FAILED 观察记入 unresolved 而非 verified_facts
# 设计：失败是待解决阻塞，应让模型可见，但不能伪装成已验证事实
def test_failed_observation_records_unresolved() -> None:
    ws = WorkingState(goals=["实现功能"])

    absorbed = ws.absorb("bash 命令退出码 1", VerificationOutcome.FAILED, EvidenceKind.COMMAND_EXIT_CODE)

    assert absorbed is True
    assert ws.unresolved == ["bash 命令退出码 1"]
    assert ws.verified_facts == []


# 功能：验证重复观察被去重，不产生重复条目
# 设计：同一事实二次吸收不应改变列表内容，避免状态膨胀
def test_duplicate_absorption_is_deduplicated() -> None:
    ws = WorkingState(goals=["实现功能"])

    ws.absorb("pytest 全部通过", VerificationOutcome.VERIFIED, EvidenceKind.TEST_OUTPUT)
    ws.absorb("pytest 全部通过", VerificationOutcome.VERIFIED, EvidenceKind.TEST_OUTPUT)

    assert ws.verified_facts == ["pytest 全部通过"]


# 功能：验证空事实被拒绝
# 设计：空字符串不是有效事实，吸收它只会浪费注入预算
def test_empty_fact_is_rejected() -> None:
    ws = WorkingState(goals=["实现功能"])

    assert ws.absorb("", VerificationOutcome.VERIFIED, EvidenceKind.TEST_OUTPUT) is False
    assert ws.verified_facts == []


# 功能：验证吸收硬证据后 updated_at 被刷新
# 设计：updated_at 是状态新鲜度的标记，任何成功吸收都应更新它
def test_absorption_refreshes_updated_at() -> None:
    before = datetime.now(UTC)
    ws = WorkingState(goals=["实现功能"])

    ws.absorb("文件已创建", VerificationOutcome.VERIFIED, EvidenceKind.FILE_STATE)

    after = datetime.now(UTC)
    assert before <= ws.updated_at <= after


# ---------------- render：紧凑渲染 ----------------

# 功能：验证空工作状态渲染为空字符串
# 设计：无 goals/facts/unresolved 时注入应整体跳过，不浪费上下文预算
def test_render_empty_state_returns_empty() -> None:
    ws = WorkingState()

    assert ws.render() == ""


# 功能：验证渲染包含三个分区且带统一前缀
# 设计：goals / verified / unresolved 各自出现，供模型按节读取
def test_render_contains_three_sections() -> None:
    ws = WorkingState(goals=["实现功能"])
    ws.absorb("pytest 全部通过", VerificationOutcome.VERIFIED, EvidenceKind.TEST_OUTPUT)
    ws.absorb("bash 失败", VerificationOutcome.FAILED, EvidenceKind.COMMAND_EXIT_CODE)

    text = ws.render()

    assert text.startswith("[Working state]")
    assert "goals=实现功能" in text
    assert "pytest 全部通过" in text
    assert "bash 失败" in text


# 功能：验证渲染受预算上限约束
# 设计：max_chars 小于完整内容时必须截断，防止注入膨胀
def test_render_respects_budget() -> None:
    ws = WorkingState(goals=["实现功能"])
    for i in range(50):
        ws.absorb(f"事实编号 {i}", VerificationOutcome.VERIFIED, EvidenceKind.TEST_OUTPUT)

    text = ws.render(max_chars=200)

    assert len(text) <= 200 + len("[truncated]")


# 功能：验证事实条目数有限制，保留最新的若干条
# 设计：单列表最多保留最近 N 条，旧事实滚动淘汰
def test_render_caps_list_entries() -> None:
    ws = WorkingState(goals=["实现功能"])
    for i in range(20):
        ws.absorb(f"事实编号 {i}", VerificationOutcome.VERIFIED, EvidenceKind.TEST_OUTPUT)

    text = ws.render()

    assert "事实编号 19" in text
    assert "事实编号 0" not in text


# ---------------- 注入：ExecutionContext 集成 ----------------

# 功能：验证工作状态仅在版本变化后注入消息尾部
# 设计：第一次注入追加 user 消息；状态未变时再次调用为 no-op，避免重复膨胀
def test_context_injects_working_state_only_on_change() -> None:
    ctx = ExecutionContext(run_id="r1", goal="g", max_steps=5)
    ws = WorkingState(goals=["实现功能"])
    ctx.working_state = ws

    assert ctx.add_working_state_update() is False  # 初始无内容，不注入

    ws.absorb("pytest 全部通过", VerificationOutcome.VERIFIED, EvidenceKind.TEST_OUTPUT)

    assert ctx.add_working_state_update() is True  # 状态变化 → 注入
    assert ctx.add_working_state_update() is False  # 未变化 → 不重复注入

    last = ctx.messages[-1]
    assert last["role"] == "user"
    blocks = last["content"]
    assert any("[Working state]" in b.get("text", "") for b in blocks)


# 功能：验证未设置 working_state 时注入调用安全无操作
# 设计：ExecutionContext 默认 working_state=None，调用不应抛错
def test_context_without_working_state_is_safe() -> None:
    ctx = ExecutionContext(run_id="r1", goal="g", max_steps=5)

    assert ctx.add_working_state_update() is False
    assert len(ctx.messages) == 1  # 仅初始 goal 消息
