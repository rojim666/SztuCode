from __future__ import annotations

import json
import os
from pathlib import Path

_DEFAULT_TRUSTED_PROJECTS_PATH = "~/.sztu/trusted-projects.json"


# 返回信任列表文件路径，优先使用环境变量覆盖以便测试
def trusted_projects_path() -> Path:
    return Path(
        os.environ.get("SZTU_TRUSTED_PROJECTS", _DEFAULT_TRUSTED_PROJECTS_PATH)
    ).expanduser()


# 读取已信任的绝对路径列表；文件缺失或损坏时返回空列表
def _load_trusted() -> list[str]:
    path = trusted_projects_path()
    if not path.is_file():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    trusted = value.get("trusted") if isinstance(value, dict) else None
    if not isinstance(trusted, list):
        return []
    return [str(item) for item in trusted if isinstance(item, str)]


# 原子写入信任列表，保证中途失败不会损坏原文件
def _save_trusted(paths: list[str]) -> None:
    path = trusted_projects_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps({"trusted": sorted(set(paths))}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


# 判断路径是否受信任：路径自身或任一父目录在信任列表中即视为受信任
def is_trusted(path: str | Path) -> bool:
    resolved = Path(path).expanduser().resolve()
    trusted = set(_load_trusted())
    if not trusted:
        return False
    for parent in [resolved, *resolved.parents]:
        if str(parent) in trusted:
            return True
    return False


# 记录一个受信任目录（幂等），信任它覆盖其下所有子目录
def add_trusted(path: str | Path) -> None:
    resolved = str(Path(path).expanduser().resolve())
    _save_trusted([*_load_trusted(), resolved])


# 从信任列表中移除指定目录（幂等），子目录的信任不受影响
def remove_trusted(path: str | Path) -> None:
    resolved = str(Path(path).expanduser().resolve())
    _save_trusted([item for item in _load_trusted() if item != resolved])
