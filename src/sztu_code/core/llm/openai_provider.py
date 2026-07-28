from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import httpx
from openai import AsyncOpenAI

from sztu_code.core.bus.events import LlmModelSelectedEvent, LlmTokenEvent, LlmUsageEvent
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import LlmResponse, ToolCallBlock, UsageStats

_DEFAULT_CONTEXT_WINDOW = 128_000

_MAX_STREAM_RETRIES = 3
_RETRY_BACKOFF_S = (1.0, 2.0, 4.0)

log = logging.getLogger(__name__)


# Return the conservative context window used for usage display.
def _context_window() -> int:
    return _DEFAULT_CONTEXT_WINDOW


_SYSTEM_PROMPT = (
    "You are a helpful AI assistant. "
    "Use the available tools to complete the user's goal. "
    "When the goal is fully achieved, respond with a final answer and do not call any more tools."
)


# 返回当前 UTC 时间的 ISO 8601 字符串
def _now() -> str:
    return datetime.now(UTC).isoformat()


# 将 Anthropic 格式的 messages 转换为 OpenAI messages 列表，system prompt 单独返回
def _anth_to_openai_messages(
    messages: list[dict[str, object]],
    system: str | None = None,
) -> list[dict[str, object]]:
    openai_msgs: list[dict[str, object]] = []

    # system prompt 作为第一条消息
    effective_system = system or _SYSTEM_PROMPT
    openai_msgs.append({"role": "system", "content": effective_system})

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "user":
            if isinstance(content, str):
                openai_msgs.append({"role": "user", "content": content})
            elif isinstance(content, list):
                text_parts: list[str] = []
                tool_msgs: list[dict[str, object]] = []
                for block in content:
                    btype = block.get("type", "")
                    if btype == "text":
                        text_parts.append(str(block.get("text", "")))
                    elif btype == "tool_result":
                        tc_id = str(block.get("tool_use_id", ""))
                        tc_content = str(block.get("content", ""))
                        if block.get("is_error"):
                            tc_content = "[ERROR] " + tc_content
                        tool_msgs.append(
                            {"role": "tool", "tool_call_id": tc_id, "content": tc_content}
                        )
                if text_parts:
                    openai_msgs.append({"role": "user", "content": "\n".join(text_parts)})
                openai_msgs.extend(tool_msgs)

        elif role == "assistant":
            if isinstance(content, str):
                openai_msgs.append({"role": "assistant", "content": content})
            elif isinstance(content, list):
                assistant_text: list[str] = []
                tool_calls: list[dict[str, object]] = []
                for block in content:
                    btype = block.get("type", "")
                    if btype == "text":
                        assistant_text.append(str(block.get("text", "")))
                    elif btype == "tool_use":
                            inp_json = json.dumps(block.get("input", {}), ensure_ascii=False)
                            tool_calls.append(
                                {
                                    "id": str(block.get("id", "")),
                                    "type": "function",
                                    "function": {
                                        "name": str(block.get("name", "")),
                                        "arguments": inp_json,
                                    },
                                }
                            )
                    # thinking 块在 OpenAI 请求中跳过，不需要传回
                assistant_msg: dict[str, object] = {"role": "assistant"}
                if assistant_text:
                    assistant_msg["content"] = "\n".join(assistant_text)
                else:
                    assistant_msg["content"] = None
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                openai_msgs.append(assistant_msg)

    return openai_msgs


# 将 Anthropic 格式的 tool_schemas 转换为 OpenAI tools 格式
def _anth_to_openai_tools(
    tool_schemas: list[dict[str, object]],
) -> list[dict[str, object]]:
    tools: list[dict[str, object]] = []
    for ts in tool_schemas:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": ts.get("name", ""),
                    "description": ts.get("description", ""),
                    "parameters": ts.get("input_schema", {"type": "object", "properties": {}}),
                },
            }
        )
    return tools


# 将 OpenAI finish_reason 映射为 Anthropic stop_reason
def _map_finish_reason(finish_reason: str | None) -> str:
    if finish_reason == "tool_calls":
        return "tool_use"
    elif finish_reason == "length":
        return "max_tokens"
    elif finish_reason == "stop":
        return "end_turn"
    elif finish_reason == "content_filter":
        return "end_turn"
    return "end_turn"


class OpenAIProvider:
    # 初始化 OpenAI 客户端；client 可在测试时注入以跳过 API key 检查
    def __init__(self, model: str, client: Any = None) -> None:
        if client is None:
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise SystemExit("OPENAI_API_KEY not set")
            base_url = os.environ.get("OPENAI_BASE_URL")
            client_kwargs: dict[str, Any] = {"api_key": api_key}
            if base_url:
                client_kwargs["base_url"] = base_url
            self._client: Any = AsyncOpenAI(**client_kwargs)
        else:
            self._client = client
        self._model = model

    # 流式调用 OpenAI 兼容 API，逐 token 发布事件并返回 LlmResponse；网络中断时自动重试
    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> LlmResponse:
        await bus.publish(
            LlmModelSelectedEvent(run_id=run_id, model=self._model, strategy="static", ts=_now())
        )

        openai_msgs = _anth_to_openai_messages(messages, system=system)
        tools = _anth_to_openai_tools(tool_schemas) if tool_schemas else None

        text_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_call_accum: dict[int, dict[str, object]] = {}
        final_finish_reason: str | None = None
        final_usage: Any = None

        for attempt in range(1, _MAX_STREAM_RETRIES + 1):
            text_parts = []
            thinking_parts = []
            tool_call_accum = {}
            final_finish_reason = None
            final_usage = None

            try:
                kwargs: dict[str, object] = {
                    "model": self._model,
                    "messages": openai_msgs,
                    "stream": True,
                }
                if tools:
                    kwargs["tools"] = tools

                stream = await self._client.chat.completions.create(**kwargs)
                async for chunk in stream:
                    if chunk.usage is not None:
                        final_usage = chunk.usage

                    if not chunk.choices:
                        continue

                    choice = chunk.choices[0]
                    delta = choice.delta

                    if delta is None:
                        continue

                    # DeepSeek reasoner 的推理内容
                    reasoning: str | None = getattr(delta, "reasoning_content", None)
                    if reasoning:
                        thinking_parts.append(reasoning)
                        continue

                    # 普通文本内容
                    if delta.content:
                        if attempt == 1:
                            await bus.publish(
                                LlmTokenEvent(run_id=run_id, token=delta.content, ts=_now())
                            )
                        text_parts.append(delta.content)

                    # 工具调用增量
                    if delta.tool_calls:
                        for tc_delta in delta.tool_calls:
                            idx = tc_delta.index
                            if idx not in tool_call_accum:
                                tool_call_accum[idx] = {
                                    "id": "",
                                    "name": "",
                                    "arguments": "",
                                }
                            acc = tool_call_accum[idx]
                            if tc_delta.id:
                                acc["id"] = tc_delta.id
                            if tc_delta.function:
                                if tc_delta.function.name:
                                    acc["name"] = tc_delta.function.name
                                if tc_delta.function.arguments:
                                    acc["arguments"] += tc_delta.function.arguments

                    if choice.finish_reason is not None:
                        final_finish_reason = choice.finish_reason

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

        # 构建 usage 统计
        input_tokens = 0
        output_tokens = 0
        cache_read = 0
        if final_usage is not None:
            input_tokens = getattr(final_usage, "prompt_tokens", 0) or 0
            output_tokens = getattr(final_usage, "completion_tokens", 0) or 0
            prompt_details = getattr(final_usage, "prompt_tokens_details", None)
            if prompt_details is not None:
                cache_read = getattr(prompt_details, "cached_tokens", 0) or 0

        context_pct = input_tokens / _context_window() if input_tokens > 0 else 0.0

        await bus.publish(
            LlmUsageEvent(
                run_id=run_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_input_tokens=cache_read,
                cache_creation_input_tokens=0,
                context_pct=context_pct,
                model=self._model,
                ts=_now(),
            )
        )

        # 解析工具调用
        tool_calls: list[ToolCallBlock] = []
        for idx in sorted(tool_call_accum.keys()):
            acc = tool_call_accum[idx]
            try:
                args_str = str(acc["arguments"])
                inp = json.loads(args_str) if args_str else {}
            except json.JSONDecodeError:
                inp = {}
            tool_calls.append(
                ToolCallBlock(
                    id=str(acc["id"]),
                    name=str(acc["name"]),
                    input=inp,
                )
            )

        # 构建 thinking blocks（DeepSeek reasoner）
        thinking_blocks: list[dict[str, object]] = []
        if thinking_parts:
            thinking_text = "".join(thinking_parts)
            thinking_blocks.append(
                {"type": "thinking", "thinking": thinking_text, "signature": ""}
            )

        stop_reason = _map_finish_reason(final_finish_reason)

        return LlmResponse(
            stop_reason=stop_reason,
            tool_calls=tool_calls,
            text="".join(text_parts),
            thinking_blocks=thinking_blocks,
            usage=UsageStats(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_input_tokens=cache_read,
                cache_creation_input_tokens=0,
                context_pct=context_pct,
            ),
        )
