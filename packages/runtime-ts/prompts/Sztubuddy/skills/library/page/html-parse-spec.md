# HTML 解析策略与字段类型推断规则

`parse_html.py` 脚本从 HTML 文件中提取数据表结构（schema）。本文档描述解析策略和推断规则。

---

## 预处理

### Body 提取

脚本在执行任何策略前，先提取 `<body>` 内容，**忽略 `<head>`** 中的 `<meta>`、`<link>`、`<style>`、外部 `<script src>` 引用。

- `<body>` 存在 → 只分析 body 内的 HTML 和 inline `<script>`
- `<body>` 不存在（HTML 片段）→ 原样分析全文
- `<title>` 会被单独提取，作为表名参考（附加在输出的 `title` 字段中）

**收益**：避免 head 中 CSS/meta 干扰策略匹配；Agent 读取时可节省 30-40% token。

### 多策略合并

脚本不再"第一个成功即返回"，而是**收集所有命中策略的结果并合并**：

- 每个表附带 `confidence` 字段（`high` / `medium` / `low`）
- 同名表合并字段（去重），取更高置信度
- `source` 字段显示所有命中的策略来源（如 `"table_structure+form_structure"`）
- **唯一例外**：策略 1（已有 `__SMART_PAGE__.database` 调用）命中时直接返回，不合并

---

## 解析策略

### 策略 1：已有 `__SMART_PAGE__.database` 调用（置信度：high）

扫描 HTML 中的 `<script>` 标签内容，正则匹配：

```
__SMART_PAGE__\.database\.(addRecord|getRecord|query)\s*\(\s*\{[^}]*databaseId\s*:\s*['"](\w+)['"]
```

- 提取 databaseId（第 2 捕获组）
- SDK 方法集合与 `database-sdk-contract.md` §6 保持一致
- 此策略只能提取 databaseId，字段需后续从实际调用参数推断
- **命中此策略时直接返回，不合并其他策略**

### 策略 2：HTML `<table>` 结构解析（置信度：high）

匹配条件：HTML 中存在 `<table>` 标签且包含 `<thead>` / `<th>`。

解析步骤：

1. 提取所有 `<table>` 标签（支持多表）
2. 对每个 `<table>`：
   - 从 `<th>` 标签提取字段名
   - 收集**最多 20 行** `<td>` 数据，用于多值类型推断
   - table 名：取 `<table>` 的 `id` / `data-table` 属性，无则用 `table_N`
3. **增强**：支持 select 枚举推断——如果某列值为有限枚举（≤10 种且重复出现），自动推断为 `select` 并附带 `options`

示例输入：
```html
<table id="orders">
  <thead>
    <tr>
      <th>订单号</th>
      <th>产品</th>
      <th>价格</th>
      <th>日期</th>
      <th>状态</th>
    </tr>
  </thead>
  <tbody>
    <tr><td>ORD-001</td><td>iPhone 15</td><td>¥7999</td><td>2026-01-15</td><td>已发货</td></tr>
    <tr><td>ORD-002</td><td>MacBook</td><td>¥14999</td><td>2026-01-16</td><td>待处理</td></tr>
    <tr><td>ORD-003</td><td>AirPods</td><td>¥1299</td><td>2026-01-17</td><td>已发货</td></tr>
  </tbody>
</table>
```

推断结果：
```json
{
  "name": "orders",
  "fields": [
    { "name": "order_id", "type": "text", "description": "订单号" },
    { "name": "product", "type": "text", "description": "产品" },
    { "name": "price", "type": "number", "description": "价格" },
    { "name": "date", "type": "date", "description": "日期" },
    { "name": "status", "type": "select", "description": "状态", "options": ["已发货", "待处理"] }
  ],
  "confidence": "high"
}
```

### 策略 3：`<form>` 表单结构解析（置信度：high）

匹配条件：HTML 中存在 `<form>` 标签且内含 `<input>` / `<select>` / `<textarea>`。

适用场景：报名表、注册表、反馈表、问卷、签到等**写入型**页面。

解析步骤：

1. 提取所有 `<form>` 标签
2. 对每个 `<form>`：
   - 从 `<input name="xxx" type="yyy">` 提取字段名和类型
   - 从 `<select name="xxx">` 提取选择字段，`<option>` 值作为 `options`
   - 从 `<select multiple>` 识别为 `multi_select`
   - 从 `<textarea name="xxx">` 提取文本字段
   - 从 `<label for="id">` 关联字段描述
   - table 名：取 `<form>` 的 `id` / `data-table` 属性，无则用 `form_N`
3. 忽略 `type="submit"` / `type="button"` / `type="reset"` / `type="image"`

input type → Database 字段类型映射：

| `<input type>` | 推断类型 |
| --- | --- |
| `text` / `hidden` / `password` | `text` |
| `email` | `email` |
| `tel` | `phone_number` |
| `url` | `url` |
| `number` / `range` | `number` |
| `date` / `datetime-local` / `month` / `week` | `date` |
| `checkbox` | `checkbox` |
| `color` | `text` |
| `file` | `file` |
| `time` | `text` |

示例输入：

```html
<form id="registration">
  <label for="name">姓名</label>
  <input id="name" name="name" type="text" required>

  <label for="email">邮箱</label>
  <input id="email" name="email" type="email">

  <label for="phone">电话</label>
  <input id="phone" name="phone" type="tel">

  <label for="dept">部门</label>
  <select id="dept" name="department">
    <option>技术部</option>
    <option>产品部</option>
    <option>设计部</option>
  </select>

  <label for="skills">技能（多选）</label>
  <select id="skills" name="skills" multiple>
    <option>前端</option>
    <option>后端</option>
    <option>设计</option>
  </select>

  <button type="submit">报名</button>
</form>
```

推断结果：

```json
{
  "name": "registration",
  "fields": [
    { "name": "name", "type": "text", "description": "姓名" },
    { "name": "email", "type": "email", "description": "邮箱" },
    { "name": "phone", "type": "phone_number", "description": "电话" },
    { "name": "department", "type": "select", "description": "部门", "options": ["技术部", "产品部", "设计部"] },
    { "name": "skills", "type": "multi_select", "description": "技能（多选）", "options": ["前端", "后端", "设计"] }
  ],
  "confidence": "high"
}
```

### 策略 4：`data-*` 属性解析（置信度：high）

匹配条件：HTML 中存在 `data-table` 或 `data-field` 属性。

```html
<div data-table="users">
  <span data-field="name">张三</span>
  <span data-field="email">zhangsan@example.com</span>
  <span data-field="age">28</span>
</div>
```

- `data-table` → table 名
- `data-field` → 字段名
- 从元素内容推断字段类型

### 策略 5：模板占位符解析（置信度：medium）

匹配条件：HTML 中存在 `{{xxx}}` 或 `${xxx}` 模板语法。

```html
<div class="card">
  <h2>{{product.name}}</h2>
  <p>价格：{{product.price}}</p>
  <p>日期：{{product.created_at}}</p>
</div>
```

- 带 `.` 的占位符：前半段为 table 名，后半段为字段名
- 无 `.` 的占位符：field 名，table 名需额外推断
- 标记 `html_has_template_syntax: true`

### 策略 6：fetch/XHR/axios 调用解析（置信度：medium）

扫描 `<script>` 中的网络请求调用：

```javascript
fetch('/api/orders?page=1&limit=10')
fetch('/api/products')
axios.get('/api/users')
```

支持的模式：
- `fetch('/api/xxx')` / `fetch("https://host/api/xxx")`
- `XMLHttpRequest.open('GET', '/api/xxx')`
- `axios.get('/api/xxx')` / `axios.post('/api/xxx')` / `axios.put` / `axios.delete` / `axios.patch`

从 URL 路径段提取 table 名（如 `/api/orders` → `orders`）。

### 策略 7：重复结构检测（置信度：medium）

**新增策略** — 解决卡片/列表布局无法识别的问题。

原理：检测 DOM 中**结构同构的重复兄弟元素组**，提取共同子元素作为字段。

适用场景：
- 产品卡片列表
- 人员信息卡片
- 新闻/文章列表
- 任何 `<div>` 重复结构

示例输入：
```html
<div class="product-card">
  <img src="phone.jpg">
  <h3>iPhone 15</h3>
  <span class="price">¥7999</span>
  <span class="category">手机</span>
</div>
<div class="product-card">
  <img src="laptop.jpg">
  <h3>MacBook Pro</h3>
  <span class="price">¥14999</span>
  <span class="category">电脑</span>
</div>
```

检测逻辑：
1. 遍历 DOM 树，按 tag 分组兄弟元素
2. 对每组相同 tag 的元素，比较子元素的 tag 序列（签名）
3. 签名相同且数量 ≥ 2 → 判定为重复结构
4. 从子元素的 CSS class / tag 推断字段名
5. 收集所有重复项对应位置的文本，做多值类型推断

#### 子策略 7.5：`<ul>/<ol>/<dl>` 列表解析（置信度：low）

当策略 7 主逻辑未命中时，回退检测语义化列表标签：

- `<ul>/<ol>` 中结构相同的 `<li>` → 提取子元素为字段
- `<dl>` 中的 `<dt>/<dd>` 对 → 每对映射为一个字段

示例：
```html
<ul class="todo-list">
  <li>
    <span class="title">完成报告</span>
    <span class="due">2026-05-20</span>
    <span class="status">进行中</span>
  </li>
  <li>
    <span class="title">代码评审</span>
    <span class="due">2026-05-21</span>
    <span class="status">待处理</span>
  </li>
</ul>
```

### 策略 8：div 伪表格检测（置信度：medium）

**新增策略** — 解决 CSS Grid/Flexbox 模拟表格无法识别的问题。

检测 `<div>` 布局中带有 header/cell 结构的网格：

```html
<div class="grid">
  <div class="header">姓名</div><div class="header">部门</div><div class="header">职级</div>
  <div class="cell">张三</div><div class="cell">技术</div><div class="cell">T9</div>
  <div class="cell">李四</div><div class="cell">产品</div><div class="cell">P7</div>
</div>
```

检测逻辑：
1. DOM 解析器检测带有 `header`/`head`/`th`/`title` class 的子元素 → 作为表头
2. 检测带有 `cell`/`td`/`col`/`data`/`value` class 的子元素 → 作为数据
3. 验证 cells 数量是 headers 数量的整数倍
4. 按列分组做多值类型推断

回退：如果 DOM 解析器未命中，用正则检测 `class` 含 `header`/`cell` 的 div。

### 策略 9：JavaScript 内联数据对象提取（置信度：medium）

**新增策略** — 解决 JS 动态渲染页面无法识别的问题。

从 `<script>` 中提取 JS 数组/对象字面量：

```html
<script>
  const data = [
    { name: "张三", age: 28, dept: "技术部" },
    { name: "李四", age: 32, dept: "产品部" },
  ];
</script>
```

检测模式：
- `const/let/var xxx = [{ ... }]` — 变量赋值的数组
- `xxx: [{ ... }]` — 对象属性中的数组

排除的变量名（非数据）：`options`, `config`, `settings`, `plugins`, `routes`, `headers`, `columns`, `rules`, `validators`, `styles`

提取逻辑：
1. 正则匹配数组变量/属性
2. 提取第一个对象的 key 作为字段名
3. 提取对应 value 做类型推断
4. 变量名 camelCase → snake_case 转换为表名，去掉 `_data`/`_list`/`_items` 后缀

---

## 类型推断表

### 单值推断

当从 HTML 内容推断字段类型时，按以下规则：

| 值特征 | 推断类型 | 示例值 |
| --- | --- | --- |
| 纯数字（含小数） | `number` | `42`, `3.14`, `1,000` |
| 含货币符号 | `number` | `¥7999`, `$29.99`, `€100` |
| 含百分号 | `number` | `85%`, `3.14％` |
| 日期格式 | `date` | `2026-01-15`, `01/15/2026`, `2026年1月` |
| 邮箱格式 | `email` | `user@example.com` |
| URL 格式 | `url` | `https://example.com`, `http://...` |
| 电话格式 | `phone_number` | `13800138000`, `+86-138-0013-8000` |
| 布尔值 | `checkbox` | `true/false`, `是/否`, `✓/✗`, `yes/no` |
| 其他 / 默认 | `text` | 普通文本 |

### 多值推断（增强）

当收集到 ≥2 个样本值时，进行多值联合推断：

| 条件 | 推断类型 | 说明 |
| --- | --- | --- |
| 基础类型为 text，唯一值 ≤10 种，且出现重复 | `select` | 有限枚举（附带 `options`） |
| 基础类型为 text，>50% 的值含逗号/顿号分隔 | `multi_select` | 多值选择 |
| 其他 | 取最常见类型 | 多数投票 |

---

## 字段名规范化

### 中文表头映射（增强版）

覆盖约 80+ 个常见中文词汇，分类如下：

| 分类 | 词汇示例 | 映射结果 |
| --- | --- | --- |
| 基础标识 | 编号、工号、学号、会员号、流水号 | `id`, `employee_id`, `student_id` 等 |
| 姓名/名称 | 名称、产品名、项目名、课程、活动 | `name`, `product_name`, `project` 等 |
| 金额/数量 | 价格、营收、利润、客单价、成交额 | `price`, `revenue`, `profit` 等 |
| 时间 | 日期、开始时间、截止日期、签到时间 | `date`, `start_time`, `deadline` 等 |
| 联系方式 | 邮箱、手机、微信、QQ | `email`, `phone`, `wechat` 等 |
| 人员 | 负责人、作者、审核人、参与者 | `owner`, `author`, `reviewer` 等 |
| 业务指标 | KPI、转化率、完成率、评分、排名 | `kpi`, `conversion_rate`, `rating` 等 |
| 分类 | 类型、部门、标签、班级 | `type`, `department`, `tags` 等 |
| 链接/图片 | 图片、头像、封面、附件 | `image`, `avatar`, `cover` 等 |

### CSS class → 字段名推断

策略 7/8 从 CSS class 名推断字段名：

1. 去掉常见前缀（`item-`、`card-`、`cell-`、`col-`、`field-`）
2. 过滤通用容器名（`container`、`wrapper`、`item`、`card` 等）
3. 保留有语义的 class 名作为字段名
4. 无法推断时按 tag 猜测（`<h3>` → `title`、`<img>` → `image`、`<p>` → `description`）

### JS 变量名 → 表名规范化

策略 9 从 JS 变量名推断表名：

1. camelCase → snake_case（如 `productList` → `product_list`）
2. 去掉常见后缀（`_data`、`_list`、`_items`、`_array`、`_records`）
3. 结果如 `product`

---

## 置信度说明

每个表和整体结果附带 `confidence` 字段：

| 级别 | 含义 | 适用策略 |
| --- | --- | --- |
| `high` | 结构明确，字段信息完整 | 策略 1（SDK 调用）、2（table）、3（form）、4（data-*） |
| `medium` | 能推断结构，但字段可能不完整 | 策略 5（模板）、6（fetch）、7（重复结构）、8（div 伪表格）、9（JS 数据） |
| `low` | 推断信心较低，建议 Agent 补充确认 | 策略 7.5（ul/ol/dl 列表） |

**Agent 决策建议**：
- `high` → 可直接使用
- `medium` → 展示给用户确认
- `low` → 仅作为参考，建议 Agent 做语义补充或让用户描述

---

## 输出格式

脚本最终输出 **canonical schema**（stdout JSON），可直接喂给 `create_database.py`：

```json
{
  "title": "<中文展示名>",
  "page_type": "form | display | mixed",
  "properties": [
    {
      "name": "<中文字段名>",
      "config": { "<oneof type>": "<占位值>" }
    }
  ],
  "field_mapping": {
    "<中文字段名>": {
      "value_type": "text | number | select | multi_select | date | checkbox | url | email | phone_number | image",
      "form_input": "string | null",
      "display_selector": "string | null",
      "render_signal": "string",
      "options_value_key": "value | text"
    }
  },
  "options_map": {
    "<中文字段名>": {
      "<value 或 text>": { "text": "<选项中文>", "id": "<16 位字母数字 id>" }
    }
  },
  "needs_database": { "level": "strong | medium | weak | none", "reason": "..." },
  "source": "<+连接的命中策略>",
  "sdk_calls_found": false,
  "html_has_template_syntax": false,
  "confidence": "high | medium | low"
}
```

### 字段说明

- **title**：从 HTML `<title>` 提取（已中文化）；缺失时取主表名翻译
- **page_type**：根据命中 source 推断
  - 命中 `form_structure` 且无展示型 source → `form`
  - 命中 `table_structure` / `repeating_structure` / `div_table` / `data_attributes` / `list_structure` / `template_syntax` 且无 form → `display`
  - 同时命中 form 与展示型 → `mixed`
- **properties**：`[{ "name": string, "config": PropertyConfig }]`（array 格式），PropertyConfig 是 oneof，详见 `../database/entry.md`
  - select / multi_select 的每个 SelectOption 自带 `id`（脚本用 `secrets.token_urlsafe(12)[:16]` 生成）
- **field_mapping**：每个 schema 字段在 HTML 中的物理位置 selector
  - selector 优先级：`[name="..."]` > `[data-field="..."]` > `#id` > `.first-class` > `td:nth-child(N)` / `:nth-child(N)`
  - `options_value_key` 仅 select / multi_select 有：所有 `<option>` 都带显式 `value` 属性 → `"value"`；否则 → `"text"`
- **options_map**：`map<字段名, map<二层 key, {text, id}>>`，供阶段 4 改造 HTML 时**整段拷贝**到 OPTIONS_MAP

> **多表场景**：HTML 中存在多张表时，脚本只输出**最高置信 + 最多字段**的那张作为主表，其余表丢弃。如需建多张表，分多次调用脚本（每次给只含一张表的 HTML 片段）。

### 特殊路径：HTML 已接入 SDK

当策略 1（`__SMART_PAGE__.database.*` 调用）命中时，**输出格式与 canonical schema 不同**——HTML 已经接入了一个或多个 database，不需要建表也不需要改造：

```json
{
  "existing_databases": [
    { "id": "<database_id_1>" },
    { "id": "<database_id_2>" }
  ],
  "source": "sdk_calls",
  "sdk_calls_found": true,
  "confidence": "high",
  "needs_database": { "level": "strong", "reason": "HTML 已包含 __SMART_PAGE__.database SDK 调用" }
}
```

字段说明：
- **existing_databases**：HTML 中所有引用过的 database 绑定列表（去重排序）。每项包含 `id`（database 唯一标识，后端已统一用 `id` 关联）
- **sdk_calls_found**：固定为 `true`，Agent 据此识别本路径

此时 Agent 应：① 识别 `sdk_calls_found=true`；② 跳过阶段 2-4（建表 / 用户 check / 改造 HTML）；③ 直接走阶段 5 上传 HTML，并把 `existing_databases` 的 `id` 作为 `import_html.py --databases` 参数。

### 解析失败

解析失败时输出空 JSON `{}`，由 Agent 提示用户描述表结构。

---

## 配套：lint_schema.py（硬校验）

`parse_html.py` 输出的 canonical schema 经过用户阶段 2 编辑后，可能出现字段不一致、selector 误改等问题。`scripts/lint_schema.py` 是配套的硬校验脚本，**必须**在阶段 4 输出最终 HTML 之前调用一次。

### 调用方式

```bash
# 仅校验 schema 自洽
echo '<canonical_schema_JSON>' | python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/lint_schema.py" --stdin

# 同时校验 selector 在 HTML 中真实存在（强烈建议）
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/lint_schema.py" --schema '<JSON>' --html page.html
```

### 输出协议

| stdout | exit | 含义 |
| --- | --- | --- |
| `MINDX_LINT_OK` | 0 | 通过 |
| `MINDX_LINT_FAIL <规则号> <字段名>: <原因>`（多行，每个违规一行）| 2 | 校验失败，按规则号修正 |
| stderr 简短提示 | 1 | 输入格式错误（不是 lint 失败） |

> 与其他 mindx 脚本"任何错误都静默 exit 0"的约定不同，lint 脚本**必须显式暴露问题**——这是它作为"硬校验"存在的意义。

### 校验规则

| 规则 | 含义 |
| --- | --- |
| R1 | 顶层契约字段齐全（title / page_type / properties / field_mapping / options_map）+ SDK 路径必有 existing_databases |
| R2 | properties / field_mapping key 字符级一致 |
| R3 | selector 形态合法（简单 CSS selector，如 `[name="x"]` / `.cell` / `#id` / `td:nth-child(1)` / `:nth-child(1)`，或为 `null`）|
| R4 | select / multi_select 必须有合法的 `options_value_key`（"value" 或 "text"）|
| R5 | PropertyConfig oneof 互斥：同一字段配置只能有一个类型 key |
| R6 | select / multi_select 选项必含 text + id；id 在所有字段间全局唯一 |
| R7 | select / multi_select 字段必须有 options_map，且每个 entry 的 id 与 properties 内同名 option 的 id 一致（防止用户改了选项后丢同步）|
| R8 | page_type=display/mixed → 至少一个字段有非空 display_selector |
| R9 | page_type=form/mixed → 至少一个字段有非空 form_input |
| R10 | （传 --html 时）每个非空 selector 在 HTML 中能找到匹配元素（class/id/attr 三种维度的存在性检查）|

## 配套：lint_database_sdk_usage.py（硬校验）

`lint_database_sdk_usage.py` 校验最终 HTML 中的 database SDK 调用是否符合 `database-sdk-contract.md`。

### 调用方式

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/database/get_database_schema.py" --token-stdin --database-id "<database_id>"

python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/lint_database_sdk_usage.py" --schema '<get_database_schema_stdout_JSON>' --html page.html
```

`--schema` 推荐传入 `get_database_schema.py` 的 stdout JSON，确保字段名来自服务端真实 database schema。
已关联 database 的页面流程执行本 lint；无 database 绑定的静态上传流程跳过本 lint。

### 输出协议

| stdout | exit | 含义 |
| --- | --- | --- |
| `MINDX_DBSDK_LINT_OK` | 0 | 通过 |
| `MINDX_DBSDK_LINT_FAIL <规则号> <target>: <原因>` | 2 | 校验失败 |
| stderr 简短提示 | 1 | 输入格式错误 |

### 首版规则

| 规则 | 含义 |
| --- | --- |
| DSDK001 | SDK 方法白名单：`query` / `addRecord` / `getRecord` |
| DSDK002 | SDK 调用包含 `databaseId`，或使用硬编码 `DATABASE_ID` 常量 |
| DSDK003 | `properties["字段名"]` 属于 `schema.properties` |
| DSDK006 | `row["字段名"]` 属于 `schema.properties` |
| DSDK007 | HTML 包含 database SDK 调用 |
| DSDK011 | `data-sp-bindable` / `data-sp-database-id` 成对出现且取值合法 |
| DSDK012 | 读取并渲染 database 数据（`query`/`getRecord` + DOM 写入）的页面须有绑定标注 |



## 附录：HTML 数据源识别优先级（兜底场景速查）

> 仅用于改造分支阶段 1 **Step 2 兜底场景**：`parse_html.py` 返回 `{}` 时，Agent 自行从 HTML 推断数据结构。
>
> 正常情况下 `parse_html.py` 已覆盖策略 1-9 并直接产出 canonical schema，Agent **不需要**从头分析。

| 优先级 | 信号 | 脚本覆盖 | 处理 |
| --- | --- | --- | --- |
| 1（最高） | HTML 中已有 `__SMART_PAGE__.database.*` 调用 | 是（策略 1） | 无需建表/改造，直接提取 databaseId 并上传 |
| 2 | HTML 中 `<table>` 有明确表头 | 是（策略 2） | 从 `<th>` 推断字段名，从多行 `<td>` 推断类型（含 select 枚举） |
| 3 | HTML 中 `<form>` 含 `<input>` / `<select>` | 是（策略 3） | 从 input name/type 和 select options 提取字段 |
| 4 | HTML 中有 `data-table` / `data-field` 属性 | 是（策略 4） | 从属性提取表名和字段名 |
| 5 | HTML 中有 `{{xxx}}` / `${xxx}` 模板占位符 | 是（策略 5） | 从占位符推断字段名 |
| 6 | HTML 中 fetch/XHR/axios 调用 | 是（策略 6） | 从 URL 路径和参数名推断 |
| 7 | 重复 DOM 结构（卡片/列表布局） | 是（策略 7） | 同构兄弟元素检测 + 子元素提取字段 |
| 8 | `<ul>/<ol>/<dl>` 语义列表 | 是（策略 7.5） | `<li>` 子元素 / `<dt><dd>` 对提取字段 |
| 9 | div 伪表格（Grid/Flexbox 模拟） | 是（策略 8） | header/cell class 检测 + 按列分组推断 |
| 10 | JavaScript 内联数据对象 | 是（策略 9） | `const xxx = [{...}]` 提取 key 为字段 |
| 11（最低） | 纯静态内容，无任何信号 | 否 | 提示用户描述表结构 |
