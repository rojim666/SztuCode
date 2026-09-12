# database · 参数参考

> 本文件承载 `database` 模块的字段值/过滤/排序结构参考。构造建表 config、写入 properties、查询 filter/sorts 时按需查阅；路由与能力契约见 `entry.md`。

## PropertyConfig

字段类型配置（建表 / 添加字段 / 修改字段类型用），使用 `oneof` 表示字段类型，各类型互斥：

| 类型字段 | 类型 | 说明 |
| --- | --- | --- |
| `number` | double | 数字类型: 适合记录数值型数据，如薪资、金额、数量、评分、年龄等 |
| `currency` | CurrencyConfig | 货币类型: 适合记录金额类数值，如价格、成本、预算、工资、账单金额等 |
| `select` | SelectConfig | 单选类型: 适合记录互斥的单一状态/分类，如跟进状态、订单状态、优先级、部门等 |
| `multi_select` | SelectConfig | 多选类型: 适合记录可同时具备多个标签/属性的字段，如员工标签、兴趣爱好、适用渠道等 |
| `date` | DateConfig | 日期类型: 适合记录任意日期或时间点，如入职日期、出生日期、当前时间、截止时间、发布日期等 |
| `checkbox` | bool | 复选框类型: 适合表示二元状态，如是否转正、是否完成、是否启用、是否已读等 |
| `url` | URLConfig | 链接类型: 适合承载网页链接类内容，如个人主页、参考资料、官网地址、文档链接等 |
| `email` | string | 邮箱类型: 适合收集各类邮箱地址，如联系邮箱、报名邮箱、订阅邮箱、找回密码邮箱等 |
| `phone_number` | string | 电话号码类型: 适合收集电话号码类信息，如联系电话、紧急联系人电话、客服热线等 |
| `image` | ImageConfig | 图片类型: 适合承载图片类内容，如头像、产品图、封面图、截图、证件照等 |
| `attachment` | AttachmentConfig | 附件类型: 适合承载多种媒体文件，如图片、视频、音频、文档、压缩包等混合附件 |
| `person` | PersonConfig | 人员类型: 适合关联系统内的用户/成员，如任务负责人、跟进人、审批人、创建人等 |
| `text` | string | 文本类型: 适合承载不属于以上任何结构化类型的自由文本，如备注、描述、说明等 |

**CurrencyConfig**：`{ currencySymbol: string, decimalPlaces: int, useSeparate: bool }`

- `currencySymbol`：货币符号，如 `"$"`、`"¥"`、`"€"`。
- `decimalPlaces`：小数位数。
- `useSeparate`：是否使用千分位分隔符。

**SelectConfig**：`{ options: [{ text: string, id?: string, style?: int }] }`

> select / multi_select 的新选项可省略 `id`，由服务端生成；create/add/update-field 成功响应的 `properties` 是最终 schema 与 id 的唯一可信来源。已有选项的 `id` **永久不变**，修改字段时必须原样复用，禁止为已有选项更换 id。`style` 可省略，新增选项默认使用服务端默认颜色。

**URLConfig**：`{ text: string, link: string }`

**ImageConfig**：`{ images: [{ title: string, imageUrl: string, width: int, height: int }] }`

**AttachmentConfig**：`{}`（空对象，列级无配置，建表/加列时固定传 `{ "attachment": {} }`）

**PersonConfig**：`{}`（空对象，列级无配置，建表/加列时固定传 `{ "person": {} }`）

**DateConfig**：`{ format: string }`

- `format`：日期显示格式，影响界面上 Date 字段的展示样式。可选值：

| 格式值 | 示例 |
| --- | --- |
| `yyyy"年"m"月"d"日"` | 2026年7月21日 |
| `yyyy-mm-dd` | 2026-07-21 |
| `yyyy/m/d` | 2026/7/21 |
| `m"月"d"日"` | 7月21日 |
| `[$-804]yyyy"年"m"月"d"日" dddd` | 2026年7月21日 星期二 |
| `m/d/yyyy` | 7/21/2026 |
| `d/m/yyyy` | 21/7/2026 |
| `yyyy"年"m"月"d"日" hh:mm` | 2026年7月21日 10:00 |
| `yyyy-mm-dd hh:mm` | 2026-07-21 10:00 |

### 完整建表 schema 示例

`create_database.py` 的 `--schema` / stdin `title + properties` 一次性建多种字段类型时的完整样板；`properties[].config` 各类型结构见上方各 Config 小节：

```json
{
  "title": "学生信息表",
  "properties": [
    { "name": "姓名",     "config": { "text":         "" } },
    { "name": "年龄",     "config": { "number":       0  } },
    { "name": "预算",     "config": { "currency":     { "currencySymbol": "¥", "decimalPlaces": 2, "useSeparate": true } } },
    { "name": "年级",     "config": { "select":       { "options": [ { "id": "g1", "text": "一年级" }, { "id": "g2", "text": "二年级" } ] } } },
    { "name": "兴趣",     "config": { "multi_select": { "options": [ { "id": "t1", "text": "篮球" }, { "id": "t2", "text": "钢琴" } ] } } },
    { "name": "入学日期", "config": { "date":         "2024-09-01T00:00:00Z" } },
    { "name": "是否住校", "config": { "checkbox":     false } },
    { "name": "主页",     "config": { "url":          { "text": "homepage", "link": "https://example.com" } } },
    { "name": "邮箱",     "config": { "email":        "" } },
    { "name": "手机",     "config": { "phone_number": "" } },
    { "name": "照片",     "config": { "image":        {} } },
    { "name": "附件",     "config": { "attachment":   {} } }
  ]
}
```

- 需要定向创建时，在顶层加 `"space_id":"<target_space_id>"`；若还指定目录，同时加归属匹配的 `"parent_id":"<target_parent_node_id>"`。
- select / multi_select 的新选项可省略 `options[].id` 由服务端生成；若传入 id 必须稳定且不与其它选项冲突。始终以成功响应 `properties` 中的最终 id 为准。

### 添加 / 修改字段 property 示例

`add_database_field.py` / `update_database_field.py` 的 `--property`（单个 `{name, config}`）：

```json
{ "name": "毕业院校", "config": { "text": "" } }
```

```json
{ "name": "状态", "config": { "select": { "options": [ { "id": "s1", "text": "在读" }, { "id": "s2", "text": "毕业" } ] } } }
```

`update_database_field.py` 未传 `config` 或传空对象时仅改名：

```json
{ "name": "阶段" }
```

## PropertyValue

写入侧字段值，各类型互斥；每个字段值必须是 `{ "<类型字段>": <值> }` 的 oneof 结构。`batch_add_database_records.py` 与 `batch_update_database_records.py` 共用此结构。

| 类型字段 | 值类型 | 示例 | 说明 |
| --- | --- | --- | --- |
| `text` | string | `{ "text": "张三" }` | 文本 |
| `number` | number | `{ "number": 25 }` | 数字 |
| `currency` | number | `{ "currency": 1234.56 }` | 货币数值；显示格式由列级 CurrencyConfig 控制 |
| `select` | string | `{ "select": "进行中" }` 或 `{ "select": "opt_1" }` | 单选；可传选项文本或选项 id |
| `multi_select` | string[] | `{ "multi_select": ["篮球", "钢琴"] }` 或 `{ "multi_select": ["opt_a", "opt_b"] }` | 多选；数组元素可传选项文本或选项 id |
| `date` | string | `{ "date": "2026-06-24" }` 或 `{ "date": "2026-06-24T10:00:00Z" }` | ISO 8601 日期/时间字符串 |
| `checkbox` | boolean | `{ "checkbox": true }` | 复选框 |
| `url` | object | `{ "url": { "text": "官网", "link": "https://example.com" } }` | 链接 |
| `email` | string | `{ "email": "a@example.com" }` | 邮箱 |
| `phone_number` | string | `{ "phone_number": "13800138000" }` | 电话号码 |
| `image` | object | `{ "image": { "images": [{ "title": "封面", "imageUrl": "https://...", "width": 800, "height": 600 }] } }` | 图片；`width` / `height` 可省略 |
| `attachment` | AttachmentItem[] | `{ "attachment": [{ "name": "报告.pdf", "attachmentId": "att_1", "fileType": "application/pdf", "fileSize": 10240, "mediaType": "file" }] }` | 附件；值为 AttachmentItem 数组，结构见下方 **AttachmentItem** |
| `person` | object[] | `{ "person": [{ "id": "uid123" }, { "id": "uid456" }] }` | 人员；**写入仅取 `id`**（用户唯一标识），`name` 由服务端在返回时填充，写入时可省略 |

完整 `properties` 示例：

```json
{
  "姓名": { "text": "张三" },
  "年龄": { "number": 25 },
  "预算": { "currency": 1234.56 },
  "状态": { "select": "进行中" },
  "标签": { "multi_select": ["重要", "客户"] },
  "截止日期": { "date": "2026-06-24" },
  "完成": { "checkbox": false },
  "官网": { "url": { "text": "官网", "link": "https://example.com" } },
  "邮箱": { "email": "a@example.com" },
  "电话": { "phone_number": "13800138000" },
  "负责人": { "person": [{ "id": "uid123" }] },
  "图片": {
    "image": {
      "images": [
        { "title": "封面", "imageUrl": "https://example.com/cover.png", "width": 800, "height": 600 }
      ]
    }
  },
  "附件": {
    "attachment": [
      { "name": "报告.pdf", "attachmentId": "att_1", "fileType": "application/pdf", "fileSize": 10240, "mediaType": "file" },
      { "name": "封面.png", "attachmentId": "att_2", "fileType": "image/png", "fileSize": 20480, "mediaType": "image", "width": 800, "height": 600 }
    ]
  }
}
```

### AttachmentItem

`attachment` 列写入侧数组元素结构（存储格式为 `[]AttachmentItem`）：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `name` | string | 是 | 文件名 |
| `url` | string | 否 | 文件访问 URL（仅图片列转换来的附件有值，无 `attachmentId` 时直接使用） |
| `thumbnailUrl` | string | 否 | 缩略图 URL（无 `attachmentId` 时使用，如图片列转换来的附件） |
| `fileType` | string | 是 | MIME type，如 `image/png`、`video/mp4`、`application/pdf` |
| `fileSize` | int64 | 是 | 文件大小（字节） |
| `mediaType` | string | 是 | 附件大类：`image` / `video` / `audio` / `file` |
| `attachmentId` | string | 否 | 服务端附件 ID（confirm 后获得，用于下载 / 预览） |
| `width` | int32 | 否 | 图片 / 视频的原始宽度 |
| `height` | int32 | 否 | 图片 / 视频的原始高度 |

> 已上传并完成 confirm 的附件用 `attachmentId` 引用；仅由图片列转换而来、尚无 `attachmentId` 的附件用 `url` / `thumbnailUrl` 直接引用。`width` / `height` 仅对图片 / 视频有意义，其它媒体类型可省略。

## FieldValue

查询 / 获取记录接口返回的字段值——**与 PropertyValue 不同**：

| 字段类型 | 返回值形态 | 示例 |
| --- | --- | --- |
| text / email / phone_number | string | `"张三"` |
| select | string（仅选项文本） | `"进行中"` |
| number / currency | number | `25` / `1234.56` |
| date | string（ISO 8601） | `"2026-06-24T10:00:00Z"` |
| checkbox | boolean | `true` |
| multi_select | string[] | `["篮球", "钢琴"]` |
| url | `{ text, link }` | `{ "text": "官网", "link": "https://..." }` |
| image | 数组 `[{ imageUrl, title, width, height }]` | 见 API 文档 |
| attachment | 数组 `[AttachmentItem]` | `[{ "name": "报告.pdf", "attachmentId": "att_1", "fileType": "application/pdf", "fileSize": 10240, "mediaType": "file" }]`；返回时含服务端补齐的 `attachmentId` / `url` 等 |
| person | 数组 `[{ id, name }]` | `[{ "id": "uid123", "name": "张三" }]`；返回时 `name` 已由服务端填充 |
| 空值 | null | `null` |

## Filter 传参规则

Filter 是一个递归的树形结构，每个节点**三选一**（互斥，不可同时存在多种）：

| 类型 | 含义 | JSON 结构 |
|------|------|----------|
| `property` | 叶子节点：单字段条件 | `{"property": {<PropertyFilter>}}` |
| `and` | 所有子条件都满足 | `{"and": [<Filter>, <Filter>, ...]}` |
| `or` | 任一子条件满足 | `{"or": [<Filter>, <Filter>, ...]}` |

### PropertyFilter（叶子节点）

`property` 字段指定列名，然后根据列类型选择**对应的条件对象**（也是互斥，只选一个）：

| 列类型 | 条件字段 | 可用操作符 |
|--------|---------|-----------|
| text / url / email / phone | `"text"` | `equals`, `contains` |
| number / currency | `"number"` | `equals`, `greater_than`, `less_than`, `greater_than_or_equal`, `less_than_or_equal`, `is_empty` |
| select / multi_select | `"select"` | `equals`, `does_not_equal` |
| date | `"date"` | `equals`、`before`、`after`（值为 ISO 8601 格式，如 `"2025-06-01"` 或 `"2025-06-01T00:00:00Z"`） |
| checkbox | `"checkbox"` | `equals`, `does_not_equal` |
| person | `"person"` | `equals`（用户 ID 数组，顺序无关）、`does_not_equal`（用户 ID 数组）、`contains`（单个用户 ID）、`does_not_contain`（单个用户 ID）、`is_empty`（bool：true=为空，false=不为空） |

### 示例

**简单条件** — 名字包含 "张"：

```json
{
  "filter": {
    "property": {
      "property": "名字",
      "text": { "contains": "张" }
    }
  }
}
```

**AND 组合** — 状态="完成" 且 分数>80：
```json
{
  "filter": {
    "and": [
      { "property": { "property": "状态", "select": { "equals": "完成" } } },
      { "property": { "property": "分数", "number": { "greater_than": 80 } } }
    ]
  }
}
```

***嵌套 AND + OR** — 已完成 且（标签="A" 或 标签="B"）：
```json
{
  "filter": {
    "and": [
      { "property": { "property": "已完成", "checkbox": { "equals": true } } },
      {
        "or": [
          { "property": { "property": "标签", "select": { "equals": "A" } } },
          { "property": { "property": "标签", "select": { "equals": "B" } } }
        ]
      }
    ]
  }
}
```

**person 条件** — 负责人包含用户 uid123：
```json
{
  "filter": {
    "property": {
      "property": "负责人",
      "person": { "contains": "uid123" }
    }
  }
}
```

**不传 filter** — 返回全部记录
```json
{}
```

## Sort

`[{ property: "字段名", direction: "ascending" | "descending" }]`
