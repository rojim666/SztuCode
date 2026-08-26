# 功能：验证 ToolRegistry 别名解析和 ToolPermission 查询
# 设计：注册带别名的工具后，通过别名查找应返回正确工具；权限查询也应通过别名工作
from __future__ import annotations

from sztu_code.core.tools.base import BaseTool, ToolPermission, ToolResult
from sztu_code.core.tools.registry import ToolRegistry


class _FakeTool(BaseTool):
    name = "test_tool"
    required_permission = ToolPermission.READ_ONLY
    aliases = ["tt", "Test"]

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        return ToolResult(content="ok")


# 功能：验证通过工具类注册的别名可以正常找到工具
# 设计：注册带 aliases 的工具，分别用原名和别名查询
def test_alias_from_tool_class() -> None:
    reg = ToolRegistry()
    reg.register(_FakeTool())

    assert reg.get("test_tool") is not None
    assert reg.get("tt") is not None
    assert reg.get("Test") is not None


# 功能：验证内置全局别名（如 read→read_file）对已注册工具生效
# 设计：注册 ReadFileTool 后通过全局别名 "read" 查询
def test_builtin_alias_for_registered_tool() -> None:
    from sztu_code.core.tools.builtin.read_file import ReadFileTool

    reg = ToolRegistry()
    reg.register(ReadFileTool())

    assert reg.get("read_file") is not None
    assert reg.get("read") is not None
    assert reg.get("Read") is not None


# 功能：验证内置全局别名在对应工具未注册时返回 None
# 设计：不注册任何工具时，全局别名查询应返回 None
def test_builtin_alias_without_tool_returns_none() -> None:
    reg = ToolRegistry()
    assert reg.get("read") is None
    assert reg.get("write") is None


# 功能：验证 permission_for 通过别名也能查询到权限级别
# 设计：注册工具后通过别名查询权限，应返回工具声明的 required_permission
def test_permission_for_alias() -> None:
    from sztu_code.core.tools.builtin.read_file import ReadFileTool

    reg = ToolRegistry()
    reg.register(ReadFileTool())

    assert reg.permission_for("read_file") == ToolPermission.READ_ONLY
    assert reg.permission_for("read") == ToolPermission.READ_ONLY
    assert reg.permission_for("Read") == ToolPermission.READ_ONLY


# 功能：验证 WriteFileTool 注册后通过别名查询返回正确权限
# 设计：write 别名应返回 WORKSPACE_WRITE
def test_write_file_alias() -> None:
    from sztu_code.core.tools.builtin.write_file import WriteFileTool

    reg = ToolRegistry()
    reg.register(WriteFileTool())

    assert reg.get("write") is not None
    assert reg.permission_for("write") == ToolPermission.WORKSPACE_WRITE


# 功能：验证 EditFileTool 注册后通过别名查询
# 设计：edit 别名应命中 edit_file
def test_edit_file_alias() -> None:
    from sztu_code.core.tools.builtin.edit_file import EditFileTool

    reg = ToolRegistry()
    reg.register(EditFileTool())

    assert reg.get("edit") is not None
    assert reg.get("Edit") is not None
    assert reg.permission_for("edit") == ToolPermission.WORKSPACE_WRITE
