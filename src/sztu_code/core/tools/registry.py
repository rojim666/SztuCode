# 工具注册表 —— 管理所有工具的注册、别名解析和 schema 导出
from __future__ import annotations

from copy import deepcopy

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

    # 为每次调用补齐供执行时间线展示的简短中文标题
    def enrich_tool_input(self, name: str, params: dict[str, object]) -> dict[str, object]:
        enriched = dict(params)
        current = enriched.get("description")
        if isinstance(current, str) and current.strip():
            enriched["description"] = current.strip()
            return enriched

        path = str(enriched.get("path", "")).strip()
        if name == "bash":
            command = str(enriched.get("command", "")).strip()
            title = f"运行命令：{command[:72]}" if command else "运行终端命令"
        elif name == "read_file":
            title = f"读取 {path}" if path else "读取文件"
        elif name == "list_dir":
            title = f"查看 {path}" if path else "获取当前工作目录"
        elif name in {"grep_search", "glob_search"}:
            query = str(enriched.get("query") or enriched.get("pattern") or "").strip()
            title = f"搜索 {query}" if query else "搜索项目文件"
        elif name == "write_file":
            title = f"写入 {path}" if path else "写入文件"
        elif name == "edit_file":
            title = f"编辑 {path}" if path else "编辑文件"
        else:
            title = f"调用 {name}"
        enriched["description"] = title
        return enriched

    # 返回所有工具的 Anthropic 格式 schema，并要求模型提供时间线标题
    def tool_schemas(self) -> list[dict[str, object]]:
        schemas: list[dict[str, object]] = []
        for tool in self._tools.values():
            input_schema = deepcopy(tool.input_schema)
            properties = dict(input_schema.get("properties", {}))
            properties["description"] = {
                "type": "string",
                "description": "用简短中文说明本次调用的具体目的，作为执行时间线标题。",
            }
            input_schema["properties"] = properties
            required = [str(item) for item in input_schema.get("required", [])]
            if "description" not in required:
                required.append("description")
            input_schema["required"] = required
            schemas.append({
                "name": tool.name,
                "description": tool.description,
                "input_schema": input_schema,
            })
        return schemas

    # 返回所有已注册工具的迭代器
    def __iter__(self):
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)
