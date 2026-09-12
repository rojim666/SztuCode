# data-page-flow —— 数据页（带 database）分支执行手册

覆盖 §0 询问文案、§1 canonical schema 规则、§3 改造分支（已有 HTML）、§5 创建分支（无 HTML）两条建库分支。上传统一走 `import-flow.md`。命令块默认客户端模式；沙箱模式删掉 token 管道与 `--token-stdin`。

---

## 0. 数据库需求预判询问文案

原则：不问技术路径（"接在线表格还是传静态页""要建表吗"）；数据管理意图明确（strong / 已描述字段）直接走改造分支；只有真分不清才问业务意图（数据要不要随时改、多人维护）。

### 0.1 strong：直接接数据，不询问

HTML 已有表格 / 表单 / 预留接口。直接走改造分支，动手时一句话告知（无需等回复）：

```
这个页面里有表格 / 表单（<reason>），我直接帮你接上在线数据表，
这样填了能存、列表能从数据库拉、后面也能随时改数据。
```

### 0.2 medium：只问业务意图

HTML 有重复卡片 / 列表，看不出是"要管理的数据"还是"一次性展示"：

```
这个页面里有一批重复的卡片 / 列表（<reason>），看起来是在展示一组数据（比如商品、报名记录）。
想确认下：这些数据以后还要随时增删改、或者要和别人一起维护吗？

· 要 → 我直接帮你做成在线版本，数据存到表里，随时能改、能多人维护
· 不用，就是这一版展示一下 → 我就把这一页原样保存成可分享的网页
```

### 0.3 占位符替换

| 占位符 | 替换来源 | 缺失时处理 |
| --- | --- | --- |
| `<reason>` | `parse_html.py` 输出的 `needs_database.reason` | 缺失时连同括号一并删除 |
| `N` | medium 场景下最大 `item_count` | 无值则删除"N 次"三字（保留"重复出现的结构"）|

### 0.4 用户回复识别

| 用户意图 | 触发关键词（任一命中） | 落地分支 |
| --- | --- | --- |
| 要管理数据（随时改 / 多人维护） | "要" / "随时改" / "要改" / "多人" / "一起维护" / "存数据" / "联数据" / "接数据" / "活的" / "能查" / "能填" / "数据库" | **改造分支**，复用已有 parse_html.py 结果，从 §3 阶段 1 开始 |
| 描述了具体要存什么 | 含"字段"或列举 ≥2 个名词（如"姓名、电话、部门"）| **改造分支**，跳过脚本结果，按描述构造 schema，进入 §3 阶段 2 |
| 描述了页面需求 | "做一个 / 我想 / 帮我" + 页面类型词（"报名 / 签到 / 留言 / 订单"等） | **创建分支**（§5） |

---

## 1. canonical schema 规则

两分支共用；改造分支由 `parse_html.py` 产出，创建分支由 Agent 产出。

### 1.1 格式

```json
{
  "title": "订单管理",
  "page_type": "display | form | mixed",
  "properties": {
    "产品名称": { "text": "" },
    "状态": { "select": { "options": [{ "text": "待发货", "id": "k3x8f2m91jqvbz4a" }, { "text": "已发货", "id": "a7b2c9d41npwke5t" }, { "text": "已送达", "id": "p9m3n7x52rqfhs6y" }] } },
    "价格": { "number": 0 },
    "下单日期": { "date": "1970-01-01T00:00:00Z" },
    "订单编号": { "text": "" }
  },
  "field_mapping": {
    "产品名称": { "value_type": "text", "form_input": "[name=\"product\"]", "display_selector": "td:nth-child(2)", "render_signal": "th:contains('产品')" },
    "状态":     { "value_type": "select", "form_input": "[name=\"status\"]", "display_selector": ".status-cell", "render_signal": "th:contains('状态')", "options_value_key": "value" },
    "价格":     { "value_type": "number", "form_input": "[name=\"price\"]", "display_selector": ".price-cell", "render_signal": "th:contains('价格')" },
    "下单日期": { "value_type": "date",   "form_input": "[name=\"order_date\"]", "display_selector": "td.date", "render_signal": "th:contains('日期')" },
    "订单编号": { "value_type": "text",   "form_input": null, "display_selector": "td:nth-child(1)", "render_signal": "th:contains('编号')" }
  },
  "options_map": {
    "状态": {
      "pending": { "text": "待发货", "id": "k3x8f2m91jqvbz4a" },
      "shipped": { "text": "已发货", "id": "a7b2c9d41npwke5t" },
      "delivered": { "text": "已送达", "id": "p9m3n7x52rqfhs6y" }
    }
  },
  "source": "...",
  "sdk_calls_found": false,
  "confidence": "high",
  "needs_database": { "level": "strong | medium | weak | none", "reason": "..." }
}
```

- `properties` / `field_mapping` / `options_map` 三者顶层 key 必须**完全一致**（同语言、同字符），一一对应。
- PropertyConfig 类型 oneof：`text`/`number`/`select`/`multi_select`/`date`/`checkbox`/`url`/`email`/`phone_number`/`image`（协议字段，永不翻译）。建表用 `PropertyConfig`，写记录用 `PropertyValue`，详见 `../database/entry.md`。

### 1.2 字段名

默认中文：HTML 中文保留原文；HTML 英文（`name=email`）查词表翻中文（`邮箱`），未命中退回原英文（阶段 2 可建议改中文）；用户要求「用英文字段名」则 properties / field_mapping 的 key 同步切英文。

### 1.3 字段排序

按 **主标识 → 业务核心 → 时间 → ID** 排序：

1. **主标识**（仅文本）：`名称`/`标题`/`产品名称`/`姓名`/`name`/`title` 等
2. **业务核心**：金额、状态、电话、库存等
3. **时间类**：`日期`/`时间`/`created_at` 靠后（除非表核心即时间，如「日程」「打卡」）
4. **ID/序号/编号**：`id`/`订单编号`/`单号`/`序号` 放最后

- `form`：properties 按上述排，但**展示给用户时**按表单原始填写顺序
- `display`：properties 顺序即最终顺序；`mixed`：以展示视图字段顺序为主
- 改造分支：脚本已排好，不重排（除非阶段 2 用户显式要求）；创建分支：Agent 输出时直接排好

### 1.4 field_mapping

`map<字段名, MappingEntry>`，key 与 `properties` 一一对应。

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `value_type` | string | 同 PropertyConfig，必填 |
| `form_input` | string \| null | 表单输入 selector（addRecord 取值）；不在表单则 `null`。必填 |
| `display_selector` | string \| null | 展示渲染 selector（renderData 写值）；纯表单页则 `null`。必填 |
| `render_signal` | string | 识别字段的 HTML 信号（如 `th:contains('产品')`），必填 |
| `options_value_key` | `"value"` \| `"text"` | 仅 `select`/`multi_select` 必填 |

**selector 优先级**（高→低）：`[name="..."]` > `[data-field="..."]` > `#id` > `.first-class` > `td:nth-child(N)` / `:nth-child(N)`。位置选择器兜底。

- 改造分支：selector 由 `parse_html.py` 收集，**禁止现猜**；创建分支：selector 是阶段 4 写 HTML 的承诺。
- `options_value_key`：所有 `<option>` 带 `value` → `"value"`；否则 → `"text"`。
- 改字段名/顺序后 `field_mapping` key 同步 rename；selector 内容不变。

### 1.5 选项 ID 与 OPTIONS_MAP

`select`/`multi_select` 每个 `SelectOption` 必带 `id`（16 位字母数字）：

- 改造分支：`parse_html.py` 用 `secrets.token_urlsafe(12)[:16]` 生成
- 创建分支：Agent 用 `Math.random().toString(36).slice(2, 10) + Date.now().toString(36)` 生成
- **禁止替换**已生成的 ID；`options_map[字段名][...].id` 必须与 `properties[字段名].select.options[].id` 一致。

`options_map` 结构 `map<字段名, map<二层 key, {text, id}>>`，二层 key 由 `field_mapping[字段名].options_value_key` 决定。阶段 4 **直接整段拷贝**，禁止重构。

**运行时选项必须动态获取，禁止硬编码**：`<option>` 由 `db.getSchema` 获取后动态渲染；提交的 `{text,id}` 映射从 `db.getSchema` 的 `config.options` 构建；筛选选项 / 字段元数据同样优先 `db.getSchema`。静态 `options_map` 仅用于建表初始选项 + lint 校验，不影响运行时。

### 1.5.5 database 绑定标注（`data-sp-bindable` / `data-sp-database-id`）· 唯一权威

两条分支、演示档（`wbp-presentation-contract.md`）、Page 编辑（`edit-flow.md`）一律引用本节。

**何时标注**：元素文本**直接来自** database（`renderData()` 写入）或**间接派生自** database（统计/聚合/计数，如「共 128 单」「KPI 数字」）时，**同时**加：

| 属性 | 值 |
| --- | --- |
| `data-sp-bindable` | `"database"` |
| `data-sp-database-id` | `"<databaseId>"`（多表派生取主要来源，硬编码字面量） |

**不标注**：硬编码文本、表单输入控件、纯容器。**粒度**：就近标在承载文本的最内层元素，不标外层容器。

```html
<div><p data-sp-bindable="database" data-sp-database-id="db_xxx">共 128 单</p></div>  <!-- 标内层 p -->
```

**运行时同步**：写 DOM 时同步 `setAttribute('data-sp-bindable','database')` 与 `setAttribute('data-sp-database-id', DATABASE_ID)`。由 DSDK011 / DSDK012 硬校验。

### 1.6 字段映射与 SDK 调用自检

任一项不通过 → **不**输出最终 HTML，回 field_mapping 重对。lint 失败禁止绕过。

#### 第一道：lint_schema.py（输出最终 HTML 前必跑）

```bash
echo '<canonical_schema_JSON>' | python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/lint_schema.py" --stdin
# HTML 在本地时同时校验 selector
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/lint_schema.py" --schema '<JSON>' --html "<path/to/page.html>"
```

| 输出 | exit | 处理 |
| --- | --- | --- |
| `MINDX_LINT_OK` | 0 | 通过，继续阶段 4 |
| `MINDX_LINT_FAIL <规则号> <字段名>: <原因>` | 2 | 禁止输出 HTML；按规则号修正后重跑 |
| stderr + exit 1 | 1 | 输入 schema JSON 格式错误 |

| 规则 | 含义 | 修复 |
| --- | --- | --- |
| R1 | 顶层契约字段缺失（title/page_type/properties/field_mapping/options_map） | 重跑 `parse_html.py` 或查阶段 2 编辑 |
| R2 | properties / field_mapping key 不一致 | 改字段名时同步 rename `field_mapping` key |
| R3 | selector 形态非法 | 从脚本输出直接拷贝，勿塞自然语言 |
| R4 | select/multi_select 缺 `options_value_key` | 补齐（"value"/"text"） |
| R5 | PropertyConfig oneof 冲突 | 一个字段只能一个类型 key |
| R6 | 选项缺 text/id 或 id 重复 | 选项 id 从脚本输出直接拷贝 |
| R7 | 缺 options_map，或 id 与 properties 不一致 | 改选项后同步两处 id |
| R8 | display/mixed 但所有字段 display_selector 为 null | 至少一个展示字段要有 selector |
| R9 | form/mixed 但所有字段 form_input 为 null | 至少一个表单字段要有 selector |
| R10 | （--html）selector 在 HTML 中无匹配 | 回 `field_mapping` 取真实 selector |

#### 第二道：lint_database_sdk_usage.py（输出最终 HTML 后、上传前必跑）

先取服务端真实 schema，再校验最终 HTML。

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/database/get_database_schema.py" --token-stdin --database-id "<database_id>"
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/lint_database_sdk_usage.py" --schema '<get_database_schema_stdout_JSON>' --html "<path/to/final.html>"
```

| stdout | exit | 含义 |
| --- | --- | --- |
| `MINDX_DBSDK_LINT_OK` | 0 | 通过，可上传 |
| `MINDX_DBSDK_LINT_FAIL <规则号> <target>: <原因>` | 2 | 修正 HTML 后重跑 |
| stderr + exit 1 | 1 | 输入 schema / HTML 不可读或格式错误 |

| 规则 | 含义 | 修复 |
| --- | --- | --- |
| DSDK001 | SDK 方法不在 `query/addRecord/getRecord/updateRecord/deleteRecord/getSchema` 内 | 对照 `database-sdk-contract.md` §2/§6 改 |
| DSDK002 | SDK 调用缺 `databaseId` 且无 `DATABASE_ID` 常量 | 补 `databaseId` 或定义 `DATABASE_ID` |
| DSDK003 | `properties["字段名"]` 不属于 `schema.properties` | 用 schema 字段名替换 |
| DSDK006 | `row["字段名"]` 不属于 `schema.properties` | renderData 按 schema 字段名读取 |
| DSDK007 | HTML 无任何 database SDK 调用 | 补 `db.query`/`db.addRecord`/`db.getRecord` |
| DSDK009 | `sorts`/`filter`/`fields` 引用了 schema 不存在字段 | 字段名须来自 `db.getSchema()` |
| DSDK010 | 用 `.records`/`.success`/`.data` 取数 | 只从 `result.results` 取数组 |
| DSDK011 | 两属性未成对，或值不合法 | 成对补齐，按 §1.5.5 取值 |
| DSDK012 | 有 `query`/`getRecord` + DOM 写入却零 `data-sp-bindable` | 按 §1.5.5 补标 |

#### 第三道：人工 checklist

| 检查项 | 通过标准 |
| --- | --- |
| `properties` key | 与 `schema.properties` 字符级一致；中文 key 禁止写英文 |
| `addRecord` selector | 全部来自 `field_mapping[字段名].form_input` |
| OPTIONS_MAP | 无硬编码常量；选项经 `db.getSchema` 填充 `SCHEMA_OPTIONS`，`<option>` 由 `renderSelectOptions()` 动态渲染 |
| select/multi_select 提交取值 | `option.value` 已设为 `opt.id`，提交直接取 `selectEl.value` |
| `renderData` 里 `row[xxx]` key | schema 字段名，不用 HTML class/id/英文 alias |
| 渲染元素 selector | 全部来自 `field_mapping[字段名].display_selector`；展示字段须非 null |
| `field_mapping`/`options_map` 与 `properties` | 改字段名/顺序后 key 已同步 rename |

---

## 3. 改造分支 · 已有 HTML（解析 → 建表 → 改造 → 上传）

### 阶段 1：解析 HTML → canonical schema

脚本是**唯一**生成 schema 的地方；仅脚本失败或字段缺失时 Agent 才补缺，禁止从零生成。

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/parse_html.py" --html "<path/to/page.html>"
```

脚本一次性完成解析（详见 `html-parse-spec.md`）+ 字段翻译 / 排序 / selector 收集 / `options_value_key` 推断 / 选项 ID 生成 / `page_type` / `needs_database` 判定。

- `properties` 非空 → 进阶段 2（confidence 低也以脚本输出为准，不重写）
- `properties` 为空或返回 `{}` → 兜底

**兜底**（仅当脚本字段为空且用户已明确要接数据）：前置为①用户已表达"想接数据"②脚本结果为空，任一不满足则回 `entry.md` §9.2 重新分发。读 HTML 只看 `<body>` 及其 `<script>`，忽略 `<head>`：<200KB 全文读入；200–500KB 读前 500 行 + 搜关键结构；>500KB 提示用户描述结构。输出格式同 §1.1。

**特殊情况**：HTML 已有 `__SMART_PAGE__.database.*` → 脚本标 `sdk_calls_found:true`，跳过阶段 4。兜底仍无法识别 → 回复：`未能从 HTML 中识别出数据结构。你可以直接描述需要的表结构（如「订单表，含产品名、价格、日期」），我按你描述建表。`

### 阶段 2：确认 Schema（用户必须显式 check）

**必须等用户显式回复**才进阶段 3，沉默 ≠ 确认。展示（字段名/选项默认中文，按 §1.3 排序，首列主标识）：

```
请 check 以下 Database 字段（默认中文展示，已按重要性排序，首列为主标识字段）：

**订单管理**
| 字段名 | 类型 | 说明 |
|--------|------|------|
| 产品名称 | 文本 | 下单的产品名（首列） |
| 状态 | 单选 | 待发货 / 已发货 / 已送达 |
| 价格 | 数字 | 订单金额 |
| 下单日期 | 日期 | 下单时间 |
| 订单编号 | 文本 | 订单唯一标识 |

请回复：
- 「确认 / OK / 可以」→ 我开始建表
- 直接说明要改的地方（如「『订单编号』改成『单号』」「价格用文本类型」「用英文字段名」「加个『备注』字段」「把『下单日期』放第二列」）→ 我调整后重新展示
```

**类型中文映射**（仅展示，schema 里仍英文 oneof）：`text`=文本、`number`=数字、`select`=单选、`multi_select`=多选、`date`=日期、`checkbox`=是否、`url`=链接、`email`=邮箱、`phone_number`=电话。

| 回复 | 处理 |
| --- | --- |
| 确认 / OK / 可以 / 好的 / 没问题 | 进阶段 3 |
| 改字段 / 类型 / 选项 | 调整后重新展示，再等确认 |
| 调字段顺序 | 调 `properties` key 顺序后重新展示；不再触发 §1.3 重排，尊重用户顺序 |
| 用英文字段名 | properties key 与选项 text 切英文，重新展示 |
| 沉默 / 无关内容 | 不进阶段 3；可追问一次"是否确认创建？" |

### 阶段 3：创建 Database

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/database/create_database.py" --schema '<JSON>'
```

`<JSON>` 是阶段 1 输出的完整 schema（含 `title`、`properties`）。

- 成功 → stdout `{"database_id":"...","space_id":"...","property_count":N,"properties":[...]}`；`properties` 是建表后服务端真实 schema（含服务端生成的选项 id）。
- 失败 → 静默 exit 0。

**从本阶段起唯一可信字段清单是 create_database 返回的 `properties`**（非阶段 1 记忆）。阶段 4 所有字段名 / 字段 id / 选项 id 一律以此为准。

### 阶段 4：改造 HTML — 注入 `__SMART_PAGE__.database`

平台自动注入 SDK，`window.__SMART_PAGE__.database` 即刻可用。SDK 方法 / `PropertyValue` / `FieldValue` / filter / sorts 见 `database-sdk-contract.md`。

- `databaseId` 硬编码到 HTML（值来自阶段 3）。
- **写前字段白名单**：`sorts`/`filter`/`fields[]`/`row["字段名"]`/`properties["字段名"]` 只能引用阶段 3 返回 `properties` 内字段，禁止臆造；按时间排序前须确认清单有对应 date 字段。

| 场景 | 信号 | 改造 |
| --- | --- | --- |
| 读取展示 | `<table>`、列表、卡片、图表、`{{占位符}}` | `db.query` 查询渲染 |
| 表单提交 | `<form>`、`<input>`、提交按钮 | `db.addRecord` 写入 |
| 混合 | 同时有表单和展示区 | 两者都加 |

**情况 1 — 已有 SDK 调用**：不改动。

**情况 2 — 数据展示类**

query 返回 `{ results, nextCursor, hasMore }`；`result.results` 每条为扁平对象 `{ "字段名": 值 }`。值形态：text/select/email/phone→string；number→number；date→ISO string；checkbox→boolean；multi_select→string[]；url→`{text,link}`；image→数组 `[{imageUrl,...}]`（取单图 `row['字段名'][0].imageUrl`，先判空）。

```html
<script>
  (function() {
    var db = window.__SMART_PAGE__.database;
    var DATABASE_ID = 'DATABASE_ID';
    var SCHEMA_OPTIONS = {};   // { "字段名": [{ text, id }] }

    db.getSchema({ databaseId: DATABASE_ID }).then(function(schema) {
      (schema.properties || []).forEach(function(field) {
        if ((field.type === 'select' || field.type === 'multi_select') && field.config && field.config.options) {
          SCHEMA_OPTIONS[field.name] = field.config.options;
        }
      });
      loadData();
    }).catch(function(err) { console.error('[database] schema 加载失败:', err); loadData(); });

    function loadData() {
      db.query({
        databaseId: DATABASE_ID,
        sorts: [{ property: 'SORT_FIELD', direction: 'descending' }], // SORT_FIELD 须是真实字段（DSDK009）
        pageSize: 50
      }).then(function(result) {
        renderData(result.results); // 只从 result.results 取（DSDK010）
      }).catch(function(err) { console.error('[database] 数据加载失败:', err); });
    }

    function renderData(rows) {
      // row 的 key 用 schema 字段名（中文），元素 selector 来自 field_mapping[字段名].display_selector
    }
  })();
</script>
```

**情况 3 — 表单提交类**：拦截 `<form>` 提交改为 `db.addRecord`。

```html
<script>
  (function() {
    var db = window.__SMART_PAGE__.database;
    var DATABASE_ID = 'DATABASE_ID';
    var form = document.querySelector('FORM_SELECTOR');
    if (!form) return;
    var SCHEMA_OPTIONS = {};

    db.getSchema({ databaseId: DATABASE_ID }).then(function(schema) {
      (schema.properties || []).forEach(function(field) {
        if ((field.type === 'select' || field.type === 'multi_select') && field.config && field.config.options) {
          SCHEMA_OPTIONS[field.name] = field.config.options;
        }
      });
      renderSelectOptions();
    }).catch(function(err) { console.error('[database] schema 加载失败:', err); });

    function renderSelectOptions() {
      // 为每个 select/multi_select 动态填 <option>，selector 来自 field_mapping[字段名].form_input
      // option.value = opt.id（提交直接取），option.textContent = opt.text
    }

    form.addEventListener('submit', function(e) {
      e.preventDefault();
      var submitBtn = form.querySelector('[type="submit"]');
      if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = '提交中...'; }

      // properties key 用 schema 字段名；selector 抄 field_mapping[字段名].form_input；类型按 value_type
      var properties = {};
      // properties['姓名']     = { text: form.querySelector('[name="name"]').value };
      // properties['邮箱']     = { email: form.querySelector('[name="email"]').value };
      // properties['电话']     = { phone_number: form.querySelector('[name="phone"]').value };
      // properties['部门']     = { select: form.querySelector('[name="department"]').value };
      // properties['年龄']     = { number: parseFloat(form.querySelector('[name="age"]').value) };
      // properties['同意条款'] = { checkbox: form.querySelector('[name="agree"]').checked };
      // properties['生日']     = { date: form.querySelector('[name="birthday"]').value };
      // properties['技能']     = { multi_select: Array.prototype.map.call(form.querySelectorAll('[name="skills"]:checked'), function(el){ return el.value; }) };
      // properties['官网']     = { url: { text: v, link: v } };

      db.addRecord({ databaseId: DATABASE_ID, properties: properties })
        .then(function() { showSuccess('提交成功！'); form.reset(); })
        .catch(function(err) { console.error('[database] 提交失败:', err); showError('提交失败，请稍后重试'); })
        .finally(function() { if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = '提交'; } });
    });

    function showSuccess(msg) { /* 按原 HTML 选提示方式 */ }
    function showError(msg) { /* 按原 HTML 选错误提示 */ }
  })();
</script>
```

**类型转换**：`number`→`{number: parseFloat(v)}`；`checkbox`→`{checkbox: el.checked}`；`date`→`{date: "ISO"}`；`select`→`{select: selectEl.value}`（value 已是 opt.id）；`multi_select`→`{multi_select: [...]}`（每项 value=opt.id）；`url`→`{url:{text,link}}`。保留 HTML5 原生校验。

**情况 4 — 混合**：合并情况 2、3 到同一 IIFE：`getSchema` → `renderSelectOptions` → `loadData`；submit 走 `addRecord`，成功后 `loadData()` 刷新。

**改造原则**：

- 只改数据交互逻辑，CSS / 布局 / 动画保持原样；仍为单文件，脚本内联；无 SDK 环境不报错。
- 兼容 ES5（`function`/`var`）；SDK 调用包 try/catch；提交期间 disable 按钮。
- database 绑定标记按 §1.5.5（DSDK011/012）；`<option>` 禁硬编码，`db.getSchema` 后渲染。
- **表单输入本地缓存**：含 `addRecord` 时仅对参与提交字段（`form_input != null`）落 `localStorage`（`input`/`change` debounce 300ms 存，成功清除、失败保留，回填在 `renderSelectOptions()` 后）；`password`/`file`/`data-no-cache` 及命中 `密码·身份证·secret·token·key` 的字段跳过；搜索/筛选/装饰控件禁缓存；storage 不可用静默降级。DSDK008 校验。

### 阶段 4.5：字段映射自检（强制）

输出前跑 `lint_schema.py`；生成后、上传前跑 `lint_database_sdk_usage.py`（见 §1.6），两道通过再上传。

### 阶段 5：上传

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/import_html.py" "<path-to-file.html>" --file-name "<schema.title>.html" --databases '[{"id":"<database_id>"}]'
```

按 `import-flow.md` 执行。成功 → 提取 `node_block_id`；失败 → 保留已完成阶段，按 `error_handling.md` 生成回执。

### 改造分支回执

```
全链路完成：
- Database 已创建（ID: <database_id>），含 <N> 个字段
- HTML 已改造并上传（node_block_id: <node_block_id>）
- 页面已具备动态数据读取能力

访问链接：<url>
（若脚本未返回 url，则回退为：可到资料库中查看和管理。）
```

---

## 5. 创建分支 · 无 HTML（Database-first，Agent 写 HTML）

**触发**：用户没有现成 HTML，描述了页面需求（「帮我做一个报名页面」「做个留言板，能提交也能看」）。

### 阶段 1：分析需求 → 提炼 Schema

Agent 自行输出 canonical schema（格式同 §1.1）。先定 `page_type`：展示型（`display`，query：列表/排行/公告）；表单型（`form`，addRecord：报名/签到/反馈）；混合型（`mixed`：留言板/签到+记录）。

```json
{
  "title": "员工报名",
  "page_type": "form",
  "properties": {
    "姓名": { "text": "" },
    "邮箱": { "email": "" },
    "部门": { "select": { "options": [{ "text": "研发", "id": "<16位字母数字>" }, { "text": "产品", "id": "<16位字母数字>" }] } }
  },
  "field_mapping": {
    "姓名": { "value_type": "text", "form_input": "[name=\"name\"]", "display_selector": null, "render_signal": "label[for]:contains('姓名')" },
    "邮箱": { "value_type": "email", "form_input": "[name=\"email\"]", "display_selector": null, "render_signal": "label[for]:contains('邮箱')" },
    "部门": { "value_type": "select", "form_input": "[name=\"dept\"]", "display_selector": null, "render_signal": "label[for]:contains('部门')", "options_value_key": "value" }
  },
  "options_map": {
    "部门": { "rd": { "text": "研发", "id": "<同 properties 内 id>" }, "pm": { "text": "产品", "id": "<同 properties 内 id>" } }
  },
  "source": "agent_analysis",
  "sdk_calls_found": false
}
```

**本分支特有约束**：① selector 是阶段 4 写 HTML 时要真实写出的承诺（先定 selector 再按其写 `[name=...]`/`[data-field=...]`）；② 选项 ID 由 Agent 生成（`Math.random().toString(36).slice(2, 10) + Date.now().toString(36)`），`options_map` 与 `properties.select.options` id 一致；③ OPTIONS_MAP 二层 key：给 `<option value>` 用 value（推荐），不给用 text；④ 排序按 §1.3，表单型按填写流。

### 阶段 2 / 3：确认 Schema、创建 Database

同 §3 阶段 2、3 → 拿到 `database_id`。

### 阶段 4：直接编写 HTML

与改造分支的区别：HTML 从一开始内置 `__SMART_PAGE__.database.*`，无「改造」步骤。字段清单以阶段 3 返回 `properties` 为唯一权威。

- 单文件（CSS/JS/HTML 内联）；兼容 ES5；无 SDK 环境降级为静态/空状态；美观响应式。
- database 绑定标记按 §1.5.5（DSDK011/012）。
- `select`/`multi_select` 写成空容器（仅 `<option value="">请选择</option>`），初始化 `db.getSchema` 填充。
- 每个字段预留稳定 selector，`addRecord`/`renderData` 用同一 selector；`properties`/`row[xxx]` key 用 schema 中文字段名。
- 表单输入本地缓存同 §3 阶段 4（DSDK008）。

按 `page_type` 选模板（见 §3 阶段 4）：展示型=情况 2，表单型=情况 3，混合型=情况 4。

### 阶段 4.5 / 5：自检、上传

自检同 §1.6。上传：

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/import_html.py" "<path-to-file.html>" --file-name "<schema.title>.html" --databases '[{"id":"<database_id>"}]'
```

### 创建分支回执

```
页面已创建：
- Database 已建（ID: <database_id>），含 <N> 个字段
- HTML 已生成并上传（node_block_id: <node_block_id>）
- 页面天然支持数据读写

访问链接：<url>
（若脚本未返回 url，则回退为：可到资料库中查看和管理。）
```
