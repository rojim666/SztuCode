"""合成长对话 — 验证滑动窗口压缩在实际长对话中的效果"""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from sztu_code.core.compact.compactor import (
    Compactor,
    _flatten_turns,
    _split_into_turns,
)
from sztu_code.core.config import SztuConfig
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import LlmResponse, ToolCallBlock, UsageStats
from sztu_code.core.runner import AgentRunner
from sztu_code.core.session.model import Session
from sztu_code.core.session.store import SessionStore


# 构造模拟 LLM 响应的 provider
def _stub_provider(summary: str | None = None) -> Any:
    provider = MagicMock()
    if summary is None:
        summary = (
            "## 1. Original Goal\n"
            "Fix the bug in the authentication module.\n\n"
            "## 2. Completed Steps\n"
            "- Read auth.py and identified the issue\n"
            "- Fixed token validation logic\n"
            "- Wrote unit tests\n\n"
            "## 3. Key Constraints & Discoveries\n"
            "- JWT tokens use RS256 algorithm\n"
            "- Token expiry is 3600 seconds\n\n"
            "## 4. Current File State\n"
            "- src/auth.py: fixed token validation\n"
            "- tests/test_auth.py: added 5 test cases\n\n"
            "## 5. Remaining TODOs\n"
            "1. Update documentation\n"
            "2. Run integration tests\n\n"
            "## 6. Critical Data\n"
            "- JWT_SECRET from env var\n"
            "- User ID format: uuid4\n"
        )
    provider.chat = AsyncMock(return_value=LlmResponse(
        stop_reason="end_turn",
        text=summary,
        usage=UsageStats(input_tokens=5000, output_tokens=300),
    ))
    return provider


# 构造一个长对话（N 个 turn，每个 turn = assistant + user(tool_results)）
def _build_long_conversation(num_turns: int, base_size: int = 800) -> list[dict[str, Any]]:
    """构造 num_turns 个完整 turn，每 turn 约 base_size 字符"""
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": (
                "Please fix the authentication bug in the codebase. "
                "The issue is that tokens are not being validated correctly. "
                "Search the codebase, identify the root cause, fix it, and verify with tests."
            ),
        }
    ]

    for t in range(num_turns):
        # assistant 消息：模拟工具调用 + 思考
        assistant_content: list[dict[str, Any]] = []
        thinking_text = (
            f"Let me analyze step {t}. I need to understand the code structure. "
            + "x" * (base_size // 2)
        )
        assistant_content.append({
            "type": "thinking",
            "thinking": thinking_text,
        })
        if t < num_turns - 1:
            assistant_content.append({
                "type": "text",
                "text": f"I'll now read the relevant files for step {t}.",
            })
            tool_id = f"toolu_{uuid.uuid4().hex[:8]}"
            assistant_content.append({
                "type": "tool_use",
                "id": tool_id,
                "name": "read",
                "input": {"file_path": f"src/module_{t}.py"},
            })
            messages.append({"role": "assistant", "content": assistant_content})
            result_text = f"File contents for module_{t}.py:\n" + "y" * base_size
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
        else:
            assistant_content.append({
                "type": "text",
                "text": "The authentication bug has been fixed. Tests pass.",
            })
            messages.append({"role": "assistant", "content": assistant_content})

    return messages


class _LongCompactionProvider:
    def __init__(self) -> None:
        self._calls = 0
        self.compact_started = asyncio.Event()
        self.compact_completed = asyncio.Event()
        self._summary = """\
## 1. Original Goal
persist compaction before returning
## 2. Completed Steps
- background compaction finished
## 3. Key Constraints & Discoveries
- runner must not finish first
## 4. Current File State
- thread.jsonl now starts with summary
## 5. Remaining TODOs
- none
## 6. Critical Data
- stable summary
"""

    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    
        usage_estimator: object | None = None,
    ) -> LlmResponse:
        self._calls += 1
        if self._calls == 1:
            return LlmResponse(
                stop_reason="tool_use",
                tool_calls=[ToolCallBlock(id="t1", name="unknown_tool", input={})],
                usage=UsageStats(
                    input_tokens=100_000,
                    output_tokens=10,
                    context_pct=0.9,
                ),
            )

        if run_id == "compact":
            self.compact_started.set()
            await asyncio.sleep(0.05)
            self.compact_completed.set()
            return LlmResponse(
                stop_reason="end_turn",
                text=self._summary,
                usage=UsageStats(input_tokens=100_000, output_tokens=10),
            )

        return LlmResponse(
            stop_reason="end_turn",
            text="done",
            usage=UsageStats(input_tokens=200, output_tokens=10),
        )


def _event_types(path: Path) -> list[str]:
    return [
        json.loads(line)["type"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


class TestLongConversationTurnDetection:
    """验证 turn 检测在长对话中的正确性"""

    def test_split_50_turns(self) -> None:
        """50 轮对话应正确切分为 1 序言 + 50 body turn"""
        msgs = _build_long_conversation(50)
        turns = _split_into_turns(msgs)

        assert len(turns) == 51
        assert isinstance(turns[0][0]["content"], str)
        assert "authentication bug" in turns[0][0]["content"]

        for turn in turns[1:]:
            roles = [m["role"] for m in turn]
            assert "assistant" in roles

    def test_flatten_roundtrip(self) -> None:
        msgs = _build_long_conversation(20)
        turns = _split_into_turns(msgs)
        restored = _flatten_turns(turns)
        assert restored == msgs

    def test_sliding_window_preserves_recent_turns(self) -> None:
        msgs = _build_long_conversation(30)
        turns = _split_into_turns(msgs)
        body_turns = turns[1:]

        sliding_window_size = 3
        old_turns = body_turns[:-sliding_window_size]
        recent_turns = body_turns[-sliding_window_size:]

        assert len(old_turns) == 27
        assert len(recent_turns) == 3

        flat_recent = _flatten_turns(recent_turns)
        recent_text = str(flat_recent)
        assert "module_29" in recent_text or "29" in recent_text
        assert "module_28" in recent_text or "28" in recent_text

    def test_turn_count_growth_linear(self) -> None:
        for n in [10, 20, 30, 50]:
            msgs = _build_long_conversation(n)
            turns = _split_into_turns(msgs)
            assert len(turns) == n + 1


class TestSlidingWindowCompactionLong:
    """端到端验证滑动窗口压缩在长对话中的行为"""

    async def test_compact_50_turns_sliding_window_3(self) -> None:
        bus = EventBus()
        session_dir = Path("eval/reports")
        compactor = Compactor(bus, session_dir, "test-session-long")
        provider = _stub_provider()
        msgs = _build_long_conversation(50)

        result, new_msgs = await compactor.compact_messages(
            msgs, provider, sliding_window_size=3,
        )

        assert result is not None
        assert new_msgs is not None
        assert len(new_msgs) < len(msgs)
        assert isinstance(new_msgs[0]["content"], str)
        assert "authentication bug" in new_msgs[0]["content"]
        assert new_msgs[1]["role"] == "user"
        assert "This session is being continued" in new_msgs[1]["content"]
        assert new_msgs[2]["role"] == "assistant"
        assert "Understood" in str(new_msgs[2]["content"])
        assert "module_49" in str(new_msgs) or "module_47" in str(new_msgs)
        assert "module_0.py" not in str(new_msgs)
        assert "module_5.py" not in str(new_msgs)
        assert len(result.summary_text) > 100
        assert "Original Goal" in result.summary_text

    async def test_compact_100_turns_sliding_window_5(self) -> None:
        bus = EventBus()
        session_dir = Path("eval/reports")
        compactor = Compactor(bus, session_dir, "test-session-100")
        provider = _stub_provider()
        msgs = _build_long_conversation(100, base_size=300)

        result, new_msgs = await compactor.compact_messages(
            msgs, provider, sliding_window_size=5,
        )

        assert result is not None
        assert new_msgs is not None
        assert len(new_msgs) < len(msgs)
        assert "module_0.py" not in str(new_msgs)
        assert "module_50.py" not in str(new_msgs)

        recent_text = str(new_msgs)
        found_recent = any(f"module_{n}" in recent_text for n in range(95, 100))
        assert found_recent, "最近 5 轮应保留"
        assert len(result.summary_text) > 100

    async def test_token_savings_long_conversation(self) -> None:
        from sztu_code.core.compact.token_counter import TokenCounter

        bus = EventBus()
        session_dir = Path("eval/reports")
        compactor = Compactor(bus, session_dir, "test-token-save")
        provider = _stub_provider()
        msgs = _build_long_conversation(60, base_size=400)

        counter = TokenCounter()
        original_tokens = counter.count("\n\n".join(str(m) for m in msgs))

        result, new_msgs = await compactor.compact_messages(
            msgs, provider, sliding_window_size=3,
        )

        assert result is not None
        assert new_msgs is not None

        compacted_tokens = counter.count("\n\n".join(str(m) for m in new_msgs))
        savings_pct = (1 - compacted_tokens / original_tokens) * 100
        assert savings_pct > 30, (
            f"Token 节省应 >30%, 实际 {savings_pct:.1f}% "
            f"(original={original_tokens}, compacted={compacted_tokens})"
        )
        assert result.summary_tokens < result.original_token_estimate

    async def test_second_compaction_smaller_input(self) -> None:
        bus = EventBus()
        session_dir = Path("eval/reports")
        compactor = Compactor(bus, session_dir, "test-second")
        provider = _stub_provider()

        msgs = _build_long_conversation(50, base_size=400)
        result1, compacted1 = await compactor.compact_messages(
            msgs, provider, sliding_window_size=3, compaction_count=0,
        )
        assert result1 is not None and compacted1 is not None

        new_turns_messages = _build_long_conversation(10, base_size=400)
        new_body_only = _split_into_turns(new_turns_messages)[1:]
        extended = compacted1 + _flatten_turns(new_body_only)

        provider2 = _stub_provider()
        result2, compacted2 = await compactor.compact_messages(
            extended, provider2, sliding_window_size=3, compaction_count=1,
        )
        assert result2 is not None and compacted2 is not None
        assert result2.original_token_estimate < result1.original_token_estimate

    async def test_old_turns_too_small_no_failure(self) -> None:
        bus = EventBus()
        session_dir = Path("eval/reports")
        compactor = Compactor(bus, session_dir, "test-small")

        msgs = _build_long_conversation(8, base_size=50)
        provider = _stub_provider()

        result, new_msgs = await compactor.compact_messages(
            msgs, provider, sliding_window_size=3,
        )
        assert result is not None
        assert new_msgs is None
        provider.chat.assert_not_called()


async def test_run_outcome_returns_after_long_compaction_is_persisted(tmp_path: Path) -> None:
    cfg = SztuConfig()
    cfg.compaction.auto_threshold = 0.8
    store = SessionStore(tmp_path / "sessions")
    session = Session(
        id="sess-1",
        mode="chat",
        status="active",
        title="",
        created_at="t",
        updated_at="t",
    )
    store.write_meta(session)
    store.append_message("sess-1", "user", "old goal")
    store.append_message("sess-1", "user", "new goal with enough history")

    provider = _LongCompactionProvider()
    runner = AgentRunner(
        cfg,
        provider=provider,  # type: ignore[arg-type]
        runs_dir=tmp_path / "runs",
    )

    outcome = await runner.run_and_capture(
        "new goal",
        run_id="run-long-compact",
        session=session,
        store=store,
    )

    assert outcome.status == "success"
    assert provider.compact_started.is_set()
    assert provider.compact_completed.is_set()
    messages = store.read_messages("sess-1")
    assert "Original Goal" in messages[0]["content"]
    summary_files = list(store.session_dir("sess-1").glob("summary_*.md"))
    assert len(summary_files) == 1
    event_types = _event_types(store.runs_dir("sess-1") / "run-long-compact" / "events.jsonl")
    assert "context.compacted" in event_types
    assert event_types.index("context.compacted") < event_types.index("run.finished")
    assert event_types[-1] == "run.finished"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
