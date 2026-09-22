from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from sztu_code.core.compact.compactor import (
    CompactionDeadlineExceeded,
    Compactor,
    _summary_is_well_formed,
)
from sztu_code.core.context import ExecutionContext
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import LlmResponse, UsageStats


def _stub_provider(summary: str = "## 1. Original Goal\nTest\n## 2. Completed Steps\n- done") -> Any:
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=LlmResponse(
        stop_reason="end_turn",
        text=summary,
        usage=UsageStats(input_tokens=100, output_tokens=30),
    ))
    return provider


def _make_messages(n: int = 5) -> list[dict[str, Any]]:
    msgs = []
    for i in range(n):
        msgs.append({"role": "user", "content": "user message " + "x" * 200})
        msgs.append({"role": "assistant", "content": "assistant reply " + "y" * 200})
    return msgs


# 功能：验证第八章新版对话摘要标题能通过摘要质量检查
# 设计：构造只含新版关键标题的最小有效摘要，防止校验逻辑仍绑定旧六段格式
def test_chapter_eight_summary_headings_are_well_formed() -> None:
    summary = (
        "## 1. Primary Request and Intent\nImplement chapter eight prompts.\n"
        "## 7. Pending Tasks\nNo pending work remains."
    )

    assert _summary_is_well_formed(summary)


# 功能：验证 compact_messages 成功时 provider.chat 被调用一次且不传工具 schema
# 设计：stub provider 返回非空摘要，断言 chat 调用一次，tool_schemas=[]
async def test_compact_messages_calls_provider(tmp_path: Path) -> None:
    provider = _stub_provider()
    bus = EventBus()
    compactor = Compactor(bus, tmp_path, "sess-1")
    messages = _make_messages()

    result = await compactor.compact_messages(messages, provider)

    assert result is not None
    provider.chat.assert_called_once()
    call_kwargs = provider.chat.call_args
    assert call_kwargs.kwargs.get("tool_schemas") == [] or call_kwargs.args[1] == []


# 功能：验证 compact_messages 返回的摘要文本来自 provider 响应
# 设计：stub provider 返回固定摘要字符串，断言 result.summary_text 等于该字符串
async def test_compact_messages_returns_summary(tmp_path: Path) -> None:
    expected = "## 1. Original Goal\nDo X\n## 2. Completed\n- step one"
    provider = _stub_provider(summary=expected)
    bus = EventBus()
    compactor = Compactor(bus, tmp_path, "sess-1")

    result = await compactor.compact_messages(_make_messages(), provider)

    assert result is not None
    assert result.summary_text == expected


# 功能：验证 compact() 将 context.messages 替换为两条摘要消息对
# 设计：调用 compact() 后断言 messages 长度为 2，role 分别为 user/assistant
async def test_compact_replaces_context_messages(tmp_path: Path) -> None:
    provider = _stub_provider()
    bus = EventBus()
    compactor = Compactor(bus, tmp_path, "sess-1")
    ctx = ExecutionContext(run_id="r1", goal="test", max_steps=5)
    ctx.messages = _make_messages()

    await compactor.compact(ctx, provider)

    assert len(ctx.messages) == 2
    assert ctx.messages[0]["role"] == "user"
    assert ctx.messages[1]["role"] == "assistant"
    assert ctx.compacted is True


# 功能：验证 compact() 在 session 目录写入 summary_*.md 文件
# 设计：使用 tmp_path，调用 compact() 后检查目录内是否存在 summary_ 开头的文件
async def test_compact_writes_summary_file(tmp_path: Path) -> None:
    provider = _stub_provider()
    bus = EventBus()
    compactor = Compactor(bus, tmp_path, "sess-1")
    ctx = ExecutionContext(run_id="r1", goal="test", max_steps=5)
    ctx.messages = _make_messages()

    await compactor.compact(ctx, provider)

    summary_files = list(tmp_path.glob("summary_*.md"))
    assert len(summary_files) == 1


# 功能：验证 compact() 成功后发布 ContextCompactedEvent 事件
# 设计：订阅 EventBus，收集事件，断言收到类型为 context.compacted 的事件
async def test_compact_publishes_event(tmp_path: Path) -> None:
    provider = _stub_provider()
    bus = EventBus()
    received: list[Any] = []

    async def handler(event: Any) -> None:
        received.append(event)

    bus.subscribe(handler)
    compactor = Compactor(bus, tmp_path, "sess-1")
    ctx = ExecutionContext(run_id="r1", goal="test", max_steps=5)
    ctx.messages = _make_messages()

    await compactor.compact(ctx, provider)

    types = [getattr(e, "type", None) for e in received]
    assert "context.compacted" in types


# 功能：验证 provider 抛异常时 context.messages 保持不变
# 设计：stub provider.chat 抛 RuntimeError，断言 compact() 返回 None 且 messages 未被修改
async def test_compact_failure_preserves_context(tmp_path: Path) -> None:
    provider = MagicMock()
    provider.chat = AsyncMock(side_effect=RuntimeError("LLM error"))
    bus = EventBus()
    compactor = Compactor(bus, tmp_path, "sess-1")
    ctx = ExecutionContext(run_id="r1", goal="test", max_steps=5)
    original_messages = _make_messages()
    ctx.messages = list(original_messages)

    result = await compactor.compact(ctx, provider)

    assert result is None
    assert ctx.messages == original_messages


# 功能：验证摘要没有收益时不会替换上下文，避免压缩反而放大 token
# 设计：provider 返回的 output_tokens 不小于原上下文估算，compact_messages 应返回 None
async def test_compact_messages_rejects_no_benefit(tmp_path: Path) -> None:
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=LlmResponse(
        stop_reason="end_turn",
        text="## 1. Original Goal\nKeep\n## 2. Completed Steps\n- noop",
        usage=UsageStats(input_tokens=100, output_tokens=5_000),
    ))
    compactor = Compactor(EventBus(), tmp_path, "sess-1")

    result = await compactor.compact_messages(_make_messages(), provider)

    assert result is None


# 功能：验证摘要响应被 max_tokens 截断时不会采用不完整摘要
async def test_compact_messages_rejects_truncated_summary(tmp_path: Path) -> None:
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=LlmResponse(
        stop_reason="max_tokens",
        text="## 1. Original Goal\npartial",
        usage=UsageStats(input_tokens=100, output_tokens=30),
    ))
    compactor = Compactor(EventBus(), tmp_path, "sess-1")

    result = await compactor.compact_messages(_make_messages(), provider)

    assert result is None


async def test_wait_pending_can_cancel_background_tasks(tmp_path: Path) -> None:
    provider = MagicMock()
    cancel_seen = asyncio.Event()

    async def _chat(**_: Any) -> LlmResponse:
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancel_seen.set()
            raise

    provider.chat = AsyncMock(side_effect=_chat)
    compactor = Compactor(EventBus(), tmp_path, "sess-1")
    ctx = ExecutionContext(run_id="r1", goal="test", max_steps=5)
    ctx.messages = _make_messages()

    task = compactor.compact_async(ctx, provider)
    assert task is not None

    await asyncio.sleep(0)
    await compactor.wait_pending(cancel_pending=True)

    assert cancel_seen.is_set()
    assert task.cancelled() is True


# 功能：验证压缩请求会把 Run 剩余墙钟预算交给 provider，而不是只让 provider 用自己的默认超时
# 设计：stub provider 记录收到的 remaining_s；显式传入剩余预算，断言 provider 收到的值不超过它
async def test_compact_messages_passes_run_remaining_to_provider(tmp_path: Path) -> None:
    provider = _stub_provider()
    compactor = Compactor(EventBus(), tmp_path, "sess-1")

    await compactor.compact_messages(_make_messages(), provider, remaining_s=5.0)

    provider.chat.assert_called_once()
    received = provider.chat.call_args.kwargs.get("remaining_s")
    assert received is not None
    assert received <= 5.0


# 功能：验证 Run 剩余时间已耗尽时不会向 provider 发起任何压缩请求
# 设计：remaining_s=0 调用 compact_messages，断言 provider 零调用且以 deadline 原因放弃
async def test_compact_messages_skips_request_when_deadline_exhausted(tmp_path: Path) -> None:
    provider = _stub_provider()
    compactor = Compactor(EventBus(), tmp_path, "sess-1")

    with pytest.raises(CompactionDeadlineExceeded):
        await compactor.compact_messages(_make_messages(), provider, remaining_s=0.0)

    provider.chat.assert_not_called()


# 功能：验证忽略剩余预算的慢 provider 仍会被外层边界截断，不会把 Run 拖到 provider 默认超时
# 设计：provider 永久阻塞且不消费 remaining_s；传入 50ms 预算，断言有界内返回且不产生摘要
async def test_compact_messages_cuts_off_provider_that_ignores_remaining(tmp_path: Path) -> None:
    provider = MagicMock()
    started = asyncio.Event()

    async def _chat(**_kwargs: Any) -> LlmResponse:
        started.set()
        await asyncio.Future()  # 永不返回：模拟不遵守 remaining_s 的慢 provider
        raise AssertionError("unreachable")  # pragma: no cover

    provider.chat = AsyncMock(side_effect=_chat)
    compactor = Compactor(EventBus(), tmp_path, "sess-1")

    started_at = time.monotonic()
    with pytest.raises(CompactionDeadlineExceeded):
        await compactor.compact_messages(_make_messages(), provider, remaining_s=0.05)
    elapsed = time.monotonic() - started_at

    assert started.is_set()
    # 远小于 provider 的 120s 默认超时，证明边界来自 Run 预算而非 provider
    assert elapsed < 2.0


# 功能：验证 deadline 之后才返回的迟到摘要不会被采用
# 设计：provider 吞掉取消后仍返回一个格式合法的摘要；断言 compact_messages 以 deadline
#       原因放弃，而不是把迟到响应当作可用摘要（对应 AgentLoop._chat 的响应后检查）
async def test_compact_messages_rejects_late_summary_after_deadline(tmp_path: Path) -> None:
    provider = MagicMock()

    async def _chat(**_kwargs: Any) -> LlmResponse:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            # 吞掉取消仍返回响应：迟到的摘要
            return LlmResponse(
                stop_reason="end_turn",
                text="## 1. Original Goal\nTest\n## 2. Completed Steps\n- done",
                usage=UsageStats(input_tokens=100, output_tokens=30),
            )
        raise AssertionError("unreachable")  # pragma: no cover

    provider.chat = AsyncMock(side_effect=_chat)
    compactor = Compactor(EventBus(), tmp_path, "sess-1")

    with pytest.raises(CompactionDeadlineExceeded):
        await compactor.compact_messages(_make_messages(), provider, remaining_s=0.05)


# 功能：验证 provider 在 deadline 后清理时抛出的异常也归类为 deadline，而非普通 LLM 失败
# 设计：provider 被取消后在清理路径抛 RuntimeError；断言映射为 CompactionDeadlineExceeded，
#       从而不会被调用方计入压缩熔断器（对应 AgentLoop._chat 的 except Exception 分支）
async def test_compact_messages_maps_cleanup_failure_after_deadline(tmp_path: Path) -> None:
    provider = MagicMock()

    async def _chat(**_kwargs: Any) -> LlmResponse:
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            raise RuntimeError("provider cleanup failed")
        raise AssertionError("unreachable")  # pragma: no cover

    provider.chat = AsyncMock(side_effect=_chat)
    compactor = Compactor(EventBus(), tmp_path, "sess-1")

    with pytest.raises(CompactionDeadlineExceeded):
        await compactor.compact_messages(_make_messages(), provider, remaining_s=0.05)


# 功能：验证后台压缩因 Run deadline 被截断时不计入压缩熔断器
# 设计：context 的 deadline 已耗尽，compact_async 后等待任务结束；断言 provider 零调用、
#       compaction_failure_count 仍为 0、未安装压缩结果
async def test_compact_async_deadline_skip_does_not_count_as_failure(tmp_path: Path) -> None:
    provider = _stub_provider()
    compactor = Compactor(EventBus(), tmp_path, "sess-1")
    now = [100.0]
    ctx = ExecutionContext(
        run_id="r1",
        goal="test",
        max_steps=5,
        max_wall_clock_s=5,
        clock=lambda: now[0],
    )
    ctx.messages = _make_messages()
    ctx.start()
    now[0] = 200.0  # 越过 deadline_at=105，剩余时间为 0

    task = compactor.compact_async(ctx, provider)
    assert task is not None
    await compactor.wait_pending()

    provider.chat.assert_not_called()
    assert ctx.compaction_failure_count == 0
    assert ctx.compacted is False


# 功能：验证 wait_pending 受 Run 剩余时间限制，不会无界等待后台压缩
# 设计：后台压缩永久阻塞；传入 50ms 剩余预算，断言有界内返回、后台任务被取消且
#       未安装半成品摘要
async def test_wait_pending_is_bounded_by_run_remaining(tmp_path: Path) -> None:
    provider = MagicMock()
    cancel_seen = asyncio.Event()

    async def _chat(**_kwargs: Any) -> LlmResponse:
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancel_seen.set()
            raise

    provider.chat = AsyncMock(side_effect=_chat)
    compactor = Compactor(EventBus(), tmp_path, "sess-1")
    ctx = ExecutionContext(run_id="r1", goal="test", max_steps=5)
    ctx.messages = _make_messages()

    task = compactor.compact_async(ctx, provider)
    assert task is not None
    await asyncio.sleep(0)

    started_at = time.monotonic()
    await compactor.wait_pending(remaining_s=0.05)
    elapsed = time.monotonic() - started_at

    assert cancel_seen.is_set()
    assert task.cancelled() is True
    assert ctx.compacted is False
    # 远小于 provider 的 120s 默认超时，证明边界来自 Run 预算
    assert elapsed < 2.0


# 功能：验证 compact() 在 Run deadline 截断时返回 None，不把 deadline 异常泄漏给调用方
# 设计：context 的 deadline 已耗尽，调用 compact()；断言返回 None、provider 零调用、
#       context.messages 未被替换
async def test_compact_returns_none_when_deadline_exhausted(tmp_path: Path) -> None:
    provider = _stub_provider()
    compactor = Compactor(EventBus(), tmp_path, "sess-1")
    now = [100.0]
    ctx = ExecutionContext(
        run_id="r1",
        goal="test",
        max_steps=5,
        max_wall_clock_s=5,
        clock=lambda: now[0],
    )
    ctx.messages = _make_messages()
    ctx.start()
    now[0] = 200.0  # 越过 deadline_at=105
    original = list(ctx.messages)

    result = await compactor.compact(ctx, provider)

    assert result is None
    provider.chat.assert_not_called()
    assert ctx.messages == original
    assert ctx.compacted is False
