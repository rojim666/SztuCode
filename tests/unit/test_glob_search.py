from __future__ import annotations

from pathlib import Path

import pytest

from sztu_code.core.tools.builtin.glob_search import GlobSearchTool


def _make_tree(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("", encoding="utf-8")
    (root / "src" / "util.py").write_text("", encoding="utf-8")
    (root / "README.md").write_text("", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "dep.py").write_text("", encoding="utf-8")


# 功能：glob 模式匹配返回相对工作区根的文件路径
# 设计：搜 "**/*.py"，断言结果含 src/main.py 与 src/util.py 的相对路径
async def test_glob_returns_relative_paths(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    tool = GlobSearchTool(tmp_path)
    result = await tool.invoke({"pattern": "**/*.py"})
    assert not result.is_error
    lines = result.content.splitlines()
    assert "src/main.py" in lines
    assert "src/util.py" in lines
    assert "README.md" not in lines


# 功能：忽略 node_modules 等目录，不列出依赖产物
# 设计：node_modules 下有 dep.py，断言 glob "*.py" 结果不含它
async def test_ignores_ignored_dirs(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    tool = GlobSearchTool(tmp_path)
    result = await tool.invoke({"pattern": "*.py"})
    assert not result.is_error
    assert "dep.py" not in result.content


# 功能：path 参数限定搜索目录
# 设计：path="src" 只列出 src 下的匹配文件
async def test_path_scopes_search(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    tool = GlobSearchTool(tmp_path)
    result = await tool.invoke({"pattern": "**/*.py", "path": "src"})
    assert not result.is_error
    assert "src/main.py" in result.content
    assert "README.md" not in result.content


# 功能：无匹配返回 No files found
# 设计：搜不存在的扩展名，断言提示文案
async def test_no_match(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    tool = GlobSearchTool(tmp_path)
    result = await tool.invoke({"pattern": "**/*.rs"})
    assert not result.is_error
    assert result.content == "No files found."


# 功能：越界 path 抛出 PermissionError
# 设计：path="../secret" 触发 resolve_workspace_path 的越界保护
async def test_path_traversal_raises(tmp_path: Path) -> None:
    tool = GlobSearchTool(tmp_path)
    with pytest.raises(PermissionError):
        await tool.invoke({"pattern": "*.py", "path": "../secret"})
