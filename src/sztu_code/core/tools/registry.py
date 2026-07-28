# 工具注册表 —— 管理所有工具的注册、别名解析和 schema 导出
from __future__ import annotations

from sztu_code.core.tools.base import BaseTool, ToolPermission


# 内置别名映射（无需在工具类上声明即可使用）
_BUILTIN_ALIASES: dict[str, str] = {
    "read": "read_file",
    "Read": "read_file",
    "write": "write_file",
    "Write": "write_file",
    "edit": "edit_file",
    "Edit": "edit_file",
    "glob": "glob_search",
    "Glob": "glob_search",
    "grep": "grep_search",
    "Grep": "grep_search",
    "ls": "list_dir",
    "List": "list_dir",
}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        # 动态别名索引: alias → canonical_name
        self._aliases: dict[str, str] = {}

    # 注册工具；同名覆盖，同时注册别名
    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool
        # 注册工具类声明的别名
        for alias in tool.aliases:
            self._aliases[alias] = tool.name

    # 按名称或别名查找工具，不存在返回 None
    def get(self, name: str) -> BaseTool | None:
        # 1. 精确匹配
        if name in self._tools:
            return self._tools[name]
        # 2. 工具类注册的别名
        if name in self._aliases:
            return self._tools[self._aliases[name]]
        # 3. 内置全局别名
        canonical = _BUILTIN_ALIASES.get(name)
        if canonical and canonical in self._tools:
            return self._tools[canonical]
        return None

    # 获取工具的基准权限级别
    def permission_for(self, name: str) -> ToolPermission | None:
        tool = self.get(name)
        return tool.required_permission if tool else None

    # 返回所有工具的 Anthropic 格式 schema 列表
    def tool_schemas(self) -> list[dict[str, object]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in self._tools.values()
        ]

    # 返回所有已注册工具的迭代器
    def __iter__(self):
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)
