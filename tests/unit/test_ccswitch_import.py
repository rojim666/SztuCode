from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from sztu_code.core.app import CoreApp
from sztu_code.core.bus.envelope import HandlerError
from sztu_code.core.config import SztuConfig, get_config
from sztu_code.core.llm import create_provider
from sztu_code.core.llm.ccswitch import list_ccswitch_providers
from sztu_code.core.permissions.manager import PermissionManager


# 功能：构造一个含 providers 表的临时 cc-switch 数据库
# 设计：用内存 Python sqlite3 直接建表，覆盖 claude 类型（应被解析）与 codex 类型（应被过滤）
def _make_ccswitch_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE providers (id TEXT, name TEXT, app_type TEXT, settings_config TEXT, is_current INTEGER)"
    )
    connection.executemany(
        "INSERT INTO providers VALUES (?, ?, ?, ?, ?)",
        [
            (
                "p-deepseek",
                "DeepSeek",
                "claude",
                json.dumps(
                    {
                        "env": {
                            "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
                            "ANTHROPIC_AUTH_TOKEN": "sk-secret-1",
                            "ANTHROPIC_MODEL": "deepseek-v4-flash",
                        }
                    }
                ),
                1,
            ),
            (
                "p-myclaude",
                "My Claude",
                "claude-desktop",
                json.dumps(
                    {
                        "env": {
                            "ANTHROPIC_BASE_URL": "https://api.aisz.mom",
                            "ANTHROPIC_API_KEY": "sk-secret-2",
                            "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-opus-4-8",
                        }
                    }
                ),
                0,
            ),
            (
                "p-codex",
                "My Codex",
                "codex",
                json.dumps({"auth": {"OPENAI_API_KEY": "sk-secret-3"}}),
                0,
            ),
        ],
    )
    connection.commit()
    connection.close()


# 功能：构造一个配置就绪的 CoreApp 实例（沿用现有 settings 测试的约定）
# 设计：只注入 config 与 permission_manager，sessions 保持 None，避免 handler 触发真实 provider 重建
def _configured_app() -> CoreApp:
    app = CoreApp()
    app._config = SztuConfig()
    app._permission_manager = PermissionManager()
    return app


# 功能：验证 list_ccswitch_providers 只解析 Anthropic 兼容供应商并正确提取字段
# 设计：用临时 DB 覆盖 claude/claude-desktop/codex 三类，断言 codex 被过滤、token 与模型回退到 SONNET 字段生效
def test_list_ccswitch_providers_parses_anthropic_only(
    tmp_path, monkeypatch,
) -> None:
    db_path = tmp_path / "cc-switch.db"
    _make_ccswitch_db(db_path)
    monkeypatch.setenv("SZTU_CCSWITCH_DB", str(db_path))

    providers = list_ccswitch_providers()

    assert [p.id for p in providers] == ["p-deepseek", "p-myclaude"]
    deepseek = providers[0]
    assert deepseek.base_url == "https://api.deepseek.com/anthropic"
    assert deepseek.api_key == "sk-secret-1"
    assert deepseek.model == "deepseek-v4-flash"
    assert deepseek.is_current is True
    myclaude = providers[1]
    assert myclaude.model == "claude-opus-4-8"


# 功能：验证 ccswitch_list 响应不含明文凭证，只暴露 has_api_key
# 设计：序列化 handler 返回值后断言 api_key 字段不存在，防止把密钥通过 IPC 暴露给客户端
async def test_ccswitch_list_handler_masks_api_key(
    tmp_path, monkeypatch,
) -> None:
    db_path = tmp_path / "cc-switch.db"
    _make_ccswitch_db(db_path)
    monkeypatch.setenv("SZTU_CCSWITCH_DB", str(db_path))
    app = _configured_app()

    result = await app._provider_ccswitch_list_handler({})

    payload = result.model_dump()
    assert len(result.providers) == 2
    assert result.providers[0].has_api_key is True
    assert "sk-secret-1" not in str(payload)
    assert "api_key" not in payload["providers"][0]


# 功能：验证 ccswitch_apply 将供应商写入 config 并持久化到 client-settings.json
# 设计：SZTU_CLIENT_SETTINGS 指向 tmp 文件，apply 后检查快照、config、落盘 JSON，再用 get_config 复现加载路径
async def test_ccswitch_apply_handler_applies_and_persists(
    tmp_path, monkeypatch,
) -> None:
    db_path = tmp_path / "cc-switch.db"
    _make_ccswitch_db(db_path)
    settings_path = tmp_path / "client-settings.json"
    monkeypatch.setenv("SZTU_CCSWITCH_DB", str(db_path))
    monkeypatch.setenv("SZTU_CLIENT_SETTINGS", str(settings_path))
    monkeypatch.setenv("SZTU_CONFIG", str(tmp_path / "missing-config.toml"))
    monkeypatch.delenv("SZTU_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("SZTU_LLM_DEFAULT_MODEL", raising=False)
    # 模拟 .env 提供了 KAMA_LLM_DEFAULT_MODEL 默认值，验证客户端保存的模型能胜出
    monkeypatch.setenv("KAMA_LLM_DEFAULT_MODEL", "env-default-model")
    monkeypatch.chdir(tmp_path)
    app = _configured_app()

    result = await app._provider_ccswitch_apply_handler({"provider_id": "p-deepseek"})

    assert result.updated == ["provider", "model", "base_url"]
    assert result.settings.provider == "anthropic"
    assert result.settings.model == "deepseek-v4-flash"
    assert result.settings.base_url == "https://api.deepseek.com/anthropic"
    assert app._config.llm.api_key == "sk-secret-1"
    assert settings_path.exists()

    stored = json.loads(settings_path.read_text(encoding="utf-8"))
    assert stored["provider"] == "anthropic"
    assert stored["base_url"] == "https://api.deepseek.com/anthropic"
    assert stored["api_key"] == "sk-secret-1"

    reloaded = get_config()
    assert reloaded.llm.default_model == "deepseek-v4-flash"
    assert reloaded.llm.base_url == "https://api.deepseek.com/anthropic"
    assert reloaded.llm.api_key == "sk-secret-1"


# 功能：验证 create_provider 会把 config 中的端点与凭证注入 provider 环境变量
# 设计：直接调用 create_provider，断言 os.environ 中 ANTHROPIC_BASE_URL/API_KEY 被写入，覆盖导入后重启再建 provider 的路径
def test_create_provider_injects_imported_endpoint_env(
    tmp_path, monkeypatch,
) -> None:
    config = SztuConfig()
    config.llm.default_model = "deepseek-v4-flash"
    config.llm.base_url = "https://api.deepseek.com/anthropic"
    config.llm.api_key = "sk-imported"

    create_provider(config)

    assert os.environ["ANTHROPIC_BASE_URL"] == "https://api.deepseek.com/anthropic"
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-imported"


# 功能：验证 cc-switch 数据库缺失时 list 返回空、apply 抛出 HandlerError
# 设计：SZTU_CCSWITCH_DB 指向不存在的路径，覆盖"未安装 cc-switch 或路径配置错误"的降级路径
async def test_ccswitch_missing_db_is_graceful(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("SZTU_CCSWITCH_DB", str(tmp_path / "missing.db"))

    assert list_ccswitch_providers() == []

    app = _configured_app()
    with pytest.raises(HandlerError):
        await app._provider_ccswitch_apply_handler({"provider_id": "p-deepseek"})
