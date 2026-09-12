from __future__ import annotations

from typing import Any, Protocol

from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import LlmResponse


class LLMProvider(Protocol):
    # 流式调用 LLM 并发布进度事件，返回完整响应。
    # max_output_tokens 为可选的单次请求输出上限（预算准入收缩时传入）；
    # None 表示使用 Provider 构造时配置的默认输出上限
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
        max_output_tokens: int | None = None,
        remaining_s: float | None = None,
    ) -> LlmResponse: ...
