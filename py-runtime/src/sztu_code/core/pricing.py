from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time
from decimal import Decimal
from enum import StrEnum
from typing import Literal

_PRICING_VERSION = "2026-08-16"
_OPENAI_PRICING_SOURCE = "https://developers.openai.com/api/docs/pricing"
_ANTHROPIC_PRICING_SOURCE = "https://docs.anthropic.com/en/docs/about-claude/pricing"
_DEEPSEEK_PRICING_SOURCE = "https://api-docs.deepseek.com/quick_start/pricing"
_OPENCODE_ZEN_SOURCE = "https://opencode.ai/zen"
_DEEPSEEK_PEAK_PRICING_START = datetime(2026, 8, 16, 16, 0, tzinfo=UTC)
_DEEPSEEK_PEAK_WINDOWS_UTC = (
    (time(1, 0), time(4, 0)),
    (time(6, 0), time(10, 0)),
)


class UnknownPricingPolicy(StrEnum):
    """未知模型定价策略"""

    FAIL_OPEN = "fail_open"  # 未知定价不阻止运行，但标记为 unknown
    FAIL_CLOSED = "fail_closed"  # 未知定价时 is_over_budget 返回 True


@dataclass(frozen=True)
class ModelPricing:
    """单个模型的价格定义"""

    provider: str  # "anthropic" | "openai" | "deepseek" | ...
    model: str  # provider-specific model id
    input_per_million: Decimal  # USD per 1M input tokens
    output_per_million: Decimal  # USD per 1M output tokens
    cache_read_per_million: Decimal | None = None  # USD per 1M cache read tokens
    cache_creation_per_million: Decimal | None = None  # USD per 1M cache creation tokens
    currency: str = "USD"
    version: str = "2024-01"  # 价格表版本号，便于追溯
    source: str = "local"  # "local" | "vendor" | "user_override"


@dataclass(frozen=True)
class TokenUsage:
    """Token 使用量封装"""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass(frozen=True)
class CostEstimate:
    """成本估算结果"""

    amount: Decimal | None  # None 表示无法计算（如未知定价）
    currency: str
    status: Literal["complete", "unknown", "incomplete"]
    # complete: 所有 token 类型都有定价
    # unknown: provider/model 在 catalog 中不存在
    # incomplete: 存在但某些 token 类型（如 cache）缺少定价
    pricing_version: str | None = None
    reason: str = ""  # status != complete 时的原因说明
    breakdown: dict[str, Decimal] | None = None  # 可选：分项成本明细


class PricingCatalog:
    """价格目录（本地硬编码 + 支持扩展）"""

    def __init__(self, entries: list[ModelPricing] | None = None) -> None:
        self._entries = entries or []
        self._index: dict[tuple[str, str], ModelPricing] = {}
        for entry in self._entries:
            key = (entry.provider.lower(), entry.model.lower())
            self._index[key] = entry

    # 查找某个 provider + model 的价格
    def get_pricing(self, provider: str, model: str) -> ModelPricing | None:
        key = (provider.lower(), model.lower())
        return self._index.get(key)

    # 添加或覆盖某个 model 的定价
    def add_pricing(self, pricing: ModelPricing) -> None:
        key = (pricing.provider.lower(), pricing.model.lower())
        self._index[key] = pricing
        if pricing not in self._entries:
            self._entries.append(pricing)


# 判断指定 UTC 时间是否处于 DeepSeek 峰值计费窗口
def _is_deepseek_peak_time(at: datetime) -> bool:
    current_time = at.astimezone(UTC).time()
    return any(start <= current_time < end for start, end in _DEEPSEEK_PEAK_WINDOWS_UTC)


# 根据当前时间解析 DeepSeek V4 动态峰谷价格
def _resolve_deepseek_pricing(pricing: ModelPricing, at: datetime) -> ModelPricing:
    model = pricing.model.lower()
    if model not in {"deepseek-v4-flash", "deepseek-v4-pro"}:
        return pricing

    current = at.astimezone(UTC)
    if current < _DEEPSEEK_PEAK_PRICING_START:
        if model == "deepseek-v4-flash":
            input_price, cache_read, output_price = "0.14", "0.0028", "0.28"
        else:
            input_price, cache_read, output_price = "0.435", "0.003625", "0.87"
        source = f"{_DEEPSEEK_PRICING_SOURCE}#before-peak-pricing"
    elif _is_deepseek_peak_time(current):
        if model == "deepseek-v4-flash":
            input_price, cache_read, output_price = "0.44", "0.014", "1.32"
        else:
            input_price, cache_read, output_price = "1.32", "0.044", "3.96"
        source = f"{_DEEPSEEK_PRICING_SOURCE}#peak"
    else:
        if model == "deepseek-v4-flash":
            input_price, cache_read, output_price = "0.22", "0.007", "0.66"
        else:
            input_price, cache_read, output_price = "0.66", "0.022", "1.98"
        source = f"{_DEEPSEEK_PRICING_SOURCE}#off-peak"

    return ModelPricing(
        provider=pricing.provider,
        model=pricing.model,
        input_per_million=Decimal(input_price),
        output_per_million=Decimal(output_price),
        cache_read_per_million=Decimal(cache_read),
        cache_creation_per_million=Decimal(input_price),
        currency=pricing.currency,
        version=_PRICING_VERSION,
        source=source,
    )


# 根据模型特性解析最终用于本次计算的价格
def _resolve_pricing(pricing: ModelPricing, at: datetime) -> ModelPricing:
    if pricing.model.lower().startswith("deepseek-v4-"):
        return _resolve_deepseek_pricing(pricing, at)
    return pricing


# 构造一条 USD / 1M tokens 的模型价格记录
def _pricing(
    provider: str,
    model: str,
    input_price: str,
    output_price: str,
    *,
    cache_read: str | None = None,
    cache_creation: str | None = None,
    source: str,
) -> ModelPricing:
    return ModelPricing(
        provider=provider,
        model=model,
        input_per_million=Decimal(input_price),
        output_per_million=Decimal(output_price),
        cache_read_per_million=Decimal(cache_read) if cache_read is not None else None,
        cache_creation_per_million=(
            Decimal(cache_creation) if cache_creation is not None else None
        ),
        version=_PRICING_VERSION,
        source=source,
    )


# 按多个 provider key 复用同一模型价格，兼容 OpenAI-compatible / Anthropic-compatible 端点
def _pricing_for_providers(
    providers: tuple[str, ...],
    model: str,
    input_price: str,
    output_price: str,
    *,
    cache_read: str | None = None,
    cache_creation: str | None = None,
    source: str,
) -> list[ModelPricing]:
    return [
        _pricing(
            provider,
            model,
            input_price,
            output_price,
            cache_read=cache_read,
            cache_creation=cache_creation,
            source=source,
        )
        for provider in providers
    ]


# 构造 Anthropic 价格；cache write 默认按 5 分钟缓存 1.25x，cache read 按 0.1x
def _anthropic_pricing(model: str, input_price: str, output_price: str) -> ModelPricing:
    input_decimal = Decimal(input_price)
    return _pricing(
        "anthropic",
        model,
        input_price,
        output_price,
        cache_read=str(input_decimal * Decimal("0.1")),
        cache_creation=str(input_decimal * Decimal("1.25")),
        source=_ANTHROPIC_PRICING_SOURCE,
    )


# 构造 opencode Zen 免 key 免费模型价格
def _free_openai_compatible_pricing(model: str) -> ModelPricing:
    return _pricing(
        "openai",
        model,
        "0",
        "0",
        cache_read="0",
        cache_creation="0",
        source=_OPENCODE_ZEN_SOURCE,
    )


# 根据 provider + model + usage 计算成本
def calculate_cost(
    provider: str,
    model: str,
    usage: TokenUsage,
    catalog: PricingCatalog,
    at: datetime | None = None,
) -> CostEstimate:
    pricing = catalog.get_pricing(provider, model)

    if pricing is None:
        return CostEstimate(
            amount=None,
            currency="USD",
            status="unknown",
            reason=f"No pricing found for provider={provider}, model={model}",
        )

    if at is None:
        at = datetime.now(UTC)
    pricing = _resolve_pricing(pricing, at)

    # 计算各项成本
    input_cost = (
        Decimal(usage.input_tokens) / Decimal(1_000_000) * pricing.input_per_million
    )
    output_cost = (
        Decimal(usage.output_tokens) / Decimal(1_000_000) * pricing.output_per_million
    )

    breakdown = {
        "input": input_cost,
        "output": output_cost,
    }

    total = input_cost + output_cost
    status: Literal["complete", "incomplete"] = "complete"
    reasons = []

    # cache_read
    if usage.cache_read_input_tokens > 0:
        if pricing.cache_read_per_million is not None:
            cache_read_cost = (
                Decimal(usage.cache_read_input_tokens)
                / Decimal(1_000_000)
                * pricing.cache_read_per_million
            )
            breakdown["cache_read"] = cache_read_cost
            total += cache_read_cost
        else:
            status = "incomplete"
            reasons.append(
                "cache_read_input_tokens present but no cache_read pricing"
            )

    # cache_creation
    if usage.cache_creation_input_tokens > 0:
        if pricing.cache_creation_per_million is not None:
            cache_creation_cost = (
                Decimal(usage.cache_creation_input_tokens)
                / Decimal(1_000_000)
                * pricing.cache_creation_per_million
            )
            breakdown["cache_creation"] = cache_creation_cost
            total += cache_creation_cost
        else:
            status = "incomplete"
            reasons.append(
                "cache_creation_input_tokens present but no cache_creation pricing"
            )

    return CostEstimate(
        amount=total,
        currency=pricing.currency,
        status=status,
        pricing_version=pricing.version,
        reason="; ".join(reasons) if reasons else "",
        breakdown=breakdown,
    )


# 返回内置价格表；价格为人工同步的官方当前价，不做联网实时抓取
def get_builtin_catalog() -> PricingCatalog:
    entries: list[ModelPricing] = [
        # OpenAI：标准价 / 短上下文，单位 USD / 1M tokens
        _pricing(
            "openai",
            "gpt-5.6",
            "2.50",
            "15.00",
            cache_read="0.25",
            cache_creation="3.125",
            source=f"{_OPENAI_PRICING_SOURCE}#gpt-5.6-aliases-sol",
        ),
        _pricing(
            "openai",
            "gpt-5.6-sol",
            "2.50",
            "15.00",
            cache_read="0.25",
            cache_creation="3.125",
            source=_OPENAI_PRICING_SOURCE,
        ),
        _pricing(
            "openai",
            "gpt-5.6-terra",
            "1.00",
            "6.00",
            cache_read="0.10",
            cache_creation="1.25",
            source=_OPENAI_PRICING_SOURCE,
        ),
        _pricing(
            "openai",
            "gpt-5.6-luna",
            "0.10",
            "0.60",
            cache_read="0.01",
            cache_creation="0.125",
            source=_OPENAI_PRICING_SOURCE,
        ),
        _pricing(
            "openai",
            "gpt-5.3-codex",
            "1.75",
            "14.00",
            cache_read="0.175",
            source=_OPENAI_PRICING_SOURCE,
        ),
        _pricing(
            "openai",
            "chat-latest",
            "5.00",
            "30.00",
            cache_read="0.50",
            source=_OPENAI_PRICING_SOURCE,
        ),
        # Anthropic：标准价，cache write 使用 5 分钟缓存价
        _anthropic_pricing("claude-fable-5", "10.00", "50.00"),
        _anthropic_pricing("claude-mythos-5", "10.00", "50.00"),
        _anthropic_pricing("claude-opus-5", "5.00", "25.00"),
        _anthropic_pricing("claude-opus-4.8", "5.00", "25.00"),
        _anthropic_pricing("claude-opus-4.7", "5.00", "25.00"),
        _anthropic_pricing("claude-opus-4.6", "5.00", "25.00"),
        _anthropic_pricing("claude-opus-4.5", "5.00", "25.00"),
        _anthropic_pricing("claude-opus-4.1", "15.00", "75.00"),
        _anthropic_pricing("claude-opus-4", "15.00", "75.00"),
        _anthropic_pricing("claude-sonnet-5", "2.00", "10.00"),
        _anthropic_pricing("claude-sonnet-4.6", "3.00", "15.00"),
        _anthropic_pricing("claude-sonnet-4.5", "3.00", "15.00"),
        _anthropic_pricing("claude-sonnet-4", "3.00", "15.00"),
        _anthropic_pricing("claude-haiku-4.5", "1.00", "5.00"),
        _anthropic_pricing("claude-haiku-3.5", "0.80", "4.00"),
        # DeepSeek：官方 2026-08-16 16:00 UTC 后启用峰谷价，计算时按当前 UTC 时间解析
        *_pricing_for_providers(
            ("openai", "anthropic"),
            "deepseek-v4-flash",
            "0.14",
            "0.28",
            cache_read="0.0028",
            cache_creation="0.14",
            source=f"{_DEEPSEEK_PRICING_SOURCE}#time-based",
        ),
        *_pricing_for_providers(
            ("openai", "anthropic"),
            "deepseek-v4-pro",
            "0.435",
            "0.87",
            cache_read="0.003625",
            cache_creation="0.435",
            source=f"{_DEEPSEEK_PRICING_SOURCE}#time-based",
        ),
        # opencode Zen 内置免 key free 模型
        _free_openai_compatible_pricing("big-pickle"),
        _free_openai_compatible_pricing("ling-3.0-flash-fin-free"),
        _free_openai_compatible_pricing("mimo-v2.5-free"),
        _free_openai_compatible_pricing("nemotron-3-ultra-free"),
        _free_openai_compatible_pricing("nemotron-3.5-lightning-free"),
        # Pollinations 免 key 免费模型
        _free_openai_compatible_pricing("openai-fast"),
    ]
    return PricingCatalog(entries)
