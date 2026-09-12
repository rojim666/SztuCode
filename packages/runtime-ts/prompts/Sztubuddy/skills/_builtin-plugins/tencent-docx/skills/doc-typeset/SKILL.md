---
name: doc-typeset
description: |
  消费 design tokens + 文档内容，输出排版美化的 HTML。
  内置 7 种垂类模板（合同/学术论文/公文/商务报告/会议纪要/研报/年报）和 4 个装饰组件，所有样式通过 CSS 变量引用 Token，禁止裸值。
  在 doc-formatter 流水线中每当需要将文本内容转化为结构化美化 HTML 时，必须使用此 skill；
  不要自己写 HTML 或内联 CSS——doc-typeset 是内容→HTML 的唯一标准转换路径。
category: capability
version: "1.0.0"
agent: doc-formatter
tags: [typesetting, html, templates, doc-formatting]
disable-user-invocation: true
---

# doc-typeset Skill

## 职责

接收上游 design-token skill 的 token 输出和原始文档内容，输出排版美化的完整 HTML 字符串。

## 输入契约

```typescript
interface TypesetInput {
  content: string;               // 原始文档内容（Markdown 或纯文本）
  design_tokens: DesignTokens;   // 来自 doc-design-token skill 的 token 对象
  genre: string;                 // 文档类型（如 legal-contract, academic-paper 等）
  scene_type?: string;           // 可选：场景类型（如 formal, casual）
}
```

## 输出契约

```typescript
interface TypesetOutput {
  html: string;                   // 美化后的完整 HTML 字符串
  template_used: string;          // 实际使用的模板名称
  components_inserted: string[];  // 插入的装饰组件列表
}
```

## 模板选择逻辑

1. 检查 `genre` 是否命中垂类（legal-contract / academic-paper / government-doc / business-report / meeting-minutes / stock-research / annual-report）
2. 命中 → 加载 `prompts/{genre}.md`（排版 prompt）+ `templates/{genre}.html`（HTML 骨架）
3. 未命中 → 加载 `prompts/base.md` + `templates/base.html`

> **渐进加载**：只在实际需要时读取对应的 prompt 和 template 文件，不要预先加载所有文件。

## 装饰组件使用指南

| 组件 | 用途 | 触发条件 |
|------|------|----------|
| `callout` | 重要提示、警告、危险信息 | 内容含"注意""警告""重要""严禁"等关键词 |
| `divider` | 章节分隔 | 主要章节之间，或文档需要视觉分隔时 |
| `section-marker` | 编号章节标题 | 有序章节，需突出层级时 |
| `data-card` | 数据/指标展示 | 表格含 KPI、评级、统计数据时 |

## 页面模型规范：语义 Section + CSS @page

> 自 S-26060126E 起，**封面页 / 分节 / 横向页 / 页眉页脚页码** 统一由「语义 `<section role>` + CSS `@page`」表达。这是生成 HTML 时表达"分页结构"的**唯一**方式。

### (a) 语义分节 `<section>`

`<body>` 下的**顶层** `<section>` 按 DOM 顺序映射为独立 docx 节（节边界自动插 `nextPage` 分节符）。无 `<section>` 时按单节处理。

```html
<body>
  <section role="cover"> … </section>                               <!-- 封面节 -->
  <section role="body" data-page-restart="1"> … </section>          <!-- 正文，页码从 1 重起 -->
  <section role="financials" data-orientation="landscape"> … </section>  <!-- 横向节（财务报表） -->
</body>
```

| 属性 | 说明 | 默认 |
|------|------|------|
| `role` | 开放字符串；用于 `section[role=X]{page:Y}` 命名页绑定 | 无 |
| `data-orientation` | `portrait` / `landscape`（横向 = 取文档尺寸交换宽高，**取代旧 section-break landscape**） | 文档默认 |
| `data-margin-top/bottom/left/right` | 该节页边距（cm），按属性合并，未设项回落文档默认 | 文档默认 |
| `data-page-restart` | 该节页码起始值（写入 `pgNumType@w:start`） | 不重起 |

> 嵌套 `<section>` 只有顶层计为节，内层降级为普通块。封面/正文内的语义块请用 `<div>` 表达。

### (b) CSS `@page` 页眉/页脚/页码（CSS Paged Media 有界子集）

在 `<style>` 中用 `@page` 声明 6 个 margin-box（`@top-left/center/right`、`@bottom-left/center/right`）的页眉页脚内容；命名页 `@page <name>` 配合 `section[role=X]{page:Y}` 实现"封面无、正文有"。

| `content` 取值 | 渲染为 | 含义 |
|------|------|------|
| `counter(page)` | Word `PAGE` 域 | 当前页码 |
| `counter(pages)` | Word `NUMPAGES` 域 | 总页数 |
| `string(<name>)` | `STYLEREF` 域 | 配合 `string-set`，引用样式（如 `h1`→Heading1），做页眉章节名 |
| `"文本"` / `'文本'` | 普通文本 | 字符串字面量 |
| `none` | 不产内容 | 该 box 真正无家具（封面） |

> 域写入后转换器自动置位 `updateFields`，Word 打开 / 按 F9 即刷新。`content: ""`（空字符串）非法 → 等同未设置 + warning（沿用上一节继承）。不支持的语法（`@page :first`、`@page { size }`）→ 忽略 + warning，不中断转换。

### (c) 三个标准模式（按需组合）

**模式 1 — 正文页脚居中页码**：
```html
<style>
  @page { @bottom-center { content: counter(page); } }
</style>
```

**模式 2 — 封面无家具 + 正文页码**（最常用）：
```html
<style>
  @page { @bottom-center { content: counter(page); } }
  @page cover { @bottom-center { content: none; } }   /* 封面真正无页脚 */
  section[role="cover"] { page: cover; }
</style>
<body>
  <section role="cover"> … </section>
  <section role="body" data-page-restart="1"> … </section>
</body>
```

**模式 3 — 页眉章节名（STYLEREF）+ 页脚"第 X 页 / 共 Y 页"**：
```html
<style>
  @page {
    @top-right     { content: string(chapter); }
    @bottom-center { content: "第 " counter(page) " 页 / 共 " counter(pages) " 页"; }
  }
  @page cover { @top-right { content: none; } @bottom-center { content: none; } }
  section[role="cover"] { page: cover; }
  h1 { string-set: chapter content(text); }   /* 每个 h1 标题更新页眉章节名 */
</style>
```

> ⚠️ **默认不加页眉 running-head**：所有内置模板（`government-doc`/`legal-contract`/`business-report`/`academic-paper`/`stock-research`/`annual-report`/`meeting-minutes`）**均只配页脚页码、不配 `@top-*` 页眉**。因此本模式（模式 3）**不是默认动作**——除非用户明确要求"页眉显示章节名"，否则**一律不要自作主张加 `@top-* { content: string(...) }` 页眉**，保持与模板一致（模式 1 / 模式 2 即可）。
>
> ⚠️ **确需加页眉时，`string-set` 必须绑到正文中真实存在且已套用的标题级别**：`string(name)` 会转成 `STYLEREF HeadingN` 域，若正文中零个段落套用该级别标题，Word 刷新域时会渲染成中文报错"错误！使用'开始'选项卡将 Heading N 应用于…"。所以绑定级别必须与正文实际章节标题级别一致（正文章节标题是 `h1` 就只能绑 `h1`，**不要绑到正文里根本没有的 `h2`/`h3`**）。

> 同区域多个 box（如 `@bottom-left` + `@bottom-center` + `@bottom-right`）合并进单段落，用 Tab 制表位左/中/右定位。

## CSS 变量规范

所有样式属性**必须**引用 CSS 变量（`var(--*)`），**禁止**裸值（如 `font-size: 14px`）。

变量命名约定：
- 字体大小：`--fs-{level}`（如 `--fs-h1`、`--fs-body`）
- 字体族：`--ff-{type}`（如 `--ff-heading`、`--ff-body`）
- 颜色：`--color-{name}`（如 `--color-primary`、`--color-text`）
- 间距：`--spacing-{name}`（如 `--spacing-paragraph`、`--spacing-section`）
- 页边距：`--margin-page`
- 内容区宽度：`--page-content-width`

## HTML 元素规范

最终产物导出为 **.docx**。docx 没有 CSS Grid、也不支持 `<dl>/<dt>/<dd>` 的结构化语义——转换器对这类元素只能降级处理，导致排版错乱、对齐丢失、信息拍平。因此**生成 HTML 时必须从源头规避**，统一用 `<table>` 承载结构化/对齐型内容。

### (a) 禁止 `display:grid` / `grid-template-*`

多列、栅格布局在 docx 中无对应能力，必须改用 `<table>`。

**反例（禁止）**：
```html
<div class="metrics" style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr">
  <div>市盈率<br>18.5</div>
  <div>市净率<br>2.1</div>
  <div>ROE<br>15.2%</div>
  <div>股息率<br>3.4%</div>
</div>
```

**正例（改用 table 多列）**：
```html
<table class="metrics">
  <tr><td>市盈率</td><td>市净率</td><td>ROE</td><td>股息率</td></tr>
  <tr><td>18.5</td><td>2.1</td><td>15.2%</td><td>3.4%</td></tr>
</table>
```

### (b) 禁止 `<dl>/<dt>/<dd>`

定义列表在 docx 中无等价结构，标签-值的对齐关系会丢失，必须改用两列 `<table>`。

**反例（禁止）**：
```html
<dl class="cover-info-list">
  <dt>指导教师</dt><dd>张三</dd>
  <dt>学生姓名</dt><dd>李四</dd>
</dl>
```

**正例（改用两列 table）**：
```html
<table class="cover-info-list">
  <tr><td>指导教师</td><td>张三</td></tr>
  <tr><td>学生姓名</td><td>李四</td></tr>
</table>
```

### (c) KV / 指标 / 多列内容 → `<table>`

任何键值对、指标矩阵、需要对齐的多列内容，一律用 `<table>` 承载，禁止用 `grid` + `dl` 拼装。

**反例（禁止）**：
```html
<div style="display:grid;grid-template-columns:auto 1fr">
  <dl><dt>评级</dt><dd>买入</dd></dl>
  <dl><dt>目标价</dt><dd>￥58.00</dd></dl>
</div>
```

**正例（2×N KV table）**：
```html
<table class="kv-table">
  <tr><td>评级</td><td>买入</td></tr>
  <tr><td>目标价</td><td>￥58.00</td></tr>
</table>
```

### (d) 多段落底纹卡片 → 裸单列 `<table>`

需要"整块底纹 + 内含多段落富文本"的卡片（如核心观点/关键发现/摘要框），用裸单列 `<table class="abstract-card"><tr><td>…</td></tr></table>` 承载，底纹与边框落在单元格上，多段落富文本完整保留。**不要**用 `<div>` 靠逐段落 shd 拼底纹（会出现段间断纹、铺不满版心）。

**反例（禁止）**：
```html
<div class="abstract-box" style="background:#eef4fb">
  <p>核心观点一……</p>
  <p>核心观点二……</p>
</div>
```

**正例（裸单列 table 承载多段落）**：
```html
<table class="abstract-card">
  <tr><td>
    <p><strong>核心观点</strong></p>
    <p>核心观点一……</p>
    <p>核心观点二……</p>
  </td></tr>
</table>
```

### (e) 单段落强调 → CSS `border` / `background`

仅单个段落需要强调（如提示、警示）时，直接用段落级 CSS `border-left` / `background`，转换器会保真为 `w:pBdr` / `w:shd`，无需套表格。**不要**把长段落塞进 callout 拍平承载。

> **左边框前导空格**：任何设置了左边框（`border-left`，无论 class 名）的块级元素，文字开头必须加两个不折叠空格 `&nbsp;&nbsp;`。Word 左边框无可靠间距，文字会紧贴竖线；普通前导空格又会被 HTML 折叠。详见 base.md「左边框段落的前导空格」。

**反例（禁止）**：
```html
<div data-component="callout"><div class="callout-content">
一大段被拍平的长文本失去了所有段落结构……
</div></div>
```

**正例（单段落 CSS 强调，注意前导 `&nbsp;&nbsp;`）**：
```html
<p style="border-left:3px solid var(--color-primary);background:#eef4fb;padding:8px">
  &nbsp;&nbsp;单段落提示：本季度营收同比增长 23%。
</p>
```

### (f) 关键 CSS 属性必须显式声明，禁止依赖继承

html4docx 不做 CSS 继承计算，只看每个块级元素自己身上的样式。父容器上写的 `text-align` / `font-family` / `color` / `font-size` **不会**递归下发到子块。因此凡是关键视觉属性，**每个块级元素**必须自己显式写，最典型的就是封面块的 `text-align: center`。

**反例（禁止，转换后子块全部左对齐）**：
```html
<style>section[role="cover"] { text-align: center; }</style>
<section role="cover">
  <p class="cover-eyebrow">SCIENCE · BIOGRAPHY</p>
  <h1>标题</h1>
  <p class="cover-subtitle">副标题</p>
</section>
```

**正例（每个封面块自己写 `text-align: center`）**：
```html
<style>
  .cover-eyebrow  { text-align: center; }
  section[role="cover"] > h1 { text-align: center; }
  .cover-subtitle { text-align: center; }
</style>
```

> 只影响 inline 元素（`<span>` / `<strong>` 等）的属性可以走继承（合并到父段落 run）；跨块级边界（`<p>`/`<h1>`/`<div>`/`<li>`/`<td>`）继承一律断。详见 `prompts/base.md`「关键 CSS 属性必须显式声明」。

### (g) 禁止装饰性短横线（封面 eyebrow-rule 等）

`<hr>` 在 docx 中只能降级为**一整段「满版下边框」段落**（见 `element_mapper.add_horizontal_rule`），无法保留「居中短线 / 彩色装饰线 / 定宽」这类视觉。因此**封面/标题区的纯装饰短横线**（如小标签 eyebrow 下面配的 `<hr class="cover-rule">`）一律**不要生成**——转 docx 后会变成突兀的满版横线，破坏版面。封面靠标题、副标题、元信息的字号层级与间距区分即可。

> 例外：仅用于**章节之间视觉分隔**的整行 divider（本身就是满版下边框，转换无损）不受此限；被禁止的只是「假装成定宽/居中/彩色装饰线」的短横线。

**反例（禁止）**：
```html
<section role="cover">
  <p class="cover-eyebrow">SCIENCE · BIOGRAPHY</p>
  <hr class="cover-rule">   <!-- 装饰短横线：docx 里会变成满版横线 -->
  <h1>标题</h1>
</section>
```

**正例（去掉装饰横线，靠层级与间距区分）**：
```html
<section role="cover">
  <p class="cover-eyebrow">SCIENCE · BIOGRAPHY</p>
  <h1>标题</h1>
  <p class="cover-subtitle">副标题……</p>
</section>
```

### (h) 禁止 `<span>` 模拟 badge

`<span>` 的 `background`/`padding`/`border-radius`/`inline-block` 在 docx 中全部丢失。需要标签/badge 效果时：
- **纯文字** → `<p>` + color/font-size/font-weight（≥700）
- **需底纹** → 单行 `<table><td>` 承载（td 的 background 可还原）


## 页面尺寸规范

HTML 输出以连续流布局，但最终导出为分页 .docx。

**核心原则**：
- **默认页面宽度为 A4**（21cm），所有模板必须通过 `<meta name="docx-page-size" content="A4">` 声明
- **只约束宽度，不设页面高度** — 因为 .docx 以分页形式排版，HTML 侧以连续流呈现，高度由内容撑开
- **必须**用 `max-width: var(--page-content-width)` 约束 body 宽度，确保 HTML 预览效果与最终 .docx 一致

### 各 Genre 页面宽度配置

| Genre | page-size | content-width | 说明 |
|-------|-----------|--------------|------|
| `*`（通用默认） | A4 | 15.6cm | 21cm - 左3.17cm - 右2.23cm |
| `academic-paper` | A4 | 16.0cm | 21cm - 左2.5cm - 右2.5cm |
| `government-doc` | A4 | 15.6cm | GB/T 9704 标准 |
| `business-report` | A4 | 15.6cm | 标准 A4 |
| `legal-contract` | A4 | 15.6cm | 标准 A4 |
| `meeting-minutes` | A4 | 15.6cm | 标准 A4 |
| `stock-research` | A4 | 满版（无max-width） | margin=0，内容靠 padding 控制 |
| `annual-report` | A4 | 15.6cm | 21cm - 左3.15cm - 右2.25cm |

### 特殊宽度

| 场景 | content-width | 说明 |
|------|--------------|------|
| 公众号/移动端 | 375px | 手机屏幕宽度 |
| A3 宽幅（横向表格） | 24.7cm | 29.7cm - 左2.5cm - 右2.5cm |
| 横向节（`<section data-orientation="landscape">`） | 24.7cm | A4 纵向高度减页边距 |

### 模板中的实现方式

```html
<meta name="docx-page-size" content="A4">
<style>
:root {
  --page-content-width: var(--layout-contentWidth, 15.6cm);
}
body {
  max-width: var(--page-content-width);
  margin-left: auto;
  margin-right: auto;
}
</style>
```

研报满版设计例外：`body { width: 21cm; margin: 0 auto; padding: 0; }`（不设 max-width，内容靠内部元素 padding 控制间距）

## 支持的 Genre 列表

| Genre | 描述 | 模板文件 |
|-------|------|----------|
| `legal-contract` | 法律合同 | `templates/legal-contract.html` |
| `academic-paper` | 学术论文 | `templates/academic-paper.html` |
| `government-doc` | 政府公文（GB/T 9704） | `templates/government-doc.html` |
| `business-report` | 商务报告 | `templates/business-report.html` |
| `meeting-minutes` | 会议纪要 | `templates/meeting-minutes.html` |
| `stock-research` | 股票研报 | `templates/stock-research.html` |
| `annual-report` | 上市公司年度报告 | `templates/annual-report.html` |
| `*`（兜底） | 通用文档 | `templates/base.html` |

## 文件结构

```
doc-typeset/
├── SKILL.md                      # 本文件
├── prompts/
│   ├── base.md                   # 通用排版 prompt
│   ├── legal-contract.md
│   ├── academic-paper.md
│   ├── government-doc.md
│   ├── business-report.md
│   ├── meeting-minutes.md
│   ├── stock-research.md
│   └── annual-report.md
├── templates/
│   ├── base.html                 # 通用 HTML 骨架
│   ├── legal-contract.html
│   ├── academic-paper.html
│   ├── government-doc.html
│   ├── business-report.html
│   ├── meeting-minutes.html
│   ├── stock-research.html
│   └── annual-report.html
└── components/
    ├── callout.html
    ├── divider.html
    ├── section-marker.html
    └── data-card.html
```
