from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sztu_code.core.bus.events import ContextCompactedEvent, ContextCompactingEvent
from sztu_code.core.compact.token_counter import TokenCounter
from sztu_code.core.events.bus import EventBus
from sztu_code.core.prompts.context_management_prompts import (
    load_context_management_prompt,
)

if TYPE_CHECKING:
    from sztu_code.core.context import ExecutionContext
    from sztu_code.core.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# 进程级共享 token 计数器（编码器按名称缓存），避免每次压缩重复加载 tiktoken
_token_counter = TokenCounter()


# 构造压缩续接 user 消息：说明会话续接并附摘要，要求直接续接不寒暄
def _continuation_message(summary_text: str) -> str:
    return (
        "This session is being continued from a previous conversation that ran out of "
        "context. The summary below covers the earlier portion of the conversation.\n\n"
        "Summary:\n"
        f"{summary_text}\n\n"
        "Continue the conversation from where it left off without asking the user any "
        "further questions. Resume directly — do not acknowledge the summary, do not "
        "recap what was happening, and do not preface with continuation text."
    )


# 构造压缩续接的 assistant ack 消息内容块（带 cache_control 断点标记）
# 借鉴 Claude Code：摘要 ack 消息上放置 cache_control，使前缀稳定可缓存
def _continuation_ack_blocks() -> list[dict[str, Any]]:
    return [
        {
            "type": "text",
            "text": "Understood, I'll continue from this summary.",
            "cache_control": {"type": "ephemeral"},
        }
    ]


# 在真正触发上下文压缩时按稳定 ID 获取摘要提示词
def _compact_prompt() -> str:
    return load_context_management_prompt("context-compaction-summary")


# 返回当前 UTC 时间的简短时间戳字符串（用于文件名）
# 宽松检查摘要质量 — 只要有关键词和足够长度就接受，不要求严格格式
def _summary_is_well_formed(summary: str) -> bool:
    keywords = any(
        kw in summary.lower()
        for kw in (
            "original goal",
            "completed",
            "remaining",
            "summary",
            "progress",
            "primary request",
            "pending tasks",
            "current work",
            "task overview",
            "current state",
            "important discoveries",
            "next steps",
            "context to preserve",
        )
    )
    return bool(keywords and len(summary) >= 30)


def _ts_compact() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


# 返回当前 UTC 时间的 ISO 8601 字符串
def _now() -> str:
    return datetime.now(UTC).isoformat()


# ─── 滑动窗口 turn 检测 ───


# 判断消息是否为独立 user 文本消息（turn 0 序言或干预消息）
def _is_standalone_user_msg(msg: dict[str, Any]) -> bool:
    return msg.get("role") == "user" and isinstance(msg.get("content"), str)


# 判断 user 消息是否包含 tool_result 块（标志一个 turn 结束）
def _has_tool_results(msg: dict[str, Any]) -> bool:
    content = msg.get("content")
    return isinstance(content, list) and any(b.get("type") == "tool_result" for b in content)


# 将扁平消息列表切分为 turn 列表
# Turn 0 = 序言（初始 goal），Turn N = [assistant] + [user(tool_results)]
# 借鉴 Claude Code keepRecent=5 的分组逻辑
def _split_into_turns(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not messages:
        return []

    turns: list[list[dict[str, Any]]] = []
    i = 0

    # Turn 0: 收集所有前导独立 user 文本消息（序言）
    preamble: list[dict[str, Any]] = []
    while i < len(messages) and _is_standalone_user_msg(messages[i]):
        preamble.append(messages[i])
        i += 1
    if preamble:
        turns.append(preamble)

    # 剩余消息：配对 assistant + user(tool_results)
    current: list[dict[str, Any]] = []
    for j in range(i, len(messages)):
        msg = messages[j]
        if msg["role"] == "assistant":
            if current:
                turns.append(current)
            current = [msg]
        elif msg["role"] == "user":
            current.append(msg)
            if _has_tool_results(msg):
                turns.append(current)
                current = []
            else:
                # 独立 user 消息（干预等）— 自成一个 turn
                turns.append(current)
                current = []
    if current:
        turns.append(current)  # 尾部 assistant（end_turn）
    return turns


# 将 turn 列表还原为扁平消息列表
def _flatten_turns(turns: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    return [msg for turn in turns for msg in turn]


# 将 turn 列表序列化为纯文本（供 LLM 摘要使用）
def _turns_to_text(turns: list[list[dict[str, Any]]]) -> str:
    return _messages_to_text(_flatten_turns(turns))


@dataclass
class CompactionResult:
    summary_text: str
    original_token_estimate: int
    summary_tokens: int


class Compactor:
    # 初始化压缩器，绑定事件总线、session 目录和 session ID
    def __init__(self, bus: EventBus, session_dir: Path, session_id: str) -> None:
        self._bus = bus
        self._session_dir = session_dir
        self._session_id = session_id
        # 跟踪后台压缩任务，供 runner 收尾时等待
        self._pending_tasks: list[asyncio.Task[None]] = []

    # 压缩 ExecutionContext.messages，就地替换消息列表并写 summary 文件
    async def compact(
        self,
        context: ExecutionContext,
        provider: LLMProvider,
        focus: str = "",
        *,
        sliding_window_size: int = 0,
    ) -> CompactionResult | None:
        await self.notify_compacting(context.run_id)
        final_result: CompactionResult | None = None
        if sliding_window_size > 0:
            ret = await self.compact_messages(
                context.messages,
                provider,
                focus=focus,
                sliding_window_size=sliding_window_size,
                compaction_count=context.compaction_count,
            )
            if isinstance(ret, tuple):
                sliding_result, new_msgs = ret
                if sliding_result is None or new_msgs is None:
                    return None
                context.messages = new_msgs
                final_result = sliding_result
            else:
                return None
        else:
            ret = await self.compact_messages(context.messages, provider, focus=focus)
            if ret is None or isinstance(ret, tuple):
                return None
            context.messages = [
                {"role": "user", "content": _continuation_message(ret.summary_text)},
                {"role": "assistant", "content": _continuation_ack_blocks()},
            ]
            final_result = ret
        if final_result is None:
            return None
        context.compacted = True
        context.compaction_count += 1
        context.compaction_failure_count = 0  # 成功一次重置熔断器
        await self.record_compaction(context.run_id, final_result)
        logger.info(
            "context compacted session=%s run=%s original≈%d summary=%d tokens mode=%s",
            self._session_id,
            context.run_id,
            final_result.original_token_estimate,
            final_result.summary_tokens,
            "sliding" if sliding_window_size > 0 else "full",
        )
        return final_result

    # 异步压缩：在后台执行压缩，不阻塞 AgentLoop
    # 借鉴 Claude Code precomputeCompactionEnabled — 后台预计算摘要
    def compact_async(
        self,
        context: ExecutionContext,
        provider: LLMProvider,
        focus: str = "",
        *,
        sliding_window_size: int = 0,
    ) -> asyncio.Task[None] | None:
        # 对当前消息做快照（浅拷贝列表，消息 dict 本身不变）
        snapshot = list(context.messages)

        async def _run() -> None:
            await self.notify_compacting(context.run_id)
            final_result: CompactionResult | None = None
            if sliding_window_size > 0:
                ret = await self.compact_messages(
                    snapshot,
                    provider,
                    focus=focus,
                    sliding_window_size=sliding_window_size,
                    compaction_count=context.compaction_count,
                )
                if not isinstance(ret, tuple):
                    context.compaction_failure_count += 1
                    logger.warning(
                        "compactor: sliding compaction attempt %d failed (session=%s)",
                        context.compaction_failure_count,
                        context.run_id,
                    )
                    return
                sliding_result, new_msgs = ret
                if sliding_result is None:
                    context.compaction_failure_count += 1
                    logger.warning(
                        "compactor: sliding compaction attempt %d failed (session=%s)",
                        context.compaction_failure_count,
                        context.run_id,
                    )
                    return
                # result 非 None 但 new_msgs 为 None → 跳过（token 不足等）
                if new_msgs is None:
                    return
                # 检查快照后是否有新消息追加
                if len(context.messages) > len(snapshot):
                    new_messages_since = context.messages[len(snapshot) :]
                    context.messages = new_msgs + new_messages_since
                else:
                    context.messages = new_msgs
                final_result = sliding_result
            else:
                ret = await self.compact_messages(snapshot, provider, focus=focus)
                if ret is None or isinstance(ret, tuple):
                    context.compaction_failure_count += 1
                    logger.warning(
                        "compactor: full compaction attempt %d failed (session=%s)",
                        context.compaction_failure_count,
                        context.run_id,
                    )
                    return
                # 检查快照后是否有新消息追加
                if len(context.messages) > len(snapshot):
                    new_messages = context.messages[len(snapshot) :]
                    context.messages = [  # type: ignore[assignment]
                        {"role": "user", "content": _continuation_message(ret.summary_text)},
                        {"role": "assistant", "content": _continuation_ack_blocks()},
                    ] + new_messages
                else:
                    context.messages = [
                        {"role": "user", "content": _continuation_message(ret.summary_text)},
                        {"role": "assistant", "content": _continuation_ack_blocks()},
                    ]
                final_result = ret
            context.compacted = True
            context.compaction_count += 1
            context.compaction_failure_count = 0  # 成功一次重置熔断器
            await self.record_compaction(context.run_id, final_result)
            logger.info(
                "context compacted (async) session=%s run=%s original≈%d summary=%d tokens mode=%s",
                self._session_id,
                context.run_id,
                final_result.original_token_estimate,
                final_result.summary_tokens,
                "sliding" if sliding_window_size > 0 else "full",
            )

        task = asyncio.create_task(_run())
        self._pending_tasks.append(task)
        return task

    # 等待所有后台压缩任务完成（runner 收尾时调用）
    async def wait_pending(self, *, cancel_pending: bool = False) -> None:
        if not self._pending_tasks:
            return
        tasks = self._pending_tasks[:]
        self._pending_tasks.clear()
        if cancel_pending:
            for task in tasks:
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def notify_compacting(self, run_id: str) -> None:
        await self._bus.publish(
            ContextCompactingEvent(
                session_id=self._session_id,
                run_id=run_id,
                ts=_now(),
            )
        )

    async def record_compaction(self, run_id: str, result: CompactionResult) -> None:
        self._write_summary(result.summary_text)
        await self._bus.publish(
            ContextCompactedEvent(
                session_id=self._session_id,
                run_id=run_id,
                original_tokens=result.original_token_estimate,
                summary_tokens=result.summary_tokens,
                ts=_now(),
            )
        )

    # 纯函数式压缩：接收消息列表，返回 CompactionResult 或 (result, new_messages)
    # sliding_window_size=0 → 全量替换（返回单个 CompactionResult | None）
    # sliding_window_size>0 → 滑动窗口（返回 (CompactionResult | None, new_messages | None)）
    async def compact_messages(
        self,
        messages: list[dict[str, Any]],
        provider: LLMProvider,
        focus: str = "",
        *,
        sliding_window_size: int = 0,
        compaction_count: int = 0,
    ) -> CompactionResult | None | tuple[CompactionResult | None, list[dict[str, Any]] | None]:
        from sztu_code.core.events.bus import EventBus as _Bus

        counter = _token_counter

        if sliding_window_size > 0:
            # ─── 滑动窗口模式 ───
            # 保留最近 N 个 turn 完整细节，仅摘要更早的 turn
            # 这样摘要前缀可以跨多次 LLM 调用保持稳定 → API 自动缓存
            turns = _split_into_turns(messages)
            if len(turns) <= 1 + sliding_window_size:
                # turn 太少 — 回退全量替换，确保短对话仍能压缩
                history_text = _messages_to_text(messages)
                original_estimate = counter.count(history_text)
                prompt = _compact_prompt()
                if focus.strip():
                    prompt += f"\n\nIMPORTANT: Pay special attention to: {focus.strip()}"

                compact_req: list[dict[str, object]] = [
                    {"role": "user", "content": f"{prompt}\n\n---\n\n{history_text}"}
                ]

                try:
                    silent_bus = _Bus()
                    response = await provider.chat(
                        messages=compact_req,
                        tool_schemas=[],
                        bus=silent_bus,
                        run_id="compact",
                        step=0,
                        system="You are a helpful assistant that summarizes conversations.",
                    )
                except Exception:
                    logger.exception("compactor: LLM call failed, skipping compaction")
                    return None, None

                result = _validate_summary(response, counter, original_estimate)
                if result is None:
                    return None, None

                fallback_msgs: list[dict[str, Any]] = [
                    {"role": "user", "content": _continuation_message(result.summary_text)},
                    {"role": "assistant", "content": _continuation_ack_blocks()},
                ]
                return result, fallback_msgs

            preamble = turns[0]  # 始终保留序言（初始 goal）
            body_turns = turns[1:]
            old_turns = body_turns[:-sliding_window_size]
            recent_turns = body_turns[-sliding_window_size:]

            history_text = _turns_to_text(old_turns)
            original_estimate = counter.count(history_text)
            # 旧 turn 太小（< 2000 tokens），跳过但不计失败
            # 返回 result 非 None 但 new_messages=None → compact_async 不增 failure_count
            if original_estimate < 2000:
                logger.info(
                    "compactor: old turns too small (%d tok, %d turns), deferring",
                    original_estimate,
                    len(old_turns),
                )
                return CompactionResult(
                    summary_text="",
                    original_token_estimate=original_estimate,
                    summary_tokens=0,
                ), None
            prompt = _compact_prompt()
            if compaction_count > 0:
                prompt += (
                    f"\n\nThis is compaction #{compaction_count + 1}. "
                    "The previous summary is already in the conversation prefix. "
                    "Focus primarily on new information in the turns below."
                )
            if focus.strip():
                prompt += f"\n\nIMPORTANT: Pay special attention to: {focus.strip()}"

            compact_req2: list[dict[str, object]] = [
                {"role": "user", "content": f"{prompt}\n\n---\n\n{history_text}"}
            ]

            try:
                silent_bus = _Bus()
                response = await provider.chat(
                    messages=compact_req2,
                    tool_schemas=[],
                    bus=silent_bus,
                    run_id="compact",
                    step=0,
                    system="You are a helpful assistant that summarizes conversations.",
                )
            except Exception:
                logger.exception("compactor: LLM call failed, skipping compaction")
                return None, None

            result = _validate_summary(response, counter, original_estimate)
            if result is None:
                return None, None

            # 重构消息列表：序言 + 摘要对 + 最近 turn
            rebuilt_msgs: list[dict[str, Any]] = (
                list(preamble)
                + [
                    {"role": "user", "content": _continuation_message(result.summary_text)},
                    {"role": "assistant", "content": _continuation_ack_blocks()},
                ]
                + _flatten_turns(recent_turns)
            )

            return result, rebuilt_msgs
        else:
            # ─── 全量替换模式（向后兼容）───
            history_text = _messages_to_text(messages)
            original_estimate = counter.count(history_text)
            prompt = _compact_prompt()
            if focus.strip():
                prompt += f"\n\nIMPORTANT: Pay special attention to: {focus.strip()}"

            compress_request: list[dict[str, object]] = [
                {"role": "user", "content": f"{prompt}\n\n---\n\n{history_text}"}
            ]

            try:
                silent_bus = _Bus()
                response = await provider.chat(
                    messages=compress_request,
                    tool_schemas=[],
                    bus=silent_bus,
                    run_id="compact",
                    step=0,
                    system="You are a helpful assistant that summarizes conversations.",
                )
            except Exception:
                logger.exception("compactor: LLM call failed, skipping compaction")
                return None

            return _validate_summary(response, counter, original_estimate)

    # 将摘要文本写入 session 目录的 summary_<ts>.md
    def _write_summary(self, text: str) -> None:
        try:
            self._session_dir.mkdir(parents=True, exist_ok=True)
            path = self._session_dir / f"summary_{_ts_compact()}_{uuid.uuid4().hex[:8]}.md"
            path.write_text(text, encoding="utf-8")
        except Exception:
            logger.exception("compactor: failed to write summary file")


# 验证 LLM 返回的摘要结果（截断、格式、大小检查）
def _validate_summary(
    response: Any,
    counter: Any,
    original_estimate: int,
) -> CompactionResult | None:
    if response.stop_reason == "max_tokens":
        logger.warning("compactor: summary response truncated, skipping compaction")
        return None

    summary_text = response.text.strip()
    if not summary_text or not _summary_is_well_formed(summary_text):
        logger.warning("compactor: LLM returned invalid summary, skipping compaction")
        return None

    summary_tokens = response.usage.output_tokens if response.usage else counter.count(summary_text)
    if summary_tokens >= original_estimate:
        logger.warning(
            "compactor: summary not beneficial original=%d summary=%d, skipping compaction",
            original_estimate,
            summary_tokens,
        )
        return None

    return CompactionResult(
        summary_text=summary_text,
        original_token_estimate=original_estimate,
        summary_tokens=summary_tokens,
    )


# 将消息列表序列化为可供 LLM 阅读的纯文本
def _messages_to_text(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(f"[{role}]\n{content}")
        elif isinstance(content, list):
            blocks: list[str] = []
            for block in content:
                btype = block.get("type", "")
                if btype == "text":
                    blocks.append(block.get("text", ""))
                elif btype == "tool_use":
                    blocks.append(
                        f"<tool_call name={block.get('name')} id={block.get('id')}>\n"
                        f"{block.get('input', {})}\n</tool_call>"
                    )
                elif btype == "tool_result":
                    error_prefix = "[ERROR] " if block.get("is_error") else ""
                    blocks.append(
                        f"<tool_result id={block.get('tool_use_id')}>\n"
                        f"{error_prefix}{block.get('content', '')}\n</tool_result>"
                    )
                elif btype == "thinking":
                    blocks.append(f"<thinking>\n{block.get('thinking', '')}\n</thinking>")
            parts.append(f"[{role}]\n" + "\n".join(blocks))
    return "\n\n".join(parts)
