from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from sztu_code.core.llm.base import LLMProvider
from sztu_code.core.llm.types import LlmResponse, ToolCallBlock, UsageStats

if TYPE_CHECKING:
    from sztu_code.core.config import SztuConfig
    from sztu_code.core.llm.openai_provider import OpenAIProvider
    from sztu_code.core.llm.provider import AnthropicProvider


# 将配置里的自定义端点与凭证注入环境变量供 provider 读取；空值不覆盖已有环境
def _apply_endpoint_env(prefix: str, llm: object) -> None:
    base_url = getattr(llm, "base_url", "") or ""
    api_key = getattr(llm, "api_key", "") or ""
    api_key_env = getattr(llm, "api_key_env", "") or ""
    if not api_key and api_key_env:
        api_key = os.environ.get(api_key_env, "")
    if base_url:
        os.environ[prefix + "BASE_URL"] = base_url
    if getattr(llm, "keyless", False):
        # 免 key 端点（如 opencode Zen）：清空环境里遗留的通用 key，避免误发被拒
        os.environ[prefix + "API_KEY"] = ""
    elif api_key:
        os.environ[prefix + "API_KEY"] = api_key


# 根据配置创建对应的 LLM provider 实例
def create_provider(config: SztuConfig) -> LLMProvider:
    if not config.llm.default_model.strip():
        raise SystemExit(
            "LLM model not configured. Set SZTU_LLM_DEFAULT_MODEL in .env."
        )
    if config.llm.provider == "openai":
        _apply_endpoint_env("OPENAI_", config.llm)
        from sztu_code.core.llm.openai_provider import OpenAIProvider

        return OpenAIProvider(
            config.llm.default_model,
            context_window=config.llm.context_window,
            max_output_tokens=config.llm.max_output_tokens,
            temperature=config.llm.temperature,
            top_p=config.llm.top_p,
            reasoning_effort=config.llm.reasoning_effort,
            timeout_s=config.llm.timeout_s,
            max_retries=config.llm.max_retries,
            cache_control=config.llm.cache_control,
        )
    _apply_endpoint_env("ANTHROPIC_", config.llm)
    from sztu_code.core.llm.provider import AnthropicProvider

    return AnthropicProvider(
        config.llm.default_model,
        context_window=config.llm.context_window,
        max_output_tokens=config.llm.max_output_tokens,
        temperature=config.llm.temperature,
        top_p=config.llm.top_p,
        reasoning_effort=config.llm.reasoning_effort,
        timeout_s=config.llm.timeout_s,
        max_retries=config.llm.max_retries,
        cache_control=config.llm.cache_control,
    )


# 惰性加载 SDK 依赖的 provider 类：客户端或 daemon 未真正创建 provider 时不加载 openai/anthropic SDK
def __getattr__(name: str) -> Any:
    if name == "OpenAIProvider":
        from sztu_code.core.llm.openai_provider import OpenAIProvider

        return OpenAIProvider
    if name == "AnthropicProvider":
        from sztu_code.core.llm.provider import AnthropicProvider

        return AnthropicProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AnthropicProvider",
    "LLMProvider",
    "LlmResponse",
    "OpenAIProvider",
    "ToolCallBlock",
    "UsageStats",
    "create_provider",
]
