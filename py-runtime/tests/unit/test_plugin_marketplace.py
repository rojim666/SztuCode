from __future__ import annotations

import json
from pathlib import Path

from sztu_code.core.plugins import MarketplaceManager


# 在指定市场根目录创建一个最小本地插件和对应目录条目
def _write_marketplace(root: Path, *, nested: bool = False) -> Path:
    plugin = root / "plugins" / "review-tools"
    (plugin / ".codex-plugin").mkdir(parents=True)
    (plugin / ".codex-plugin" / "plugin.json").write_text(
        json.dumps(
            {
                "name": "review-tools",
                "version": "1.2.0",
                "description": "Review changes safely",
                "interface": {"displayName": "Review Tools"},
            }
        ),
        encoding="utf-8",
    )
    manifest = (
        root / ".agents" / "plugins" / "marketplace.json"
        if nested
        else root / "marketplace.json"
    )
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "name": "quality-market",
                "interface": {"displayName": "Quality Market"},
                "plugins": [
                    {
                        "name": "review-tools",
                        "source": {"source": "local", "path": "./plugins/review-tools"},
                        "policy": {
                            "installation": "AVAILABLE",
                            "authentication": "ON_INSTALL",
                        },
                        "category": "Productivity",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest


# 功能：工作区 .agents/plugins/marketplace.json 应自动成为默认市场来源
# 设计：创建官方目录结构并验证市场标题、插件元数据和本地源路径解析。
def test_repo_default_marketplace_is_discovered(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write_marketplace(workspace, nested=True)
    manager = MarketplaceManager(
        project_root=workspace,
        config_root=tmp_path / "config",
        agents_root=tmp_path / "agents",
    )

    marketplaces = manager.list_marketplaces()
    plugins = manager.list_plugins()

    assert len(marketplaces) == 1
    assert marketplaces[0].display_name == "Quality Market"
    assert marketplaces[0].kind == "default"
    assert plugins[0].display_name == "Review Tools"
    assert plugins[0].source_path == workspace / "plugins" / "review-tools"


# 功能：用户可登记本地市场目录且移除配置不会删除原始目录
# 设计：添加本地根目录后重建管理器验证持久化，再移除并确认源文件仍存在。
def test_add_and_remove_local_marketplace_without_deleting_source(tmp_path: Path) -> None:
    source = tmp_path / "local-market"
    manifest = _write_marketplace(source)
    config_root = tmp_path / "config"
    manager = MarketplaceManager(
        project_root=tmp_path / "workspace",
        config_root=config_root,
        agents_root=tmp_path / "agents",
    )

    added = manager.add(str(source))
    assert added.kind == "local"
    assert added.removable is True
    assert len(manager.list_plugins()) == 1

    reloaded = MarketplaceManager(
        project_root=tmp_path / "workspace",
        config_root=config_root,
        agents_root=tmp_path / "agents",
    )
    assert reloaded.list_marketplaces()[0].id == added.id
    reloaded.remove(added.id)
    assert reloaded.list_marketplaces() == []
    assert manifest.is_file()


# 功能：GitHub 简写、Git 引用和稀疏路径应转换为官方兼容克隆参数
# 设计：替换 Git 执行边界生成假快照，验证配置和展示摘要而不访问网络。
def test_add_github_marketplace_with_ref_and_sparse_path(
    tmp_path: Path, monkeypatch,
) -> None:
    commands: list[list[str]] = []

    # 模拟 Git clone，并在目标目录构造稀疏市场内容
    def fake_git(args: list[str], *, timeout: int) -> None:
        commands.append(args)
        if args and args[0] == "clone":
            destination = Path(args[-1])
            _write_marketplace(destination, nested=True)

    monkeypatch.setattr(MarketplaceManager, "_run_git", staticmethod(fake_git))
    manager = MarketplaceManager(
        project_root=tmp_path / "workspace",
        config_root=tmp_path / "config",
        agents_root=tmp_path / "agents",
    )

    added = manager.add(
        "openai/plugins",
        ref="main",
        sparse_paths=[".agents/plugins"],
    )

    assert added.kind == "git"
    assert added.ref == "main"
    assert added.sparse_paths == (".agents/plugins",)
    assert added.updatable is True
    clone = commands[0]
    assert "https://github.com/openai/plugins.git" in clone
    assert "--sparse" in clone
    assert commands[1][-2:] == ["origin", "main"]
    assert commands[2][-2:] == ["--detach", "FETCH_HEAD"]
    assert commands[3][-1] == ".agents/plugins"


# 功能：SSH URL 中标准 git 用户名应被接受，HTTP 嵌入式凭据仍被拒绝
# 设计：直接验证来源规范化结果，覆盖官方文档列出的 ssh:// Git URL 形式。
def test_marketplace_accepts_ssh_url_username() -> None:
    source = "ssh://git@github.com/openai/plugins.git"

    normalized, ref, label = MarketplaceManager._normalize_git_source(source)

    assert normalized == source
    assert ref == ""
    assert label == "plugins"


# 功能：固定 Git 引用刷新应兼容分支、标签与提交，而不依赖当前检出分支
# 设计：持久化一个假 Git 市场，验证刷新使用 fetch + detached checkout。
def test_refresh_pinned_marketplace_fetches_configured_ref(
    tmp_path: Path, monkeypatch,
) -> None:
    commands: list[list[str]] = []

    def fake_git(args: list[str], *, timeout: int) -> None:
        commands.append(args)
        if args and args[0] == "clone":
            _write_marketplace(Path(args[-1]), nested=True)

    monkeypatch.setattr(MarketplaceManager, "_run_git", staticmethod(fake_git))
    manager = MarketplaceManager(
        project_root=tmp_path / "workspace",
        config_root=tmp_path / "config",
        agents_root=tmp_path / "agents",
    )
    added = manager.add("openai/plugins", ref="release-1")
    commands.clear()

    refreshed = manager.refresh(added.id)

    assert refreshed[0].id == added.id
    assert commands[0][-2:] == ["origin", "release-1"]
    assert commands[1][-2:] == ["--detach", "FETCH_HEAD"]


# 功能：越界稀疏路径和包含凭据的 Git URL 必须在执行 Git 前被拒绝
# 设计：直接调用公开 add 验证两类不安全输入均抛出 ValueError。
def test_marketplace_rejects_unsafe_git_inputs(tmp_path: Path) -> None:
    manager = MarketplaceManager(
        project_root=tmp_path / "workspace",
        config_root=tmp_path / "config",
        agents_root=tmp_path / "agents",
    )

    for source, sparse_paths in [
        ("openai/plugins", ["../secrets"]),
        ("https://user:token@github.com/openai/plugins.git", []),
    ]:
        try:
            manager.add(source, sparse_paths=sparse_paths)
        except ValueError:
            continue
        raise AssertionError(f"unsafe marketplace input was accepted: {source}")
