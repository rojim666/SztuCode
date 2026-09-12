# doc-typeset / stock-research prompt

继承 `base.md` 的全部规则，并应用以下研究报告（研报）专属排版规范。

## 封面（强制）

**每份研报必须以 `<section role="cover">` 开头**（绑定 `@page cover`，封面无页眉/页脚/页码）。

封面自上而下：品牌区 → 核心区（视觉焦点+留白）→ 数据区（KV table）→ 元信息区。

> ⚠️ **禁止使用 `<dl>/<dt>/<dd>` 和 `display:grid`**（见 SKILL.md `## HTML 元素规范`）。指标数据用 `<table class="metrics-table">` 承载。

```html
<section role="cover">
  <!-- 品牌区 -->
  <div class="cover-brand">
    <span class="cover-org">{{broker_name}}</span>
  </div>

  <!-- 核心区（视觉焦点 + 留白） -->
  <div class="cover-core">
    <p class="cover-category">{{category}} | {{report_type}}</p>
    <p class="cover-stock">{{company_name}} {{stock_code}}</p>
    <p class="cover-rating">{{rating_text}}（{{rating_change}}）</p>
    <h1 class="cover-title">{{report_title}}</h1>
  </div>

  <!-- 数据区（核心指标 KV table，替代旧 dl + grid） -->
  <div class="cover-data">
    <table class="metrics-table">
      <tr>
        <td class="m-label">股价</td><td class="m-value">{{current_price}}</td>
        <td class="m-label">目标价格</td><td class="m-value">{{target_price}}</td>
        <td class="m-label">52周最高</td><td class="m-value">{{high_52w}}</td>
        <td class="m-label">52周最低</td><td class="m-value">{{low_52w}}</td>
      </tr>
      <tr>
        <td class="m-label">总股本</td><td class="m-value">{{total_shares}}</td>
        <td class="m-label">流通A股</td><td class="m-value">{{float_shares}}</td>
        <td class="m-label">EPS(TTM)</td><td class="m-value">{{eps_ttm}}</td>
        <td class="m-label">PE(TTM)</td><td class="m-value">{{pe_ttm}}</td>
      </tr>
    </table>
  </div>

  <!-- 元信息区 -->
  <div class="cover-meta">
    <p class="cover-author">分析师：{{analyst}}</p>
    <p class="cover-cert">执业证书编号：{{cert_no}}</p>
    <p class="cover-contact">{{email}} | {{phone}}</p>
    <p class="cover-date">{{pub_date}}</p>
  </div>
</section>
```

封面绑定 `@page cover`（无页脚页码），正文从新页开始。

## 额外 CSS 变量

```css
--ff-mono: var(--typography-fontFamily-mono, monospace);
--color-abstract-border: var(--color-primary);
--color-abstract-bg: var(--color-highlight, #f5f7fa);
--abstract-border-left-width: 4px;
--color-rating-buy: var(--color-success, #2e7d32);
--color-rating-hold: var(--color-warning, #e65100);
--color-rating-sell: var(--color-danger, #c62828);
```

## 正文 Section 标题

正文各大章节使用 `.section-header` 类（深色背景条 + 白字标题）：

```html
<div class="section-header">盈利预测与投资建议</div>
```

样式定义：
```css
.section-header {
  background: var(--color-bg-dark);
  color: var(--color-bg);
  font-size: var(--fs-section-header);
  font-family: var(--ff-heading);
  font-weight: var(--fw-bold);
  padding: 0.4em 2cm;
  margin-top: var(--spacing-section);
  margin-bottom: var(--spacing-block);
}
```

正文内的二级小节标题使用 `<h2>`（主色+左边框，次高层级），三级小节使用 `<h3>`（主色加粗，第三层级）。

```css
.research-body h2 {
  font-size: var(--fs-h2);
  font-family: var(--ff-heading);
  font-weight: var(--fw-bold);
  color: var(--color-primary);
  border-left: 3px solid var(--color-primary);
  padding-left: 0.6em;
  margin-bottom: 0.7em;
}
.research-body h3 {
  font-size: var(--fs-h3);
  font-family: var(--ff-heading);
  font-weight: var(--fw-bold);
  color: var(--color-primary);
  margin-bottom: 0.6em;
}
```

四级层级靠「字号+字重+颜色/底色」三重区分（券商研报标准做法）：
- **章节** `.section-header`：深底白字 13pt（最高层级）
- **小节** `h2`：主色+左边框 11pt
- **子小节** `h3`：主色加粗 10pt
- **正文**：9pt

## 摘要框 / 多段落底纹卡片

多段落需要"整块底纹铺满版心"时，使用裸单列 `<table class="abstract-card">`（见 SKILL.md 元素规范 (d)）。**禁止** `<div class="abstract-box">` 靠逐段 shd 拼底纹。

```html
<table class="abstract-card"><tr><td>
  <p class="card-title">核心观点</p>
  <p>{{point_1}}</p>
  <p>{{point_2}}</p>
</td></tr></table>
```

`.abstract-card td`：`background-color: var(--color-card-bg); border-left: 3px solid var(--color-primary); padding: 0.8em 1em;`

## 数据表格

研报数据表格使用三线表 + 数字列特殊样式：

```html
<table class="three-line-table research-table">
  <thead>
    <tr><th>指标</th><th class="num-cell">FY2023A</th><th class="num-cell">FY2024E</th></tr>
  </thead>
  <tbody>
    <tr>
      <td>营业收入（亿元）</td>
      <td class="num-cell">123.4</td>
      <td class="num-cell estimated">145.0</td>
    </tr>
  </tbody>
</table>
```

`.num-cell`：`text-align: right; font-family: var(--ff-mono);`

`.estimated`：`font-style: italic; color: var(--color-muted);`（预测值斜体）

## 风险提示（强制）

**每份研报必须包含风险提示区。** 多条风险时用 `<table class="abstract-card">` 承载底纹卡片，保持正式克制：

```html
<table class="abstract-card"><tr><td>
  <p class="card-title">风险提示</p>
  <p><strong>市场竞争风险</strong>：{{risk_1}}</p>
  <p><strong>技术落地风险</strong>：{{risk_2}}</p>
</td></tr></table>
```

单条风险可简化为正文段落：
```html
<p style="border-left:3px solid var(--color-primary);background:var(--color-card-bg);padding:0.6em 1em">
  <strong>风险提示：</strong>{{risk_content}}
</p>
```

❌ 错误做法：`<div data-component="callout" data-variant="warning">` — 彩色边框/背景不符合研报正式风格

✅ 正确做法：abstract-card 底纹卡片或单段落 CSS 强调，克制正式

## 免责声明

```html
<div class="disclaimer">
  <p class="disclaimer-title">免责声明</p>
  <p>{{disclaimer_text}}</p>
</div>
```

`.disclaimer`：`font-size: var(--fs-small); color: var(--color-muted);`

## 装饰组件触发规则

研报风格**克制正式**，仅使用以下组件：

| 触发内容 | 组件 | 说明 |
|---------|------|------|
| 封面（强制） | cover | variant=finance |
| 章节标题 | 原生 HTML（.section-header） | 深色背景条白字 |
| 章节之间视觉分隔 | divider | 细线分隔，正式克制 |
| 核心观点摘要 | 原生 HTML（`<table class="abstract-card">`） | 裸单列 table 底纹卡片 |
| 财务数据表 | 原生 HTML（.three-line-table） | 三线表样式 |

**不使用以下组件**（不符合研报正式风格）：

| 组件 | 原因 |
|------|------|
| ❌ `callout` | 彩色提示框过于花哨，研报是监管级文件 |
| ❌ `data-card` | 卡片式布局不符合券商研报排版惯例 |
