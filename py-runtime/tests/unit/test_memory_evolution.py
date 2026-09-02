from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sztu_code.core.memory.evolution import (
    MemoryPatch,
    ValidationGate,
    evolve_memory,
    extract_patches,
    run_memory_evolution,
    should_evolve,
)


# 构造三步轨迹：前两步成功、第三步测试失败（失败定位的典型形态）
def _trajectory() -> list[dict[str, object]]:
    return [
        {
            "node_id": "step_01",
            "label": "搜索认证代码",
            "status": "done",
            "verified": "verified",
        },
        {
            "node_id": "step_02",
            "label": "修改 refresh_token",
            "status": "done",
            "verified": "verified",
        },
        {
            "node_id": "step_03",
            "label": "运行测试",
            "status": "failed",
            "verified": "failed",
            "observation": "1 failed: test_refresh_token",
        },
    ]


# 构造一个默认合法的 patch（各字段可覆盖）
def _patch(**overrides: object) -> MemoryPatch:
    args: dict[str, object] = dict(
        target_note="auth-token-refresh",
        proposed_content="刷新 token 前必须先检查过期时间，直接重放会 401",
        attribution="note_content",
        evidence_refs=["step_03"],
        reason="测试失败定位到笔记遗漏过期检查",
    )
    args.update(overrides)
    return MemoryPatch(**args)  # type: ignore[arg-type]


# ============================================================
# ValidationGate 规则裁决
# ============================================================


# 功能：验证合法 patch 通过规则门
# 设计：证据引用指向真实轨迹节点、内容非空未超限、无重复 → accept
def test_gate_accepts_valid_patch() -> None:
    gate = ValidationGate(trajectory=_trajectory())
    decision = gate.evaluate(_patch(), existing_notes={})
    assert decision.accepted is True
    assert decision.reasons == []


# 功能：验证无证据引用的 patch 被拒绝（模型不能自评自证，AC-3 核心）
# 设计：Meta-Agent 声称完成分析但拿不出轨迹证据 → missing_evidence_refs
def test_gate_rejects_patch_without_evidence_refs() -> None:
    gate = ValidationGate(trajectory=_trajectory())
    decision = gate.evaluate(_patch(evidence_refs=[]), existing_notes={})
    assert decision.accepted is False
    assert "missing_evidence_refs" in decision.reasons


# 功能：验证证据引用指向不存在的轨迹节点被拒绝
# 设计：伪造 step_99 引用不能通过门——证据必须指向轨迹中的具体记录
def test_gate_rejects_unknown_evidence_refs() -> None:
    gate = ValidationGate(trajectory=_trajectory())
    decision = gate.evaluate(
        _patch(evidence_refs=["step_03", "step_99"]), existing_notes={}
    )
    assert decision.accepted is False
    assert any("evidence_refs_not_in_trajectory" in r for r in decision.reasons)


# 功能：验证空内容 patch 被拒绝
# 设计：空笔记无记忆价值，写入只会浪费检索预算
def test_gate_rejects_empty_content() -> None:
    gate = ValidationGate(trajectory=_trajectory())
    decision = gate.evaluate(_patch(proposed_content="   "), existing_notes={})
    assert decision.accepted is False
    assert "empty_content" in decision.reasons


# 功能：验证超长内容 patch 被拒绝
# 设计：记忆条目超限会污染检索质量（spec 风险：gate 规则过松导致记忆污染）
def test_gate_rejects_oversized_content() -> None:
    gate = ValidationGate(trajectory=_trajectory())
    decision = gate.evaluate(_patch(proposed_content="x" * 5000), existing_notes={})
    assert decision.accepted is False
    assert "content_over_limit" in decision.reasons


# 功能：验证与现有笔记完全一致的 patch 被去重拒绝
# 设计：重复写入无信息增益，且让台账膨胀
def test_gate_rejects_duplicate_content() -> None:
    gate = ValidationGate(trajectory=_trajectory())
    existing = {"auth-token-refresh": "刷新 token 前必须先检查过期时间，直接重放会 401"}
    decision = gate.evaluate(_patch(), existing_notes=existing)
    assert decision.accepted is False
    assert "duplicate_content" in decision.reasons


# 功能：验证包含路径分隔符的 target_note 被拒绝
# 设计：防止记忆写入逃逸出 .sztu/memory/notes/ 目录
def test_gate_rejects_path_traversal_target() -> None:
    gate = ValidationGate(trajectory=_trajectory())
    decision = gate.evaluate(_patch(target_note="../evil"), existing_notes={})
    assert decision.accepted is False
    assert "invalid_target_note" in decision.reasons


# ============================================================
# evolve_memory：AC-3 / AC-4 文件级断言
# ============================================================


# 功能：验证被拒绝的 patch 不改变现有笔记（AC-3）
# 设计：无证据引用的 patch 裁决 reject 后，笔记文件 hash 不变，仅台账记录
def test_rejected_patch_keeps_notes_unchanged(tmp_path: Path) -> None:
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    note_path = notes_dir / "auth-token-refresh.md"
    note_path.write_text("原有笔记内容", encoding="utf-8")
    before_hash = hashlib.sha256(note_path.read_bytes()).hexdigest()

    decisions = evolve_memory(
        [_patch(evidence_refs=[])],
        trajectory=_trajectory(),
        memory_root=tmp_path,
        round_id=1,
    )

    assert len(decisions) == 1
    assert decisions[0].accepted is False
    # 笔记文件未被触碰
    assert hashlib.sha256(note_path.read_bytes()).hexdigest() == before_hash
    # 台账记录了 reject
    ledger = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8")
    entry = json.loads(ledger.strip().split("\n")[0])
    assert entry["gate_result"] == "reject"
    assert entry["accepted"] is False


# 功能：验证通过的 patch 写入笔记文件并记台账 accept（AC-4）
# 设计：notes/<target>.md 内容与 proposed_content 一致；台账含证据引用/门控结果/accept
def test_accepted_patch_writes_note_and_ledger(tmp_path: Path) -> None:
    decisions = evolve_memory(
        [_patch()],
        trajectory=_trajectory(),
        memory_root=tmp_path,
        round_id=1,
    )

    assert len(decisions) == 1
    assert decisions[0].accepted is True
    note_path = tmp_path / "notes" / "auth-token-refresh.md"
    assert note_path.exists()
    assert "过期时间" in note_path.read_text(encoding="utf-8")

    entry = json.loads(
        (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").strip()
    )
    assert entry["gate_result"] == "accept"
    assert entry["accepted"] is True
    assert entry["evidence_refs"] == ["step_03"]
    assert entry["round"] == 1
    assert entry["target_note"] == "auth-token-refresh"


# 功能：验证台账为追加式——多轮 patch 全部可审计
# 设计：两轮各一条记录，逐行解析均完整
def test_ledger_is_append_only_across_rounds(tmp_path: Path) -> None:
    evolve_memory([_patch()], trajectory=_trajectory(), memory_root=tmp_path, round_id=1)
    evolve_memory(
        [_patch(target_note="second-note", proposed_content="第二条经验")],
        trajectory=_trajectory(),
        memory_root=tmp_path,
        round_id=2,
    )

    lines = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    rounds = [json.loads(line)["round"] for line in lines]
    assert rounds == [1, 2]


# 功能：验证同轮 patch 数超过 reg-cap 上限时自动拒绝
# 设计：防止 Meta-Agent patch 循环打转（spec 边界：每轮 patch 数上限）
def test_round_patch_cap_rejects_excess(tmp_path: Path) -> None:
    patches = [
        _patch(target_note=f"note-{i}", proposed_content=f"经验 {i}")
        for i in range(8)
    ]
    decisions = evolve_memory(
        patches, trajectory=_trajectory(), memory_root=tmp_path, round_id=1
    )

    assert len(decisions) == 8
    accepted = [d for d in decisions if d.accepted]
    rejected = [d for d in decisions if not d.accepted]
    assert len(accepted) == 5  # 上限内通过
    assert len(rejected) == 3  # 超限拒绝
    assert all("round_patch_cap_exceeded" in d.reasons for d in rejected)


# 功能：验证重复内容在磁盘已有笔记时被去重拒绝
# 设计：existing_notes 由 evolve_memory 从磁盘自动加载
def test_evolve_memory_deduplicates_against_disk_notes(tmp_path: Path) -> None:
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    (notes_dir / "auth-token-refresh.md").write_text(
        "刷新 token 前必须先检查过期时间，直接重放会 401", encoding="utf-8"
    )

    decisions = evolve_memory(
        [_patch()], trajectory=_trajectory(), memory_root=tmp_path, round_id=1
    )

    assert decisions[0].accepted is False
    assert "duplicate_content" in decisions[0].reasons


# 功能：验证同一轮多个 patch 全部写盘且台账逐条对应
# 设计：批量裁决的完整性——每个 patch 一条台账记录
def test_multiple_patches_all_recorded(tmp_path: Path) -> None:
    patches = [
        _patch(target_note="note-a", proposed_content="经验 A"),
        _patch(target_note="note-b", proposed_content="经验 B"),
        _patch(target_note="note-c", proposed_content="经验 C"),
    ]
    decisions = evolve_memory(
        patches, trajectory=_trajectory(), memory_root=tmp_path, round_id=1
    )

    assert all(d.accepted for d in decisions)
    lines = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3
    targets = {json.loads(line)["target_note"] for line in lines}
    assert targets == {"note-a", "note-b", "note-c"}


# ============================================================
# 进化触发判定（should_evolve）
# ============================================================


# 功能：验证 failed run 触发记忆进化
# 设计：失败是最强进化信号——策略性失败都应归因分析
def test_should_evolve_triggers_on_failed_run() -> None:
    assert should_evolve("failed", "stuck_loop") is True
    assert should_evolve("failed", "repeated_error") is True


# 功能：验证 success run 不触发记忆进化
# 设计：无失败信号的 run 没有进化素材，触发只会浪费 LLM 调用
def test_should_evolve_skips_success_run() -> None:
    assert should_evolve("success", None) is False


# 功能：验证用户取消的 run 不触发记忆进化
# 设计：取消是用户意图而非策略失败，归因分析只会产生噪声
def test_should_evolve_skips_user_cancelled() -> None:
    assert should_evolve("failed", "cancelled") is False


# 功能：验证受困类 interrupted run 触发进化
# 设计：stuck_loop / repeated_error / exceeded_max_steps 都是策略性受困信号
def test_should_evolve_triggers_on_stuck_interruptions() -> None:
    assert should_evolve("interrupted", "stuck_loop") is True
    assert should_evolve("interrupted", "repeated_error") is True
    assert should_evolve("interrupted", "exceeded_max_steps") is True


# 功能：验证环境限制类 interrupted run 不触发进化
# 设计：预算/墙钟/上下文溢出是资源问题，记忆进化无法改进
def test_should_evolve_skips_budget_interruptions() -> None:
    assert should_evolve("interrupted", "max_budget_usd") is False
    assert should_evolve("interrupted", "max_wall_clock_exceeded") is False
    assert should_evolve("interrupted", "blocking_limit") is False


# ============================================================
# Meta-Agent 输出解析（extract_patches）
# ============================================================


# 功能：验证纯 JSON 数组输出被正确解析为 MemoryPatch 列表
# 设计：Meta-Agent 按提示词约定输出 JSON 数组，逐字段还原
def test_extract_patches_parses_json_array() -> None:
    text = json.dumps(
        [
            {
                "target_note": "auth-token-refresh",
                "proposed_content": "刷新前检查过期时间",
                "attribution": "note_content",
                "evidence_refs": ["step_03"],
                "reason": "测试失败定位到笔记遗漏",
            }
        ],
        ensure_ascii=False,
    )
    patches = extract_patches(text)
    assert len(patches) == 1
    assert patches[0].target_note == "auth-token-refresh"
    assert patches[0].evidence_refs == ["step_03"]


# 功能：验证 markdown 代码栅栏包裹的 JSON 被正确解析
# 设计：LLM 常在 JSON 外加 ```json 围栏，解析必须容错
def test_extract_patches_parses_fenced_json() -> None:
    text = "分析如下：\n```json\n" + json.dumps(
        [
            {
                "target_note": "note-a",
                "proposed_content": "经验 A",
                "attribution": "invocation_timing",
                "evidence_refs": ["step_01"],
            }
        ],
        ensure_ascii=False,
    ) + "\n```"
    patches = extract_patches(text)
    assert len(patches) == 1
    assert patches[0].target_note == "note-a"


# 功能：验证 {"patches": [...]} 对象形态被解析
# 设计：部分模型会输出对象包裹的数组，两种形态都应支持
def test_extract_patches_parses_object_with_patches_key() -> None:
    text = json.dumps(
        {"patches": [{"target_note": "note-a", "proposed_content": "经验 A"}]},
        ensure_ascii=False,
    )
    patches = extract_patches(text)
    assert len(patches) == 1


# 功能：验证无法解析的文本返回空列表而非抛异常
# 设计：进化是尽力而为，Meta-Agent 输出跑偏不能中断 run 收尾
def test_extract_patches_returns_empty_on_invalid_text() -> None:
    assert extract_patches("这不是 JSON") == []
    assert extract_patches("") == []


# 功能：验证缺失必要字段的条目被跳过
# 设计：target_note / proposed_content 缺失的条目无法构成有效 patch
def test_extract_patches_skips_invalid_items() -> None:
    text = json.dumps(
        [
            {"target_note": "note-a", "proposed_content": "有效条目"},
            {"target_note": "missing-content"},
            {"proposed_content": "missing-target"},
            "not-an-object",
        ],
        ensure_ascii=False,
    )
    patches = extract_patches(text)
    assert len(patches) == 1
    assert patches[0].target_note == "note-a"


# ============================================================
# run_memory_evolution：Meta-Agent 编排
# ============================================================


class _MetaAgentProvider:
    """按注入文本返回 end_turn 响应；可配置抛异常。"""

    def __init__(self, text: str = "", *, exc: Exception | None = None) -> None:
        self._text = text
        self._exc = exc
        self.system: str | None = None

    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: object,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
        usage_estimator: object | None = None,
    ) -> object:
        from sztu_code.core.llm.types import LlmResponse

        if self._exc is not None:
            raise self._exc
        self.system = system
        return LlmResponse(stop_reason="end_turn", text=self._text)


def _meta_agent_json() -> str:
    return json.dumps(
        [
            {
                "target_note": "auth-token-refresh",
                "proposed_content": "刷新 token 前必须先检查过期时间",
                "attribution": "note_content",
                "evidence_refs": ["step_03"],
                "reason": "测试失败定位到笔记遗漏过期检查",
            }
        ],
        ensure_ascii=False,
    )


# 功能：验证 run_memory_evolution 端到端：LLM 输出 → patch → 门控 → 落盘
# 设计：Meta-Agent 返回引用 step_03 的合法 patch，应写入 notes 并记台账 accept
async def test_run_memory_evolution_writes_accepted_patch(tmp_path: Path) -> None:
    provider = _MetaAgentProvider(text=_meta_agent_json())

    decisions = await run_memory_evolution(
        provider=provider,  # type: ignore[arg-type]
        trajectory=_trajectory(),
        memory_root=tmp_path,
        goal="修复认证问题",
    )

    assert len(decisions) == 1
    assert decisions[0].accepted is True
    note = tmp_path / "notes" / "auth-token-refresh.md"
    assert "过期时间" in note.read_text(encoding="utf-8")
    # Meta-Agent 调用使用专用 system prompt
    assert provider.system is not None
    assert "[memory-evolution]" in provider.system


# 功能：验证 Meta-Agent 调用失败时安全返回空列表
# 设计：进化绝不中断 run 收尾——LLM 异常被吞并记录日志
async def test_run_memory_evolution_safe_on_llm_failure(tmp_path: Path) -> None:
    provider = _MetaAgentProvider(exc=RuntimeError("api down"))

    decisions = await run_memory_evolution(
        provider=provider,  # type: ignore[arg-type]
        trajectory=_trajectory(),
        memory_root=tmp_path,
    )

    assert decisions == []
    assert not (tmp_path / "ledger.jsonl").exists()


# 功能：验证未给出 round_id 时从台账自动递增轮次
# 设计：每次进化调用是一个轮次——两次不同内容的调用 → ledger 轮次 1、2
async def test_run_memory_evolution_increments_round(tmp_path: Path) -> None:
    await run_memory_evolution(
        provider=_MetaAgentProvider(text=_meta_agent_json()),  # type: ignore[arg-type]
        trajectory=_trajectory(),
        memory_root=tmp_path,
    )
    other = json.dumps(
        [
            {
                "target_note": "another-note",
                "proposed_content": "另一条经验",
                "evidence_refs": ["step_01"],
            }
        ],
        ensure_ascii=False,
    )
    await run_memory_evolution(
        provider=_MetaAgentProvider(text=other),  # type: ignore[arg-type]
        trajectory=_trajectory(),
        memory_root=tmp_path,
    )

    lines = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").strip().split("\n")
    rounds = [json.loads(line)["round"] for line in lines]
    assert rounds == [1, 2]
