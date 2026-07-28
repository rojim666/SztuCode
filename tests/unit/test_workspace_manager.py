from __future__ import annotations

from pathlib import Path

import pytest

from sztu_code.core.workspace import WorkspaceManager


# 功能：验证打开工作区后可持久化最近目录、读取受限文件树并进行文本搜索。
# 设计：使用临时目录构造嵌套源码与被忽略目录，重建 manager 验证磁盘恢复，同时断言 tree/search 只暴露工作区内可读内容。
def test_workspace_open_persists_tree_and_search(tmp_path: Path) -> None:
    root = tmp_path / "project"
    source = root / "src"
    source.mkdir(parents=True)
    (source / "main.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")
    (root / "README.md").write_text("hello workspace\n", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("hidden", encoding="utf-8")

    recent_file = tmp_path / "state" / "workspaces.json"
    manager = WorkspaceManager(recent_file)
    workspace = manager.open(str(root))

    tree = manager.tree(workspace.id, max_depth=2)
    assert {node["name"] for node in tree} == {"README.md", "src"}
    assert manager.read_file(workspace.id, "src/main.py").startswith("def hello")
    assert manager.search(workspace.id, "hello") == [
        {"path": "README.md", "line": 1, "preview": "hello workspace"},
        {"path": "src/main.py", "line": 1, "preview": "def hello():"},
    ]

    restored = WorkspaceManager(recent_file)
    assert restored.list_recent() == [workspace]


# 功能：验证工作区文件读取拒绝目录穿越及不存在目录，避免客户端借 IPC 读取任意本地文件。
# 设计：对已打开临时工作区传入 ../ 路径和无效 open 路径，分别断言 ValueError，覆盖路径边界与输入验证。
def test_workspace_rejects_paths_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    manager = WorkspaceManager(tmp_path / "workspaces.json")
    workspace = manager.open(str(root))

    with pytest.raises(ValueError, match="escapes workspace"):
        manager.read_file(workspace.id, "../outside.txt")
    with pytest.raises(ValueError, match="existing directory"):
        manager.open(str(tmp_path / "missing"))
