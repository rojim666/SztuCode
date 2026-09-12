# doc-typeset / government-doc prompt

继承 `base.md` 的全部规则，并严格按照 **GB/T 9704-2012** 应用以下公文排版规范。

## 额外 CSS 变量

```css
--color-gov-red: var(--palette-govRed, #cc0000);
--fs-issuer: var(--typography-fontSize-h1, 26pt);
```

## 红头区结构

```html
<header class="gov-doc-header">
  <hr class="doc-redline">
  <div class="doc-issuer">
    <span class="issuer-name">{{org_name}}</span>
    <span class="issuer-type">{{doc_type}}</span>
  </div>
  <hr class="doc-redline">
  <div class="doc-signatory-row">
    <span class="doc-number">{{org_code}}〔{{year}}〕{{serial_no}}号</span>
    <span class="doc-signatory">签发人：{{signer_name}}</span>
  </div>
</header>
```

`.doc-redline`：`border: none; border-top: 3px solid var(--color-gov-red); margin: 0;`

`.doc-issuer`：红色、居中、字号 `var(--fs-issuer)`，使用 `color: var(--color-gov-red)`

`.doc-signatory-row`：`display: flex; justify-content: space-between;`

## 标题与正文结构

```html
<h1 class="gov-doc-title">{{doc_title}}</h1>
<p class="doc-recipient">{{recipient}}：</p>
<div class="gov-doc-body">{{body_content}}</div>
```

`.gov-doc-title`：居中、加粗、字号 `var(--fs-h1)`

## 标题层级格式（顶格）

| 层级 | 格式 | 示例 |
|------|------|------|
| h2 | 一、二、三… | `<strong>一、总体要求</strong>` |
| h3 | （一）（二）… | `<strong>（一）基本原则</strong>` |
| h4 | 1. 2. 3. | `<strong>1.</strong> 具体要求` |
| h5 | （1）（2）… | （1）第一项 |

所有层级均 `<strong>`，顶格（`text-indent: 0`）。

## 落款区

```html
<footer class="doc-footer-sign">
  <div class="issuer-sign">{{issuer_org}}</div>
  <div class="doc-date">{{year}}年{{month}}月{{day}}日</div>
</footer>
<div class="doc-copy-info">抄送：{{copy_list}}</div>
```

`.doc-footer-sign`：右对齐，`text-align: right`

## 页脚页码（GB/T 9704）

公文按 GB/T 9704 惯例用页脚居中页码，格式 `— 1 —`（数字两侧空格 + 短横）。在 `<style>` 内声明 `@page`（参见 SKILL.md「页面模型规范」）：

```html
<style>
  @page { @bottom-center { content: "— " counter(page) " —"; } }
</style>
```

> 注意：红头区 `<header class="gov-doc-header">` 与落款区 `<footer class="doc-footer-sign">` 是**正文内容块**（每文一次），与 `@page` 的**每页重复页码**是两套机制，互不冲突。

## 装饰组件触发规则

| 触发内容 | 组件 | variant |
|---------|------|---------|
| 通知、要求、规定 | callout | info |
| 严禁、不得、禁止 | callout | danger |
