from __future__ import annotations

import json
from pathlib import Path

from sztu_code.core.trust import add_trusted, is_trusted, remove_trusted


# 功能：验证 add_trusted 后 is_trusted 对该目录返回真
# 设计：路径无需真实存在（信任逻辑只解析绝对路径），用 tmp_path 避免污染用户目录
def test_add_and_is_trusted_exact_match(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("SZTU_TRUSTED_PROJECTS", str(tmp_path / "trusted.json"))
    project = tmp_path / "proj"

    add_trusted(project)

    assert is_trusted(project) is True


# 功能：验证信任父目录后其下所有子目录都被视为受信任
# 设计：只 add 根目录，断言深层子路径返回真，模拟"信任工作区根目录覆盖整个仓库"
def test_parent_dir_trust_covers_subdirs(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("SZTU_TRUSTED_PROJECTS", str(tmp_path / "trusted.json"))
    add_trusted(tmp_path / "code")

    assert is_trusted(tmp_path / "code" / "project-a" / "src") is True
    assert is_trusted(tmp_path / "elsewhere") is False


# 功能：验证 remove_trusted 后目录不再受信任
# 设计：add 再 remove，断言变回 False，验证幂等移除不报错
def test_remove_trusted(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setenv("SZTU_TRUSTED_PROJECTS", str(tmp_path / "trusted.json"))
    project = tmp_path / "proj"
    add_trusted(project)
    remove_trusted(project)

    assert is_trusted(project) is False


# 功能：验证信任列表落盘后重新加载仍然生效
# 设计：add 后不依赖内存状态，重新调用 is_trusted 走文件加载路径，验证持久化 round-trip
def test_persistence_round_trip(
    tmp_path: Path, monkeypatch,
) -> None:
    store_path = tmp_path / "trusted.json"
    monkeypatch.setenv("SZTU_TRUSTED_PROJECTS", str(store_path))
    add_trusted(tmp_path / "proj")

    assert store_path.exists()
    assert json.loads(store_path.read_text(encoding="utf-8"))["trusted"] == [
        str((tmp_path / "proj").resolve())
    ]
    assert is_trusted(tmp_path / "proj") is True


# 功能：验证信任文件损坏或缺失时静默降级为空列表，且 add 仍能重建文件
# 设计：写入非法 JSON，断言 is_trusted 为 False、add_trusted 不抛异常并覆盖损坏内容
def test_corrupt_file_is_graceful(
    tmp_path: Path, monkeypatch,
) -> None:
    store_path = tmp_path / "trusted.json"
    monkeypatch.setenv("SZTU_TRUSTED_PROJECTS", str(store_path))
    store_path.write_text("{ not json", encoding="utf-8")

    assert is_trusted(tmp_path / "proj") is False
    add_trusted(tmp_path / "proj")
    assert is_trusted(tmp_path / "proj") is True
