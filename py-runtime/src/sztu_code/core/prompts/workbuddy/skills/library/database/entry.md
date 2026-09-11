# database —— 结构化数据表品类入口

> 资料库内**「结构化数据表（database）」**品类的能力承载者，对标类 Notion 多维表。
> 本入口承载**路由 + 能力契约 + 接口字段 + stdout 协议**；脚本直接平铺在 `database/` 目录下。
> **字段值 / 过滤 / 排序结构**：建表 `config`、写入 `properties`、查询 `filter`/`sorts` 的完整结构与示例统一放在 `params-reference.md`，本文件各能力仅给出调用形态，设计表结构和构造 payload 时按需查阅该文件。

## 模块定位

- **建表**：定义字段（text / number / currency / select / multi_select / date / checkbox / url / email / phone / image / attachment / person 等）
- **schema 查询**：拉取已有表结构
- **字段变更**：向已有表新增、修改（含改名 / 改类型）、删除列
- **记录写入**：每次批量插入、增量修改或删除 1–100 条记录
- **记录查询**：按 filter + sort + 分页查记录、按 record_id 取单条
- **内容导出**：获取整张表的内容（CSV 格式文本）
- **CSV / Excel 导入**：CSV 按 `csv-import-flow.md` 导入；Excel 先按子表拆成 CSV，再复用同一流程
- 服务于「数据页面（page）」的下游能力（page 模块会跨模块调用本模块脚本）

## 与其它模块的关系

| 模块 / 能力 | 关系 |
| --- | --- |
| `manage` 模块 | 共享 `library/_common.py`（runtime 分派 / token 读取 / HTTP / URL 拼接 / 脱敏 / 退出）；person 只有 name、没有 id 时，写入前调用 `space.permission.collaborators` 解析协作成员 UID |
| `page` 模块 | page 模块**会调用**本模块脚本；接口契约稳定后再开放调用 |
| `doc` 模块 | 文档中嵌入数据表通过后续版本联动协议实现 |

## 能力总览

| 能力 ID | 触发关键词 | 落地脚本 | stdout 协议 |
|---|---|---|---|
| `create_database` | 在空间里建一张表 / 创建 database | `create_database.py` | JSON `{"database_id": "...", "space_id": "...", "property_count": N, "properties": [...]}` |
| `get_database_schema` | 看看这个 database 有哪些字段 / 获取 schema | `get_database_schema.py` | JSON `{"id": "...", "title": "...", "properties": [...]}` |
| `add_database_field` | 给这张表加一列 / 新增字段 | `add_database_field.py` | JSON `{"field_id": "...", "properties": [...]}` |
| `update_database_field` | 修改字段名 / 修改字段类型 | `update_database_field.py` | JSON `{"properties": [...]}` |
| `delete_database_field` | 删掉这张表的某一列 / 删除字段 | `delete_database_field.py` | JSON `{"properties": [...]}` |
| `batch_add_database_records` | 往这个表里批量添加数据 / 插入多条记录 | `batch_add_database_records.py` | JSON `{"results":[...]}` |
| `batch_update_database_records` | 批量修改记录字段 / 更新记录 | `batch_update_database_records.py` | JSON `{"results":[...]}` |
| `batch_delete_database_records` | 批量删除记录 / 删除数据行 | `batch_delete_database_records.py` | JSON `{"results":[...]}` |
| `get_database_record` | 取 record_id=<rid> 的详情 | `get_database_record.py` | JSON `{"record_id": "...", "fields": {...}}` |
| `query_database_record` | 查一下 xxx 表里满足条件的记录 | `query_database_record.py` | JSON `{"results": [{"record_id":"...", ...}], "next_cursor": "...", "has_more": bool}` |
| `get_database_content` | 导出这个 database 的全部内容 / 获取表数据 CSV | `get_database_content.py` | JSON `{"database_id": "...", "content": "..."}` |
| `import_csv` | 导入本地 CSV 文件创建/更新 Database | `csv-import-flow.md`（按路径调用现有脚本） | 见 `csv-import-flow.md` §5 |
| `import_excel` | 导入本地 Excel，每个 sheet 创建一张 Database | 宿主拆表后复用 `csv-import-flow.md` | 按 sheet 汇总 `csv-import-flow.md` §5 结果 |

> **互斥**：单次路由只进入一个能力；能力内部如需串联多个脚本（如 Excel 拆表后逐 CSV 导入，或先 get_schema 再 batch_add_records），按流程顺序执行，每次独立失败不阻塞下一次。
>
> **目录布局**：脚本与流程文档平铺在 `database/` 目录下；`entry.md` 为本模块主文档，`params-reference.md` 为字段结构参考。

---

## 1. 能力 · 创建 Database（create_database）

**触发**：「在空间里建一张学生信息表」「创建一个 database」等。

> **前置**：先按 `manage/entry.md` 选择运行分支；仅客户端模式需要 `connect_open_platform` 拿到 `<token>`。目标空间按顶层 `SKILL.md` §调用前置执行；按 `parent_id` 新建时同时传入其所属的匹配 `space_id`。

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/database/create_database.py" --token-stdin --schema '<JSON>'
```

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--schema <JSON>` | **是（flags 模式）** | 完整 schema JSON（含 title、properties、可选 space_id / parent_id） |

schema `properties[].config` 各类型结构、**完整建表 schema 样板**（含 12 种字段类型一次性建表）见 `params-reference.md` §PropertyConfig / §完整建表 schema 示例。最小 `<JSON>` 形如：

```json
{
  "title": "学生信息表",
  "properties": [
    { "name": "姓名", "config": { "text":   "" } },
    { "name": "年龄", "config": { "number": 0  } }
  ]
}
```

按顶层规则需要传入目标空间时，才在 schema 中加入 `"space_id":"<target_space_id>"`；若还指定目录，则同时加入归属匹配的 `"parent_id":"<target_parent_node_id>"`。

select / multi_select 的新选项可省略 `options[].id` 由服务端生成；若调用方传入 id，必须保证稳定且不与其它选项冲突。始终以成功响应 `properties` 中的最终 id 为准。

**输出契约**：成功 → stdout JSON `{"database_id": "...", "space_id": "...", "property_count": N, "properties": [...]}`。`properties` 是创建后的完整最新字段 schema，包含服务端生成的字段 / 选项 id；后续写入记录应使用这里返回的 id。

---

## 2. 能力 · 获取 Database Schema（get_database_schema）

**触发**：「看看这个 database 有哪些字段」「获取 schema / 表结构」等。

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/database/get_database_schema.py" --token-stdin --database-id "<database_id>"
```

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--database-id <id>` | **是** | 目标 Database ID |

**输出契约**：成功 → stdout JSON `{"id": "...", "title": "...", "properties": [...]}`（`properties[]` 含 id / name / type / config）。返回侧 `config` 是当前 `type` 的内部配置，不带类型 oneof 包裹；例如 select 字段返回 `{"id":"f1","name":"状态","type":"select","config":{"options":[{"id":"opt_1","text":"进行中","style":0}]}}`。create/add/update/delete-field 返回的 `properties` 采用相同结构。

---

## 2.1 能力 · 添加字段（add_database_field）

**触发**：「给这张表加一列」「新增一个字段」「加个 xxx 列」等。

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/database/add_database_field.py" --token-stdin --database-id "<id>" --property '<JSON>'
```

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--database-id <id>` | **是（flags 模式）** | 目标 Database ID |
| `--property <JSON>` | **是（flags 模式）** | 新字段定义 `{name, config}`；字段名不能与已有字段重复，config 见 `params-reference.md` §PropertyConfig |

`property` 结构为单个 `{name, config}`，示例（text / select 等）见 `params-reference.md` §添加 / 修改字段 property 示例。新选项可省略 `options[].id` 由服务端生成；始终以成功响应 `properties` 中的最终 id 为准。

**输出契约**：成功 → stdout JSON `{"field_id": "...", "properties": [...]}`。`properties` 是添加后的完整最新字段 schema，包含服务端生成的选项 id。

---

## 2.2 能力 · 修改字段（update_database_field）

**触发**：「把状态列改名为阶段」「把这个字段改成单选」「修改字段类型 / 更新列」等。

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/database/update_database_field.py" --token-stdin --database-id "<id>" --field-id "<fid>" --property '<JSON>'
```

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--database-id <id>` | **是（flags 模式）** | 目标 Database ID |
| `--field-id <fid>` | **是（flags 模式）** | 要修改的字段 ID（可通过 `get_database_schema.py` 的 `properties[].id` 获取） |
| `--property <JSON>` | **是（flags 模式）** | 新字段定义 `{name, config}`；`name` 必填且不能为空，未传 `config` 或传空对象时仅改名 |

两种调用形态：仅改名传 `{ "name": "阶段" }`；改名 + 改类型 / 改选项传完整 `{name, config}`。示例见 `params-reference.md` §添加 / 修改字段 property 示例。修改字段类型时也必须同时传入当前字段名或新字段名。

**输出契约**：成功 → stdout JSON `{"properties": [...]}`，为修改后的完整最新字段 schema。

> 改字段类型 / 删 select·multi_select 已有选项有数据清空风险，详见 §13 安全约束。只改字段名无此风险。修改 select / multi_select 选项时，已有选项必须复用当前 schema 中的 id；新选项可省略 id 由服务端生成。

---

## 2.3 能力 · 删除字段（delete_database_field）

**触发**：「删掉这张表的某一列」「删除 xxx 字段」「移除这个属性」等。

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/database/delete_database_field.py" --token-stdin --database-id "<id>" --field-id "<fid>"
```

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--database-id <id>` | **是（flags 模式）** | 目标 Database ID |
| `--field-id <fid>` | **是（flags 模式）** | 要删除的字段 ID（可通过 `get_database_schema.py` 的 `properties[].id` 获取） |

**输出契约**：成功 → stdout JSON `{"properties": [...]}`，为删除后的完整最新字段 schema。

> 删除后该列数据不可恢复；执行条件与确认规则详见 §13 安全约束。

---

## Person 写入前置解析（新增 / 修改记录共用）

新增或修改 person 列前统一解析：

- 已有 `id`：直接使用。
- 只有 `name`：调用 `space.permission.collaborators`，`node-id` 传当前操作的 `database-id`（调用方式见 `../manage/entry.md`），用去除首尾空白后的姓名查找成员。
- 唯一精确命中：将 `uid` 转为 `id` 后直接写入。
- 无精确命中：展示模糊候选并请用户确认；模糊候选不得自动写入。
- 多个精确命中或查询异常：整批都不提交；多个精确命中时列出 UID 和 role，请用户确认。

同批多个姓名须全部得到唯一精确结果或用户确认后再写入。

---

## 3. 能力 · 批量添加记录（batch_add_database_records）

**触发**：「往这个表里添加数据」「批量插入记录」等。即使只添加一条，也使用单元素 `records` 数组。

> 写入 person 列前必须执行上方「Person 写入前置解析」；未唯一解析的姓名不得进入本接口。

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/database/batch_add_database_records.py" --token-stdin --database-id "<id>" --records '<JSON array>'
```

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--database-id <id>` | **是（flags 模式）** | 目标 Database ID |
| `--records <JSON array>` | **是（flags 模式）** | 1–100 个字段值对象；每个对象是 map<字段名, PropertyValue>，结构见 `params-reference.md` §PropertyValue |

`records` 每个对象是 map<字段名, PropertyValue>，完整字段值示例见 `params-reference.md` §PropertyValue。每条记录都会先校验字段名和 PropertyValue oneof；任一记录校验后为空时整批拒绝且不发请求。select / multi_select 可传选项文本或选项 id，服务端按当前 schema 解析。

**输出契约**：整体请求成功 → stdout 直接输出服务端批量结果 JSON，例如 `{"results":[{"index":0,"id":"rec_1","success":true},{"index":1,"success":false,"error":"错误信息"}]}`。逐条失败保留在 `results` 中，不提升为整体脚本失败。

---

## 4. 能力 · 批量修改记录（batch_update_database_records）

**触发**：「修改这些记录」「批量更新记录」等。即使只更新一条，也使用单元素 `records` 数组。

> 修改 person 列前必须执行上方「Person 写入前置解析」；未唯一解析的姓名不得进入本接口。

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/database/batch_update_database_records.py" --token-stdin --database-id "<id>" --records '<JSON array>'
```

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--database-id <id>` | **是（flags 模式）** | 目标 Database ID |
| `--records <JSON array>` | **是（flags 模式）** | 1–100 个 `{record_id, properties}` 对象；`record_id` 必须非空，`properties` 必须至少含一个有效字段 |

```json
[
  { "record_id": "rec_1", "properties": { "状态": { "select": "完成" } } },
  { "record_id": "rec_2", "properties": { "完成": { "checkbox": true } } }
]
```

`properties` 格式见 `params-reference.md` §PropertyValue。本接口是**增量更新**，未传字段保持不变；任一项非法时整批拒绝且不发请求。

**输出契约**：整体请求成功 → stdout 直接输出完整 `{"results":[...]}` JSON；逐条失败不提升为整体脚本失败。

---

## 5. 能力 · 批量删除记录（batch_delete_database_records）

**触发**：「删除这些记录」「批量删除数据行」等。即使只删除一条，也使用单元素 `record_ids` 数组。

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/database/batch_delete_database_records.py" --token-stdin --database-id "<id>" --record-ids '["rec_1","rec_2"]'
```

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--database-id <id>` | **是（flags 模式）** | 目标 Database ID |
| `--record-ids <JSON array>` | **是（flags 模式）** | 1–100 个非空记录 ID |

删除遵循服务端幂等语义：记录不存在也视为成功。

**输出契约**：整体请求成功 → stdout 直接输出完整 `{"results":[...]}` JSON；逐条失败不提升为整体脚本失败。

---

## 6. 能力 · 获取单条记录（get_database_record）

**触发**：「取 record_id=<rid> 的详情」「获取这条记录」等。

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/database/get_database_record.py" --token-stdin --database-id "<id>" --record-id "<rid>"
```

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--database-id <id>` | **是** | 目标 Database ID |
| `--record-id <rid>` | **是** | 目标记录 ID |

**输出契约**：成功 → stdout JSON `{"record_id": "...", "fields": {...}}`（`fields` 各字段返回值形态见 `params-reference.md` §FieldValue）

---

## 7. 能力 · 查询记录列表（query_database_record）

**触发**：「查一下 xxx 表里满足条件的记录」「列出所有记录」「按条件查记录」等。

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/database/query_database_record.py" --token-stdin --database-id "<id>"
```

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--database-id <id>` | **是（flags 模式）** | 目标 Database ID |
| `--filter <JSON>` | 否 | 过滤条件，结构见 `params-reference.md` §Filter |
| `--sorts <JSON>` | 否 | 排序规则，结构见 `params-reference.md` §Sort |
| `--fields <JSON>` | 否 | 需要返回的字段名列表 |
| `--page-size N` | 否 | 每页返回记录数 |
| `--start-cursor <cursor>` | 否 | 分页游标 |

**输出契约**：成功 → stdout JSON `{"results": [{"record_id":"...", "<字段名>":<FieldValue>, ...}], "next_cursor": "...", "has_more": bool}`。`results[]` 保持扁平行结构，记录 ID 统一使用 `record_id`，其余字段值形态见 `params-reference.md` §FieldValue。

---

## 8. 能力 · 获取数据库内容（get_database_content）

**触发**：「导出这个 database 的全部内容」「获取表数据」「拿一下这张表的 CSV」等。

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/database/get_database_content.py" --token-stdin --database-id "<database_id>"
```

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--database-id <id>` | **是** | 目标 Database ID |

**输出契约**：成功 → stdout JSON `{"database_id": "...", "content": "..."}`（`content` 为 CSV 文本，首行表头、后续数据行）

---

## 9. 能力 · 导入 CSV（import_csv）

**触发**：「把这个 CSV 导入成 database」「导入本地 CSV 文件」「从 CSV 创建数据表」等。

> 参考 `csv-import-flow.md`。

---

## 10. 能力 · 导入 Excel（import_excel）

**触发**：用户提供本地 `.xlsx` / `.xls` 文件，并要求导入成数据表 / database / 在线表 / 多维表。

1. 转换前先枚举工作簿的**全部 sheet**，生成清单 `{sheet_index, sheet_name, visibility, csv_path, status}`；后续转换、调度和汇总均以该清单为准，禁止通过扫描临时目录推断 sheet 集合。
2. 每个非空 sheet 转成独立的 UTF-8 CSV：表头拍平为单行；合并单元格按需填充；公式取计算后的值；文件名使用 `<安全化 sheet_name>.csv`，安全化后重名时追加递增后缀避免覆盖。空 sheet 标记为 `skipped_empty`；隐藏 sheet 不得静默跳过，默认转换，明确不导入时标记为 `skipped_hidden`。
3. 调度前逐项校验清单：每个 sheet 必须处于 `converted` / `skipped_empty` / `skipped_hidden` / `convert_failed` 之一；`converted` 项对应的 CSV 必须存在、非空且包含表头。转换失败须记录错误，不得从清单中删除。
4. 只有 1 个 `converted` sheet 时，由当前 agent 串行执行 `csv-import-flow.md`，无需创建子 agent。
5. 有 ≥2 个 `converted` sheet 且各 sheet 独立建表时，每个 CSV 分配一个独立子 agent 并发执行 `csv-import-flow.md`；并发度建议为 3~5，超过上限时分批调度，子 agent 之间不得共享中间状态。
6. 多个 sheet 需要写入同一个既有 Database、存在先后依赖，或用户明确要求按顺序处理时，保持串行，禁止并发写同一 Database。
7. 每个执行单元返回 `csv-import-flow.md` §5 的结构化结果并附带 `sheet_index`、`sheet_name`；最终逐项回填清单并校验 `sheet 总数 = 成功 + 部分失败 + 失败 + 跳过`。存在未归档 sheet 时不得宣称导入完成，必须列出缺失项。

---

## 11. 参数参考

字段值 / 过滤 / 排序结构统一见 **`params-reference.md`**：

- **PropertyConfig**：建表 / 添加字段 / 修改字段类型的字段配置（text / number / currency / select / multi_select / date / checkbox / url / email / phone_number / image / attachment / person）
- **PropertyValue**：写入侧字段值结构（add / update 记录共用）
- **FieldValue**：查询 / 获取记录接口的返回值形态（与 PropertyValue 不同）
- **Filter**：递归树形过滤结构（property / and / or）及各列类型操作符
- **Sort**：排序规则

---

## 12. 用户回执模板

| 操作 | 成功回执 | 失败回执 |
| --- | --- | --- |
| 创建 Database | `已创建 Database「<title>」（id=<database_id>），可在资料库中查看。` | 按 `error_handling.md` 错误码行动表生成回执 |
| 获取 schema | 摘要展示字段名 / 类型 / 选项 | `获取表结构失败。` |
| 添加字段 | `已为 Database <database_id> 新增字段「<name>」（field_id=<field_id>）。` | 按 `error_handling.md` 错误码行动表生成回执 |
| 修改字段 | `已更新 Database <database_id> 中的字段 <field_id>。` | 按 `error_handling.md` 错误码行动表生成回执 |
| 删除字段 | `已删除 Database <database_id> 中的字段 <field_id>。` | 按 `error_handling.md` 错误码行动表生成回执 |
| 批量插入记录 | 根据 `results` 汇总成功/失败数，并列出逐条错误 | 按 `error_handling.md` 错误码行动表生成回执 |
| 批量修改记录 | 根据 `results` 汇总成功/失败数，并列出逐条错误 | 按 `error_handling.md` 错误码行动表生成回执 |
| 批量删除记录 | 根据 `results` 汇总成功/失败数，并列出逐条错误 | 按 `error_handling.md` 错误码行动表生成回执 |
| 取单条 / 查询 | 用 markdown 表格展示 results | 按 `error_handling.md` 错误码行动表生成回执 |
| 获取数据库内容 | 展示 CSV 文本或摘要信息 | 按 `error_handling.md` 错误码行动表生成回执 |
| 导入 CSV | `已成功导入 CSV 文件「<file_name>」到 Database（node_block_id=<id>）。` | 按 `error_handling.md` 错误码行动表生成回执 |
| 导入 Excel | 按 sheet 汇总 database 标识、访问链接及成功 / 失败行数 | 按 sheet 汇总错误，其余 sheet 照常回执 |

被其它 skill 内部调用时**不单独回执**，直接消费脚本 stdout。

---

## 13. 安全约束

- 涉及密码 / key / 身份证号等 L3/L4 数据时立即按顶层 `SKILL.md` 停止，不得以用户确认放行。
- 删除字段（delete_database_field）、批量删除记录（batch_delete_database_records）仅在用户明确要求且目标或目标集合已确定时执行；删除后数据不可恢复，需要用户确认。
- 修改字段类型时服务端转换存量数据，无法兼容转换的单元格会被清空；删除 select / multi_select 已有选项会清理引用该选项的单元格。这两类只在用户明确要求且受影响字段或选项集合已确定时执行；需要用户确认。只改字段名无此风险，按普通空间分支处理。
- select / multi_select 的 `option.id` 一旦写入后端**永久有效**，禁止替换；修改字段时已有选项必须原样复用其 id。
