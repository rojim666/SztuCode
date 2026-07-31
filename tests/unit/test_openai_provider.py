from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.openai_provider import (
    OpenAIProvider,
    _anth_to_openai_messages,
    _anth_to_openai_tools,
    _map_finish_reason,
)
from sztu_code.core.llm.types import LlmResponse

# --- helpers -----------------------------------------------------------------


def _make_chunk(
    content: str | None = None,
    reasoning: str | None = None,
    tool_calls: list[dict[str, object]] | None = None,
    finish_reason: str | None = None,
    usage: MagicMock | None = None,
) -> MagicMock:
    """构建单个 OpenAI 流式 chunk"""
    chunk = MagicMock()
    chunk.usage = usage

    if content is None and reasoning is None and tool_calls is None and finish_reason is None:
        chunk.choices = []
        return chunk

    choice = MagicMock()
    choice.finish_reason = finish_reason

    delta = MagicMock()
    delta.content = content
    # reasoning_content 通过 getattr 访问，需要显式设置属性
    if reasoning is not None:
        delta.reasoning_content = reasoning
    else:
        delta.reasoning_content = None  # 显式设为 None 防止 MagicMock 自动创建

    if tool_calls is not None:
        tc_deltas = []
        for tc in tool_calls:
            tc_delta = MagicMock()
            tc_delta.index = tc.get("index", 0)
            tc_delta.id = tc.get("id")
            tc_delta.function = MagicMock()
            tc_delta.function.name = tc.get("name")
            tc_delta.function.arguments = tc.get("arguments", "")
            tc_deltas.append(tc_delta)
        delta.tool_calls = tc_deltas
    else:
        delta.tool_calls = None

    choice.delta = delta
    chunk.choices = [choice]
    return chunk


def _make_usage(
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    cached_tokens: int = 0,
) -> MagicMock:
    u = MagicMock()
    u.prompt_tokens = prompt_tokens
    u.completion_tokens = completion_tokens
    details = MagicMock()
    details.cached_tokens = cached_tokens
    u.prompt_tokens_details = details
    return u


class FakeStream:
    """Minimal async iterator that fakes the OpenAI streaming interface."""

    def __init__(self, chunks: list[MagicMock]) -> None:
        self._chunks = chunks

    def __aiter__(self) -> FakeStream:
        return self

    async def __anext__(self) -> MagicMock:
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


def _make_provider(
    chunks: list[MagicMock] | None = None,
    model: str = "test-model",
) -> tuple[OpenAIProvider, MagicMock]:
    client = MagicMock()
    stream = FakeStream(chunks or [])
    client.chat.completions.create = AsyncMock(return_value=stream)
    return OpenAIProvider(model=model, client=client), client


async def _chat(
    provider: OpenAIProvider,
    messages: list[dict[str, object]] | None = None,
    tool_schemas: list[dict[str, object]] | None = None,
) -> tuple[LlmResponse, list[BaseModel]]:
    collected: list[BaseModel] = []
    bus = EventBus()

    async def _collect(e: BaseModel) -> None:
        collected.append(e)

    bus.subscribe(_collect)
    result = await provider.chat(
        messages=messages or [],
        tool_schemas=tool_schemas or [],
        bus=bus,
        run_id="r1",
    )
    return result, collected


# --- message translation tests -----------------------------------------------


# 功能：验证纯文本 user/assistant 消息正确转换为 OpenAI 格式
# 设计：覆盖最简单的对话场景，检查 role 和 content 的逐字段映射
def test_simple_text_messages_translated() -> None:
    messages: list[dict[str, object]] = [
        {"role": "user", "content": [{"type": "text", "text": "hello"}]},
        {"role": "assistant", "content": [{"type": "text", "text": "hi!"}]},
    ]
    result = _anth_to_openai_messages(messages)
    # result[0] 是 system 消息
    assert result[1] == {"role": "user", "content": "hello"}
    assert result[2] == {"role": "assistant", "content": "hi!"}


# 功能：验证 tool_use 块被正确转换为 OpenAI tool_calls 数组格式
# 设计：检查 tool_calls 的 id、type、function.name、function.arguments，确保 JSON 序列化正确
def test_tool_use_translated_to_tool_calls() -> None:
    messages: list[dict[str, object]] = [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "t1", "name": "bash", "input": {"cmd": "ls"}},
            ],
        },
    ]
    result = _anth_to_openai_messages(messages)
    assistant_msg = result[1]
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["content"] is None
    tc = assistant_msg["tool_calls"][0]  # type: ignore[index]
    assert tc["id"] == "t1"
    assert tc["type"] == "function"
    assert tc["function"]["name"] == "bash"
    assert "ls" in tc["function"]["arguments"]


# 功能：验证 tool_result 块被正确转换为 role=tool 消息
# 设计：检查 tool_call_id 和 content 的映射，覆盖等值断言
def test_tool_result_translated_to_tool_role() -> None:
    messages: list[dict[str, object]] = [
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "file1\nfile2"},
            ],
        },
    ]
    result = _anth_to_openai_messages(messages)
    tool_msg = result[1]
    assert tool_msg["role"] == "tool"
    assert tool_msg["tool_call_id"] == "t1"
    assert tool_msg["content"] == "file1\nfile2"


# 功能：验证 is_error 的 tool_result 被加上 [ERROR] 前缀
# 设计：OpenAI 无原生错误标记，确认前缀作为替代方案正确添加
def test_tool_result_error_prefixed() -> None:
    messages: list[dict[str, object]] = [
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": "command not found",
                    "is_error": True,
                },
            ],
        },
    ]
    result = _anth_to_openai_messages(messages)
    tool_msg = result[1]
    assert str(tool_msg["content"]).startswith("[ERROR] ")


# 功能：验证 system 参数被转换为第一条 role=system 消息
# 设计：传入自定义 system 文本，检查 result[0] 为 system role
def test_system_prompt_converted_to_message() -> None:
    result = _anth_to_openai_messages([], system="Custom system prompt")
    assert result[0] == {"role": "system", "content": "Custom system prompt"}


# 功能：验证 thinking 块在转换为 OpenAI 消息时被静默丢弃
# 设计：OpenAI 请求不需要传回 reasoning，thinking 块仅内部保留用于历史重建
def test_thinking_blocks_skipped_in_translation() -> None:
    messages: list[dict[str, object]] = [
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "hmm...", "signature": "sig1"},
                {"type": "text", "text": "answer"},
            ],
        },
    ]
    result = _anth_to_openai_messages(messages)
    assistant_msg = result[1]
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["content"] == "answer"
    assert "tool_calls" not in assistant_msg


# 功能：验证同一 user 消息中混合 text 和 tool_result 块被拆分为独立消息
# 设计：text → user 消息，每个 tool_result → 独立 tool 消息，覆盖多 tool_result 场景
def test_mixed_user_content_split_to_messages() -> None:
    messages: list[dict[str, object]] = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "check results"},
                {"type": "tool_result", "tool_use_id": "t1", "content": "r1"},
                {"type": "tool_result", "tool_use_id": "t2", "content": "r2"},
            ],
        },
    ]
    result = _anth_to_openai_messages(messages)
    # 应该产生 3 条消息（不含 system）：1 user + 2 tool
    non_system = [m for m in result if m["role"] != "system"]
    assert len(non_system) == 3
    assert non_system[0] == {"role": "user", "content": "check results"}
    assert non_system[1] == {"role": "tool", "tool_call_id": "t1", "content": "r1"}
    assert non_system[2] == {"role": "tool", "tool_call_id": "t2", "content": "r2"}


# --- tool schema translation tests -------------------------------------------


# 功能：验证 Anthropic input_schema 被映射为 OpenAI parameters 字段
# 设计：检查 type=function 包装和 function 子对象结构
def test_tool_schema_translated() -> None:
    schemas: list[dict[str, object]] = [
        {
            "name": "bash",
            "description": "Run a command",
            "input_schema": {
                "type": "object",
                "properties": {"cmd": {"type": "string"}},
            },
        },
    ]
    result = _anth_to_openai_tools(schemas)
    assert len(result) == 1
    assert result[0]["type"] == "function"
    fn = result[0]["function"]
    assert fn["name"] == "bash"  # type: ignore[index]
    assert fn["description"] == "Run a command"  # type: ignore[index]
    assert fn["parameters"]["type"] == "object"  # type: ignore[index]


# --- finish reason mapping tests ---------------------------------------------


# 功能：验证 OpenAI 各 finish_reason 正确映射为 Anthropic stop_reason
# 设计：覆盖 stop/tool_calls/length/content_filter/None 五种情况，用参数化避免重复代码
@pytest.mark.parametrize(
    "openai_reason,expected",
    [
        ("stop", "end_turn"),
        ("tool_calls", "tool_use"),
        ("length", "max_tokens"),
        ("content_filter", "end_turn"),
        (None, "end_turn"),
    ],
)
def test_finish_reason_mapping(openai_reason: str | None, expected: str) -> None:
    assert _map_finish_reason(openai_reason) == expected


# --- event publishing tests --------------------------------------------------


# 功能：验证每次 chat 调用都发布 llm.model_selected 事件
# 设计：使用 FakeStream + _chat，检查事件类型、model 和 strategy 字段
async def test_model_selected_event_published() -> None:
    chunks = [_make_chunk(content="hi"), _make_chunk(finish_reason="stop")]
    provider, _ = _make_provider(chunks)
    _, events = await _chat(provider)
    sel = [e for e in events if e.type == "llm.model_selected"]  # type: ignore[attr-defined]
    assert len(sel) == 1
    assert sel[0].model == "test-model"  # type: ignore[attr-defined]
    assert sel[0].strategy == "static"  # type: ignore[attr-defined]


# 功能：验证流式 token 每个 chunk 触发一次 llm.token 事件
# 设计：两段 token，检查事件数量和内容值，排除合并或跳过情况
async def test_token_events_published() -> None:
    chunks = [
        _make_chunk(content="Hello"),
        _make_chunk(content=" world"),
        _make_chunk(finish_reason="stop"),
    ]
    provider, _ = _make_provider(chunks)
    _, events = await _chat(provider)
    tokens = [e for e in events if e.type == "llm.token"]  # type: ignore[attr-defined]
    assert len(tokens) == 2
    assert tokens[0].token == "Hello"  # type: ignore[attr-defined]
    assert tokens[1].token == " world"  # type: ignore[attr-defined]


# 功能：验证最终 chunk 携带 usage 时 llm.usage 事件正确填充
# 设计：检查 input/output/cache_read 三字段精确匹配
async def test_usage_event_published() -> None:
    usage = _make_usage(prompt_tokens=200, completion_tokens=75, cached_tokens=150)
    chunks = [
        _make_chunk(content="hi"),
        _make_chunk(finish_reason="stop", usage=usage),
    ]
    provider, _ = _make_provider(chunks)
    _, events = await _chat(provider)
    usage_events = [e for e in events if e.type == "llm.usage"]  # type: ignore[attr-defined]
    assert len(usage_events) == 1
    ue = usage_events[0]
    assert ue.input_tokens == 200  # type: ignore[attr-defined]
    assert ue.output_tokens == 75  # type: ignore[attr-defined]
    assert ue.cache_read_input_tokens == 150  # type: ignore[attr-defined]


# 功能：验证事件发布顺序为 model_selected → token（×N） → usage
# 设计：检查类型列表的首尾元素，聚焦 provider 的时序契约
async def test_event_order_correct() -> None:
    chunks = [
        _make_chunk(content="hi"),
        _make_chunk(finish_reason="stop"),
    ]
    provider, _ = _make_provider(chunks)
    _, events = await _chat(provider)
    types = [e.type for e in events]  # type: ignore[attr-defined]
    assert types[0] == "llm.model_selected"
    assert "llm.token" in types
    assert types[-1] == "llm.usage"


# --- response parsing tests --------------------------------------------------


# 功能：验证 finish_reason=tool_calls 时工具调用被正确解析为 ToolCallBlock
# 设计：注入多段 tool_calls delta，覆盖 id/name/arguments 碎片累积和 JSON 解析
async def test_tool_calls_parsed_from_stream() -> None:
    chunks = [
        _make_chunk(
            tool_calls=[
                {"index": 0, "id": "call_1", "name": "bash", "arguments": '{"cmd":'},
            ]
        ),
        _make_chunk(
            tool_calls=[
                {"index": 0, "arguments": '"ls"}'},
            ]
        ),
        _make_chunk(finish_reason="tool_calls"),
    ]
    provider, _ = _make_provider(chunks)
    result, _ = await _chat(provider)
    assert result.stop_reason == "tool_use"
    assert len(result.tool_calls) == 1
    tc = result.tool_calls[0]
    assert tc.id == "call_1"
    assert tc.name == "bash"
    assert tc.input == {"cmd": "ls"}


# 功能：验证 finish_reason=stop 时 result.text 为累积的完整响应文本
# 设计：多段 content delta 拼接，断言完整字符串匹配
async def test_text_accumulated_from_chunks() -> None:
    chunks = [
        _make_chunk(content="foo"),
        _make_chunk(content="bar"),
        _make_chunk(content="baz"),
        _make_chunk(finish_reason="stop"),
    ]
    provider, _ = _make_provider(chunks)
    result, _ = await _chat(provider)
    assert result.text == "foobarbaz"


# 功能：验证 finish_reason=stop 且无工具调用时不产生任何 ToolCallBlock
# 设计：与 tool_calls 场景互补，确认空列表而非 None
async def test_stop_produces_no_tool_calls() -> None:
    chunks = [
        _make_chunk(content="done"),
        _make_chunk(finish_reason="stop"),
    ]
    provider, _ = _make_provider(chunks)
    result, _ = await _chat(provider)
    assert result.stop_reason == "end_turn"
    assert result.tool_calls == []


# 功能：验证 DeepSeek reasoner 的 reasoning_content 被转换为 thinking blocks
# 设计：注入 reasoning_content delta，检查 thinking_blocks 的 type 和内容
async def test_reasoning_content_converted_to_thinking() -> None:
    chunks = [
        _make_chunk(reasoning="Let me think..."),
        _make_chunk(content="answer"),
        _make_chunk(finish_reason="stop"),
    ]
    provider, _ = _make_provider(chunks)
    result, _ = await _chat(provider)
    assert len(result.thinking_blocks) == 1
    assert result.thinking_blocks[0]["type"] == "thinking"
    assert result.thinking_blocks[0]["thinking"] == "Let me think..."


# 功能：验证空流式响应不产生 token 事件且 text 为空字符串
# 设计：texts=[] 覆盖零 token 边界，确认 text="" 而非 None
async def test_empty_stream() -> None:
    chunks: list[MagicMock] = []
    provider, _ = _make_provider(chunks)
    result, events = await _chat(provider)
    tokens = [e for e in events if e.type == "llm.token"]  # type: ignore[attr-defined]
    assert tokens == []
    assert result.text == ""


# --- error handling tests ----------------------------------------------------


# 功能：验证缺少 OPENAI_API_KEY 时 provider 初始化立即 SystemExit
# 设计：清除环境变量后实例化，确认 fail-fast 行为
async def test_missing_api_key_raises_system_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        OpenAIProvider(model="any")

# 功能：验证 OpenAI reasoning_content 会在流式到达时立刻发布 llm.thinking 事件。
# 设计：这是深度思考面板的增量来源，顺序和碎片内容必须与上游流一致。
async def test_reasoning_content_published_incrementally() -> None:
    chunks = [
        _make_chunk(reasoning="first analyze"),
        _make_chunk(reasoning="then execute"),
        _make_chunk(content="done"),
        _make_chunk(finish_reason="stop"),
    ]
    provider, _ = _make_provider(chunks)
    _, events = await _chat(provider)
    thinking_events = [event for event in events if event.type == "llm.thinking"]  # type: ignore[attr-defined]
    assert [event.thinking for event in thinking_events] == ["first analyze", "then execute"]  # type: ignore[attr-defined]
    assert all(event.step == 0 for event in thinking_events)  # type: ignore[attr-defined]