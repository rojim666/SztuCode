from __future__ import annotations

from pathlib import Path

import pytest

from sztu_code.core.tools.builtin.read_file import ReadFileTool
from sztu_code.core.tools.builtin.write_file import WriteFileTool


# 功能：验证绑定工作区后的读写工具仅操作 session 指定的项目目录。
# 设计：使用独立临时根目录读写相对文件，再断言文件不出现在测试进程 cwd，排除仅修改显示路径而未改变实际目标的假阳性。
async def test_workspace_bound_read_and_write_use_project_root(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    writer = WriteFileTool(project)

    result = await writer.invoke({"path": "src/example.txt", "content": "workspace scoped"})

    assert result.is_error is False
    assert (project / "src" / "example.txt").read_text(encoding="utf-8") == "workspace scoped"
    read = await ReadFileTool(project).invoke({"path": "src/example.txt"})
    assert read.content == "workspace scoped"


# 功能：验证绑定工作区后的文件工具拒绝绝对路径和父目录穿越。
# 设计：对同一根目录分别提供 ../ 与临时目录绝对路径，直接断言 PermissionError，覆盖 resolve 后的真实边界检查。
@pytest.mark.parametrize("path", ["../outside.txt", "C:/outside.txt"])
async def test_workspace_bound_tools_reject_paths_outside_project(tmp_path: Path, path: str) -> None:
    project = tmp_path / "project"
    project.mkdir()

    with pytest.raises(PermissionError, match="path (escapes workspace|traversal not allowed)"):
        await WriteFileTool(project).invoke({"path": path, "content": "nope"})
