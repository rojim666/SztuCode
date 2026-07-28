from __future__ import annotations

from sztu_code.core.app import CoreApp
from sztu_code.core.config import SztuConfig, get_config
from sztu_code.core.mcp.server import McpServerManager
from sztu_code.core.permissions.manager import PermissionManager


def _configured_app() -> CoreApp:
    app = CoreApp()
    app._config = SztuConfig()
    app._config.llm.default_model = "configured-model"
    app._permission_manager = PermissionManager()
    app._mcp_manager = McpServerManager()
    return app


async def test_settings_update_applies_to_the_next_run_configuration(
    tmp_path, monkeypatch,
) -> None:
    settings_path = tmp_path / "client-settings.json"
    monkeypatch.setenv("SZTU_CLIENT_SETTINGS", str(settings_path))
    monkeypatch.setenv("SZTU_CONFIG", str(tmp_path / "missing-config.toml"))
    monkeypatch.delenv("SZTU_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("SZTU_LLM_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("KAMA_LLM_DEFAULT_MODEL", raising=False)
    monkeypatch.chdir(tmp_path)
    app = _configured_app()

    result = await app._settings_update_handler(
        {"provider": "openai", "model": "gpt-4o", "permission_mode": "plan"}
    )

    assert result.updated == ["provider", "model", "permission_mode"]
    assert result.settings.provider == "openai"
    assert result.settings.model == "gpt-4o"
    assert result.settings.permission_mode == "plan"
    assert result.settings.persistent is True
    assert settings_path.exists()

    reloaded = get_config()
    assert reloaded.llm.provider == "openai"
    assert reloaded.llm.default_model == "gpt-4o"
    assert reloaded.permission.mode == "plan"


async def test_provider_status_reports_presence_without_exposing_credentials(
    monkeypatch,
) -> None:
    app = _configured_app()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-value")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.test")

    result = await app._provider_status_handler({})
    payload = result.model_dump()

    assert result.ready_for_next_run is True
    assert result.custom_endpoint_configured is True
    assert "secret-value" not in str(payload)
    assert isinstance(result.skills, list)


async def test_provider_status_requires_a_model_for_a_ready_run(monkeypatch) -> None:
    app = _configured_app()
    app._config.llm.default_model = ""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-value")

    result = await app._provider_status_handler({})

    assert result.model == ""
    assert result.ready_for_next_run is False
