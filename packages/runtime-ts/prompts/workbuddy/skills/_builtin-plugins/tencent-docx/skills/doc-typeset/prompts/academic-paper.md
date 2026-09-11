# doc-typeset / academic-paper prompt

继承 `base.md` 的全部规则，并应用以下学术论文专属排版规范（参照 GB/T 7713）。

## IMRaD 结构映射

| 章节 | HTML id | aria-label |
|------|---------|------------|
| 引言 / Introduction | `section-introduction` | 引言 |
| 方法 / Methods | `section-methods` | 研究方法 |
| 结果 / Results | `section-results` | 研究结果 |
| 讨论 / Discussion | `section-discussion` | 讨论 |
| 结论 / Conclusion | `section-conclusion` | 结论 |

每个 IMRaD 章节使用 `<div id="section-{name}">` 包裹。`<section>` 仅用于封面与正文等真实页面边界，不能用于正文内部章节。

## 章节编号格式

| 层级 | 格式 | 示例 |
|------|------|------|
| h2 | 一、二、三… | `<h2 id="section-introduction">一、引言</h2>` |
| h3 | （一）（二）… | `<h3>（一）基本原理与相平衡</h3>` |
| h4 | 1. 2. 3. | `<h4>1. 溶剂选择策略</h4>` |

摘要、参考文献、致谢、附录**不编号**；正文主体章节的序号跳过它们后继续连续。

目录条目文本与正文标题逐字一致，含序号在内。

## 摘要与关键词

```html
<div class="abstract" aria-label="摘要">
  <p class="abstract-heading">摘要</p>
  <p class="abstract-text">{{abstract_content}}</p>
  <p class="keywords"><strong>关键词：</strong>{{keyword1}}；{{keyword2}}；{{keyword3}}</p>
</div>
```

## 三线表规则

学术表格使用三线表（`.three-line-table`），**仅保留三条横线，禁止竖线**：

```css
.three-line-table { border-collapse: collapse; width: 100%; }
.three-line-table caption { font-size: var(--fs-small); margin-bottom: var(--spacing-paragraph); }
.three-line-table thead tr:first-child { border-top: 2px solid var(--color-text); }
.three-line-table thead tr:last-child { border-bottom: 1px solid var(--color-text); }
.three-line-table tbody tr:last-child { border-bottom: 2px solid var(--color-text); }
.three-line-table td, .three-line-table th {
  border-left: none; border-right: none;
  padding: 0.4em 0.8em; text-align: left;
}
```

## 脚注格式

行内引用标记：
```html
<sup class="footnote-ref"><a href="#fn-1" id="fnref-1">1</a></sup>
```

脚注区（文末）：
```html
<div class="footnotes">
  <ol>
    <li id="fn-1">脚注内容 <a href="#fnref-1" class="footnote-back">↩</a></li>
  </ol>
</div>
```

## 参考文献格式

```html
<div class="references" aria-label="参考文献">
  <h2>参考文献</h2>
  <ol class="reference-list">
    <li class="reference-item">
      作者. 题名<span class="ref-type">[J]</span>. 刊名, 年份, 卷(期): 页码. DOI.
    </li>
  </ol>
</div>
```

文献类型标记：`[J]` 期刊、`[M]` 专著、`[C]` 会议论文、`[D]` 学位论文、`[R]` 报告。

## 装饰组件触发规则

| 触发位置 | 组件 | style |
|---------|------|-------|
| 摘要前后 | divider | simple |
| IMRaD 各章节之间 | divider | section-break |
