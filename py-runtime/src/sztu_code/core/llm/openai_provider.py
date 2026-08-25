from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import openai
from openai import AsyncOpenAI

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
    ("deepseek-v4-", 1_000_000),
    ("gpt-4.1-mini", 1_000_000),
    ("gpt-4.1-nano", 1_000_000),
    ("gpt-4.1", 1_000_000),
    ("gpt-4o", 128_000),
    ("gpt-4", 128_000),
    ("o1", 200_000),
    ("o3", 200_000),
    ("deepseek-reasoner", 64_000),
    ("deepseek-chat", 64_000),
]

_MAX_STREAM_RETRIES = 3
_RETRY_BACKOFF_S = (1.0, 2.0, 4.0)
# 限流/服务过载（429/503/5xx）用更长的退避
_RATE_LIMIT_BACKOFF_S = (5.0, 10.0, 20.0)

log = logging.getLogger(__name__)


# 单次流式调用的累积结果：文本、推理片段、工具调用增量、结束原因与 usage
@dataclass
class _StreamResult:
    text_parts: list[str] = field(default_factory=list)
    thinking_parts: list[str] = field(default_factory=list)
    tool_call_accum: dict[int, dict[str, object]] = field(default_factory=dict)
    finish_reason: str | None = None
    usage: Any = None


# 返回用于用量展示与压缩阈值的上下文窗口大小
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


# 返回当前 UTC 时间的 ISO 8601 字符串
def _now() -> str:
    return datetime.now(UTC).isoformat()


# 构建带可选 cache 断点的 system 消息
def _system_message(system: str | None, cache_control: bool) -> dict[str, object]:
    msg: dict[str, object] = {"role": "system", "content": system or _SYSTEM_PROMPT}
    if cache_control:
        msg["cache_control"] = {"type": "ephemeral"}
    return msg


# 将 Anthropic image 块转换为 OpenAI image_url 块；缺少素材时返回 None
def _image_block_to_openai(block: dict[str, object]) -> dict[str, object] | None:
    source = block.get("source", {})
    if not isinstance(source, dict):
        return None
    media_type = str(source.get("media_type", ""))
    data = str(source.get("data", ""))
    if not (media_type and data):
        return None
    return {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{data}"}}


# 追加 tool_result 块：文本历史模式并入文本，否则生成 role=tool 消息
def _append_tool_result(
    block: dict[str, object],
    tool_names: dict[str, str],
    text_tool_history: bool,
    text_parts: list[str],
    tool_msgs: list[dict[str, object]],
) -> None:
    tc_id = str(block.get("tool_use_id", ""))
    tc_content = str(block.get("content", ""))
    if block.get("is_error"):
        tc_content = "[ERROR] " + tc_content
    if text_tool_history:
        tool_name = tool_names.get(tc_id, tc_id or "unknown")
        text_parts.append(f"[Tool result for {tool_name}]\n{tc_content}")
    else:
        tool_msgs.append({"role": "tool", "tool_call_id": tc_id, "content": tc_content})


# 解析 user 消息的块列表，返回文本、图片与 tool 结果三部分
def _parse_user_blocks(
    blocks: list[dict[str, object]],
    tool_names: dict[str, str],
    text_tool_history: bool,
) -> tuple[list[str], list[dict[str, object]], list[dict[str, object]]]:
    text_parts: list[str] = []
    image_parts: list[dict[str, object]] = []
    tool_msgs: list[dict[str, object]] = []
    for block in blocks:
        btype = block.get("type", "")
        if btype == "text":
            text_parts.append(str(block.get("text", "")))
        elif btype == "image":
            image = _image_block_to_openai(block)
            if image is not None:
                image_parts.append(image)
        elif btype == "tool_result":
            _append_tool_result(block, tool_names, text_tool_history, text_parts, tool_msgs)
    return text_parts, image_parts, tool_msgs


# 追加一条 user 消息：字符串直接输出，块列表拆分为 user + tool 消息
def _append_user_message(
    openai_msgs: list[dict[str, object]],
    content: object,
    tool_names: dict[str, str],
    text_tool_history: bool,
) -> None:
    if isinstance(content, str):
        openai_msgs.append({"role": "user", "content": content})
        return
    if not isinstance(content, list):
        return
    text_parts, image_parts, tool_msgs = _parse_user_blocks(
        content, tool_names, text_tool_history
    )
    if image_parts:
        # OpenAI 多模态要求 content 为数组：text + image_url
        user_content: list[dict[str, object]] = []
        if text_parts:
            user_content.append({"type": "text", "text": "\n".join(text_parts)})
        user_content.extend(image_parts)
        openai_msgs.append({"role": "user", "content": user_content})
    elif text_parts:
        openai_msgs.append({"role": "user", "content": "\n".join(text_parts)})
    openai_msgs.extend(tool_msgs)


# 提取 tool_use 块的 id、名称与 JSON 序列化参数
def _tool_use_parts(block: dict[str, object]) -> tuple[str, str, str]:
    tool_id = str(block.get("id", ""))
    tool_name = str(block.get("name", ""))
    args_json = json.dumps(block.get("input", {}), ensure_ascii=False)
    return tool_id, tool_name, args_json


# 解析 assistant 消息的块列表，返回文本、推理内容与 OpenAI tool_calls
def _parse_assistant_blocks(
    blocks: list[dict[str, object]],
    tool_names: dict[str, str],
    text_tool_history: bool,
) -> tuple[list[str], list[str], list[dict[str, object]]]:
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[dict[str, object]] = []
    for block in blocks:
        btype = block.get("type", "")
        if btype == "text":
            text_parts.append(str(block.get("text", "")))
        elif btype == "thinking":
            # DeepSeek 推理模型要求把 reasoning_content 原样传回
            thinking = str(block.get("thinking", ""))
            if thinking:
                reasoning_parts.append(thinking)
        elif btype == "tool_use":
            tool_id, tool_name, args_json = _tool_use_parts(block)
            tool_names[tool_id] = tool_name
            if text_tool_history:
                text_parts.append(f"[Tool call] {tool_name}({args_json})")
            else:
                tool_calls.append(
                    {
                        "id": tool_id,
                        "type": "function",
                        "function": {"name": tool_name, "arguments": args_json},
                    }
                )
    return text_parts, reasoning_parts, tool_calls


# 追加一条 assistant 消息：块列表解析为文本/推理内容/tool_calls
def _append_assistant_message(
    openai_msgs: list[dict[str, object]],
    content: object,
    tool_names: dict[str, str],
    text_tool_history: bool,
) -> None:
    if isinstance(content, str):
        openai_msgs.append({"role": "assistant", "content": content})
        return
    if not isinstance(content, list):
        return
    text_parts, reasoning_parts, tool_calls = _parse_assistant_blocks(
        content, tool_names, text_tool_history
    )
    assistant_msg: dict[str, object] = {"role": "assistant"}
    assistant_msg["content"] = "\n".join(text_parts) if text_parts else None
    if reasoning_parts:
        assistant_msg["reasoning_content"] = "".join(reasoning_parts)
    if tool_calls:
        assistant_msg["tool_calls"] = tool_calls
    openai_msgs.append(assistant_msg)


# 将 Anthropic 格式的 messages 转换为 OpenAI messages 列表，system prompt 单独返回
def _anth_to_openai_messages(
    messages: list[dict[str, object]],
    system: str | None = None,
    *,
    text_tool_history: bool = False,
    cache_control: bool = False,
) -> list[dict[str, object]]:
    openai_msgs = [_system_message(system, cache_control)]
    tool_names: dict[str, str] = {}
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            _append_user_message(openai_msgs, content, tool_names, text_tool_history)
        elif role == "assistant":
            _append_assistant_message(openai_msgs, content, tool_names, text_tool_history)
    return openai_msgs


# 将 Anthropic 格式的 tool_schemas 转换为 OpenAI tools 格式
def _anth_to_openai_tools(
    tool_schemas: list[dict[str, object]],
    *,
    cache_control: bool = False,
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
    # 在最后一个 tool 上打 cache 断点，使工具定义作为稳定前缀被缓存
    if cache_control and tools:
        last = dict(tools[-1])
        last["cache_control"] = {"type": "ephemeral"}
        tools = tools[:-1] + [last]
    return tools


_FINISH_REASON_MAP = {
    "tool_calls": "tool_use",
    "length": "max_tokens",
    "stop": "end_turn",
    "content_filter": "end_turn",
}


# 将 OpenAI finish_reason 映射为 Anthropic stop_reason
def _map_finish_reason(finish_reason: str | None) -> str:
    if finish_reason is None:
        return "end_turn"
    return _FINISH_REASON_MAP.get(finish_reason, "end_turn")


# 去掉 Authorization 头的 httpx transport，用于免 key 的 OpenAI 兼容端点（如 opencode Zen 免费模型）
class _StripAuthTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner: httpx.AsyncHTTPTransport) -> None:
        self._inner = inner

    # 发送请求前移除 Authorization 头，其余原样转发
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        request.headers.pop("Authorization", None)
        return await self._inner.handle_async_request(request)


# 构建免 key 模式使用的 httpx 客户端（内部用去 auth 的 transport）
def _keyless_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=_StripAuthTransport(httpx.AsyncHTTPTransport()))


# 累积单个 tool_call delta 到按 index 分组的字典
def _accumulate_tool_call(
    tool_call_accum: dict[int, dict[str, object]],
    tc_delta: Any,
) -> None:
    idx = tc_delta.index
    if idx not in tool_call_accum:
        tool_call_accum[idx] = {"id": "", "name": "", "arguments": ""}
    acc = tool_call_accum[idx]
    if tc_delta.id:
        acc["id"] = tc_delta.id
    if tc_delta.function:
        if tc_delta.function.name:
            acc["name"] = tc_delta.function.name
        if tc_delta.function.arguments:
            acc["arguments"] += tc_delta.function.arguments


# 消费单个流式 chunk，更新累积结果；首次尝试时发布增量事件
async def _consume_chunk(
    chunk: Any,
    result: _StreamResult,
    bus: EventBus,
    run_id: str,
    step: int,
    attempt: int,
) -> None:
    if chunk.usage is not None:
        result.usage = chunk.usage
    if not chunk.choices:
        return

    choice = chunk.choices[0]
    delta = choice.delta
    if delta is None:
        return

    # DeepSeek reasoner 的推理内容
    reasoning: str | None = getattr(delta, "reasoning_content", None)
    if reasoning:
        result.thinking_parts.append(reasoning)
        if attempt == 1:
            await bus.publish(
                LlmThinkingEvent(run_id=run_id, step=step, thinking=reasoning, ts=_now())
            )
        return

    # 普通文本内容
    if delta.content:
        if attempt == 1:
            await bus.publish(LlmTokenEvent(run_id=run_id, token=delta.content, ts=_now()))
        result.text_parts.append(delta.content)

    # 工具调用增量
    if delta.tool_calls:
        for tc_delta in delta.tool_calls:
            _accumulate_tool_call(result.tool_call_accum, tc_delta)

    if choice.finish_reason is not None:
        result.finish_reason = choice.finish_reason


# 将按 index 累积的工具调用增量解析为 ToolCallBlock 列表
def _parse_tool_calls(tool_call_accum: dict[int, dict[str, object]]) -> list[ToolCallBlock]:
    tool_calls: list[ToolCallBlock] = []
    for idx in sorted(tool_call_accum.keys()):
        acc = tool_call_accum[idx]
        args_str = str(acc["arguments"])
        try:
            inp = json.loads(args_str) if args_str else {}
        except json.JSONDecodeError:
            inp = {}
        tool_calls.append(ToolCallBlock(id=str(acc["id"]), name=str(acc["name"]), input=inp))
    return tool_calls


# 将累积的推理片段合并为 thinking block（DeepSeek reasoner）
def _thinking_blocks(thinking_parts: list[str]) -> list[dict[str, object]]:
    if not thinking_parts:
        return []
    return [{"type": "thinking", "thinking": "".join(thinking_parts), "signature": ""}]


# 从最终 usage 对象提取输入/输出 token 数与缓存命中数
def _usage_from_final(final_usage: Any) -> tuple[int, int, int]:
    if final_usage is None:
        return 0, 0, 0
    input_tokens: int = getattr(final_usage, "prompt_tokens", 0) or 0
    output_tokens: int = getattr(final_usage, "completion_tokens", 0) or 0
    cache_read: int = 0
    prompt_details = getattr(final_usage, "prompt_tokens_details", None)
    if prompt_details is not None:
        cache_read = getattr(prompt_details, "cached_tokens", 0) or 0
    if not cache_read:
        # DeepSeek 兼容 API 用顶层 prompt_cache_hit_tokens 上报缓存命中
        top_level_hit = getattr(final_usage, "prompt_cache_hit_tokens", 0)
        if isinstance(top_level_hit, int):
            cache_read = top_level_hit
    return input_tokens, output_tokens, cache_read


class OpenAIProvider:
    # 初始化 OpenAI 客户端；client 可在测试时注入以跳过 API key 检查
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
        base_url = os.environ.get("OPENAI_BASE_URL")
        is_campus_deepseek = bool(
            model == "deepseek-v4-pro"
            and base_url
            and "apiai.sztu.edu.cn" in base_url.lower()
        )
        if client is None:
            api_key = os.environ.get("OPENAI_API_KEY") or ""
            if not api_key and not base_url:
                raise SystemExit("OPENAI_API_KEY not set (或设置 OPENAI_BASE_URL 使用免 key 端点)")
            client_kwargs: dict[str, Any] = {
                "api_key": api_key or "keyless-placeholder",
                "timeout": timeout_s,
                "max_retries": max_retries,
            }
            if base_url:
                client_kwargs["base_url"] = base_url
            client_kwargs["http_client"] = httpx.AsyncClient(trust_env=False)
            if not api_key:
                # 免 key 端点：SDK 需要非空 key，但用自定义 transport 剥掉 Authorization 头
                client_kwargs["http_client"] = _keyless_http_client()
            self._client: Any = AsyncOpenAI(**client_kwargs)
        else:
            self._client = client
        self._model = model
        self._text_tool_history = is_campus_deepseek
        self._context_window_override = context_window
        self._max_output_tokens = max_output_tokens
        self._temperature = temperature
        self._top_p = top_p
        self._reasoning_effort = reasoning_effort
        self._cache_control = cache_control

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

        openai_msgs = _anth_to_openai_messages(
            messages,
            system=system,
            text_tool_history=self._text_tool_history,
            cache_control=self._cache_control,
        )
        tools = (
            _anth_to_openai_tools(tool_schemas, cache_control=self._cache_control)
            if tool_schemas else None
        )

        acc = await self._stream_with_retries(openai_msgs, tools, bus, run_id, step)

        input_tokens, output_tokens, cache_read = _usage_from_final(acc.usage)
        context_window = _context_window(self._model, self._context_window_override)
        context_pct = input_tokens / context_window if input_tokens > 0 else 0.0

        from sztu_code.core.compact.context_usage import estimate_context_usage
        breakdown = estimate_context_usage(
            messages=messages, tool_schemas=tools or [], system=system or _SYSTEM_PROMPT,
            actual_input_tokens=input_tokens, context_window=context_window,
            reserved_output_tokens=self._max_output_tokens,
        )

        await bus.publish(
            LlmUsageEvent(
                run_id=run_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_input_tokens=cache_read,
                cache_creation_input_tokens=0,
                context_pct=context_pct,
                model=self._model,
                **breakdown.__dict__,
                ts=_now(),
            )
        )

        return LlmResponse(
            stop_reason=_map_finish_reason(acc.finish_reason),
            tool_calls=_parse_tool_calls(acc.tool_call_accum),
            text="".join(acc.text_parts),
            thinking_blocks=_thinking_blocks(acc.thinking_parts),
            usage=UsageStats(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_input_tokens=cache_read,
                cache_creation_input_tokens=0,
                context_pct=context_pct,
            ),
        )

    # 带退避重试的流式调用：网络中断与限流错误按各自策略重试
    async def _stream_with_retries(
        self,
        openai_msgs: list[dict[str, object]],
        tools: list[dict[str, object]] | None,
        bus: EventBus,
        run_id: str,
        step: int,
    ) -> _StreamResult:
        for attempt in range(1, _MAX_STREAM_RETRIES + 1):
            try:
                return await self._stream_once(openai_msgs, tools, bus, run_id, step, attempt)
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
            except openai.APIError as exc:
                # 免费档限流/过载（429/503/5xx）带更长退避重试；其余 API 错误（401 等）直接抛
                status = getattr(exc, "status_code", None)
                retryable = status in (429, 503) or (status is not None and status >= 500)
                if not retryable or attempt == _MAX_STREAM_RETRIES:
                    raise
                delay = _RATE_LIMIT_BACKOFF_S[attempt - 1]
                log.warning(
                    "LLM transient API error status=%s (attempt %d/%d) "
                    "run_id=%s: %s — retry in %.0fs",
                    status, attempt, _MAX_STREAM_RETRIES, run_id, exc, delay,
                )
                await asyncio.sleep(delay)
        raise RuntimeError("unreachable: 重试循环必然以 return 或 raise 结束")

    # 执行单次流式请求并累积 chunk 数据，返回当次累积结果
    async def _stream_once(
        self,
        openai_msgs: list[dict[str, object]],
        tools: list[dict[str, object]] | None,
        bus: EventBus,
        run_id: str,
        step: int,
        attempt: int,
    ) -> _StreamResult:
        kwargs = self._request_kwargs(openai_msgs, tools)
        stream = await self._client.chat.completions.create(**kwargs)
        result = _StreamResult()
        async for chunk in stream:
            await _consume_chunk(chunk, result, bus, run_id, step, attempt)
        return result

    # 构建单次请求参数（模型、消息、流式选项与可选采样参数）
    def _request_kwargs(
        self,
        openai_msgs: list[dict[str, object]],
        tools: list[dict[str, object]] | None,
    ) -> dict[str, object]:
        kwargs: dict[str, object] = {
            "model": self._model,
            "messages": openai_msgs,
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_completion_tokens": self._max_output_tokens,
        }
        if self._temperature is not None:
            kwargs["temperature"] = self._temperature
        if self._top_p is not None:
            kwargs["top_p"] = self._top_p
        if self._reasoning_effort:
            kwargs["reasoning_effort"] = self._reasoning_effort
        if tools:
            kwargs["tools"] = tools
        return kwargs
