# Page Database SDK Contract

> 本文件定义 Agent 写 HTML 时可使用的 `window.__SMART_PAGE__.database` 运行时协议。
> 跨模块建表、查 schema、导入 CSV、服务端侧更新记录等能力详见 `../database/entry.md`。

## 1. 注入与调用

平台 iframe-sandbox 会在用户脚本执行前注入 SDK。HTML 中直接读取：

```javascript
var db = window.__SMART_PAGE__.database;
```

所有方法返回 `Promise`。`databaseId` 必须以字符串字面量硬编码到 HTML，值来自 `../database/create_database.py` 的 stdout。

## 2. 可用方法

| 方法 | 用途 | 参数 |
| --- | --- | --- |
| `db.query(params)` | 查询记录列表 | `{ databaseId, filter?, sorts?, fields?, startCursor?, pageSize? }` |
| `db.addRecord(params)` | 添加一条记录 | `{ databaseId, properties }` |
| `db.getRecord(params)` | 获取单条记录 | `{ databaseId, recordId, fields? }` |
| `db.updateRecord(params)` | 更新一条记录（增量，仅更新传入的字段） | `{ databaseId, recordId, properties? }` |
| `db.deleteRecord(params)` | 删除一条记录 | `{ databaseId, recordId }` |
| `db.getSchema(params)` | 获取数据库 Schema | `{ databaseId }` |

写入类方法返回：`db.updateRecord` → `{ id }`（**增量更新**：只覆盖 `properties` 中传入的字段，未传字段保持不变）；`db.deleteRecord` → `{}`（无返回体）。`updateRecord` 的 `properties` 结构同 `db.addRecord`（见 §3 PropertyValue）。

## 3. PropertyValue

`db.addRecord` 的 `properties` 是 `map<string, PropertyValue>`，key 必须与 database schema 字段名完全一致。

每个 `PropertyValue` 是 oneof 结构：`{ "<类型字段>": <值> }`。

| 类型字段 | 值类型 | 示例 |
| --- | --- | --- |
| `text` | string | `{ text: "张三" }` |
| `number` | number | `{ number: 25 }` |
| `select` | string | `{ select: "opt_1" }` 或 `{ select: "进行中" }` |
| `multi_select` | string[] | `{ multi_select: ["opt_a", "opt_b"] }` 或 `{ multi_select: ["篮球", "钢琴"] }` |
| `date` | string | `{ date: "2026-06-24" }` |
| `checkbox` | boolean | `{ checkbox: true }` |
| `url` | object | `{ url: { text: "官网", link: "https://example.com" } }` |
| `email` | string | `{ email: "a@example.com" }` |
| `phone_number` | string | `{ phone_number: "13800138000" }` |
| `image` | object | `{ image: { images: [{ title: "封面", imageUrl: "https://example.com/a.png", width: 800, height: 600 }] } }` |

`select` / `multi_select` 可传选项文本或选项 id；Agent 写 HTML 时优先从 `OPTIONS_MAP` 取 `.id`。

```javascript
properties["部门"] = { select: OPTIONS_MAP["部门"][selectedKey].id };
properties["技能"] = {
  multi_select: Array.prototype.map.call(selectedEls, function(el) {
    return OPTIONS_MAP["技能"][el.value].id;
  })
};
```

## 4. Query Params

`filter` 是递归树，节点三选一：

| 节点 | JSON 结构 |
| --- | --- |
| 单字段条件 | `{ property: { property: "字段名", text/number/select/date/checkbox: {...} } }` |
| AND | `{ and: [filter1, filter2] }` |
| OR | `{ or: [filter1, filter2] }` |

条件字段与操作符：

| 字段类型 | 条件字段 | 操作符 |
| --- | --- | --- |
| text / url / email / phone_number | `text` | `equals`, `contains` |
| number | `number` | `equals`, `greater_than`, `less_than` |
| select / multi_select | `select` | `equals`, `does_not_equal` |
| date | `date` | `equals`, `before`, `after` |
| checkbox | `checkbox` | `equals`, `does_not_equal` |

`sorts` 结构：

```javascript
[{ property: "字段名", direction: "ascending" }]
```

`direction` 可为 `"ascending"` 或 `"descending"`。

> **字段引用约束**：`sorts[].property`、`filter` 叶子的 `property`、以及 `fields[]` 里的字段名，**必须逐一来自 `db.getSchema()` 返回的真实字段名**；schema 中没有的字段不能引用。

## 5. GetSchema 返回值

`db.getSchema({ databaseId })` 返回 `{ id, title, properties }`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 数据库 ID |
| `title` | string | 数据库标题 |
| `properties` | array | 字段定义列表 |

`properties` 中每项结构：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | string | 字段 ID |
| `name` | string | 字段名称 |
| `type` | string | 字段类型（`text`、`number`、`select`、`multi_select`、`date`、`checkbox`、`url`、`email`、`phone_number`、`image`） |
| `config` | object? | 字段配置，`select`/`multi_select` 类型包含 `options: [{ text, id }]` |

示例：

```javascript
var schema = await db.getSchema({ databaseId: "db_xxx" });
// schema.properties → [{ id: "f1", name: "姓名", type: "text" }, { id: "f2", name: "状态", type: "select", config: { options: [{ text: "进行中", id: "opt_1" }] } }]
```

## 6. FieldValue

`db.query` 返回 `{ results, nextCursor, hasMore }`，记录数组一律从 `result.results` 取（翻页配套 `result.nextCursor` / `result.hasMore`）；`db.getRecord` 返回 `{ result }`。记录对象是扁平对象：`{ "字段名": 值 }`（含系统主键 `_id`）。

`db.query` 返回示例：

```json
{
  "results": [
    {
      "_id": "2rVLfQTl3uHurZq7dfrbdG",
      "姓名": "小李",
      "所属单位": "腾讯",
      "手机号": "123456",
      "邮箱": "123456789@qq.com",
      "参与人数": 2,
      "参与场次": "全天参与"
    }
  ],
  "nextCursor": "2rVLfQTl3uHurZq7dfrbdG",
  "hasMore": true
}
```

| 字段类型 | 返回值 |
| --- | --- |
| text / select / email / phone_number | string |
| number | number |
| date | string，ISO 8601（如 `"2026-06-24T10:00:00Z"`） |
| checkbox | boolean |
| multi_select | string[] |
| url | `{ text, link }` |
| image | `[{ imageUrl, title, width, height }]` |
| 空值 | `null` |

渲染 image 时先判空：

```javascript
var imgs = row["图片"];
var src = imgs && imgs[0] ? imgs[0].imageUrl : "";
```

## 7. SDK 调用识别

`parse_html.py` 识别已有 SDK 调用时使用的方法集合：

```text
addRecord|deleteRecord|getRecord|getSchema|query|updateRecord
```

命中后输出 `existing_databases`，后续上传时通过 `import_html.py --databases` 关联这些 database。
