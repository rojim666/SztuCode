from __future__ import annotations

import os
from typing import TYPE_CHECKING

from sztu_code.core.llm.base import LLMProvider
from sztu_code.core.llm.openai_provider import OpenAIProvider
from sztu_code.core.llm.provider import AnthropicProvider
from sztu_code.core.llm.types import LlmResponse, ToolCallBlock, UsageStats

if TYPE_CHECKING:
    from sztu_code.core.config import SztuConfig


# 将配置里的自定义端点与凭证注入环境变量供 provider 读取；空值不覆盖已有环境
def _apply_endpoint_env(prefix: str, llm: object) -> None:
    base_url = getattr(llm, "base_url", "") or ""
    api_key = getattr(llm, "api_key", "") or ""
    if base_url:
        os.environ[prefix + "BASE_URL"] = base_url
    if api_key:
        os.environ[prefix + "API_KEY"] = api_key


# 根据配置创建对应的 LLM provider 实例
def create_provider(config: SztuConfig) -> LLMProvider:
    if not config.llm.default_model.strip():
        raise SystemExit(
            "LLM model not configured. Set SZTU_LLM_DEFAULT_MODEL in .env."
        )
    if config.llm.provider == "openai":
        _apply_endpoint_env("OPENAI_", config.llm)
        return OpenAIProvider(
            config.llm.default_model,
            context_window=config.llm.context_window,
        )
    _apply_endpoint_env("ANTHROPIC_", config.llm)
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
