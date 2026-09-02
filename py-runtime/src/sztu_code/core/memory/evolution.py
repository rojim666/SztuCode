"""Recuris 循环二：跨任务记忆进化（MemoryPatch + ValidationGate + Ledger）。

run 失败/受困结束后，Meta-Agent 基于结构化轨迹做失败归因，产出定向
MemoryPatch；ValidationGate 以确定性规则裁决（模型不能自评自证），
通过才写入记忆包，拒绝则保持原状仅记台账。

记忆包布局（memory_root 即 workspace 的 .sztu/memory/）::

    <memory_root>/ledger.jsonl      # 台账：追加式，每轮 patch 裁决记录
    <memory_root>/notes/<stem>.md   # 通过 gate 的记忆条目（一 note 一文件）
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sztu_code.core.events.bus import EventBus

if TYPE_CHECKING:
    from sztu_code.core.llm.base import LLMProvider
    from sztu_code.core.llm.types import LlmResponse

# patch 内容长度上限（字节）——防止记忆条目污染检索质量
_MAX_CONTENT_BYTES = 4096
# 单轮 patch 数上限（reg-cap，防 Meta-Agent patch 循环打转）
_MAX_PATCHES_PER_ROUND = 5
# 记忆条目文件名禁止的字符（防路径逃逸）
_FORBIDDEN_NOTE_CHARS = "/\\:*?\"<>|"
# 触发进化的 interrupted 原因：受困信号（策略性问题，记忆进化可改进）
_EVOLUTION_INTERRUPT_REASONS: frozenset[str] = frozenset(
    {"stuck_loop", "repeated_error", "exceeded_max_steps"}
)
# markdown 代码栅栏（LLM 常把 JSON 包在 ```json ... ``` 里）
_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```")


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class MemoryPatch:
    """定向记忆补丁：Meta-Agent 产出，交 ValidationGate 裁决。"""

    target_note: str  # 目标笔记标识（文件名 stem，如 "auth-token-refresh"）
    proposed_content: str  # 提议写入的笔记内容
    attribution: str  # 失败归因组件：note_content / state_representation / invocation_timing
    evidence_refs: list[str] = field(default_factory=list)  # 轨迹证据引用（node_id）
    reason: str = ""  # patch 理由（可审计）


@dataclass
class GateDecision:
    """ValidationGate 裁决结果：拒绝原因列表保证台账可审计。"""

    accepted: bool
    reasons: list[str] = field(default_factory=list)


class ValidationGate:
    """确定性规则门：证据引用校验、去重、长度上限、target 合法性。

    与 WorkingState 同一哲学：模型的断言（attribution/reason 文本）不构成
    通过依据，只有指向结构化轨迹具体记录的证据引用才有效。
    """

    def __init__(
        self,
        trajectory: list[dict[str, object]] | None = None,
        *,
        max_content_bytes: int = _MAX_CONTENT_BYTES,
    ) -> None:
        # 轨迹节点 ID 集合（来自 TaskCanvas.export()）
        self._node_ids: set[str] = {
            str(node.get("node_id"))
            for node in (trajectory or [])
            if node.get("node_id")
        }
        self._max_content_bytes = max_content_bytes

    # 裁决单个 patch；existing_notes 为 {target_note: 当前内容}
    def evaluate(
        self, patch: MemoryPatch, existing_notes: dict[str, str]
    ) -> GateDecision:
        reasons: list[str] = []

        # 规则 1：证据引用必须指向轨迹中的具体记录（模型不能自评自证）
        if not patch.evidence_refs:
            reasons.append("missing_evidence_refs")
        else:
            unknown = [r for r in patch.evidence_refs if r not in self._node_ids]
            if unknown:
                reasons.append(
                    "evidence_refs_not_in_trajectory:" + ",".join(unknown)
                )

        # 规则 2：内容非空
        if not patch.proposed_content.strip():
            reasons.append("empty_content")

        # 规则 3：长度上限
        if len(patch.proposed_content.encode("utf-8")) > self._max_content_bytes:
            reasons.append("content_over_limit")

        # 规则 4：去重——与现有笔记完全一致的内容拒绝（无信息增益）
        existing = existing_notes.get(patch.target_note, "")
        if existing and existing.strip() == patch.proposed_content.strip():
            reasons.append("duplicate_content")

        # 规则 5：target_note 合法（非空、无路径分隔/保留字符）
        if not patch.target_note.strip() or any(
            c in patch.target_note for c in _FORBIDDEN_NOTE_CHARS
        ):
            reasons.append("invalid_target_note")

        if reasons:
            return GateDecision(accepted=False, reasons=reasons)
        return GateDecision(accepted=True)


# 从磁盘加载现有记忆条目 {stem: 内容}，作为去重/冲突检查的基准
def _load_existing_notes(notes_dir: Path) -> dict[str, str]:
    if not notes_dir.is_dir():
        return {}
    notes: dict[str, str] = {}
    for path in notes_dir.glob("*.md"):
        notes[path.stem] = path.read_text(encoding="utf-8")
    return notes


# 追加一条台账记录（JSONL，追加式可审计）
def _append_ledger_entry(
    ledger_path: Path,
    *,
    round_id: int,
    patch: MemoryPatch,
    decision: GateDecision,
) -> None:
    entry = {
        "round": round_id,
        "target_note": patch.target_note,
        "attribution": patch.attribution,
        "evidence_refs": list(patch.evidence_refs),
        "gate_result": "accept" if decision.accepted else "reject",
        "accepted": decision.accepted,
        "reasons": list(decision.reasons),
        "content_sha256": hashlib.sha256(
            patch.proposed_content.encode("utf-8")
        ).hexdigest(),
        "ts": _now(),
    }
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def evolve_memory(
    patches: list[MemoryPatch],
    *,
    trajectory: list[dict[str, object]],
    memory_root: Path,
    round_id: int = 1,
) -> list[GateDecision]:
    """裁决并应用一批 MemoryPatch（AC-3/AC-4）。

    - 通过 gate → 写入 <memory_root>/notes/<target>.md + 台账 accept
    - 拒绝 → 现有笔记保持原状，仅台账记录 reject
    - 单轮超过 reg-cap 的 patch 直接拒绝（round_patch_cap_exceeded）
    """
    memory_root.mkdir(parents=True, exist_ok=True)
    notes_dir = memory_root / "notes"
    notes_dir.mkdir(exist_ok=True)
    ledger_path = memory_root / "ledger.jsonl"

    existing_notes = _load_existing_notes(notes_dir)
    gate = ValidationGate(trajectory)

    decisions: list[GateDecision] = []
    for index, patch in enumerate(patches):
        if index >= _MAX_PATCHES_PER_ROUND:
            decision = GateDecision(
                accepted=False, reasons=["round_patch_cap_exceeded"]
            )
        else:
            decision = gate.evaluate(patch, existing_notes)
        if decision.accepted:
            # 通过：写入记忆条目并更新去重基准
            note_path = notes_dir / f"{patch.target_note}.md"
            note_path.write_text(patch.proposed_content, encoding="utf-8")
            existing_notes[patch.target_note] = patch.proposed_content
        _append_ledger_entry(
            ledger_path,
            round_id=round_id,
            patch=patch,
            decision=decision,
        )
        decisions.append(decision)
    return decisions


# ============================================================
# 进化触发判定
# ============================================================


def should_evolve(status: str, reason: str | None) -> bool:
    """失败/受困信号判定：只有策略性失败才触发记忆进化。

    - success → 不进化（无失败信号）
    - 用户取消（failed + cancelled）→ 不进化（用户意图，非策略问题）
    - 预算/墙钟/上下文溢出中断 → 不进化（环境限制，记忆无法改进）
    - 其余 failed / 受困 interrupted（stuck_loop 等）→ 进化
    """
    if status == "failed":
        return reason != "cancelled"
    if status == "interrupted":
        return reason in _EVOLUTION_INTERRUPT_REASONS
    return False


# ============================================================
# Meta-Agent 输出解析
# ============================================================


def extract_patches(text: str) -> list[MemoryPatch]:
    """从 Meta-Agent 输出解析 MemoryPatch 列表（尽力而为，永不抛异常）。

    支持三种形态：裸 JSON 数组、markdown 栅栏包裹、{"patches": [...]} 对象。
    缺少 target_note / proposed_content 的条目直接跳过。
    """
    if not text or not text.strip():
        return []
    raw = text.strip()
    fenced = _FENCE_RE.search(raw)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        data: object = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = data.get("patches", [])
    if not isinstance(data, list):
        return []

    patches: list[MemoryPatch] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        target = item.get("target_note")
        content = item.get("proposed_content")
        if not isinstance(target, str) or not isinstance(content, str):
            continue
        refs_raw = item.get("evidence_refs", [])
        if not isinstance(refs_raw, list):
            refs_raw = []
        patches.append(
            MemoryPatch(
                target_note=target,
                proposed_content=content,
                attribution=str(item.get("attribution", "")),
                evidence_refs=[str(r) for r in refs_raw],
                reason=str(item.get("reason", "")),
            )
        )
    return patches


# ============================================================
# Meta-Agent 编排
# ============================================================


# 从既有台账解析下一个轮次号（取最大 round + 1）
def _next_round(ledger_path: Path) -> int:
    if not ledger_path.exists():
        return 1
    best = 0
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry: object = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            value = entry.get("round", 0)
            if isinstance(value, int) and value > best:
                best = value
    return best + 1


async def run_memory_evolution(
    *,
    provider: LLMProvider,
    trajectory: list[dict[str, object]],
    memory_root: Path,
    bus: EventBus | None = None,
    run_id: str = "",
    goal: str = "",
    round_id: int | None = None,
) -> list[GateDecision]:
    """Meta-Agent 进化循环：轨迹 → 失败归因 → MemoryPatch → 规则裁决。

    LLM 调用失败不抛出（进化是尽力而为），返回空列表；
    未给 round_id 时从台账自动递增轮次。
    """
    from sztu_code.core.prompts.memory_evolution_prompts import (
        build_evolution_prompt,
        memory_evolution_system_prompt,
    )

    prompt = build_evolution_prompt(trajectory, goal=goal)
    try:
        local_bus: EventBus = bus if bus is not None else EventBus()
        response: LlmResponse = await provider.chat(
            messages=[{"role": "user", "content": prompt}],
            tool_schemas=[],
            bus=local_bus,
            run_id=run_id or "memory-evolution",
            step=0,
            system=memory_evolution_system_prompt(),
        )
    except Exception:
        logging.getLogger(__name__).exception(
            "memory evolution meta-agent call failed"
        )
        return []

    patches = extract_patches(getattr(response, "text", "") or "")
    if not patches:
        return []
    return evolve_memory(
        patches,
        trajectory=trajectory,
        memory_root=memory_root,
        round_id=round_id
        if round_id is not None
        else _next_round(memory_root / "ledger.jsonl"),
    )
