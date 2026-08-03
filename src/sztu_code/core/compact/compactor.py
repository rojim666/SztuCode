from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sztu_code.core.bus.events import ContextCompactedEvent, ContextCompactingEvent
from sztu_code.core.events.bus import EventBus

if TYPE_CHECKING:
    from sztu_code.core.context import ExecutionContext
    from sztu_code.core.llm.base import LLMProvider

logger = logging.getLogger(__name__)


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


_COMPACT_PROMPT = """\
You are compressing an agent conversation into a handoff summary.
Another LLM instance will continue this task from your summary alone — make it complete.

Structure your response with exactly these six sections:

## 1. Original Goal
One sentence describing what the user asked the agent to accomplish.

## 2. Completed Steps
Bullet list of what has been done. Be specific (file paths, commands run, decisions made).

## 3. Key Constraints & Discoveries
Facts learned during the run that affect future decisions \
(e.g., API limitations, file formats, user preferences stated mid-conversation).

## 4. Current File State
For each file that was created or modified: path, a one-line description of its current state.

## 5. Remaining TODOs
Ordered list of what still needs to be done to complete the original goal.

## 6. Critical Data
Any values the next LLM needs verbatim: IDs, tokens, exact error messages, config values \
discovered during the run.

Be concise. Omit reasoning steps and intermediate attempts. Keep conclusions.\
"""


# 返回当前 UTC 时间的简短时间戳字符串（用于文件名）
def _summary_is_well_formed(summary: str) -> bool:
    return bool(
        re.search(r"^##\s*1\.\s*Original Goal", summary, re.MULTILINE)
        and summary.count("## ") >= 2
    )


def _ts_compact() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


# 返回当前 UTC 时间的 ISO 8601 字符串
def _now() -> str:
    return datetime.now(UTC).isoformat()


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

    # 压缩 ExecutionContext.messages，就地替换消息列表并写 summary 文件
    async def compact(
        self,
        context: ExecutionContext,
        provider: LLMProvider,
        focus: str = "",
    ) -> CompactionResult | None:
        await self.notify_compacting(context.run_id)
        result = await self.compact_messages(context.messages, provider, focus=focus)
        if result is None:
            return None

        context.messages = [
            {"role": "user", "content": _continuation_message(result.summary_text)},
            {"role": "assistant", "content": "Understood, I'll continue from this summary."},
        ]
        context.compacted = True
        await self.record_compaction(context.run_id, result)
        logger.info(
            "context compacted session=%s run=%s original≈%d summary=%d tokens",
            self._session_id, context.run_id,
            result.original_token_estimate, result.summary_tokens,
        )
        return result

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

    # 纯函数式压缩：接收消息列表，返回 CompactionResult；失败时返回 None
    async def compact_messages(
        self,
        messages: list[dict[str, Any]],
        provider: LLMProvider,
        focus: str = "",
    ) -> CompactionResult | None:
        from sztu_code.core.events.bus import EventBus as _Bus

        history_text = _messages_to_text(messages)
        original_estimate = max(1, len(history_text) // 4)
        prompt = _COMPACT_PROMPT
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

        if response.stop_reason == "max_tokens":
            logger.warning("compactor: summary response truncated, skipping compaction")
            return None

        summary_text = response.text.strip()
        if not summary_text or not _summary_is_well_formed(summary_text):
            logger.warning("compactor: LLM returned invalid summary, skipping compaction")
            return None

        summary_tokens = response.usage.output_tokens if response.usage else len(summary_text) // 4
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

    # 将摘要文本写入 session 目录的 summary_<ts>.md
    def _write_summary(self, text: str) -> None:
        try:
            self._session_dir.mkdir(parents=True, exist_ok=True)
            path = self._session_dir / f"summary_{_ts_compact()}_{uuid.uuid4().hex[:8]}.md"
            path.write_text(text, encoding="utf-8")
        except Exception:
            logger.exception("compactor: failed to write summary file")


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
