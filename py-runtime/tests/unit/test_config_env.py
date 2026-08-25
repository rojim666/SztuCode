from __future__ import annotations

from pathlib import Path

import pytest

from sztu_code.core.config import get_config


def _write_env(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


# 功能：验证 .env 文件中的值被正确加载并覆盖内建默认值
# 设计：写 .env 到临时目录并 chdir 进去，清除同名系统环境变量排除干扰，确认 .env 加载路径有效
def test_dotenv_base_loaded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file, "SZTU_PORT=9999\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SZTU_PORT", raising=False)

    cfg = get_config()

    assert cfg.port == 9999


# 功能：验证系统环境变量的优先级高于 .env 文件中的值
# 设计：.env 写 9999，系统环境变量写 8888，确认最终值为 8888，对应四级优先链的顶层约束
def test_system_env_overrides_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    _write_env(env_file, "SZTU_PORT=9999\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SZTU_PORT", "8888")

    cfg = get_config()

    assert cfg.port == 8888


# 功能：验证 .env 文件不存在时静默跳过，使用内建默认值（不抛异常）
# 设计：chdir 到空目录，清除系统环境变量，确认 get_config() 不因 .env 缺失而崩溃，默认端口为 7437
def test_missing_env_file_silent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SZTU_PORT", raising=False)

    cfg = get_config()

    assert cfg.port == 7437


def test_model_is_empty_when_no_model_environment_variable_is_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SZTU_CLIENT_SETTINGS", str(tmp_path / "missing-settings.json"))
    monkeypatch.setenv("SZTU_CONFIG", str(tmp_path / "missing-config.toml"))
    monkeypatch.delenv("SZTU_LLM_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("KAMA_LLM_DEFAULT_MODEL", raising=False)

    cfg = get_config()

    assert cfg.llm.default_model == ""


def test_legacy_kama_model_environment_variable_is_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_env(tmp_path / ".env", "KAMA_LLM_DEFAULT_MODEL=legacy-model\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SZTU_CLIENT_SETTINGS", str(tmp_path / "missing-settings.json"))
    monkeypatch.setenv("SZTU_CONFIG", str(tmp_path / "missing-config.toml"))
    monkeypatch.delenv("SZTU_LLM_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("KAMA_LLM_DEFAULT_MODEL", raising=False)

    cfg = get_config()

    assert cfg.llm.default_model == "legacy-model"


def test_sztu_model_environment_variable_takes_priority_over_legacy_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_env(
        tmp_path / ".env",
        "KAMA_LLM_DEFAULT_MODEL=legacy-model\nSZTU_LLM_DEFAULT_MODEL=sztu-model\n",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SZTU_CLIENT_SETTINGS", str(tmp_path / "missing-settings.json"))
    monkeypatch.setenv("SZTU_CONFIG", str(tmp_path / "missing-config.toml"))
    monkeypatch.delenv("KAMA_LLM_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("SZTU_LLM_DEFAULT_MODEL", raising=False)

    cfg = get_config()

    assert cfg.llm.default_model == "sztu-model"


# 功能：验证 .env 中设置的 SZTU_CONFIG 能正确影响 TOML 配置文件的加载路径
# 设计：.env 指向自定义 TOML 文件，TOML 中写入不同端口，确认 .env 在 TOML 加载前被读取（优先级链的正确顺序）
def test_dotenv_before_toml_kama_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    toml_path = tmp_path / "custom.toml"
    toml_path.write_bytes(b'[core]\nport = 5555\n')

    env_file = tmp_path / ".env"
    _write_env(env_file, f"SZTU_CONFIG={toml_path}\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SZTU_CONFIG", raising=False)
    monkeypatch.delenv("SZTU_PORT", raising=False)

    cfg = get_config()

    assert cfg.port == 5555


# 功能：验证同一变量经过完整四级优先链后，最终值为最高优先级来源（系统环境变量）
# 设计：同时设置默认值(7437)/TOML(6000)/.env(7000)/系统环境变量(8000)，确认最终值为 8000，是优先级链的综合正确性验证
def test_priority_chain_full(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 默认值：7437
    # TOML：6000
    # .env：7000
    # 系统环境变量：8000（最高）
    toml_path = tmp_path / "sztu.toml"
    toml_path.write_bytes(b'[core]\nport = 6000\n')

    env_file = tmp_path / ".env"
    _write_env(env_file, "SZTU_PORT=7000\n")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SZTU_CONFIG", str(toml_path))
    monkeypatch.setenv("SZTU_PORT", "8000")

    cfg = get_config()

    assert cfg.port == 8000


# 功能：验证 [budget] TOML 段的 max_tokens/max_wall_clock_s 被解析
# 设计：写含 [budget] 的 TOML 并通过 SZTU_CONFIG 加载，断言两个字段值
def test_budget_toml_parsed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    toml_path = tmp_path / "sztu.toml"
    toml_path.write_bytes(b"[budget]\nmax_tokens = 1234\nmax_wall_clock_s = 60\n")
    monkeypatch.setenv("SZTU_CONFIG", str(toml_path))
    cfg = get_config()
    assert cfg.budget.max_tokens == 1234
    assert cfg.budget.max_wall_clock_s == 60


# 功能：验证 [agent] 的收尾/结语/卡死键被解析
# 设计：写含新键的 TOML，断言 wrap_up/grace_step/stuck_max_failures/stuck_max_total
def test_agent_budget_keys_toml_parsed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    toml_path = tmp_path / "sztu.toml"
    toml_path.write_bytes(
        b"[agent]\nwrap_up_on_max_steps = false\n"
        b"grace_step_on_max_steps = false\n"
        b"stuck_max_failures = 5\nstuck_max_total = 2\n"
    )
    monkeypatch.setenv("SZTU_CONFIG", str(toml_path))
    cfg = get_config()
    assert cfg.agent.wrap_up_on_max_steps is False
    assert cfg.agent.grace_step_on_max_steps is False
    assert cfg.agent.stuck_max_failures == 5
    assert cfg.agent.stuck_max_total == 2


# 功能：验证 Agent 工具并发上限支持 TOML 与环境变量配置并由环境变量覆盖
# 设计：先加载 agent.tool_max_concurrency，再设置同名 SZTU 环境变量，覆盖配置传播的两条入口
def test_agent_tool_concurrency_config_parsed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    toml_path = tmp_path / "sztu.toml"
    toml_path.write_bytes(b"[agent]\ntool_max_concurrency = 3\n")
    monkeypatch.setenv("SZTU_CONFIG", str(toml_path))
    cfg = get_config()
    assert cfg.agent.tool_max_concurrency == 3

    monkeypatch.setenv("SZTU_TOOL_MAX_CONCURRENCY", "5")
    cfg = get_config()
    assert cfg.agent.tool_max_concurrency == 5


# 功能：验证 Agent 工具并发上限拒绝零值和非整数
# 设计：分别覆盖 TOML 与环境变量的无效边界，防止配置为零导致调度器永远无法取得执行槽
@pytest.mark.parametrize("source", ["toml", "env"])
def test_agent_tool_concurrency_rejects_invalid_values(
    source: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if source == "toml":
        toml_path = tmp_path / "sztu.toml"
        toml_path.write_bytes(b"[agent]\ntool_max_concurrency = 0\n")
        monkeypatch.setenv("SZTU_CONFIG", str(toml_path))
    else:
        monkeypatch.setenv("SZTU_TOOL_MAX_CONCURRENCY", "not-an-int")

    with pytest.raises(SystemExit):
        get_config()


# 功能：验证 SZTU_GRACE_STEP_ON_MAX_STEPS 环境变量可关闭结语宽限步
# 设计：设 env=false，断言 get_config 读到 False；未设置时保持默认 True
def test_grace_step_env_var_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SZTU_GRACE_STEP_ON_MAX_STEPS", "false")
    cfg = get_config()
    assert cfg.agent.grace_step_on_max_steps is False
    monkeypatch.delenv("SZTU_GRACE_STEP_ON_MAX_STEPS")
    cfg = get_config()
    assert cfg.agent.grace_step_on_max_steps is True


# 功能：验证 max_steps 默认值为 100（硬止损），TOML 显式写 0 可恢复不限
# 设计：默认 100 提供软着陆；用户显式设 0 仍为不限（0 语义保留）
def test_max_steps_default_unlimited(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SZTU_MAX_STEPS", raising=False)
    cfg = get_config()
    assert cfg.agent.max_steps == 100  # 新默认：硬止损，而非 0 不限
    # 用户显式设 0 仍为不限步数
    toml_path = tmp_path / "sztu.toml"
    toml_path.write_bytes(b"[agent]\nmax_steps = 0\n")
    monkeypatch.setenv("SZTU_CONFIG", str(toml_path))
    cfg = get_config()
    assert cfg.agent.max_steps == 0


# 功能：验证 SZTU_MAX_STEPS 允许 0（不限），负数才报错
# 设计：env=0 读到 0；env=-1 抛 SystemExit
def test_max_steps_env_accepts_zero_rejects_negative(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SZTU_MAX_STEPS", "0")
    cfg = get_config()
    assert cfg.agent.max_steps == 0
    monkeypatch.setenv("SZTU_MAX_STEPS", "-1")
    with pytest.raises(SystemExit):
        get_config()


# 功能：验证 SZTU_BUDGET_* 环境变量仍可读取旧配置（但主 Agent 不再使用 Token 上限）
# 设计：直接设环境变量，断言 get_config 读到对应值
def test_budget_env_vars_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SZTU_BUDGET_MAX_TOKENS", "999")
    monkeypatch.setenv("SZTU_BUDGET_MAX_WALL_CLOCK_S", "42")
    cfg = get_config()
    assert cfg.budget.max_tokens == 999
    assert cfg.budget.max_wall_clock_s == 42


# 功能：未知 [budget] 键应导致配置退出
# 设计：写含 foo 键的 TOML，断言抛出 SystemExit
def test_unknown_budget_key_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    toml_path = tmp_path / "sztu.toml"
    toml_path.write_bytes(b"[budget]\nfoo = 1\n")
    monkeypatch.setenv("SZTU_CONFIG", str(toml_path))
    with pytest.raises(SystemExit):
        get_config()


# 功能：验证 [workflow] TOML 段会解析并发、深度和重试预算
# 设计：一次写入三个边界不同的整数，断言配置对象完整承载而非只支持部分字段
def test_workflow_toml_parsed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    toml_path = tmp_path / "sztu.toml"
    toml_path.write_bytes(
        b"[workflow]\nmax_concurrency = 3\nmax_depth = 1\nmax_retries = 2\n"
    )
    monkeypatch.setenv("SZTU_CONFIG", str(toml_path))
    cfg = get_config()
    assert cfg.workflow.max_concurrency == 3
    assert cfg.workflow.max_depth == 1
    assert cfg.workflow.max_retries == 2


# 功能：验证 SZTU_WORKFLOW_* 环境变量覆盖工作流默认预算
# 设计：设置三个独立环境变量并读取配置，覆盖环境解析循环的全部字段
def test_workflow_env_vars_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SZTU_WORKFLOW_MAX_CONCURRENCY", "6")
    monkeypatch.setenv("SZTU_WORKFLOW_MAX_DEPTH", "3")
    monkeypatch.setenv("SZTU_WORKFLOW_MAX_RETRIES", "4")
    cfg = get_config()
    assert cfg.workflow.max_concurrency == 6
    assert cfg.workflow.max_depth == 3
    assert cfg.workflow.max_retries == 4


# 功能：验证工作流并发数不能为零而深度和重试允许为零
# 设计：只设置非法并发环境变量并断言 SystemExit，锁定最容易造成调度死锁的配置边界
def test_workflow_concurrency_rejects_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SZTU_WORKFLOW_MAX_CONCURRENCY", "0")
    with pytest.raises(SystemExit):
        get_config()


# ============================================================
# P0 兜底线新增配置测试
# ============================================================


# 功能：验证累计 Token 预算默认关闭，墙钟预算仍有安全默认值
# 设计：无覆盖时默认值提供硬止损，不再全零
def test_budget_defaults_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for env in ("SZTU_BUDGET_MAX_TOKENS", "SZTU_BUDGET_MAX_WALL_CLOCK_S"):
        monkeypatch.delenv(env, raising=False)
    cfg = get_config()
    assert cfg.budget.max_tokens == 0
    assert cfg.budget.max_wall_clock_s == 1_200


# 功能：验证压缩新字段 auto_compact_min_tokens/min_steps 的 TOML 解析
# 设计：TOML 正确解析并写入 CompactionConfig
def test_compaction_min_tokens_toml_parsed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    toml_path = tmp_path / "comp.toml"
    toml_path.write_bytes(
        b"[compaction]\n"
        b"auto_threshold = 0.50\n"
        b"auto_compact_min_tokens = 120000\n"
        b"auto_compact_min_steps = 50\n"
    )
    monkeypatch.setenv("SZTU_CONFIG", str(toml_path))
    cfg = get_config()
    assert cfg.compaction.auto_threshold == 0.50
    assert cfg.compaction.auto_compact_min_tokens == 120_000
    assert cfg.compaction.auto_compact_min_steps == 50


# 功能：验证压缩新字段的环境变量覆盖
# 设计：SZTU_COMPACT_MIN_TOKENS / SZTU_COMPACT_MIN_STEPS 覆盖默认值
def test_compaction_min_tokens_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SZTU_COMPACT_MIN_TOKENS", "160000")
    monkeypatch.setenv("SZTU_COMPACT_MIN_STEPS", "40")
    cfg = get_config()
    assert cfg.compaction.auto_compact_min_tokens == 160_000
    assert cfg.compaction.auto_compact_min_steps == 40


# 功能：验证压缩百分比阈值默认值从 0 改为 0.70
# 设计：context_pct 超过 70% 自动触发压缩，而非完全禁用
def test_compaction_threshold_default_changed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SZTU_COMPACT_THRESHOLD", raising=False)
    cfg = get_config()
    assert cfg.compaction.auto_threshold == 0.70


# 功能：验证默认失败干预为两次且旧压缩阈值字段关闭
# 设计：简单任务两次同类失败即注入换方案提示，Token/步数字段只保留兼容
def test_execution_defaults_are_short_task_friendly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SZTU_STUCK_MAX_FAILURES", raising=False)
    monkeypatch.delenv("SZTU_COMPACT_MIN_TOKENS", raising=False)
    monkeypatch.delenv("SZTU_COMPACT_MIN_STEPS", raising=False)
    cfg = get_config()
    assert cfg.agent.stuck_max_failures == 2
    assert cfg.compaction.auto_compact_min_tokens == 0
    assert cfg.compaction.auto_compact_min_steps == 0


# 功能：验证 agent 默认 max_steps 从 0 改为 100
# 设计：默认提供步数硬止损，防止无限步数
def test_agent_max_steps_default_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SZTU_MAX_STEPS", raising=False)
    cfg = get_config()
    assert cfg.agent.max_steps == 100
