# 排版合理性检测规则

**维度权重：20%**

## 检测目标

确保文档排版合理，段落长度适当，空白分布正常，视觉层次清晰。

## 检测项列表

### TQ-01：段落长度控制

单个 `<p>` 内文字不得超过 **500 个字符**。超过应拆分为多段。

**违规模式：**
- 单段落包含 600+ 字符的连续文字

**修正方向：** 按语义在合适位置断段，每段 150-300 字为宜。

---

### TQ-02：禁止过多连续空段落

连续出现 **3 个或以上**内容为空（或仅含空白符）的 `<p>` 标签为异常。

**违规模式：**
```html
<p>&nbsp;</p>
<p></p>
<p> </p>
```

**修正方向：** 删除多余空段，用 CSS `margin` 控制间距。

---

### TQ-03：标题后必须有正文

两个相邻标题之间（同级或降级）必须有至少一段正文内容。不允许 `h2` 紧接 `h3` 而中间无内容。

**违规模式：**
```html
<h2>第一章</h2>
<h3>第一节</h3>  <!-- 中间无任何内容 ❌ -->
```

**合规示例：**
```html
<h2>第一章</h2>
<p>本章概述...</p>
<h3>第一节</h3>
```

**例外：** `<h1>` 紧接 `<h2>` 允许（文档开头可以直接分章）。

---

### TQ-04：h1 最多出现 1 次

文档中 `<h1>` 不得超过 1 个（每个文档只有一个主标题）。

**违规模式：** 文档中出现 2 个及以上 `<h1>`

---

### TQ-05：h2 数量建议不超过 10 个

`<h2>` 超过 10 个时发出警告（不强制降分，但建议检查文档是否过于碎片化）。

严重程度：WARNING（不影响 passed 判定，但计入 issues）

---

### TQ-06：正文字号一致性

`<p>` 元素的 font-size 应统一使用 `var(--fs-body)`，不得在不同段落间使用不同的字号 token（特殊标注如摘要、小字注释除外）。

---

### TQ-07：表格标题（caption）位置

有 `<caption>` 的表格，`<caption>` 必须是 `<table>` 的第一个子元素，不得放在 `<tbody>` 后。

---

### TQ-08：封面块级元素必须显式声明 text-align

若文档存在 `.cover` 容器，其**直接后代**中的块级封面元素（`<h1>`、`class` 含 `subtitle` / `report-tag` / `report-title` / `cover-*` 的块级元素）必须在 `style` 属性内**显式包含 `text-align`** 声明。

**违规模式：**
```html
<style>
  p { text-align: justify; }  /* 常见默认 */
  .cover { text-align: center; }
</style>
<section class="cover">
  <h1 style="font-size: var(--fs-cover-title);">模拟人生 4</h1>  <!-- ❌ 未显式声明 text-align -->
  <div class="subtitle" style="color: var(--color-muted);">副标题</div>  <!-- ❌ -->
</section>
```

**为什么严重：** `text-align` 不从 `.cover` 继承到子块。当 CSS 里存在 `p { text-align: justify }`（正文两端对齐是常见默认），封面 `<h1>` / `.subtitle` 若未自己写对齐，转 docx 后会被 justify 兜底，出现 "模 拟 人 生 4"（字距被强行撑开）的严重视觉 bug。

**合规示例：**
```html
<h1 style="font-size: var(--fs-cover-title); text-align: center;">模拟人生 4</h1>
<div class="subtitle" style="color: var(--color-muted); text-align: center;">副标题</div>
```

**修正方向：** 在每个封面块级元素的 `style` 内补 `text-align: center`（或 left/right 视设计而定），不允许"靠父容器继承"。

---

## 评分标准

| 违规类型 | 扣分 |
|---------|------|
| TQ-01 超长段落（每处） | -10 |
| TQ-02 连续空段落 | -15 |
| TQ-03 相邻标题无正文（每处） | -10 |
| TQ-04 多个 h1 | -20 |
| TQ-05 h2 > 10（仅警告） | -0 |
| TQ-06 字号不一致 | -10 |
| TQ-07 caption 位置错误 | -5 |
| TQ-08 封面块级元素缺 text-align（每处） | -10 |

初始分 100，扣分后最低 0。综合分 < 75 则该维度 `passed = false`。

## 修正建议格式

```
[TQ-0X] {问题描述}，建议 {具体修正方式}
```

示例：
- `[TQ-01] 第 2 个 <p> 包含 650 字符，超出 500 字上限，请在第 3 句后断段`
- `[TQ-03] <h2 id="section-3"> 后直接出现 <h3>，中间无正文，请补充章节导语`
- `[TQ-08] 封面 <h1> 未显式声明 text-align，可能被 p{text-align:justify} 兜底导致字距撑开，请补 style="... text-align: center;"`
