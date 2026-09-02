"""Recuris 工作记忆（Working State）。

每 run 维护结构化任务状态（goals / verified_facts / unresolved），
仅吸收经验证的观察（evidence-grounded update）：
- VERIFIED + 硬证据（非 model_assertion）→ verified_facts
- FAILED → unresolved（待解决阻塞）
- 其余（UNVERIFIED / PARTIAL / ENV_BLOCKED / STALE / 模型自述）→ 拒绝
"""

from __future__ import annotations

from datetime import UTC, datetime

from sztu_code.core.verification.models import EvidenceKind, VerificationOutcome

# 单列表最多渲染条数（保留最新）；总渲染预算默认 2048 字符
_MAX_ENTRIES_PER_LIST = 8
_DEFAULT_RENDER_BUDGET = 2048


class WorkingState:
    """任务内工作记忆：模型自述永不构成验证证据（模型不能自评自证）。"""

    def __init__(self, goals: list[str] | None = None) -> None:
        self.goals: list[str] = [g.strip() for g in (goals or []) if g.strip()]
        self.verified_facts: list[str] = []
        self.unresolved: list[str] = []
        self.updated_at: datetime = datetime.now(UTC)
        # 版本号：每次有效吸收 +1，供注入方判断是否需要重新渲染
        self.version: int = 0

    def absorb(
        self,
        fact: str,
        outcome: VerificationOutcome,
        evidence_kind: EvidenceKind,
    ) -> bool:
        """按证据门吸收一条观察；返回是否改变了状态。"""
        text = fact.strip()
        if not text:
            return False

        if outcome == VerificationOutcome.FAILED:
            return self._append_unique(self.unresolved, text)
        if (
            outcome == VerificationOutcome.VERIFIED
            and evidence_kind != EvidenceKind.MODEL_ASSERTION
        ):
            return self._append_unique(self.verified_facts, text)
        return False

    def render(self, max_chars: int = _DEFAULT_RENDER_BUDGET) -> str:
        """渲染为紧凑注入文本；空状态返回空字符串。"""
        sections: list[str] = []
        if self.goals:
            sections.append("goals=" + "; ".join(self.goals[-_MAX_ENTRIES_PER_LIST:]))
        if self.verified_facts:
            facts = "; ".join(self.verified_facts[-_MAX_ENTRIES_PER_LIST:])
            sections.append("verified=" + facts)
        if self.unresolved:
            pending = "; ".join(self.unresolved[-_MAX_ENTRIES_PER_LIST:])
            sections.append("unresolved=" + pending)
        if not sections:
            return ""

        text = "[Working state] " + " | ".join(sections)
        if len(text) > max_chars:
            text = text[:max_chars].rstrip() + "[truncated]"
        return text

    def _append_unique(self, target: list[str], text: str) -> bool:
        if text in target:
            return False
        target.append(text)
        self.updated_at = datetime.now(UTC)
        self.version += 1
        return True
