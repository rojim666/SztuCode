"""模拟长对话 Agent Loop — 验证滑动窗口压缩的 token 节省效果

模拟一个完整的 agent loop，逐步追加消息，在条件触发时调用 compaction，
然后对比"有压缩"和"无压缩"两种场景下的每步 token 消耗。

这样无需网络即可完整验证滑动窗口压缩的实际效果。
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from sztu_code.core.compact.compactor import (
    Compactor,
    _split_into_turns,
)
from sztu_code.core.compact.token_counter import TokenCounter
from sztu_code.core.events.bus import EventBus

# ─── 模拟 LLM provider，返回可定制的响应 ───

def _make_provider(
    text: str = "I'll analyze this code.",
    tool_calls: list[dict[str, Any]] | None = None,
    input_tokens: int = 5000,
    output_tokens: int = 200,
    stop_reason: str = "tool_use",
) -> Any:
    """构造模拟 provider，可指定 LLM 响应内容"""
    from sztu_code.core.llm.types import LlmResponse, ToolCallBlock, UsageStats

    tcs = []
    if tool_calls:
        for tc in tool_calls:
            tcs.append(ToolCallBlock(
                id=tc.get("id", f"toolu_{uuid.uuid4().hex[:8]}"),
                name=tc["name"],
                input=tc.get("input", {}),
            ))

    provider = MagicMock()
    provider.chat = AsyncMock(return_value=LlmResponse(
        stop_reason=stop_reason,
        text=text,
        tool_calls=tcs,
        thinking_blocks=[],
        usage=UsageStats(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            context_pct=0,
        ),
    ))
    return provider


# ─── 模拟 compaction provider，返回有效摘要 ───

def _make_compact_provider() -> Any:
    """构造用于 compaction 的 provider，返回格式正确的摘要"""
    from sztu_code.core.llm.types import LlmResponse, UsageStats

    summary = (
        "## 1. Original Goal\n"
        "Fix bugs and improve the codebase.\n\n"
        "## 2. Completed Steps\n"
        "- Read multiple source files\n"
        "- Identified several issues\n"
        "- Fixed syntax errors\n\n"
        "## 3. Key Constraints & Discoveries\n"
        "- Codebase uses Python 3.12+\n"
        "- Strict typing with mypy\n\n"
        "## 4. Current File State\n"
        "- No files were permanently modified\n\n"
        "## 5. Remaining TODOs\n"
        "1. Continue reading remaining files\n"
        "2. Apply suggested fixes\n\n"
        "## 6. Critical Data\n"
        "- None discovered yet\n"
    )

    provider = MagicMock()
    provider.chat = AsyncMock(return_value=LlmResponse(
        stop_reason="end_turn",
        text=summary,
        usage=UsageStats(input_tokens=3000, output_tokens=250),
    ))
    return provider


# ─── 模拟一个 agent turn（LLM 响应 + 工具执行 + 结果追加）───

def _simulate_turn(
    messages: list[dict[str, Any]],
    turn_num: int,
    *,
    result_size: int = 500,
) -> None:
    """向消息列表追加一个完整的 agent turn（assistant + user(tool_results)）"""
    tool_id = f"toolu_{uuid.uuid4().hex[:8]}"

    # assistant 消息
    thinking_text = f"Thinking about step {turn_num}. " + "x" * 100
    assistant_content: list[dict[str, Any]] = [
        {"type": "thinking", "thinking": thinking_text},
        {"type": "text", "text": f"Let me read file number {turn_num}."},
        {
            "type": "tool_use",
            "id": tool_id,
            "name": "read",
            "input": {"file_path": f"src/module_{turn_num}.py"},
        },
    ]
    messages.append({"role": "assistant", "content": assistant_content})

    # user 消息（工具结果）
    result_text = (
        f"Content of module_{turn_num}.py:\n"
        + "def function():\n    pass\n" * (result_size // 40)
        + f"\n# End of module_{turn_num}.py\n"
    )
    messages.append({
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result_text,
            }
        ],
    })


# ─── 模拟 end_turn（最终 assistant 响应）───

def _simulate_end_turn(messages: list[dict[str, Any]]) -> None:
    messages.append({
        "role": "assistant",
        "content": [{"type": "text", "text": "Task completed successfully."}],
    })


# ─── 测试类 ───

class TestSimulatedAgentLoop:
    """模拟完整的 agent loop，验证滑动窗口压缩对 token 增长的控制效果"""

    async def test_token_growth_with_vs_without_compaction(self) -> None:
        """对比：有压缩 vs 无压缩 的 60 步 token 消耗曲线"""
        counter = TokenCounter()

        # ── 无压缩场景 ──
        msgs_no_comp: list[dict[str, Any]] = [
            {"role": "user", "content": "Fix all bugs in the codebase."},
        ]
        per_step_no_comp: list[int] = []

        for step in range(60):
            _simulate_turn(msgs_no_comp, step, result_size=300)
            tokens = counter.count(json.dumps(msgs_no_comp, ensure_ascii=False))
            per_step_no_comp.append(tokens)

        # ── 有压缩场景（滑动窗口=3）──
        bus = EventBus()
        session_dir = Path("eval/reports")
        compactor = Compactor(bus, session_dir, "test-sim-loop")
        compact_provider = _make_compact_provider()

        msgs_with_comp: list[dict[str, Any]] = [
            {"role": "user", "content": "Fix all bugs in the codebase."},
        ]
        per_step_with_comp: list[int] = []
        compaction_events: list[dict[str, Any]] = []

        sliding_window = 3
        compact_trigger_turns = sliding_window + 2  # 5 turns 触发
        cooldown = 3
        last_compact_at = -cooldown - 1
        failure_count = 0
        compaction_count = 0

        for step in range(60):
            _simulate_turn(msgs_with_comp, step, result_size=300)
            tokens = counter.count(json.dumps(msgs_with_comp, ensure_ascii=False))
            per_step_with_comp.append(tokens)

            # 检查是否应触发压缩
            turns = _split_into_turns(msgs_with_comp)
            body_turns = turns[1:] if turns else []
            should_compact = (
                len(body_turns) > compact_trigger_turns
                and step - last_compact_at >= cooldown
                and failure_count < 3
            )

            if should_compact:
                result, new_msgs = await compactor.compact_messages(
                    msgs_with_comp, compact_provider, sliding_window_size=sliding_window,
                    compaction_count=compaction_count,
                )
                if result is not None and new_msgs is not None:
                    msgs_with_comp = new_msgs
                    compaction_count += 1
                    failure_count = 0
                    last_compact_at = step
                    compaction_events.append({
                        "step": step,
                        "before_tokens": tokens,
                        "after_tokens": counter.count(
                            json.dumps(msgs_with_comp, ensure_ascii=False)
                        ),
                        "summary_tokens": result.summary_tokens,
                        "original_estimate": result.original_token_estimate,
                    })
                elif result is not None and new_msgs is None:
                    # 跳过（旧 turn 太小）
                    last_compact_at = step
                else:
                    failure_count += 1

        # ── 验证 ──
        assert len(per_step_no_comp) == 60
        assert len(per_step_with_comp) == 60

        # 无压缩：每步 token 线性增长
        step_10_no = per_step_no_comp[10]
        step_59_no = per_step_no_comp[59]
        growth_no_comp = step_59_no / max(step_10_no, 1)
        print(f"\n无压缩: step 10 = {step_10_no}, step 59 = {step_59_no}, 增长 {growth_no_comp:.1f}x")

        # 有压缩：最终 token 应显著少于无压缩
        step_59_with = per_step_with_comp[59]
        savings_pct = (1 - step_59_with / step_59_no) * 100
        print(f"有压缩: step 59 = {step_59_with}, 节省 {savings_pct:.1f}%")
        print(f"压缩事件: {len(compaction_events)} 次")

        assert savings_pct > 20, (
            f"滑动窗口压缩应节省 >20% token, 实际 {savings_pct:.1f}%"
        )
        assert len(compaction_events) >= 1, "应至少触发 1 次成功压缩"

    async def test_compaction_caps_per_step_cost(self) -> None:
        """验证：压缩后每步 token 趋于平稳而非线性增长"""
        counter = TokenCounter()
        bus = EventBus()
        session_dir = Path("eval/reports")
        compactor = Compactor(bus, session_dir, "test-cap")
        compact_provider = _make_compact_provider()

        msgs: list[dict[str, Any]] = [
            {"role": "user", "content": "Fix all bugs."},
        ]
        per_step: list[int] = []
        sliding_window = 3

        for step in range(80):
            _simulate_turn(msgs, step, result_size=200)

            # 每次超过阈值就压缩
            turns = _split_into_turns(msgs)
            body_turns = turns[1:] if turns else []
            if len(body_turns) > sliding_window + 2:
                result, new_msgs = await compactor.compact_messages(
                    msgs, compact_provider, sliding_window_size=sliding_window,
                )
                if result is not None and new_msgs is not None:
                    msgs = new_msgs

            tokens = counter.count(json.dumps(msgs, ensure_ascii=False))
            per_step.append(tokens)

        # 统计后半段的增长趋势
        second_half = per_step[40:]
        # 后半段 token 的变异系数（标准差/均值）应该很小
        import statistics
        mean_second = statistics.mean(second_half)
        if mean_second > 0:
            stdev = statistics.stdev(second_half)
            cv = stdev / mean_second
            print(f"\n后半段 (step 40-79): mean={mean_second:.0f}, stdev={stdev:.0f}, CV={cv:.3f}")

            # 后半段 token 波动应 < 30%（说明增长被控制住了）
            assert cv < 0.30, (
                f"后半段 token 变异系数应 < 0.30, 实际 {cv:.3f} (mean={mean_second:.0f})"
            )

        # 后半段不应该大幅超过前半段的末尾
        first_half_end = per_step[39]
        second_half_max = max(second_half)
        growth = second_half_max / max(first_half_end, 1)
        print(f"前半段末尾: {first_half_end}, 后半段最大: {second_half_max}, 增长: {growth:.2f}x")
        assert growth < 2.5, (
            f"压缩后 token 增长应 < 2.5x (无压缩为 5x+), 实际 {growth:.2f}x"
        )

    async def test_compaction_frequency_decreases_over_time(self) -> None:
        """验证：压缩频率随着运行逐渐降低（因为摘要越来越稳定）"""
        bus = EventBus()
        session_dir = Path("eval/reports")
        compactor = Compactor(bus, session_dir, "test-freq")
        compact_provider = _make_compact_provider()

        msgs: list[dict[str, Any]] = [
            {"role": "user", "content": "Fix bugs."},
        ]
        compaction_steps: list[int] = []
        sliding_window = 3

        for step in range(100):
            _simulate_turn(msgs, step, result_size=250)

            turns = _split_into_turns(msgs)
            body_turns = turns[1:] if turns else []
            if len(body_turns) > sliding_window + 2:
                result, new_msgs = await compactor.compact_messages(
                    msgs, compact_provider, sliding_window_size=sliding_window,
                )
                if result is not None and new_msgs is not None:
                    msgs = new_msgs
                    compaction_steps.append(step)

        print(f"\n压缩发生步数: {compaction_steps}")

        # 前 50 步和后 50 步的压缩密度对比
        early = [s for s in compaction_steps if s < 50]
        late = [s for s in compaction_steps if s >= 50]

        # 后半段压缩间隔应该更大（或相等），说明系统趋于稳定
        if early:
            early_density = len(early) / 50
        else:
            early_density = 0
        if late:
            late_density = len(late) / 50
        else:
            late_density = 0

        print(f"前 50 步压缩密度: {early_density:.2f}/步, 后 50 步: {late_density:.2f}/步")
        assert late_density <= early_density + 0.02, (
            "后半段压缩密度不应显著高于前半段"
        )

    async def test_compact_preserves_recent_context(self) -> None:
        """验证：压缩后最近 turn 的工具调用和结果完整保留"""
        bus = EventBus()
        session_dir = Path("eval/reports")
        compactor = Compactor(bus, session_dir, "test-preserve")
        compact_provider = _make_compact_provider()

        msgs: list[dict[str, Any]] = [
            {"role": "user", "content": "Read file1.py and file2.py."},
        ]

        # 构建 20 个 turn
        for i in range(20):
            _simulate_turn(msgs, i, result_size=200)

        turns_before = _split_into_turns(msgs)
        body_turns_before = turns_before[1:]
        recent_before = body_turns_before[-3:]  # 最近 3 个 turn

        # 压缩
        result, new_msgs = await compactor.compact_messages(
            msgs, compact_provider, sliding_window_size=3,
        )

        assert result is not None
        assert new_msgs is not None

        # 验证最近 turn 的内容被保留
        turns_after = _split_into_turns(new_msgs)
        body_turns_after = turns_after[1:]
        recent_after = body_turns_after[-3:]

        # 最近 turn 的 assistant 和 user 消息数量应该一致
        assert len(recent_after) == len(recent_before), (
            f"最近 turn 数应一致: {len(recent_after)} vs {len(recent_before)}"
        )

        # 最近 turn 中的工具调用 ID 应该保留
        recent_before_text = str(recent_before)
        recent_after_text = str(recent_after)
        # 提取 tool_use id
        import re
        ids_before = set(re.findall(r"toolu_[a-f0-9]+", recent_before_text))
        ids_after = set(re.findall(r"toolu_[a-f0-9]+", recent_after_text))
        assert ids_before == ids_after, (
            f"最近 turn 的工具调用 ID 应保留: {ids_before} vs {ids_after}"
        )

    async def test_first_few_turns_never_lost(self) -> None:
        """验证：序言（goal）和最近 turn 始终保留，只压缩中间旧 turn"""
        bus = EventBus()
        session_dir = Path("eval/reports")
        compactor = Compactor(bus, session_dir, "test-preamble")
        compact_provider = _make_compact_provider()

        goal = "Find and fix all performance issues in the codebase."
        msgs: list[dict[str, Any]] = [
            {"role": "user", "content": goal},
        ]

        for i in range(30):
            _simulate_turn(msgs, i, result_size=300)

        result, new_msgs = await compactor.compact_messages(
            msgs, compact_provider, sliding_window_size=3,
        )

        assert result is not None
        assert new_msgs is not None

        # 第一条消息应该是序言（goal）
        first_msg_content = new_msgs[0]["content"]
        assert isinstance(first_msg_content, str)
        assert "performance issues" in first_msg_content, (
            f"序言应保留 goal: {first_msg_content[:100]}"
        )

        # 旧 turn 不应直接出现在消息中
        msgs_text = str(new_msgs)
        assert "module_0.py" not in msgs_text, "旧 turn 应被压缩移除"

        # 最近 turn 应保留
        assert "module_29" in msgs_text or "module_28" in msgs_text, (
            "最近 turn 应保留"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
