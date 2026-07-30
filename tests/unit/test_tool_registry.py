from __future__ import annotations

from sztu_code.core.tools.base import BaseTool, ToolResult
from sztu_code.core.tools.registry import ToolRegistry


class _FakeTool(BaseTool):
    name = "fake"
    description = "A fake tool"
    input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        return ToolResult(content="ok")


# 功能：验证注册工具后能通过名称检索到同一实例
# 设计：断言 `is`（同一对象引用）而非 `==`，确认 registry 存储的是引用而非副本，避免不必要的对象复制
def test_register_and_get() -> None:
    registry = ToolRegistry()
    tool = _FakeTool()
    registry.register(tool)
    assert registry.get("fake") is tool


# 功能：验证查询不存在的工具名返回 None 而非抛出异常
# 设计：空 registry 直接查询，确认返回值语义为 None（而非 KeyError），invoke_tool 依赖此行为判断"未知工具"
def test_get_unknown_returns_none() -> None:
    assert ToolRegistry().get("missing") is None


# 功能：验证 tool_schemas() 输出的每条记录包含 Anthropic API 所需的三个必填字段
# 设计：这三个字段（name/description/input_schema）是 Anthropic tool definition 格式，缺少任何一个都会导致 LLM 调用失败
def test_tool_schemas_contains_name_description_input_schema() -> None:
    registry = ToolRegistry()
    registry.register(_FakeTool())
    schemas = registry.tool_schemas()
    assert len(schemas) == 1
    assert schemas[0]["name"] == "fake"
    assert schemas[0]["description"] == "A fake tool"
    assert "input_schema" in schemas[0]
    input_schema = schemas[0]["input_schema"]
    assert "description" in input_schema["properties"]  # type: ignore[index]
    assert "description" in input_schema["required"]  # type: ignore[index]


# 功能：验证多工具注册后 tool_schemas() 包含所有工具，不遗漏
# 设计：用 set 比较名称集合而非检查顺序，聚焦"完整性"而非"顺序"，确认 registry 不遗漏任何已注册工具
def test_multiple_tools_all_appear_in_schemas() -> None:
    class _AnotherTool(BaseTool):
        name = "another"
        description = "Another"
        input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}

        async def invoke(self, params: dict[str, object]) -> ToolResult:
            return ToolResult(content="")

    registry = ToolRegistry()
    registry.register(_FakeTool())
    registry.register(_AnotherTool())
    names = {s["name"] for s in registry.tool_schemas()}
    assert names == {"fake", "another"}


# 功能：验证重复注册同名工具时新版本覆盖旧版本（覆盖语义而非追加）
# 设计：检查 description 变更，确认 registry 的覆盖语义，防止工具版本冲突导致旧实现残留
def test_register_same_name_overwrites() -> None:
    class _Updated(BaseTool):
        name = "fake"
        description = "updated"
        input_schema: dict[str, object] = {}

        async def invoke(self, params: dict[str, object]) -> ToolResult:
            return ToolResult(content="")

    registry = ToolRegistry()
    registry.register(_FakeTool())
    registry.register(_Updated())
    found = registry.get("fake")
    assert found is not None
    assert found.description == "updated"

# 功能：验证工具调用标题保留模型输入，并在缺失时按工具参数自动生成。
# 设计：分别覆盖显式 description 与 bash/read_file 兜底，保证实时和历史标题稳定。
def test_enrich_tool_input_adds_timeline_description() -> None:
    registry = ToolRegistry()
    assert registry.enrich_tool_input("bash", {"command": "pytest -q"})["description"] == "运行命令：pytest -q"
    assert registry.enrich_tool_input("read_file", {"path": "README.md"})["description"] == "读取 README.md"
    assert registry.enrich_tool_input("bash", {"command": "pwd", "description": "获取当前工作目录"})["description"] == "获取当前工作目录"