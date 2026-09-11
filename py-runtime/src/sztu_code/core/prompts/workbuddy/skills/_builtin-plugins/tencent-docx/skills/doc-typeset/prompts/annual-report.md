# doc-typeset / annual-report prompt

继承 `base.md` 的全部规则，并应用以下上市公司年度报告专属排版规范。

## 文档特征

年报是上交所/深交所格式的监管文件，特点：
- **极简朴素**：纯黑白 + 红色标题，无装饰图形
- **5 级标题层次**：第X节 → 一、 → (一) → 1、 → (1).
- **大量表格**：财务数据是核心信息载体
- **横向页面混排**：合并利润表/资产负债表使用横向排版
- **标准 8 节结构**：释义 → 公司简介 → 管理层讨论 → 公司治理 → 重要事项 → 股份变动 → 债券 → 财务报告

## 封面规范

封面用语义 `<section role="cover">`（绑定 `@page cover`，封面无页眉/页脚/页码）：

```html
<section role="cover">
  <div class="cover-body">
    <p class="cover-code">公司代码：{{stock_code}}</p>
    <p class="cover-abbr">公司简称：{{company_abbr}}</p>
    <h1 class="cover-title">{{company_full_name}}{{report_year}}年年度报告</h1>
  </div>
</section>
```

封面标题：红色加粗居中（22pt），大量留白。

## 标题层级映射

| 层级 | HTML 标签 | 格式 | 示例 |
|------|----------|------|------|
| 节标题 | `<h1>` | 14pt 黑体加粗 | 第一节　释义 |
| 二级 | `<h2>` | 正文字号加粗 | 一、报告期内公司从事的业务情况 |
| 三级 | `<h3>` | 正文字号加粗 | (一) 主营业务分析 |
| 四级 | `<h4>` | 正文字号加粗 | 1、利润表及现金流量表相关科目变动分析表 |
| 五级 | `<h5>` | 正文字号加粗 | (1). 主营业务分行业情况 |

## 表格规范

年报使用**全边框表格**（非三线表）：

```html
<table class="annual-table">
  <thead>
    <tr><th>项目</th><th class="num-cell">本年</th><th class="num-cell">上年</th></tr>
  </thead>
  <tbody>
    <tr><td>营业收入</td><td class="num-cell">168,838</td><td class="num-cell">170,899</td></tr>
  </tbody>
</table>
```

`.annual-table td, .annual-table th`：`border: 1px solid var(--color-border);`

`.num-cell`：`text-align: right; font-family: Arial, sans-serif;`

## 横向页面（财务报表）

合并利润表、资产负债表等宽表格需要横向排版——用语义 `<section data-orientation="landscape">` 独立成节，结束后另起纵向节：

```html
<section role="financials" data-orientation="landscape">
  <!-- 宽财务报表 -->
</section>
<section role="body" data-orientation="portrait">
  <!-- 回到纵向正文 -->
</section>
```

## 页眉页脚页码

正文页脚居中页码、封面无家具（在 `<style>` 内声明，参见 SKILL.md「页面模型规范」模式 2）：

```html
<style>
  @page { @bottom-center { content: counter(page); } }
  @page cover { @bottom-center { content: none; } }
  section[role="cover"] { page: cover; }
</style>
```

> 横向财务节继承默认 `@page` 页脚页码，无需单独声明。

## 字体规范

- 正文：宋体 10.5pt
- 标题：黑体
- 数字/英文：Arial
- 行距：1.5 倍

## 页边距

- 上：2.07cm
- 下：2.55cm
- 左：3.15cm
- 右：2.25cm

## 装饰组件触发规则

年报风格**极度克制**，仅使用以下组件：

| 触发内容 | 表达方式 | 说明 |
|---------|---------|------|
| 封面 | `<section role="cover">` | 绑定 @page cover，无家具 |
| 财务报表前后 | `<section data-orientation="landscape/portrait">` | 横向/纵向分节 |

**不使用** callout、divider、data-card 等装饰性组件——年报是监管文件，不适合花哨装饰。
