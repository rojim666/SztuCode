# 工具 Schema 缓存隔离 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `ToolRegistry.tool_schemas()` 返回可独立修改的深拷贝，同时保留内部缓存及注册后的失效行为。

**Architecture:** `_schema_cache` 继续保存 Registry 私有的规范 Schema。`tool_schemas()` 只在缓存为空时构建，所有公开返回都对缓存执行 `deepcopy`；测试通过修改顶层和嵌套对象验证调用方隔离，并验证注册后缓存替换和旧快照稳定。

**Tech Stack:** Python 3.12、`copy.deepcopy`、pytest、Ruff、Mypy。

---

### Task 1: 添加公开快照隔离的失败测试

**Files:**
- Modify: `tests/unit/test_tool_registry.py`

- [ ] **Step 1: 为假工具加入可识别的嵌套属性**

将 `_FakeTool.input_schema` 调整为包含一个实际参数：

```python
input_schema: dict[str, object] = {
    "type": "object",
    "properties": {"value": {"type": "string"}},
    "required": [],
}
```

- [ ] **Step 2: 写顶层和嵌套修改隔离测试**

```python
# 功能：验证调用方修改公开 Schema 的任意可变层级都不会污染后续调用
# 设计：同时追加顶层列表、改写工具字典并清空嵌套 properties，覆盖浅拷贝无法隔离的边界
def test_tool_schemas_returns_isolated_provider_snapshots() -> None:
    registry = ToolRegistry()
    registry.register(_FakeTool())

    provider_a_schemas = registry.tool_schemas()
    provider_a_schemas.append({"name": "injected"})
    provider_a_schemas[0]["description"] = "changed"
    input_schema = provider_a_schemas[0]["input_schema"]
    assert isinstance(input_schema, dict)
    properties = input_schema["properties"]
    assert isinstance(properties, dict)
    properties.clear()

    provider_b_schemas = registry.tool_schemas()
    assert len(provider_b_schemas) == 1
    assert provider_b_schemas[0]["name"] == "fake"
    assert provider_b_schemas[0]["description"] == "A fake tool"
    provider_b_input_schema = provider_b_schemas[0]["input_schema"]
    assert isinstance(provider_b_input_schema, dict)
    provider_b_properties = provider_b_input_schema["properties"]
    assert isinstance(provider_b_properties, dict)
    assert set(provider_b_properties) == {"value", "description"}
```

- [ ] **Step 3: 运行测试并确认 RED 原因**

Run:

```text
pytest tests/unit/test_tool_registry.py::test_tool_schemas_returns_isolated_provider_snapshots -q
```

Expected: FAIL，第二次调用仍包含注入的工具或被修改的字段，证明公开返回泄露内部缓存。

### Task 2: 验证内部缓存复用与注册失效

**Files:**
- Modify: `tests/unit/test_tool_registry.py`

- [ ] **Step 1: 替换依赖公开对象身份的旧测试**

将 `test_tool_schemas_are_cached_until_registration` 改为验证私有缓存身份和公开副本隔离：

```python
# 功能：验证连续调用复用内部缓存，但每次公开结果都是独立快照
# 设计：分别比较 `_schema_cache` 与公开结果的对象身份，避免把缓存实现误当成公开所有权契约
def test_tool_schemas_reuses_internal_cache_without_sharing_results() -> None:
    registry = ToolRegistry()
    registry.register(_FakeTool())

    first = registry.tool_schemas()
    cached = registry._schema_cache
    second = registry.tool_schemas()

    assert registry._schema_cache is cached
    assert second == first
    assert second is not first
    assert second[0] is not first[0]
    assert second[0]["input_schema"] is not first[0]["input_schema"]
```

- [ ] **Step 2: 添加注册后新旧快照测试**

```python
# 功能：验证注册新工具会替换内部缓存，且不会反向修改注册前取得的快照
# 设计：保留旧快照和旧缓存引用，注册另一工具后同时比较名称集合与缓存身份
def test_registration_invalidates_cache_without_changing_old_snapshot() -> None:
    registry = ToolRegistry()
    registry.register(_FakeTool())
    old_snapshot = registry.tool_schemas()
    old_cache = registry._schema_cache

    registry.register(_AnotherTool())
    new_snapshot = registry.tool_schemas()

    assert {schema["name"] for schema in old_snapshot} == {"fake"}
    assert {schema["name"] for schema in new_snapshot} == {"fake", "another"}
    assert registry._schema_cache is not old_cache
```

- [ ] **Step 3: 运行三个新测试并确认现有实现仍为 RED**

Run:

```text
pytest tests/unit/test_tool_registry.py -k "isolated_provider_snapshots or internal_cache or invalidates_cache" -q
```

Expected: 快照隔离测试和公开结果身份断言失败；注册失效行为本身通过。

### Task 3: 实现安全副本契约

**Files:**
- Modify: `src/sztu_code/core/tools/registry.py:88-118`

- [ ] **Step 1: 让所有返回路径深拷贝内部缓存**

移除缓存命中时直接返回的分支，把现有构建逻辑放在 `_schema_cache is None` 条件内，并在方法末尾统一返回：

```python
# 返回工具 schema 的独立深拷贝，内部缓存仅由注册表持有
def tool_schemas(self) -> list[dict[str, object]]:
    if self._schema_cache is None:
        schemas: list[dict[str, object]] = []
        # 保留现有 Schema 构建循环
        self._schema_cache = schemas
    return deepcopy(self._schema_cache)
```

- [ ] **Step 2: 运行专项测试验证 GREEN**

Run:

```text
pytest tests/unit/test_tool_registry.py -q
```

Expected: 全部测试通过。

### Task 4: 全量验证与发布准备

**Files:**
- Modify: no additional files

- [ ] **Step 1: 运行静态检查和完整单元测试**

Run:

```text
ruff check src/sztu_code/core/tools/registry.py tests/unit/test_tool_registry.py
mypy src/sztu_code/core/tools/registry.py
pytest tests/unit -q
git diff --check
```

Expected: 专项 Ruff、Mypy 和差异检查通过；完整单元测试不新增相对 `upstream/main` 的失败。

- [ ] **Step 2: 检查最终变更范围**

Run:

```text
git status --short
git diff --stat upstream/main...HEAD
git diff -- src/sztu_code/core/tools/registry.py tests/unit/test_tool_registry.py
```

Expected: 只包含 Registry、对应单元测试以及本 issue 的两份过程文档。

- [ ] **Step 3: 创建中文签名提交并发布 PR**

Run:

```text
git add src/sztu_code/core/tools/registry.py tests/unit/test_tool_registry.py docs/superpowers/specs/2026-08-09-tool-schema-cache-isolation-design.md docs/superpowers/plans/2026-08-09-tool-schema-cache-isolation.md
git commit -s -m "fix: 隔离工具 Schema 缓存"
git push -u origin fix/78-tool-schema-cache
```

Expected: 提交包含 `Signed-off-by`，分支推送到个人 fork；随后创建中文 Draft PR、核对 CI，并在检查通过后设为 Ready for review。
