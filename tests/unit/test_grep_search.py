from __future__ import annotations

from pathlib import Path

import pytest

from sztu_code.core.tools.builtin.grep_search import GrepSearchTool


def _make_tree(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text(
        "import os\n\nclass Greeter:\n    def hello(self):\n        return \"hi\"\n",
        encoding="utf-8",
    )
    (root / "src" / "util.py").write_text("def helper():\n    pass\n", encoding="utf-8")
    (root / "README.md").write_text("# Project\ngreeter is a demo\n", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "pkg.py").write_text("GREETER_SENTINEL = 1\n", encoding="utf-8")


# 功能：正则命中时返回 file:line: text 格式且路径相对工作区根
# 设计：在 tmp 树中搜 "class Greeter"，断言命中行含相对路径 src/main.py 与行号
async def test_match_returns_file_line_text(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    tool = GrepSearchTool(tmp_path)
    result = await tool.invoke({"pattern": "class Greeter"})
    assert not result.is_error
    assert "src/main.py:3: class Greeter:" in result.content


# 功能：默认忽略大小写，case_sensitive=True 时区分大小写
# 设计：同一 pattern 分别搜大小写两种写法，验证开关行为
async def test_case_sensitivity_flag(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    tool = GrepSearchTool(tmp_path)
    insensitive = await tool.invoke({"pattern": "GREETER"})
    assert not insensitive.is_error
    assert "src/main.py" in insensitive.content
    sensitive = await tool.invoke({"pattern": "GREETER", "case_sensitive": True})
    assert not sensitive.is_error
    assert sensitive.content == "No matches found."


# 功能：忽略 node_modules/.git 等目录，不扫入依赖产物
# 设计：node_modules 下放置含目标词的哨兵文件，确认搜索结果不包含它
async def test_ignores_ignored_dirs(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    tool = GrepSearchTool(tmp_path)
    result = await tool.invoke({"pattern": "GREETER_SENTINEL"})
    assert not result.is_error
    assert "No matches found." == result.content


# 功能：glob 过滤只搜索匹配的文件名
# 设计：同 pattern 带 glob="*.py"，断言 README.md（含目标词）不被搜到
async def test_glob_filter(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    tool = GrepSearchTool(tmp_path)
    result = await tool.invoke({"pattern": "greeter", "glob": "*.py"})
    assert not result.is_error
    assert "README.md" not in result.content
    assert "src/main.py" in result.content


# 功能：path 参数指定搜索范围，越界路径抛出 PermissionError
# 设计：path="../secret" 触发 resolve_workspace_path 的越界保护
async def test_path_traversal_raises(tmp_path: Path) -> None:
    tool = GrepSearchTool(tmp_path)
    with pytest.raises(PermissionError):
        await tool.invoke({"pattern": "x", "path": "../secret"})


# 功能：非法正则返回 is_error 且 error_type 为 schema_error
# 设计：pattern="[" 无法编译，断言错误分类而不是抛异常
async def test_invalid_regex_returns_error(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    tool = GrepSearchTool(tmp_path)
    result = await tool.invoke({"pattern": "["})
    assert result.is_error
    assert result.error_type == "schema_error"


# 功能：命中数超过上限时截断并追加 [truncated] 标记
# 设计：生成 250 行匹配文件，断言结果以 [truncated] 结尾且行数受限
async def test_truncated_at_match_limit(tmp_path: Path) -> None:
    f = tmp_path / "bulk.txt"
    f.write_text("\n".join(f"line {i} TARGET" for i in range(250)), encoding="utf-8")
    tool = GrepSearchTool(tmp_path)
    result = await tool.invoke({"pattern": "TARGET"})
    assert not result.is_error
    assert result.content.endswith("[truncated]")
    # 200 条命中 + 1 条截断标记
    assert result.content.count("\n") == 200


# 功能：无命中返回 No matches found
# 设计：搜索不存在的词，断言返回提示文案
async def test_no_matches(tmp_path: Path) -> None:
    _make_tree(tmp_path)
    tool = GrepSearchTool(tmp_path)
    result = await tool.invoke({"pattern": "nonexistent_symbol_xyz"})
    assert not result.is_error
    assert result.content == "No matches found."
