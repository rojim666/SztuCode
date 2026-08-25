from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sztu_code.core.context import ExecutionContext
from sztu_code.core.pricing import (
    ModelPricing,
    PricingCatalog,
    TokenUsage,
    UnknownPricingPolicy,
    calculate_cost,
    get_builtin_catalog,
)


# 功能：验证固定 usage 和固定价格精确计算成本
# 设计：使用 Decimal 避免浮点误差，断言 input/output 成本之和
def test_fixed_usage_calculates_exact_cost() -> None:
    catalog = PricingCatalog(
        [
            ModelPricing(
                provider="test",
                model="model-a",
                input_per_million=Decimal("2.00"),
                output_per_million=Decimal("10.00"),
            )
        ]
    )

    usage = TokenUsage(input_tokens=500_000, output_tokens=100_000)
    estimate = calculate_cost("test", "model-a", usage, catalog)

    assert estimate.status == "complete"
    assert (
        estimate.amount
        == Decimal("2.00") * Decimal("0.5") + Decimal("10.00") * Decimal("0.1")
    )
    assert estimate.amount == Decimal("2.00")  # 1.00 + 1.00
    assert estimate.currency == "USD"


# 功能：验证相同 usage 不同 model 产生不同成本
# 设计：两个 model 有不同单价，相同 usage，断言成本不等
def test_same_usage_different_models_different_costs() -> None:
    catalog = PricingCatalog(
        [
            ModelPricing(
                provider="test",
                model="cheap",
                input_per_million=Decimal("1.00"),
                output_per_million=Decimal("5.00"),
            ),
            ModelPricing(
                provider="test",
                model="expensive",
                input_per_million=Decimal("10.00"),
                output_per_million=Decimal("50.00"),
            ),
        ]
    )

    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)

    cheap_estimate = calculate_cost("test", "cheap", usage, catalog)
    expensive_estimate = calculate_cost("test", "expensive", usage, catalog)

    assert cheap_estimate.amount == Decimal("6.00")  # 1 + 5
    assert expensive_estimate.amount == Decimal("60.00")  # 10 + 50
    assert expensive_estimate.amount > cheap_estimate.amount


# 功能：验证 cache_read 和 cache_creation 分项计费
# 设计：提供完整 cache 定价，断言 breakdown 包含所有四项
def test_cache_tokens_charged_separately() -> None:
    catalog = PricingCatalog(
        [
            ModelPricing(
                provider="test",
                model="cached",
                input_per_million=Decimal("3.00"),
                output_per_million=Decimal("15.00"),
                cache_read_per_million=Decimal("0.30"),
                cache_creation_per_million=Decimal("3.75"),
            )
        ]
    )

    usage = TokenUsage(
        input_tokens=1_000_000,
        output_tokens=500_000,
        cache_read_input_tokens=2_000_000,
        cache_creation_input_tokens=1_000_000,
    )

    estimate = calculate_cost("test", "cached", usage, catalog)

    assert estimate.status == "complete"
    assert estimate.breakdown is not None
    assert estimate.breakdown["input"] == Decimal("3.00")
    assert estimate.breakdown["output"] == Decimal("7.50")
    assert estimate.breakdown["cache_read"] == Decimal("0.60")
    assert estimate.breakdown["cache_creation"] == Decimal("3.75")
    assert estimate.amount == Decimal("14.85")


# 功能：验证未知 model 返回 unknown 状态
# 设计：空 catalog，断言 status=unknown 且 amount=None
def test_unknown_model_returns_unknown_status() -> None:
    catalog = PricingCatalog([])
    usage = TokenUsage(input_tokens=100, output_tokens=100)

    estimate = calculate_cost("unknown_provider", "unknown_model", usage, catalog)

    assert estimate.status == "unknown"
    assert estimate.amount is None
    assert "No pricing found" in estimate.reason


# 功能：验证未知 model 不使用旧默认价格
# 设计：即使 usage 非零，未知 model 不应返回 3/15 计算的金额
def test_unknown_model_does_not_use_legacy_default() -> None:
    catalog = PricingCatalog([])
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)

    estimate = calculate_cost("unknown", "model", usage, catalog)

    # 旧版会返回 3 + 15 = 18 USD，新版必须返回 None
    assert estimate.amount is None
    assert estimate.status == "unknown"


# 功能：验证 incomplete 状态（有 cache usage 但无 cache pricing）
# 设计：model 定义中 cache_read_per_million=None，但 usage 有 cache_read_input_tokens
def test_incomplete_pricing_when_cache_usage_but_no_cache_price() -> None:
    catalog = PricingCatalog(
        [
            ModelPricing(
                provider="test",
                model="no-cache-price",
                input_per_million=Decimal("2.00"),
                output_per_million=Decimal("10.00"),
                cache_read_per_million=None,  # 明确没有 cache 定价
            )
        ]
    )

    usage = TokenUsage(
        input_tokens=100_000,
        output_tokens=50_000,
        cache_read_input_tokens=200_000,  # 有 cache 使用
    )

    estimate = calculate_cost("test", "no-cache-price", usage, catalog)

    assert estimate.status == "incomplete"
    assert "cache_read_input_tokens present but no cache_read pricing" in estimate.reason
    # 成本仍会计算 input + output，只是标记为 incomplete
    assert estimate.amount is not None


# 功能：验证 ExecutionContext.is_over_budget_with_pricing 的 fail_open 策略
# 设计：未知 model + fail_open 策略应返回 False（允许继续）
def test_budget_check_fail_open_allows_unknown_pricing() -> None:
    context = ExecutionContext(
        run_id="test",
        goal="test",
        max_steps=10,
        max_budget_usd=5.0,
    )
    context.total_input_tokens = 1_000_000
    context.total_output_tokens = 1_000_000

    empty_catalog = PricingCatalog([])

    result = context.is_over_budget_with_pricing(
        provider="unknown",
        model="unknown",
        pricing_catalog=empty_catalog,
        unknown_policy=UnknownPricingPolicy.FAIL_OPEN,
    )

    # fail_open：未知定价不阻止运行
    assert result is False


# 功能：验证 ExecutionContext.is_over_budget_with_pricing 的 fail_closed 策略
# 设计：未知 model + fail_closed 策略应返回 True（阻止继续）
def test_budget_check_fail_closed_blocks_unknown_pricing() -> None:
    context = ExecutionContext(
        run_id="test",
        goal="test",
        max_steps=10,
        max_budget_usd=5.0,
    )
    context.total_input_tokens = 1_000_000
    context.total_output_tokens = 1_000_000

    empty_catalog = PricingCatalog([])

    result = context.is_over_budget_with_pricing(
        provider="unknown",
        model="unknown",
        pricing_catalog=empty_catalog,
        unknown_policy=UnknownPricingPolicy.FAIL_CLOSED,
    )

    # fail_closed：未知定价阻止运行
    assert result is True


# 功能：验证 incomplete 定价在 fail_closed 策略下会阻止继续
# 设计：构造有 cache usage 但缺少 cache 价格的模型，避免用部分金额低估成本
def test_budget_check_fail_closed_blocks_incomplete_pricing() -> None:
    catalog = PricingCatalog(
        [
            ModelPricing(
                provider="test",
                model="partial",
                input_per_million=Decimal("1.00"),
                output_per_million=Decimal("2.00"),
                cache_read_per_million=None,
            )
        ]
    )
    context = ExecutionContext(
        run_id="test",
        goal="test",
        max_steps=10,
        max_budget_usd=100.0,
    )
    context.total_input_tokens = 1_000
    context.total_cache_read_input_tokens = 1_000

    result = context.is_over_budget_with_pricing(
        provider="test",
        model="partial",
        pricing_catalog=catalog,
        unknown_policy=UnknownPricingPolicy.FAIL_CLOSED,
    )

    assert result is True


# 功能：验证已知 model 超预算时返回 True
# 设计：成本 6.0 USD，预算 5.0 USD，应阻止
def test_budget_check_blocks_when_over_budget() -> None:
    catalog = PricingCatalog(
        [
            ModelPricing(
                provider="test",
                model="model",
                input_per_million=Decimal("3.00"),
                output_per_million=Decimal("15.00"),
            )
        ]
    )

    context = ExecutionContext(
        run_id="test",
        goal="test",
        max_steps=10,
        max_budget_usd=5.0,
    )
    # 1M input + 0.2M output = 3.0 + 3.0 = 6.0 USD
    context.total_input_tokens = 1_000_000
    context.total_output_tokens = 200_000

    result = context.is_over_budget_with_pricing(
        provider="test",
        model="model",
        pricing_catalog=catalog,
    )

    assert result is True


# 功能：验证未超预算时返回 False
# 设计：成本 4.0 USD，预算 5.0 USD，应允许
def test_budget_check_allows_when_under_budget() -> None:
    catalog = PricingCatalog(
        [
            ModelPricing(
                provider="test",
                model="model",
                input_per_million=Decimal("2.00"),
                output_per_million=Decimal("10.00"),
            )
        ]
    )

    context = ExecutionContext(
        run_id="test",
        goal="test",
        max_steps=10,
        max_budget_usd=5.0,
    )
    # 1M input + 0.2M output = 2.0 + 2.0 = 4.0 USD
    context.total_input_tokens = 1_000_000
    context.total_output_tokens = 200_000

    result = context.is_over_budget_with_pricing(
        provider="test",
        model="model",
        pricing_catalog=catalog,
    )

    assert result is False


# 功能：验证内置 catalog 包含当前官方同步的 OpenAI 价格
# 设计：用 1M input + 1M output 断言 GPT-5.6 Sol 标准价，不依赖联网
def test_builtin_catalog_has_openai_gpt_56_sol_price() -> None:
    catalog = get_builtin_catalog()
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)

    estimate = calculate_cost("openai", "gpt-5.6-sol", usage, catalog)

    assert estimate.status == "complete"
    assert estimate.amount == Decimal("17.50")
    assert estimate.pricing_version == "2026-08-16"


# 功能：验证 Anthropic 内置价格包含缓存分项
# 设计：Claude Sonnet 5 的 5 分钟 cache write 为 input 1.25x，cache read 为 input 0.1x
def test_builtin_catalog_has_anthropic_cache_prices() -> None:
    catalog = get_builtin_catalog()
    usage = TokenUsage(
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_read_input_tokens=1_000_000,
        cache_creation_input_tokens=1_000_000,
    )

    estimate = calculate_cost("anthropic", "claude-sonnet-5", usage, catalog)

    assert estimate.status == "complete"
    assert estimate.breakdown is not None
    assert estimate.breakdown["input"] == Decimal("2.00")
    assert estimate.breakdown["output"] == Decimal("10.00")
    assert estimate.breakdown["cache_read"] == Decimal("0.200")
    assert estimate.breakdown["cache_creation"] == Decimal("2.5000")


# 功能：验证 DeepSeek 价格可兼容 OpenAI-compatible 和 Anthropic-compatible 配置
# 设计：同一模型在两个 provider key 下都能查到，避免 GUI 端不同 API 格式导致 unknown
def test_builtin_catalog_has_deepseek_provider_alias_prices() -> None:
    catalog = get_builtin_catalog()
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    peak_time = datetime(2026, 8, 17, 1, 30, tzinfo=UTC)

    openai_estimate = calculate_cost("openai", "deepseek-v4-flash", usage, catalog, peak_time)
    anthropic_estimate = calculate_cost(
        "anthropic", "deepseek-v4-flash", usage, catalog, peak_time
    )

    assert openai_estimate.status == "complete"
    assert anthropic_estimate.status == "complete"
    assert openai_estimate.amount == Decimal("1.76")
    assert anthropic_estimate.amount == Decimal("1.76")


# 功能：验证 DeepSeek 新峰谷价生效前仍使用旧价
# 设计：选择 2026-08-16 15:59 UTC，断言 deepseek-v4-flash 按旧 input/output 计算
def test_deepseek_uses_old_price_before_peak_pricing_start() -> None:
    catalog = get_builtin_catalog()
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    before_start = datetime(2026, 8, 16, 15, 59, tzinfo=UTC)

    estimate = calculate_cost("openai", "deepseek-v4-flash", usage, catalog, before_start)

    assert estimate.status == "complete"
    assert estimate.amount == Decimal("0.42")
    assert estimate.pricing_version == "2026-08-16"


# 功能：验证 DeepSeek 生效后峰值时间使用峰值价
# 设计：选择 01:30 UTC 峰值窗口，断言 deepseek-v4-pro 按 peak 价格计算
def test_deepseek_uses_peak_price_in_peak_window() -> None:
    catalog = get_builtin_catalog()
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    peak_time = datetime(2026, 8, 17, 1, 30, tzinfo=UTC)

    estimate = calculate_cost("openai", "deepseek-v4-pro", usage, catalog, peak_time)

    assert estimate.status == "complete"
    assert estimate.amount == Decimal("5.28")
    assert estimate.reason == ""


# 功能：验证 DeepSeek 生效后非峰值时间使用谷值价
# 设计：选择 11:00 UTC 非峰值窗口，断言 deepseek-v4-pro 按 off-peak 价格计算
def test_deepseek_uses_off_peak_price_outside_peak_window() -> None:
    catalog = get_builtin_catalog()
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    off_peak_time = datetime(2026, 8, 17, 11, 0, tzinfo=UTC)

    estimate = calculate_cost("openai", "deepseek-v4-pro", usage, catalog, off_peak_time)

    assert estimate.status == "complete"
    assert estimate.amount == Decimal("2.64")


# 功能：验证 opencode Zen 内置 free 模型估价为 0
# 设计：免 key 免费模型不应因为有 usage 而产生预算成本
def test_builtin_catalog_has_free_opencode_zen_models() -> None:
    catalog = get_builtin_catalog()
    usage = TokenUsage(
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_read_input_tokens=1_000_000,
        cache_creation_input_tokens=1_000_000,
    )

    estimate = calculate_cost("openai", "mimo-v2.5-free", usage, catalog)

    assert estimate.status == "complete"
    assert estimate.amount == Decimal("0")
