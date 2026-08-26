# 功能：验证 edit_file 工具的所有行为和边界条件
# 设计：在临时目录创建文件后执行各种编辑操作，覆盖精确替换、replace_all、不存在、不唯一等场景
from __future__ import annotations

from pathlib import Path

import pytest

from sztu_code.core.tools.builtin.edit_file import EditFileTool


# 功能：验证精确替换单次出现
# 设计：写入已知内容后替换一次，断言替换成功且只替换了第一个匹配
async def test_edit_file_single_replace(tmp_path: Path) -> None:
    path = tmp_path / "test.py"
    path.write_text("hello world\nhi again\n")

    tool = EditFileTool(tmp_path)
    result = await tool.invoke({
        "path": "test.py",
        "old_string": "hello world",
        "new_string": "hi world",
    })

    assert not result.is_error
    assert "replaced 1 occurrence" in result.content
    assert path.read_text() == "hi world\nhi again\n"


# 功能：验证 replace_all 替换所有出现
# 设计：写入多处重复字符串，使用 replace_all=true 断言全部替换
async def test_edit_file_replace_all(tmp_path: Path) -> None:
    path = tmp_path / "test.py"
    path.write_text("TODO: fix\n# TODO: improve\nTODO: remove\n")

    tool = EditFileTool(tmp_path)
    result = await tool.invoke({
        "path": "test.py",
        "old_string": "TODO:",
        "new_string": "DONE:",
        "replace_all": True,
    })

    assert not result.is_error
    assert "replaced 3 occurrence" in result.content
    assert "TODO:" not in path.read_text()
    assert path.read_text().count("DONE:") == 3


# 功能：验证 old_string 不存在时返回错误
# 设计：搜索不存在的字符串，断言返回 is_error=True 且提示 not found
async def test_edit_file_old_string_not_found(tmp_path: Path) -> None:
    path = tmp_path / "test.py"
    path.write_text("hello world\n")

    tool = EditFileTool(tmp_path)
    result = await tool.invoke({
        "path": "test.py",
        "old_string": "nonexistent",
        "new_string": "replacement",
    })

    assert result.is_error
    assert "not found" in result.content


# 功能：验证 old_string 出现多次且未设置 replace_all 时返回错误
# 设计：写入重复字符串，不设 replace_all，断言提示"appears N times"
async def test_edit_file_ambiguous_without_replace_all(tmp_path: Path) -> None:
    path = tmp_path / "test.py"
    path.write_text("x = 1\ny = x\nz = x\n")

    tool = EditFileTool(tmp_path)
    result = await tool.invoke({
        "path": "test.py",
        "old_string": "x",
        "new_string": "n",
    })

    assert result.is_error
    assert "appears" in result.content and "times" in result.content


# 功能：验证 old_string == new_string 时返回错误
# 设计：新旧字符串相同，断言直接拒绝
async def test_edit_file_identical_strings(tmp_path: Path) -> None:
    path = tmp_path / "test.py"
    path.write_text("hello\n")

    tool = EditFileTool(tmp_path)
    result = await tool.invoke({
        "path": "test.py",
        "old_string": "hello",
        "new_string": "hello",
    })

    assert result.is_error
    assert "identical" in result.content


# 功能：验证文件不存在时返回错误
# 设计：指定不存在的文件路径，断言返回错误
async def test_edit_file_missing_file(tmp_path: Path) -> None:
    tool = EditFileTool(tmp_path)
    result = await tool.invoke({
        "path": "nonexistent.py",
        "old_string": "a",
        "new_string": "b",
    })

    assert result.is_error
    assert "not found" in result.content


# 功能：验证 .. 路径遍历被拒绝
# 设计：路径中包含 .. 组件，断言抛出 PermissionError
async def test_edit_file_rejects_traversal(tmp_path: Path) -> None:
    tool = EditFileTool(tmp_path)
    with pytest.raises(PermissionError):
        await tool.invoke({
            "path": "../outside.py",
            "old_string": "a",
            "new_string": "b",
        })
