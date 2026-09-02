from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Any

import anthropic
import httpx

from sztu_code.core.bus.events import (
    LlmModelSelectedEvent,
    LlmThinkingEvent,
    LlmTokenEvent,
    LlmUsageEvent,
)
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import LlmResponse, ToolCallBlock, UsageStats

_DEFAULT_CONTEXT_WINDOW = 128_000

_KNOWN_CONTEXT_WINDOWS: list[tuple[str, int]] = [
    ("gpt-4.1-mini", 1_000_000),
    ("gpt-4.1-nano", 1_000_000),
    ("gpt-4.1", 1_000_000),
    ("gpt-4o", 128_000),
    ("gpt-4", 128_000),
    ("o1", 200_000),
    ("o3", 200_000),
    ("deepseek-reasoner", 64_000),
    ("deepseek-chat", 64_000),
    ("claude", 200_000),
]

_MAX_STREAM_RETRIES = 3
_RETRY_BACKOFF_S = (1.0, 2.0, 4.0)

log = logging.getLogger(__name__)


# Return the context window used for usage display and compaction thresholds.
def _context_window(model: str, override: int = 0) -> int:
    if override > 0:
        return override
    normalized = model.lower()
    for prefix, window in _KNOWN_CONTEXT_WINDOWS:
        if normalized.startswith(prefix):
            return window
    return _DEFAULT_CONTEXT_WINDOW


_SYSTEM_PROMPT = (
    "You are a helpful AI assistant. "
    "Use the available tools to complete the user's goal. "
    "When the goal is fully achieved, respond with a final answer and do not call any more tools."
)


# 在消息列表中扫描摘要确认消息，放置 cache_control 断点
# 借鉴 Claude Code：摘要 ack 消息上的 cache_control 使前缀稳定可缓存
# 缓存前缀 = [system + summary_user + summary_ack + 历史摘要]
def _annotate_cache_control(messages: list[dict[str, object]]) -> None:
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "text":
                continue
            text = block.get("text", "")
            if isinstance(text, str) and "Understood" in text:
                # 放置 cache_control 断点 — 使此前所有内容可被 API 缓存
                block["cache_control"] = {"type": "ephemeral"}
                return


# 返回当前 UTC 时间的 ISO 8601 字符串
def _now() -> str:
    return datetime.now(UTC).isoformat()


class AnthropicProvider:
    # 初始化 Anthropic 客户端；client 可在测试时注入以跳过 API key 检查
    def __init__(
        self,
        model: str,
        client: Any = None,
        *,
        context_window: int = 0,
        max_output_tokens: int = 8192,
        temperature: float | None = None,
        top_p: float | None = None,
        reasoning_effort: str = "",
        timeout_s: float = 120.0,
        max_retries: int = 2,
        cache_control: bool = True,
    ) -> None:
        if client is None:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise SystemExit("ANTHROPIC_API_KEY not set")
            base_url = os.environ.get("ANTHROPIC_BASE_URL")
            kwargs: dict[str, Any] = {
                "api_key": api_key,
                "timeout": timeout_s,
                "max_retries": max_retries,
            }
            if base_url:
                kwargs["base_url"] = base_url
            self._client: Any = anthropic.AsyncAnthropic(**kwargs)
        else:
            self._client = client
        self._model = model
        self._context_window_override = context_window
        self._max_output_tokens = max_output_tokens
        self._temperature = temperature
        self._top_p = top_p
        self._reasoning_effort = reasoning_effort
        self._cache_control = cache_control

    # 流式调用 Anthropic API，逐 token 发布事件并返回 LlmResponse；网络中断时自动重试
    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
        usage_estimator: Any | None = None,
    ) -> LlmResponse:
        await bus.publish(
            LlmModelSelectedEvent(run_id=run_id, model=self._model, strategy="static", ts=_now())
        )

        system_block: dict[str, object] = {
            "type": "text",
            "text": system or _SYSTEM_PROMPT,
        }
        if self._cache_control:
            system_block["cache_control"] = {"type": "ephemeral"}
        system_blocks: list[dict[str, object]] = [system_block]

        tools: list[dict[str, object]] = list(tool_schemas)
        if self._cache_control and tools:
            last = dict(tools[-1])
            last["cache_control"] = {"type": "ephemeral"}
            tools = tools[:-1] + [last]

        # 扫描消息列表，在摘要确认消息上放置 cache_control 断点
        # 使 [system + summary_user + summary_ack] 前缀可被 API 缓存
        if self._cache_control:
            _annotate_cache_control(messages)

        kwargs: dict[str, object] = {
            "model": self._model,
            "max_tokens": self._max_output_tokens,
            "system": system_blocks,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        if self._temperature is not None:
            kwargs["temperature"] = self._temperature
        if self._top_p is not None:
            kwargs["top_p"] = self._top_p
        if self._reasoning_effort:
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": self._reasoning_effort}

        text_parts: list[str] = []
        final_message: Any = None
        thinking_published = False

        for attempt in range(1, _MAX_STREAM_RETRIES + 1):
            text_parts = []
            try:
                async with self._client.messages.stream(**kwargs) as stream:
                    async for event in stream:
                        if getattr(event, "type", "") != "content_block_delta":
                            continue
                        delta = getattr(event, "delta", None)
                        delta_type = getattr(delta, "type", "")
                        if delta_type == "text_delta":
                            text = str(getattr(delta, "text", ""))
                            if not text:
                                continue
                            # Only publish first-attempt events to avoid UI duplicates.
                            if attempt == 1:
                                await bus.publish(
                                    LlmTokenEvent(run_id=run_id, token=text, ts=_now())
                                )
                            text_parts.append(text)
                        elif delta_type == "thinking_delta":
                            thinking = str(getattr(delta, "thinking", ""))
                            if not thinking or attempt != 1:
                                continue
                            await bus.publish(
                                LlmThinkingEvent(
                                    run_id=run_id,
                                    step=step,
                                    thinking=thinking,
                                    ts=_now(),
                                )
                            )
                            thinking_published = True
                    final_message = await stream.get_final_message()
                break  # success
            except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError) as exc:
                if attempt == _MAX_STREAM_RETRIES:
                    log.error(
                        "stream failed after %d attempts run_id=%s step=%d: %s",
                        _MAX_STREAM_RETRIES, run_id, step, exc,
                    )
                    raise
                delay = _RETRY_BACKOFF_S[attempt - 1]
                log.warning(
                    "stream dropped (attempt %d/%d) run_id=%s step=%d: %s — retrying in %.0fs",
                    attempt, _MAX_STREAM_RETRIES, run_id, step, exc, delay,
                )
                await asyncio.sleep(delay)

        assert final_message is not None

        usage = final_message.usage
        cache_read: int = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_create: int = getattr(usage, "cache_creation_input_tokens", 0) or 0
        context_window = _context_window(self._model, self._context_window_override)
        # Anthropic 的 input_tokens 不含缓存部分（净输入）；上下文占用按全量 prompt
        # （净输入+缓存读+缓存写）计算——缓存命中部分同样占用上下文窗口
        total_prompt_tokens = usage.input_tokens + cache_read + cache_create
        context_pct = total_prompt_tokens / context_window
        from sztu_code.core.compact.context_usage import estimate_context_usage
        # 用原始（未加 cache_control 注解）tool_schemas 作增量键，跨调用内容稳定
        breakdown = estimate_context_usage(
            messages=messages, tool_schemas=tool_schemas, system=system or _SYSTEM_PROMPT,
            actual_input_tokens=total_prompt_tokens, context_window=context_window,
            reserved_output_tokens=self._max_output_tokens,
            incremental=usage_estimator,
        )

        await bus.publish(
            LlmUsageEvent(
                run_id=run_id,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_input_tokens=cache_read,
                cache_creation_input_tokens=cache_create,
                context_pct=context_pct,
                model=self._model,
                **breakdown.__dict__,
                ts=_now(),
            )
        )

        tool_calls: list[ToolCallBlock] = []
        thinking_blocks: list[dict[str, object]] = []
        for block in final_message.content:
            if block.type == "tool_use":
                tool_calls.append(
                    ToolCallBlock(id=block.id, name=block.name, input=dict(block.input))
                )
            elif block.type == "thinking":
                # thinking blocks must be passed back verbatim in subsequent requests
                thinking_blocks.append(
                    {
                        "type": "thinking",
                        "thinking": block.thinking,
                        "signature": block.signature,
                    }
                )

        # Older/custom Anthropic-compatible endpoints may not expose thinking_delta.
        # Fall back to the final block only when no live thinking was published.
        if thinking_blocks and not thinking_published:
            await bus.publish(
                LlmThinkingEvent(
                    run_id=run_id,
                    step=step,
                    thinking="\n\n".join(str(block["thinking"]) for block in thinking_blocks),
                    ts=_now(),
                )
            )
        return LlmResponse(
            stop_reason=final_message.stop_reason or "end_turn",
            tool_calls=tool_calls,
            text="".join(text_parts),
            thinking_blocks=thinking_blocks,
            usage=UsageStats(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_input_tokens=cache_read,
                cache_creation_input_tokens=cache_create,
                context_pct=context_pct,
            ),
        )
