from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 7437
_DEFAULT_LOG_LEVEL = "INFO"
_DEFAULT_LOG_FILE = "~/.sztu/logs/core.log"
_DEFAULT_LOG_FORMAT = "text"
_DEFAULT_CONFIG_PATH = "~/.sztu/config.toml"
_DEFAULT_CLIENT_SETTINGS_PATH = "~/.sztu/client-settings.json"
_DEFAULT_MAX_STEPS = 100  # 硬止损；SWE-bench 极少需要 >100 步；显式设为 0 可恢复不限
_DEFAULT_WRAP_UP_ON_MAX_STEPS = True
_DEFAULT_GRACE_STEP_ON_MAX_STEPS = True
_DEFAULT_STUCK_MAX_FAILURES = 2
_DEFAULT_STUCK_MAX_TOTAL = 0
_DEFAULT_TOOL_MAX_CONCURRENCY = 4
_DEFAULT_TRACE_FILE = "~/.sztu/traces/daemon.jsonl"
_DEFAULT_TUI_THEME = "dark"
_DEFAULT_TUI_WALLPAPER = "none"

# TUI 主题与壁纸的可选值，与 src/sztu_code/tui/theme.py 的注册表保持一致
TUI_THEME_NAMES: tuple[str, ...] = ("dark", "light")
TUI_WALLPAPER_NAMES: tuple[str, ...] = ("none", "aurora", "ocean", "sunset")

API_FORMATS = {
    "openai_chat_completions",
    "anthropic_messages",
    "openai_responses",
}


# 将 API 格式映射为兼容旧配置的 SDK 供应商族
def provider_for_api_format(api_format: str) -> str:
    return "anthropic" if api_format == "anthropic_messages" else "openai"


# 将旧 provider 值归一化为明确的 API 格式
def normalize_api_format(api_format: object, provider: object = None) -> str:
    if isinstance(api_format, str) and api_format in API_FORMATS:
        return api_format
    return "openai_chat_completions" if provider == "openai" else "anthropic_messages"


@dataclass
class LoggingConfig:
    level: str = _DEFAULT_LOG_LEVEL
    file: str = _DEFAULT_LOG_FILE
    format: str = _DEFAULT_LOG_FORMAT  # "text" | "json"


@dataclass
class AgentConfig:
    # 0 = 不限步数；时间预算和上下文窗口保护仍然生效
    max_steps: int = _DEFAULT_MAX_STEPS
    max_budget_usd: float = 0.0  # 0 = 不限制 USD 成本上限
    repeated_error_threshold: int = 3  # 同一工具同类错误连续 N 次触发熔断
    # max_steps 到达前给一次总结回合，避免裸失败
    wrap_up_on_max_steps: bool = _DEFAULT_WRAP_UP_ON_MAX_STEPS
    # max_steps 边界且最后一步工具全部成功时，追加一步无工具结语回合让模型正常收尾
    grace_step_on_max_steps: bool = _DEFAULT_GRACE_STEP_ON_MAX_STEPS
    # 同一操作连续失败达到该次数触发软干预；0=关闭
    stuck_max_failures: int = _DEFAULT_STUCK_MAX_FAILURES
    # 累计干预达到该次数硬停；0=永不硬停
    stuck_max_total: int = _DEFAULT_STUCK_MAX_TOTAL
    # 同轮全只读工具批次的最大并发数；1 保持完全串行
    tool_max_concurrency: int = _DEFAULT_TOOL_MAX_CONCURRENCY
    # run 结束前是否强制执行完成契约验证（issue #94）
    require_verification: bool = False
    # 单条完成条件检查命令的超时秒数
    verification_check_timeout_s: int = 60
    # 验证失败后自动修复的最大轮数（issue #94 分支 4）；0=关闭修复闭环。
    # 不另设 enable_repair_loop 开关：门禁本身由 require_verification 守卫，
    # 本字段置 0 即可单独关闭闭环，再加布尔开关属冗余配置
    max_repair_attempts: int = 2


@dataclass
class BudgetConfig:
    # 已废弃：不再使用跨轮累计 Token 预算终止 Agent Run，保留字段仅兼容旧配置。
    max_tokens: int = 0
    # 本 run 累计墙钟秒数上限；0=不限
    max_wall_clock_s: int = 1_200  # 20 分钟


@dataclass
class WorkflowConfig:
    # 同一工作流最多并行执行的角色任务数
    max_concurrency: int = 4
    # 任务图允许的最大嵌套深度
    max_depth: int = 2
    # 单个角色任务失败后的最大重试次数
    max_retries: int = 1


@dataclass
class LlmConfig:
    # A model must be supplied by configuration; never silently select a vendor model.
    default_model: str = ""
    provider: str = "anthropic"  # legacy SDK family derived from api_format
    api_format: str = "anthropic_messages"
    router: str = "static"  # "static" | "rule_based" (S4) | "cost_budget" (S6)
    context_window: int = 0  # 0 = use provider's model-aware default
    max_output_tokens: int = 8_192
    temperature: float | None = None
    top_p: float | None = None
    reasoning_effort: str = ""
    timeout_s: float = 120.0
    max_retries: int = 2
    base_url: str = ""  # 自定义端点，空表示使用官方默认地址
    api_key: str = ""  # 导入的凭证，优先于 .env 注入 provider 环境
    api_key_env: str = ""  # 内置模型使用的凭证变量名，避免把密钥写入模型配置
    keyless: bool = False  # 免 key 端点（如 opencode Zen 免费模型），跳过凭证校验
    # OpenAI 兼容端点是否发送 cache_control 标记（system + 最后一个 tool）。
    # 部分端点（DeepSeek/Zen）是自动前缀缓存、忽略此字段，纯 OpenAI 规范端点也忽略；
    # 仅对识别该标记的网关有命中收益；端点拒收未知字段时可关掉。
    cache_control: bool = True


@dataclass
class TraceConfig:
    enabled: bool = True
    file: str = _DEFAULT_TRACE_FILE
    include_llm_payload: bool = True  # false 时 LLM 记录只保留摘要


@dataclass
class PermissionConfig:
    timeout_s: float = 60.0  # 审批超时秒数；0 表示不超时
    mode: str = "normal"


@dataclass
class CompactionConfig:
    # context_pct 触发压缩的阈值；0 表示禁用百分比触发
    # 70% × 200K 窗口 = 140K 上下文才触发，避免过早失忆
    auto_threshold: float = 0.70
    # 已废弃：自动压缩现在仅由上下文占用率触发，字段保留用于旧配置兼容
    auto_compact_min_tokens: int = 0
    # 已废弃：自动压缩现在仅由上下文占用率触发，字段保留用于旧配置兼容
    auto_compact_min_steps: int = 0
    tool_result_limit: int = 8_000
    tool_result_keep: int = 4_000
    # --- 滑动窗口压缩（借鉴 Claude Code keepRecent=5）---
    # 保留最近 N 个 turn 完整细节，仅摘要更早的 turn；0=回退全量替换
    sliding_window_size: int = 5
    # 两次压缩之间的最小步数间隔（滑动窗口下可大幅降低，因为不丢失即时上下文）
    compact_cooldown_steps: int = 3
    # 连续压缩失败 N 次后熔断，不再尝试自动压缩（借鉴 Claude Code circuit breaker）
    circuit_breaker_max_failures: int = 3


@dataclass
class OffloadConfig:
    enabled: bool = True  # 是否启用上下文卸载
    min_chars: int = 2_000  # 触发卸载的最小字符数
    min_lines: int = 50  # 触发卸载的最小行数
    force_tools: list[str] = field(default_factory=lambda: ["bash", "grep", "glob"])
    summary_max_chars: int = 300  # 摘要最大字符数


@dataclass
class McpServerConfig:
    name: str
    transport: str = "stdio"       # "stdio" | "tcp"
    command: str = ""              # stdio 专用：可执行文件路径
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    host: str = "localhost"        # tcp 专用
    port: int = 3000               # tcp 专用


@dataclass
class McpConfig:
    servers: list[McpServerConfig] = field(default_factory=list)


@dataclass
class TuiConfig:
    # TUI 明暗主题与背景壁纸样式（可选值见 TUI_THEME_NAMES / TUI_WALLPAPER_NAMES）
    theme: str = _DEFAULT_TUI_THEME
    wallpaper: str = _DEFAULT_TUI_WALLPAPER


@dataclass
class SztuConfig:
    host: str = _DEFAULT_HOST
    port: int = _DEFAULT_PORT
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    trace: TraceConfig = field(default_factory=TraceConfig)
    permission: PermissionConfig = field(default_factory=PermissionConfig)
    compaction: CompactionConfig = field(default_factory=CompactionConfig)
    offload: OffloadConfig = field(default_factory=OffloadConfig)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    mcp: McpConfig = field(default_factory=McpConfig)
    tui: TuiConfig = field(default_factory=TuiConfig)


# 构建并返回运行时配置：默认值 → 全局 TOML → 项目本地 TOML → .env → 系统环境变量（后者优先级最高）
def get_config() -> SztuConfig:
    config = SztuConfig()

    # .env 必须在读取 SZTU_CONFIG 之前加载，以便 .env 中的 SZTU_CONFIG 能影响 TOML 路径
    load_dotenv(".env", override=False)

    # 若显式指定 SZTU_CONFIG，只读该文件；否则按优先级叠加：全局 → 项目本地
    explicit = os.environ.get("SZTU_CONFIG")
    if explicit:
        config_paths = [Path(explicit).expanduser()]
    else:
        config_paths = [
            Path(_DEFAULT_CONFIG_PATH).expanduser(),
            Path(".sztu/config.toml"),
        ]

    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path, "rb") as f:
                    data = tomllib.load(f)
            except tomllib.TOMLDecodeError as e:
                raise SystemExit(f"Config parse error ({config_path}): {e}") from e
            _apply_toml(config, data)

    _apply_client_settings(config)

    _apply_env(config)
    return config


def _client_settings_path() -> Path:
    return Path(
        os.environ.get("SZTU_CLIENT_SETTINGS", _DEFAULT_CLIENT_SETTINGS_PATH)
    ).expanduser()


def _read_client_settings() -> dict[str, Any]:
    path = _client_settings_path()
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _apply_client_settings(config: SztuConfig) -> None:
    value = _read_client_settings()
    provider = value.get("provider")
    api_format = normalize_api_format(value.get("api_format"), provider)
    model = value.get("model")
    permission_mode = value.get("permission_mode")
    config.llm.api_format = api_format
    config.llm.provider = provider_for_api_format(api_format)
    if isinstance(model, str) and model:
        config.llm.default_model = model
        # 让客户端显式保存的模型优先于 .env 里的 KAMA_LLM_DEFAULT_MODEL 默认值
        os.environ["SZTU_LLM_DEFAULT_MODEL"] = model
    if permission_mode in {"normal", "accept_edits", "plan", "auto"}:
        config.permission.mode = str(permission_mode)
    if isinstance(value.get("base_url"), str):
        config.llm.base_url = value["base_url"]
    if isinstance(value.get("api_key"), str):
        config.llm.api_key = value["api_key"]
    if isinstance(value.get("api_key_env"), str):
        config.llm.api_key_env = value["api_key_env"]
    # 免 key 标志持久化：重启后仍能正确识别 Zen 等免 key 端点，避免泄漏环境里的通用 key
    if isinstance(value.get("keyless"), bool):
        config.llm.keyless = value["keyless"]
    for name in ("context_window", "max_output_tokens", "max_retries"):
        field_value = value.get(name)
        if isinstance(field_value, int):
            setattr(config.llm, name, field_value)
    for name in ("temperature", "top_p", "timeout_s"):
        field_value = value.get(name)
        if isinstance(field_value, (int, float)) and not isinstance(field_value, bool):
            setattr(config.llm, name, float(field_value))
    if isinstance(value.get("reasoning_effort"), str):
        config.llm.reasoning_effort = value["reasoning_effort"]
    if isinstance(value.get("cache_control"), bool):
        config.llm.cache_control = value["cache_control"]
    # TUI 明暗主题与壁纸选择：客户端设置优先于 TOML（用户即时切换后落盘到这里）
    tui_settings = value.get("tui")
    if isinstance(tui_settings, dict):
        if isinstance(tui_settings.get("theme"), str) and tui_settings["theme"] in TUI_THEME_NAMES:
            config.tui.theme = tui_settings["theme"]
        if (
            isinstance(tui_settings.get("wallpaper"), str)
            and tui_settings["wallpaper"] in TUI_WALLPAPER_NAMES
        ):
            config.tui.wallpaper = tui_settings["wallpaper"]


def load_model_profiles() -> tuple[list[dict[str, Any]], str]:
    value = _read_client_settings()
    profiles = value.get("models")
    normalized: list[dict[str, Any]] = []
    if isinstance(profiles, list):
        for item in profiles:
            if not isinstance(item, dict):
                continue
            profile = dict(item)
            profile["api_format"] = normalize_api_format(
                profile.get("api_format"), profile.get("provider")
            )
            profile["provider"] = provider_for_api_format(profile["api_format"])
            normalized.append(profile)
    return normalized, str(value.get("active_model_id", "") or "")


def save_client_settings(
    config: SztuConfig,
    *,
    models: list[dict[str, Any]] | None = None,
    active_model_id: str | None = None,
) -> Path:
    """持久化桌面可编辑字段；base_url/api_key 为导入的本地凭证（与 cc-switch 同级明文存储）"""
    path = _client_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    value = _read_client_settings()
    value.update(
        {
            "provider": config.llm.provider,
            "api_format": config.llm.api_format,
            "model": config.llm.default_model,
            "permission_mode": config.permission.mode,
            "base_url": config.llm.base_url,
            "api_key": config.llm.api_key,
            "api_key_env": config.llm.api_key_env,
            "keyless": config.llm.keyless,
            "context_window": config.llm.context_window,
            "max_output_tokens": config.llm.max_output_tokens,
            "temperature": config.llm.temperature,
            "top_p": config.llm.top_p,
            "reasoning_effort": config.llm.reasoning_effort,
            "timeout_s": config.llm.timeout_s,
            "max_retries": config.llm.max_retries,
            "cache_control": config.llm.cache_control,
        }
    )
    if models is not None:
        value["models"] = models
    if active_model_id is not None:
        value["active_model_id"] = active_model_id
    value["tui"] = {"theme": config.tui.theme, "wallpaper": config.tui.wallpaper}
    temporary.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


# 仅持久化 TUI 的明暗主题与壁纸选择（不动 LLM 等其余设置），返回写入的路径
def save_tui_settings(theme: str | None = None, wallpaper: str | None = None) -> Path:
    path = _client_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    value = _read_client_settings()
    tui = value.get("tui")
    if not isinstance(tui, dict):
        tui = {}
    if theme is not None and theme in TUI_THEME_NAMES:
        tui["theme"] = theme
    if wallpaper is not None and wallpaper in TUI_WALLPAPER_NAMES:
        tui["wallpaper"] = wallpaper
    value["tui"] = tui
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


# 将已解析的 TOML 根表写入 config；未知小节或类型错误时退出进程
def _apply_toml(config: SztuConfig, data: dict[str, Any]) -> None:
    unknown = set(data.keys()) - {
        "core",
        "logging",
        "agent",
        "llm",
        "trace",
        "permission",
        "compaction",
        "offload",
        "budget",
        "workflow",
        "mcp",
        "tui",
    }
    if unknown:
        raise SystemExit(f"Unknown top-level config keys: {', '.join(sorted(unknown))}")

    if "core" in data:
        core = data["core"]
        if not isinstance(core, dict):
            raise SystemExit("Config error: [core] must be a table")
        unknown_core: set[str] = set(core.keys()) - {"host", "port"}
        if unknown_core:
            raise SystemExit(f"Unknown [core] keys: {', '.join(sorted(unknown_core))}")
        if "host" in core:
            val = core["host"]
            if not isinstance(val, str):
                raise SystemExit("Config error: core.host must be a string")
            config.host = val
        if "port" in core:
            val = core["port"]
            if not isinstance(val, int):
                raise SystemExit("Config error: core.port must be an integer")
            config.port = val

    if "logging" in data:
        log = data["logging"]
        if not isinstance(log, dict):
            raise SystemExit("Config error: [logging] must be a table")
        unknown_log: set[str] = set(log.keys()) - {"level", "file", "format"}
        if unknown_log:
            raise SystemExit(f"Unknown [logging] keys: {', '.join(sorted(unknown_log))}")
        for key in ("level", "file", "format"):
            if key in log:
                val = log[key]
                if not isinstance(val, str):
                    raise SystemExit(f"Config error: logging.{key} must be a string")
                setattr(config.logging, key, val)

    if "agent" in data:
        agent = data["agent"]
        if not isinstance(agent, dict):
            raise SystemExit("Config error: [agent] must be a table")
        unknown_agent: set[str] = set(agent.keys()) - {
            "max_steps", "wrap_up_on_max_steps", "grace_step_on_max_steps",
            "stuck_max_failures", "stuck_max_total", "tool_max_concurrency",
            "require_verification", "verification_check_timeout_s",
            "max_repair_attempts",
        }
        if unknown_agent:
            raise SystemExit(f"Unknown [agent] keys: {', '.join(sorted(unknown_agent))}")
        if "max_steps" in agent:
            val = agent["max_steps"]
            if not isinstance(val, int) or val < 0:
                raise SystemExit(
                    "Config error: agent.max_steps must be a non-negative integer "
                    "(0 = unlimited)"
                )
            config.agent.max_steps = val
        if "wrap_up_on_max_steps" in agent:
            val = agent["wrap_up_on_max_steps"]
            if not isinstance(val, bool):
                raise SystemExit("Config error: agent.wrap_up_on_max_steps must be a boolean")
            config.agent.wrap_up_on_max_steps = val
        if "grace_step_on_max_steps" in agent:
            val = agent["grace_step_on_max_steps"]
            if not isinstance(val, bool):
                raise SystemExit("Config error: agent.grace_step_on_max_steps must be a boolean")
            config.agent.grace_step_on_max_steps = val
        for _key in ("stuck_max_failures", "stuck_max_total"):
            if _key in agent:
                val = agent[_key]
                if not isinstance(val, int) or val < 0:
                    raise SystemExit(f"Config error: agent.{_key} must be a non-negative integer")
                setattr(config.agent, _key, val)
        if "tool_max_concurrency" in agent:
            val = agent["tool_max_concurrency"]
            if not isinstance(val, int) or isinstance(val, bool) or val < 1:
                raise SystemExit(
                    "Config error: agent.tool_max_concurrency must be an integer >= 1"
                )
            config.agent.tool_max_concurrency = val
        if "require_verification" in agent:
            val = agent["require_verification"]
            if not isinstance(val, bool):
                raise SystemExit("Config error: agent.require_verification must be a boolean")
            config.agent.require_verification = val
        if "verification_check_timeout_s" in agent:
            val = agent["verification_check_timeout_s"]
            if not isinstance(val, int) or isinstance(val, bool) or val < 1:
                raise SystemExit(
                    "Config error: agent.verification_check_timeout_s must be an integer >= 1"
                )
            config.agent.verification_check_timeout_s = val
        if "max_repair_attempts" in agent:
            val = agent["max_repair_attempts"]
            if not isinstance(val, int) or isinstance(val, bool) or val < 0:
                raise SystemExit(
                    "Config error: agent.max_repair_attempts must be a non-negative integer"
                )
            config.agent.max_repair_attempts = val

    if "budget" in data:
        budget = data["budget"]
        if not isinstance(budget, dict):
            raise SystemExit("Config error: [budget] must be a table")
        unknown_budget: set[str] = set(budget.keys()) - {"max_tokens", "max_wall_clock_s"}
        if unknown_budget:
            raise SystemExit(f"Unknown [budget] keys: {', '.join(sorted(unknown_budget))}")
        for _key in ("max_tokens", "max_wall_clock_s"):
            if _key in budget:
                val = budget[_key]
                if not isinstance(val, int) or val < 0:
                    raise SystemExit(f"Config error: budget.{_key} must be a non-negative integer")
                setattr(config.budget, _key, val)

    if "workflow" in data:
        workflow = data["workflow"]
        if not isinstance(workflow, dict):
            raise SystemExit("Config error: [workflow] must be a table")
        allowed_workflow = {"max_concurrency", "max_depth", "max_retries"}
        unknown_workflow = set(workflow.keys()) - allowed_workflow
        if unknown_workflow:
            raise SystemExit(
                f"Unknown [workflow] keys: {', '.join(sorted(unknown_workflow))}"
            )
        for _key in allowed_workflow:
            if _key not in workflow:
                continue
            val = workflow[_key]
            minimum = 1 if _key == "max_concurrency" else 0
            if not isinstance(val, int) or val < minimum:
                raise SystemExit(
                    f"Config error: workflow.{_key} must be an integer >= {minimum}"
                )
            setattr(config.workflow, _key, val)

    if "llm" in data:
        llm = data["llm"]
        if not isinstance(llm, dict):
            raise SystemExit("Config error: [llm] must be a table")
        unknown_llm: set[str] = set(llm.keys()) - {
            "default_model",
            "provider",
            "api_format",
            "router",
            "context_window",
            "max_output_tokens",
            "temperature",
            "top_p",
            "reasoning_effort",
            "timeout_s",
            "max_retries",
            "cache_control",
        }
        if unknown_llm:
            raise SystemExit(f"Unknown [llm] keys: {', '.join(sorted(unknown_llm))}")
        if "default_model" in llm:
            val = llm["default_model"]
            if not isinstance(val, str):
                raise SystemExit("Config error: llm.default_model must be a string")
            config.llm.default_model = val
        if "provider" in llm:
            val = llm["provider"]
            if not isinstance(val, str) or val not in ("anthropic", "openai"):
                raise SystemExit(
                    "Config error: llm.provider must be 'anthropic' or 'openai'"
                )
            config.llm.provider = val
            if "api_format" not in llm:
                config.llm.api_format = normalize_api_format(None, val)
        if "api_format" in llm:
            val = llm["api_format"]
            if not isinstance(val, str) or val not in API_FORMATS:
                raise SystemExit(
                    "Config error: llm.api_format must be 'openai_chat_completions', "
                    "'anthropic_messages', or 'openai_responses'"
                )
            config.llm.api_format = val
            config.llm.provider = provider_for_api_format(val)
        if "router" in llm:
            val = llm["router"]
            if not isinstance(val, str):
                raise SystemExit("Config error: llm.router must be a string")
            config.llm.router = val
        if "context_window" in llm:
            val = llm["context_window"]
            if not isinstance(val, int) or val <= 0:
                raise SystemExit("Config error: llm.context_window must be a positive integer")
            config.llm.context_window = val
        for name in ("max_output_tokens", "max_retries"):
            if name not in llm:
                continue
            val = llm[name]
            minimum = 1 if name == "max_output_tokens" else 0
            if not isinstance(val, int) or val < minimum:
                raise SystemExit(f"Config error: llm.{name} must be an integer >= {minimum}")
            setattr(config.llm, name, val)
        for name in ("temperature", "top_p"):
            if name not in llm:
                continue
            val = llm[name]
            if not isinstance(val, (int, float)) or isinstance(val, bool) or not 0 <= val <= 1:
                raise SystemExit(f"Config error: llm.{name} must be between 0 and 1")
            setattr(config.llm, name, float(val))
        if "reasoning_effort" in llm:
            val = llm["reasoning_effort"]
            if val not in {"", "low", "medium", "high", "xhigh", "max"}:
                raise SystemExit("Config error: llm.reasoning_effort is invalid")
            config.llm.reasoning_effort = str(val)
        if "timeout_s" in llm:
            val = llm["timeout_s"]
            if not isinstance(val, (int, float)) or isinstance(val, bool) or val <= 0:
                raise SystemExit("Config error: llm.timeout_s must be a positive number")
            config.llm.timeout_s = float(val)
        if "cache_control" in llm:
            val = llm["cache_control"]
            if not isinstance(val, bool):
                raise SystemExit("Config error: llm.cache_control must be a boolean")
            config.llm.cache_control = val

    if "trace" in data:
        trace = data["trace"]
        if not isinstance(trace, dict):
            raise SystemExit("Config error: [trace] must be a table")
        unknown_trace: set[str] = set(trace.keys()) - {"enabled", "file", "include_llm_payload"}
        if unknown_trace:
            raise SystemExit(f"Unknown [trace] keys: {', '.join(sorted(unknown_trace))}")
        if "enabled" in trace:
            val = trace["enabled"]
            if not isinstance(val, bool):
                raise SystemExit("Config error: trace.enabled must be a boolean")
            config.trace.enabled = val
        if "file" in trace:
            val = trace["file"]
            if not isinstance(val, str):
                raise SystemExit("Config error: trace.file must be a string")
            config.trace.file = val
        if "include_llm_payload" in trace:
            val = trace["include_llm_payload"]
            if not isinstance(val, bool):
                raise SystemExit("Config error: trace.include_llm_payload must be a boolean")
            config.trace.include_llm_payload = val

    if "permission" in data:
        perm = data["permission"]
        if not isinstance(perm, dict):
            raise SystemExit("Config error: [permission] must be a table")
        unknown_perm: set[str] = set(perm.keys()) - {"timeout_s", "mode"}
        if unknown_perm:
            raise SystemExit(f"Unknown [permission] keys: {', '.join(sorted(unknown_perm))}")
        if "timeout_s" in perm:
            val = perm["timeout_s"]
            if not isinstance(val, (int, float)) or val < 0:
                raise SystemExit("Config error: permission.timeout_s must be a non-negative number")
            config.permission.timeout_s = float(val)
        if "mode" in perm:
            val = perm["mode"]
            if val not in {"normal", "accept_edits", "plan", "auto"}:
                raise SystemExit("Config error: permission.mode is invalid")
            config.permission.mode = str(val)

    if "compaction" in data:
        comp = data["compaction"]
        if not isinstance(comp, dict):
            raise SystemExit("Config error: [compaction] must be a table")
        unknown_comp: set[str] = set(comp.keys()) - {
            "auto_threshold",
            "auto_compact_min_tokens",
            "auto_compact_min_steps",
            "tool_result_limit",
            "tool_result_keep",
            "sliding_window_size",
            "compact_cooldown_steps",
            "circuit_breaker_max_failures",
        }
        if unknown_comp:
            raise SystemExit(f"Unknown [compaction] keys: {', '.join(sorted(unknown_comp))}")
        if "auto_threshold" in comp:
            val = comp["auto_threshold"]
            if not isinstance(val, (int, float)) or not (0.0 <= val <= 1.0):
                raise SystemExit("Config error: compaction.auto_threshold must be between 0 and 1")
            config.compaction.auto_threshold = float(val)
        for _key in ("auto_compact_min_tokens", "auto_compact_min_steps"):
            if _key in comp:
                val = comp[_key]
                if not isinstance(val, int) or val < 0:
                    raise SystemExit(
                        f"Config error: compaction.{_key} must be a non-negative integer"
                    )
                setattr(config.compaction, _key, val)
        if "tool_result_limit" in comp:
            val = comp["tool_result_limit"]
            if not isinstance(val, int) or val <= 0:
                raise SystemExit(
                    "Config error: compaction.tool_result_limit must be a positive integer"
                )
            config.compaction.tool_result_limit = val
        if "tool_result_keep" in comp:
            val = comp["tool_result_keep"]
            if not isinstance(val, int) or val <= 0:
                raise SystemExit(
                    "Config error: compaction.tool_result_keep must be a positive integer"
                )
            config.compaction.tool_result_keep = val
        _compaction_keys = (
            "sliding_window_size", "compact_cooldown_steps", "circuit_breaker_max_failures"
        )
        for _key in _compaction_keys:
            if _key in comp:
                val = comp[_key]
                if not isinstance(val, int) or val < 0:
                    raise SystemExit(
                        f"Config error: compaction.{_key} must be a non-negative integer"
                    )
                setattr(config.compaction, _key, val)

    if "offload" in data:
        off = data["offload"]
        if not isinstance(off, dict):
            raise SystemExit("Config error: [offload] must be a table")
        unknown_off: set[str] = set(off.keys()) - {
            "enabled", "min_chars", "min_lines", "force_tools", "summary_max_chars",
        }
        if unknown_off:
            raise SystemExit(f"Unknown [offload] keys: {', '.join(sorted(unknown_off))}")
        if "enabled" in off:
            val = off["enabled"]
            if not isinstance(val, bool):
                raise SystemExit("Config error: offload.enabled must be a boolean")
            config.offload.enabled = val
        if "min_chars" in off:
            val = off["min_chars"]
            if not isinstance(val, int) or val <= 0:
                raise SystemExit("Config error: offload.min_chars must be a positive integer")
            config.offload.min_chars = val
        if "min_lines" in off:
            val = off["min_lines"]
            if not isinstance(val, int) or val <= 0:
                raise SystemExit("Config error: offload.min_lines must be a positive integer")
            config.offload.min_lines = val
        if "force_tools" in off:
            val = off["force_tools"]
            if not isinstance(val, list) or not all(isinstance(t, str) for t in val):
                raise SystemExit("Config error: offload.force_tools must be a list of strings")
            config.offload.force_tools = val
        if "summary_max_chars" in off:
            val = off["summary_max_chars"]
            if not isinstance(val, int) or val <= 0:
                raise SystemExit(
                    "Config error: offload.summary_max_chars must be a positive integer"
                )
            config.offload.summary_max_chars = val

    if "mcp" in data:
        mcp = data["mcp"]
        if not isinstance(mcp, dict):
            raise SystemExit("Config error: [mcp] must be a table")
        unknown_mcp: set[str] = set(mcp.keys()) - {"servers"}
        if unknown_mcp:
            raise SystemExit(f"Unknown [mcp] keys: {', '.join(sorted(unknown_mcp))}")
        servers_raw = mcp.get("servers", [])
        if not isinstance(servers_raw, list):
            raise SystemExit("Config error: mcp.servers must be an array of tables")
        for i, srv in enumerate(servers_raw):
            if not isinstance(srv, dict):
                raise SystemExit(f"Config error: mcp.servers[{i}] must be a table")
            srv_name = srv.get("name")
            if not isinstance(srv_name, str) or not srv_name:
                raise SystemExit(f"Config error: mcp.servers[{i}].name must be a non-empty string")
            transport = srv.get("transport", "stdio")
            if transport not in ("stdio", "tcp"):
                raise SystemExit(
                    f"Config error: mcp.servers[{i}].transport must be 'stdio' or 'tcp'"
                )
            s = McpServerConfig(name=srv_name, transport=transport)
            if "command" in srv:
                val = srv["command"]
                if not isinstance(val, str):
                    raise SystemExit(f"Config error: mcp.servers[{i}].command must be a string")
                s.command = val
            if "args" in srv:
                val = srv["args"]
                if not isinstance(val, list):
                    raise SystemExit(f"Config error: mcp.servers[{i}].args must be an array")
                s.args = [str(a) for a in val]
            if "env" in srv:
                val = srv["env"]
                if not isinstance(val, dict):
                    raise SystemExit(f"Config error: mcp.servers[{i}].env must be a table")
                s.env = {str(k): str(v) for k, v in val.items()}
            if "host" in srv:
                val = srv["host"]
                if not isinstance(val, str):
                    raise SystemExit(f"Config error: mcp.servers[{i}].host must be a string")
                s.host = val
            if "port" in srv:
                val = srv["port"]
                if not isinstance(val, int):
                    raise SystemExit(f"Config error: mcp.servers[{i}].port must be an integer")
                s.port = val
            config.mcp.servers.append(s)

    if "tui" in data:
        tui = data["tui"]
        if not isinstance(tui, dict):
            raise SystemExit("Config error: [tui] must be a table")
        unknown_tui: set[str] = set(tui.keys()) - {"theme", "wallpaper"}
        if unknown_tui:
            raise SystemExit(f"Unknown [tui] keys: {', '.join(sorted(unknown_tui))}")
        if "theme" in tui:
            val = tui["theme"]
            if not isinstance(val, str) or val not in TUI_THEME_NAMES:
                raise SystemExit(
                    f"Config error: tui.theme must be one of {', '.join(TUI_THEME_NAMES)}"
                )
            config.tui.theme = val
        if "wallpaper" in tui:
            val = tui["wallpaper"]
            if not isinstance(val, str) or val not in TUI_WALLPAPER_NAMES:
                raise SystemExit(
                    f"Config error: tui.wallpaper must be one of {', '.join(TUI_WALLPAPER_NAMES)}"
                )
            config.tui.wallpaper = val


# 用 SZTU_* 环境变量覆盖 config 中对应字段（若变量已设置）
def _apply_env(config: SztuConfig) -> None:
    host = os.environ.get("SZTU_HOST")
    if host is not None:
        config.host = host

    port_str = os.environ.get("SZTU_PORT")
    if port_str is not None:
        try:
            config.port = int(port_str)
        except ValueError:
            raise SystemExit(f"Config error: SZTU_PORT must be an integer, got: {port_str!r}")

    log_level = os.environ.get("SZTU_LOG_LEVEL")
    if log_level is not None:
        config.logging.level = log_level

    log_file = os.environ.get("SZTU_LOG_FILE")
    if log_file is not None:
        config.logging.file = log_file

    log_format = os.environ.get("SZTU_LOG_FORMAT")
    if log_format is not None:
        config.logging.format = log_format

    max_steps_str = os.environ.get("SZTU_MAX_STEPS")
    if max_steps_str is not None:
        try:
            val = int(max_steps_str)
            if val < 0:
                raise SystemExit(
                    "Config error: SZTU_MAX_STEPS must be a non-negative integer "
                    f"(0 = unlimited), got: {max_steps_str!r}"
                )
            config.agent.max_steps = val
        except ValueError:
            raise SystemExit(
                f"Config error: SZTU_MAX_STEPS must be an integer, got: {max_steps_str!r}"
            )

    # wrap-up / 结语宽限步 / stuck-loop 环境变量
    wrap_up_str = os.environ.get("SZTU_WRAP_UP_ON_MAX_STEPS")
    if wrap_up_str is not None:
        config.agent.wrap_up_on_max_steps = wrap_up_str.lower() not in ("0", "false", "no")
    grace_str = os.environ.get("SZTU_GRACE_STEP_ON_MAX_STEPS")
    if grace_str is not None:
        config.agent.grace_step_on_max_steps = grace_str.lower() not in ("0", "false", "no")
    for _env, _attr in (
        ("SZTU_STUCK_MAX_FAILURES", "stuck_max_failures"),
        ("SZTU_STUCK_MAX_TOTAL", "stuck_max_total"),
    ):
        _str = os.environ.get(_env)
        if _str is not None:
            try:
                val = int(_str)
                if val < 0:
                    raise SystemExit(
                        f"Config error: {_env} must be a non-negative integer, got: {_str!r}"
                    )
                setattr(config.agent, _attr, val)
            except ValueError:
                raise SystemExit(
                    f"Config error: {_env} must be an integer, got: {_str!r}"
                )

    tool_concurrency_str = os.environ.get("SZTU_TOOL_MAX_CONCURRENCY")
    if tool_concurrency_str is not None:
        try:
            tool_concurrency = int(tool_concurrency_str)
        except ValueError:
            raise SystemExit(
                "Config error: SZTU_TOOL_MAX_CONCURRENCY must be an integer, "
                f"got: {tool_concurrency_str!r}"
            )
        if tool_concurrency < 1:
            raise SystemExit(
                "Config error: SZTU_TOOL_MAX_CONCURRENCY must be >= 1, "
                f"got: {tool_concurrency_str!r}"
            )
        config.agent.tool_max_concurrency = tool_concurrency

    # --- 完成契约验证环境变量 ---
    require_verification_str = os.environ.get("SZTU_REQUIRE_VERIFICATION")
    if require_verification_str is not None:
        config.agent.require_verification = (
            require_verification_str.lower() not in ("0", "false", "no")
        )

    verification_timeout_str = os.environ.get("SZTU_VERIFICATION_CHECK_TIMEOUT_S")
    if verification_timeout_str is not None:
        try:
            verification_timeout = int(verification_timeout_str)
        except ValueError:
            raise SystemExit(
                "Config error: SZTU_VERIFICATION_CHECK_TIMEOUT_S must be an integer, "
                f"got: {verification_timeout_str!r}"
            )
        if verification_timeout < 1:
            raise SystemExit(
                "Config error: SZTU_VERIFICATION_CHECK_TIMEOUT_S must be >= 1, "
                f"got: {verification_timeout_str!r}"
            )
        config.agent.verification_check_timeout_s = verification_timeout

    max_repair_attempts_str = os.environ.get("SZTU_MAX_REPAIR_ATTEMPTS")
    if max_repair_attempts_str is not None:
        try:
            max_repair_attempts = int(max_repair_attempts_str)
        except ValueError:
            raise SystemExit(
                "Config error: SZTU_MAX_REPAIR_ATTEMPTS must be an integer, "
                f"got: {max_repair_attempts_str!r}"
            )
        if max_repair_attempts < 0:
            raise SystemExit(
                "Config error: SZTU_MAX_REPAIR_ATTEMPTS must be >= 0, "
                f"got: {max_repair_attempts_str!r}"
            )
        config.agent.max_repair_attempts = max_repair_attempts

    # --- 多智能体工作流环境变量 ---
    for _env, _attr, _minimum in (
        ("SZTU_WORKFLOW_MAX_CONCURRENCY", "max_concurrency", 1),
        ("SZTU_WORKFLOW_MAX_DEPTH", "max_depth", 0),
        ("SZTU_WORKFLOW_MAX_RETRIES", "max_retries", 0),
    ):
        _str = os.environ.get(_env)
        if _str is None:
            continue
        try:
            val = int(_str)
        except ValueError:
            raise SystemExit(f"Config error: {_env} must be an integer, got: {_str!r}")
        if val < _minimum:
            raise SystemExit(
                f"Config error: {_env} must be >= {_minimum}, got: {_str!r}"
            )
        setattr(config.workflow, _attr, val)

    llm_provider = os.environ.get("SZTU_LLM_PROVIDER")
    if llm_provider is not None:
        if llm_provider not in ("anthropic", "openai"):
            raise SystemExit(
                    "Config error: SZTU_LLM_PROVIDER must be 'anthropic' or 'openai',"
                    f" got: {llm_provider!r}"
                )
        config.llm.provider = llm_provider
        if os.environ.get("SZTU_LLM_API_FORMAT") is None:
            config.llm.api_format = normalize_api_format(None, llm_provider)

    llm_api_format = os.environ.get("SZTU_LLM_API_FORMAT")
    if llm_api_format is not None:
        if llm_api_format not in API_FORMATS:
            raise SystemExit(
                "Config error: SZTU_LLM_API_FORMAT must be a supported API format, "
                f"got: {llm_api_format!r}"
            )
        config.llm.api_format = llm_api_format
        config.llm.provider = provider_for_api_format(llm_api_format)

    # SZTU_* is the supported name. Keep the original KAMA name so existing
    # project .env files remain valid while migrating to the SztuCode prefix.
    default_model = os.environ.get(
        "SZTU_LLM_DEFAULT_MODEL", os.environ.get("KAMA_LLM_DEFAULT_MODEL")
    )
    if default_model is not None:
        config.llm.default_model = default_model

    trace_enabled = os.environ.get("SZTU_TRACE_ENABLED")
    if trace_enabled is not None:
        config.trace.enabled = trace_enabled.lower() not in ("0", "false", "no")

    trace_file = os.environ.get("SZTU_TRACE_FILE")
    if trace_file is not None:
        config.trace.file = trace_file

    trace_payload = os.environ.get("SZTU_TRACE_INCLUDE_LLM_PAYLOAD")
    if trace_payload is not None:
        config.trace.include_llm_payload = trace_payload.lower() not in ("0", "false", "no")

    perm_timeout = os.environ.get("SZTU_PERMISSION_TIMEOUT_S")
    if perm_timeout is not None:
        try:
            perm_timeout_val = float(perm_timeout)
            if perm_timeout_val < 0:
                raise SystemExit(
                    f"Config error: SZTU_PERMISSION_TIMEOUT_S must be >= 0, got: {perm_timeout!r}"
                )
            config.permission.timeout_s = perm_timeout_val
        except ValueError:
            raise SystemExit(
                f"Config error: SZTU_PERMISSION_TIMEOUT_S must be a number, got: {perm_timeout!r}"
            )

    permission_mode = os.environ.get("SZTU_PERMISSION_MODE")
    if permission_mode is not None:
        if permission_mode not in {"normal", "accept_edits", "plan", "auto"}:
            raise SystemExit(f"Config error: SZTU_PERMISSION_MODE is invalid: {permission_mode!r}")
        config.permission.mode = permission_mode

    llm_context_window = os.environ.get("SZTU_LLM_CONTEXT_WINDOW")
    if llm_context_window is not None:
        try:
            llm_context_window_val = int(llm_context_window)
            if llm_context_window_val <= 0:
                raise SystemExit(
                    "Config error: SZTU_LLM_CONTEXT_WINDOW must be a positive "
                    f"integer, got: {llm_context_window!r}"
                )
            config.llm.context_window = llm_context_window_val
        except ValueError:
            raise SystemExit(
                "Config error: SZTU_LLM_CONTEXT_WINDOW must be an integer, "
                f"got: {llm_context_window!r}"
            )

    llm_cache_control = os.environ.get("SZTU_LLM_CACHE_CONTROL")
    if llm_cache_control is not None:
        config.llm.cache_control = llm_cache_control.lower() not in ("0", "false", "no")

    for env_name, attr, minimum in (
        ("SZTU_LLM_MAX_OUTPUT_TOKENS", "max_output_tokens", 1),
        ("SZTU_LLM_MAX_RETRIES", "max_retries", 0),
    ):
        raw = os.environ.get(env_name)
        if raw is None:
            continue
        try:
            value: int | float = int(raw)
        except ValueError:
            raise SystemExit(f"Config error: {env_name} must be an integer, got: {raw!r}")
        if value < minimum:
            raise SystemExit(f"Config error: {env_name} must be >= {minimum}, got: {raw!r}")
        setattr(config.llm, attr, value)

    for env_name, attr in (
        ("SZTU_LLM_TEMPERATURE", "temperature"),
        ("SZTU_LLM_TOP_P", "top_p"),
    ):
        raw = os.environ.get(env_name)
        if raw is None:
            continue
        try:
            value = float(raw)
        except ValueError:
            raise SystemExit(f"Config error: {env_name} must be a number, got: {raw!r}")
        if not 0 <= value <= 1:
            raise SystemExit(f"Config error: {env_name} must be between 0 and 1")
        setattr(config.llm, attr, value)

    reasoning_effort = os.environ.get("SZTU_LLM_REASONING_EFFORT")
    if reasoning_effort is not None:
        if reasoning_effort not in {"", "low", "medium", "high", "xhigh", "max"}:
            raise SystemExit("Config error: SZTU_LLM_REASONING_EFFORT is invalid")
        config.llm.reasoning_effort = reasoning_effort

    timeout_raw = os.environ.get("SZTU_LLM_TIMEOUT_S")
    if timeout_raw is not None:
        try:
            timeout = float(timeout_raw)
        except ValueError:
            raise SystemExit(
                f"Config error: SZTU_LLM_TIMEOUT_S must be a number, got: {timeout_raw!r}"
            )
        if timeout <= 0:
            raise SystemExit("Config error: SZTU_LLM_TIMEOUT_S must be positive")
        config.llm.timeout_s = timeout

    compact_threshold = os.environ.get("SZTU_COMPACT_THRESHOLD")
    if compact_threshold is not None:
        try:
            compact_threshold_val = float(compact_threshold)
            if not (0.0 <= compact_threshold_val <= 1.0):
                raise SystemExit(
                    "Config error: SZTU_COMPACT_THRESHOLD must be between 0 and 1, "
                    f"got: {compact_threshold!r}"
                )
            config.compaction.auto_threshold = compact_threshold_val
        except ValueError:
            raise SystemExit(
                "Config error: SZTU_COMPACT_THRESHOLD must be a number, "
                f"got: {compact_threshold!r}"
            )

    compact_tool_limit = os.environ.get("SZTU_COMPACT_TOOL_LIMIT")
    if compact_tool_limit is not None:
        try:
            compact_tool_limit_val = int(compact_tool_limit)
            if compact_tool_limit_val <= 0:
                raise SystemExit(
                    "Config error: SZTU_COMPACT_TOOL_LIMIT must be a positive integer, "
                    f"got: {compact_tool_limit!r}"
                )
            config.compaction.tool_result_limit = compact_tool_limit_val
        except ValueError:
            raise SystemExit(
                "Config error: SZTU_COMPACT_TOOL_LIMIT must be an integer, "
                f"got: {compact_tool_limit!r}"
            )

    compact_tool_keep = os.environ.get("SZTU_COMPACT_TOOL_KEEP")
    if compact_tool_keep is not None:
        try:
            compact_tool_keep_val = int(compact_tool_keep)
            if compact_tool_keep_val <= 0:
                raise SystemExit(
                    "Config error: SZTU_COMPACT_TOOL_KEEP must be a positive integer, "
                    f"got: {compact_tool_keep!r}"
                )
            config.compaction.tool_result_keep = compact_tool_keep_val
        except ValueError:
            raise SystemExit(
                "Config error: SZTU_COMPACT_TOOL_KEEP must be an integer, "
                f"got: {compact_tool_keep!r}"
            )

    for _env, _attr in (
        ("SZTU_COMPACT_MIN_TOKENS", "auto_compact_min_tokens"),
        ("SZTU_COMPACT_MIN_STEPS", "auto_compact_min_steps"),
        ("SZTU_SLIDING_WINDOW_SIZE", "sliding_window_size"),
        ("SZTU_COMPACT_COOLDOWN", "compact_cooldown_steps"),
        ("SZTU_COMPACT_CIRCUIT_BREAKER", "circuit_breaker_max_failures"),
    ):
        _str = os.environ.get(_env)
        if _str is not None:
            try:
                val = int(_str)
                if val < 0:
                    raise SystemExit(
                        f"Config error: {_env} must be a non-negative integer, got: {_str!r}"
                    )
                setattr(config.compaction, _attr, val)
            except ValueError:
                raise SystemExit(
                    f"Config error: {_env} must be an integer, got: {_str!r}"
                )

    # --- 上下文卸载环境变量 ---
    offload_enabled = os.environ.get("SZTU_OFFLOAD_ENABLED")
    if offload_enabled is not None:
        config.offload.enabled = offload_enabled.lower() not in ("0", "false", "no")

    offload_min_chars = os.environ.get("SZTU_OFFLOAD_MIN_CHARS")
    if offload_min_chars is not None:
        try:
            offload_min_chars_val = int(offload_min_chars)
            if offload_min_chars_val <= 0:
                raise SystemExit(
                    "Config error: SZTU_OFFLOAD_MIN_CHARS must be a positive integer, "
                    f"got: {offload_min_chars!r}"
                )
            config.offload.min_chars = offload_min_chars_val
        except ValueError:
            raise SystemExit(
                "Config error: SZTU_OFFLOAD_MIN_CHARS must be an integer, "
                f"got: {offload_min_chars!r}"
            )

    offload_min_lines = os.environ.get("SZTU_OFFLOAD_MIN_LINES")
    if offload_min_lines is not None:
        try:
            offload_min_lines_val = int(offload_min_lines)
            if offload_min_lines_val <= 0:
                raise SystemExit(
                    "Config error: SZTU_OFFLOAD_MIN_LINES must be a positive integer, "
                    f"got: {offload_min_lines!r}"
                )
            config.offload.min_lines = offload_min_lines_val
        except ValueError:
            raise SystemExit(
                "Config error: SZTU_OFFLOAD_MIN_LINES must be an integer, "
                f"got: {offload_min_lines!r}"
            )

    # --- 运行预算环境变量 ---
    for _env, _attr in (
        ("SZTU_BUDGET_MAX_TOKENS", "max_tokens"),
        ("SZTU_BUDGET_MAX_WALL_CLOCK_S", "max_wall_clock_s"),
    ):
        _str = os.environ.get(_env)
        if _str is not None:
            try:
                val = int(_str)
                if val < 0:
                    raise SystemExit(
                        f"Config error: {_env} must be a non-negative integer, got: {_str!r}"
                    )
                setattr(config.budget, _attr, val)
            except ValueError:
                raise SystemExit(
                    f"Config error: {_env} must be an integer, got: {_str!r}"
                )
