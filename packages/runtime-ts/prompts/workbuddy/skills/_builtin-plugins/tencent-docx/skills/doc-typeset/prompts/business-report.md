# doc-typeset / business-report prompt

继承 `base.md` 的全部规则，并应用以下商务报告专属排版规范。

## 额外 CSS 变量

```css
--color-summary-bg: var(--color-highlight, #f5f7fa);
--color-summary-border: var(--color-primary);
--summary-border-width: 4px;
--radius-card: var(--spacing-block, 8px);
--shadow-card: 0 2px 8px rgba(0,0,0,0.08);
--color-accent: var(--color-primary);
/* 重点数据高亮（见「重点数据高亮规范」） */
--color-emphasis: var(--color-danger, #c62828);   /* 通用重点数据强调色：红 */
--color-stock-up: var(--color-danger, #c62828);   /* 股票涨：默认按 A 股惯例=红 */
--color-stock-down: var(--color-success, #2e7d32); /* 股票跌：默认按 A 股惯例=绿 */
```

## 重点数据高亮规范

报告中的**关键数据必须标红强调**，让读者一眼抓住核心结论；股票涨跌数据则按**所在市场的惯用颜色**标注，不能一律标红。

### 规则 1：通用重点数据 → 标红

营收、增长率、目标价、关键 KPI、同比/环比变化等**结论性数字**，用 `<span class="data-emphasis">` 包裹，引用 `--color-emphasis`（默认红）。普通陈述性数字不标，避免满屏皆红失去强调意义（**每段建议 ≤2 处**）。

```css
.data-emphasis { color: var(--color-emphasis); font-weight: var(--fw-bold); }
```

```html
<p>本季度营业收入 <span class="data-emphasis">123.4 亿元</span>，同比增长 <span class="data-emphasis">+23%</span>，超出市场预期。</p>
```

### 规则 2：股票涨跌数据 → 按市场惯例

涨跌幅、股价变动、指数涨跌等数据用 `.stock-up`（涨）/ `.stock-down`（跌），颜色由 `--color-stock-up` / `--color-stock-down` 决定。**颜色不是固定的，取决于标的所在市场**：

| 市场 | 涨（up） | 跌（down） |
|------|---------|-----------|
| 中国 A 股 / 港股 / 台股 / 日股 / 韩股（东亚） | 红 | 绿 |
| 美股 / 欧股 / 其他欧美市场 | 绿 | 红 |

**做法**：先判断标的市场，在 `:root` 里给两个变量赋对应语义色，正文只用语义 class，不写裸色值。

```css
.stock-up   { color: var(--color-stock-up);   font-weight: var(--fw-bold); }
.stock-down { color: var(--color-stock-down); font-weight: var(--fw-bold); }
```

```css
/* 东亚市场（A股/港股…）：涨红跌绿 —— 默认值 */
--color-stock-up: var(--color-danger, #c62828);
--color-stock-down: var(--color-success, #2e7d32);

/* 美股 / 欧股：涨绿跌红 —— 写报告前按市场切换为下列映射 */
--color-stock-up: var(--color-success, #2e7d32);
--color-stock-down: var(--color-danger, #c62828);
```

```html
<!-- A 股标的：涨用红 -->
<p>贵州茅台收盘 <span class="stock-up">1680.00 (+2.35%)</span>。</p>
<!-- 美股标的：涨用绿（同一份报告若跨市场，分别赋值） -->
<p>苹果收盘 <span class="stock-up">+1.8%</span>，标普 <span class="stock-down">-0.6%</span>。</p>
```

❌ 错误做法：把美股的上涨也标成红色（红=涨是东亚惯例，欧美红=跌，会误导）。
❌ 错误做法：`<span style="color:#c62828">`（裸色值，违反「禁止裸值」纪律）。
✅ 正确做法：先按市场给 `--color-stock-up/down` 赋语义色，正文统一用 `.stock-up` / `.stock-down`。
✅ 正确做法：涨跌不确定市场时默认 A 股惯例（涨红跌绿），并在报告中保持全篇一致。



## 执行摘要结构（Executive Summary）

```html
<div class="executive-summary">
  <div class="summary-header">
    <h2>执行摘要</h2>
    <span class="summary-badge">Executive Summary</span>
  </div>
  <div class="summary-highlights">
    <!-- 3-5 个 data-card 数据卡片 -->
    <div data-component="data-card" data-title="{{metric_name}}">
      <span class="card-value">{{value}}</span>
      <span class="card-unit">{{unit}}</span>
      <span class="card-trend card-trend--up">↑ {{change}}</span>
    </div>
  </div>
  <div class="summary-body">{{summary_text}}</div>
</div>
```

`.executive-summary`：`border-left: var(--summary-border-width) solid var(--color-summary-border); background: var(--color-summary-bg); padding: var(--spacing-section);`

## 进度表格

进度条通过 CSS 变量间接引用宽度（避免内联 `width: XX%`）：

```html
<table class="progress-table">
  <thead><tr><th>项目</th><th>进度</th><th>状态</th></tr></thead>
  <tbody>
    <tr>
      <td>{{item_name}}</td>
      <td>
        <div class="progress-bar" role="progressbar"
             aria-valuenow="{{percent}}" aria-valuemin="0" aria-valuemax="100">
          <div class="progress-fill" style="width: var(--progress-{{id}})"></div>
        </div>
      </td>
      <td><span class="status-badge status-{{status}}">{{status_label}}</span></td>
    </tr>
  </tbody>
</table>
```

状态 class：`status-done`、`status-in-progress`、`status-pending`

## 页脚页码

商务报告用页脚居中页码。在 `<style>` 内声明 `@page`（参见 SKILL.md「页面模型规范」）：

```html
<style>
  @page { @bottom-center { content: counter(page); } }
</style>
```

## 封面分类标签（cover-category）

封面标题上方的分类标签**必须**用 `<p class="cover-category">`，**禁止** `<span>` + background badge。样式仅用 color/font-size/font-weight(≥700)/letter-spacing。

```html
<p class="cover-category">行业深度研究</p>
```

## 装饰组件触发规则

| 触发内容 | 组件 | variant/style |
|---------|------|---------------|
| 关键数据指标（3-5 项） | data-card | primary/success |
| 结论性重点数字（营收/增长/目标价等） | `.data-emphasis` | 标红强调（见「重点数据高亮规范」） |
| 股票涨跌/股价变动/指数涨跌 | `.stock-up` / `.stock-down` | 按市场惯例着色（东亚涨红跌绿，欧美涨绿跌红） |
| 风险提示、注意项 | callout | warning |
| 重要结论、建议 | callout | info |
| 章节之间 | divider | section-break |
