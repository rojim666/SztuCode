# 工具 Schema 缓存隔离设计

## 背景

`ToolRegistry.tool_schemas()` 会缓存构建完成的工具 Schema，但当前公开方法直接返回 `_schema_cache`。调用方因此获得 Registry 内部可变对象的所有权：修改返回列表、其中的工具字典或更深层的 `input_schema.properties`，都会污染后续调用以及其他 Provider 看到的 Schema。

Issue #78 要求保留缓存和现有 Schema 格式，同时让每个调用方获得可以独立修改的安全快照。

## 目标与验收标准

- 调用方修改第一次返回值的顶层列表、工具字典和嵌套 `properties` 后，下一次调用仍返回完整原始 Schema。
- Registry 未发生注册变更时继续复用内部缓存，但不同公开返回值不共享可变对象。
- 注册新工具后缓存失效，新结果包含新工具，注册前取得的旧快照不被反向修改。
- 不同 Provider 依次获取和转换 Schema 时，各自的修改不会影响 Registry 或其他 Provider。
- `tests/unit/test_tool_registry.py` 的专项测试通过。

## 非目标

- 不重构 `ToolRegistry` 的注册、别名或权限逻辑。
- 不移除 Schema 缓存，也不把整个缓存改造成不可变数据模型。
- 不改变对外 Schema 的字段、顺序或内容。
- 不修改 Provider API 或引入新的 Provider 抽象。

## 方案比较

### 方案一：公开返回深拷贝（推荐）

Registry 继续用可变的 `list[dict]` 保存内部缓存；首次调用构建缓存，之后每次公开返回时对缓存执行 `deepcopy`。该方案同时隔离顶层和任意深度的嵌套对象，改动集中在 `tool_schemas()`，不会改变调用方类型或 Schema 格式。

代价是每次调用仍需复制 Schema，但缓存继续避免重复遍历工具和补齐字段。工具 Schema 规模有限，相比跨请求共享状态的风险，这一成本可接受。

### 方案二：只复制列表或顶层字典

浅拷贝成本较低，但 `input_schema.properties` 等嵌套对象仍会共享，不能满足验收标准，予以排除。

### 方案三：缓存不可变结构，在 Provider 边界转换

把内部缓存改为递归不可变结构，再由每个 Provider 转回可变字典，可以建立更强约束，但需要新增转换逻辑并改变多个边界，超出本 issue 的最小范围，予以排除。

## 详细设计

### 缓存所有权

`_schema_cache` 仍是 Registry 私有的规范副本，只能在 `tool_schemas()` 构建、在 `register()` 中失效。公开方法不再把该对象本身交给调用方。

`tool_schemas()` 的流程调整为：

1. `_schema_cache` 为 `None` 时，按现有逻辑构建 Schema 并写入缓存。
2. `_schema_cache` 已存在时跳过构建。
3. 无论缓存是新建还是复用，都返回 `deepcopy(self._schema_cache)`。

方法上方的中文注释明确说明返回值是独立深拷贝、内部缓存只由 Registry 持有，避免后续代码重新依赖对象身份。

### 注册失效

`register()` 继续把 `_schema_cache` 设为 `None`。注册前已经返回的快照与缓存没有共享可变对象，因此注册新工具既不会修改旧快照，也会让下一次调用重新构建包含新工具的缓存。

### Provider 边界

Anthropic 和 OpenAI Provider 每次从 Agent Loop 获得的是独立 Registry 快照。现有转换代码不需要修改；即使某个转换结果或其嵌套参数随后被修改，也只能影响该次快照，下一次 `tool_schemas()` 会从未污染的内部缓存生成新副本。

## 测试设计

在 `tests/unit/test_tool_registry.py` 中增加或调整三类行为测试：

1. 修改第一次返回值的列表、工具字典和嵌套 `properties`，断言第二次调用的工具数量、名称、描述和属性仍完整。
2. 检查连续调用复用同一个 `_schema_cache`，但公开结果及其嵌套对象不是同一对象。
3. 注册第二个工具后，断言旧快照仍只含原工具，新快照包含两个工具，并且内部缓存已替换。

这些测试直接验证公开所有权契约，不依赖网络、模型或 daemon。

## 验收命令

```text
pytest tests/unit/test_tool_registry.py -q
ruff check src/sztu_code/core/tools/registry.py tests/unit/test_tool_registry.py
mypy src/sztu_code/core/tools/registry.py
git diff --check
```

实现完成后还会运行完整 `tests/unit`，并把 `upstream/main` 已存在的无关失败与本次结果对照记录。
