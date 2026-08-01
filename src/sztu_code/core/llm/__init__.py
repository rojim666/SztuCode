from __future__ import annotations

from typing import TYPE_CHECKING

from sztu_code.core.llm.base import LLMProvider
from sztu_code.core.llm.openai_provider import OpenAIProvider
from sztu_code.core.llm.provider import AnthropicProvider
from sztu_code.core.llm.types import LlmResponse, ToolCallBlock, UsageStats

if TYPE_CHECKING:
    from sztu_code.core.config import SztuConfig


# 根据配置创建对应的 LLM provider 实例
def create_provider(config: SztuConfig) -> LLMProvider:
    if not config.llm.default_model.strip():
        raise SystemExit(
            "LLM model not configured. Set SZTU_LLM_DEFAULT_MODEL in .env."
        )
    if config.llm.provider == "openai":
        return OpenAIProvider(
            config.llm.default_model,
            context_window=config.llm.context_window,
        )
    return AnthropicProvider(
        config.llm.default_model,
        context_window=config.llm.context_window,
    )


__all__ = [
    "AnthropicProvider",
    "LLMProvider",
    "LlmResponse",
    "OpenAIProvider",
    "ToolCallBlock",
    "UsageStats",
    "create_provider",
]
