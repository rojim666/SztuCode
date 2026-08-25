from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# 默认的 CC Switch 数据库路径（Windows 与 macOS 均为用户目录下的 .cc-switch）
_DEFAULT_CCSWITCH_DB = "~/.cc-switch/cc-switch.db"

# 可导入到 SztuCode anthropic provider 的 app_type 集合
_ANTHROPIC_APP_TYPES = {"claude", "claude-desktop"}


@dataclass
class CcswitchProvider:
    # 单条可导入的 CC Switch 供应商配置（已解析为 SztuCode 需要的字段）
    id: str
    name: str
    base_url: str
    model: str
    api_key: str
    is_current: bool


# 返回 CC Switch 数据库路径，优先使用环境变量覆盖以便测试
def _db_path() -> Path:
    return Path(os.environ.get("SZTU_CCSWITCH_DB", _DEFAULT_CCSWITCH_DB)).expanduser()


# 从 settings_config 的 env 字段解析出 base_url/api_key/model，缺失时返回空
def _parse_env(settings_config: str) -> tuple[str, str, str]:
    try:
        payload = json.loads(settings_config)
    except (ValueError, TypeError):
        return "", "", ""
    env = payload.get("env") if isinstance(payload, dict) else None
    if not isinstance(env, dict):
        return "", "", ""
    base_url = str(env.get("ANTHROPIC_BASE_URL", "") or "").strip()
    api_key = str(
        env.get("ANTHROPIC_AUTH_TOKEN", "") or env.get("ANTHROPIC_API_KEY", "") or ""
    ).strip()
    model = str(
        env.get("ANTHROPIC_MODEL", "") or env.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "") or ""
    ).strip()
    return base_url, api_key, model


# 读取 providers 表并转换为可导入的供应商列表；数据库缺失或损坏时返回空列表
def list_ccswitch_providers() -> list[CcswitchProvider]:
    path = _db_path()
    if not path.is_file():
        return []
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        cursor = connection.execute(
            "SELECT id, name, app_type, settings_config, is_current FROM providers"
        )
        rows = cursor.fetchall()
    except sqlite3.Error:
        return []
    finally:
        connection.close()

    providers: list[CcswitchProvider] = []
    for row in rows:
        if len(row) < 5:
            continue
        provider_id, name, app_type, settings_config, is_current = row[:5]
        if str(app_type or "") not in _ANTHROPIC_APP_TYPES:
            continue
        base_url, api_key, model = _parse_env(str(settings_config or ""))
        if not base_url or not api_key or not model:
            continue
        providers.append(
            CcswitchProvider(
                id=str(provider_id),
                name=str(name or provider_id),
                base_url=base_url,
                model=model,
                api_key=api_key,
                is_current=bool(is_current),
            )
        )
    return providers


# 按 provider_id 返回单个可导入的供应商，不存在时返回 None
def get_ccswitch_provider(provider_id: str) -> CcswitchProvider | None:
    for provider in list_ccswitch_providers():
        if provider.id == provider_id:
            return provider
    return None
