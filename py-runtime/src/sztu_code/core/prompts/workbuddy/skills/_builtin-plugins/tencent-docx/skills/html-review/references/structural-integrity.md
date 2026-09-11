# 结构完整性检测规则

**维度权重：25%**

## 检测目标

确保 HTML 文档结构合法，元素嵌套正确，必需元素完整存在。

## 检测项列表

### SI-01：标题层级连续性

标题层级必须连续递进，不得跳级。

**违规模式：**
- `<h1>` 后直接出现 `<h3>`（跳过 h2）
- `<h2>` 后直接出现 `<h4>`（跳过 h3）
- 正文中出现 `<h6>`（层级过深，通常为误用）

**合规示例：**
```
h1 → h2 → h3 → h4  ✅
h1 → h2 → h2 → h3  ✅（同级出现多次无问题）
h1 → h3            ❌（跳级）
```

---

### SI-02：表格结构完整性

所有 `<table>` 必须包含 `<thead>` 和 `<tbody>`。

**违规模式：**
- `<table>` 内直接放 `<tr>`，无 `<thead>/<tbody>` 包裹
- `<thead>` 内使用 `<td>` 而非 `<th>`

**合规示例：**
```html
<table>
  <thead><tr><th>列1</th><th>列2</th></tr></thead>
  <tbody><tr><td>值1</td><td>值2</td></tr></tbody>
</table>
```

---

### SI-03：列表结构完整性

`<ol>` 和 `<ul>` 内只能直接包含 `<li>`，不得直接包含 `<p>` 或其他块级元素。

**违规模式：**
```html
<ul>
  <p>这不是列表项</p>  ❌
</ul>
```

**合规示例：**
```html
<ul>
  <li>这是列表项</li>
</ul>
```

---

### SI-04：禁止非法块级嵌套

`<p>` 内不得嵌套块级元素（`<div>`、`<table>`、`<ul>`、`<ol>`、`<h1>`-`<h6>` 等）。

**违规模式：**
```html
<p>
  文本
  <div>这是非法嵌套</div>  ❌
</p>
```

---

### SI-05：图片必须有 alt 属性

所有 `<img>` 必须包含非空的 `alt` 属性。

**违规模式：**
- `<img src="...">` （缺少 alt）
- `<img src="..." alt="">` （alt 为空）

**合规示例：**
- `<img src="..." alt="图表：2024年营收趋势">`

---

### SI-06：链接 href 不得为空

`<a>` 标签的 `href` 属性不得为 `#` 占位（锚点链接除外）或空字符串。

**例外：** `href="#section-N"` 等文档内锚点链接允许。

---

### SI-07：禁止不可还原的 inline badge

`<span>` 元素上的 `background` + `padding` / `border-radius` / `display:inline-block` 组合在 docx 中完全不可还原（`<span>` 不对应独立段/行/单元格，无载体承载底纹）。

**违规模式（满足任一组合即触发）：**
- `<span>` 同时含 `background`（非 transparent/none）+ `padding`
- `<span>` 含 `background` + `border-radius`
- `<span>` 含 `background` + `display: inline-block`

**替代方案：**
- 纯文字标签 → 改为 `<p class="cover-category">` + 可还原属性（color/font-size/font-weight/letter-spacing）
- 需要底纹效果 → 改为单行 `<table>` 单元格（`<td>` 的 background 在 docx 中可还原为单元格底纹）

**合规示例：**
```html
<!-- 方案 A：纯字体属性 -->
<p class="cover-category" style="color:var(--color-primary);font-weight:700;font-size:14pt">行业深度研究</p>

<!-- 方案 B：table 单元格承载底纹 -->
<table class="cover-category-badge"><tr>
  <td style="background:var(--color-primary);color:#fff;font-weight:700;padding:4px 12px">行业深度研究</td>
</tr></table>
```

---

### SI-08：禁止 table-in-table 嵌套

`<table>` 的子树内不得再出现 `<table>`。html-to-docx 转换器（`html4docx` + `python-docx`）的表格样式后处理依赖 `document.tables`，**该 API 只返回顶层表格**，嵌套在单元格里的内层表格无法被应用边框、单元格对齐、底纹等样式，导致渲染严重偏差。此外 `abstract-card` 类单列表格（见 `doc-typeset/SKILL.md §(d)`）按规则只承载**多段落 `<p>` 富文本**，不得塞入子表格。

**违规模式：**
```html
<table class="abstract-card">
  <tr><td>
    <p>核心指标速览</p>
    <table class="three-line-table">   <!-- ❌ table-in-table -->
      <thead>...</thead><tbody>...</tbody>
    </table>
  </td></tr>
</table>
```

**合规示例（内层表格移出作为顶层独立表格）：**
```html
<h3>核心指标速览</h3>
<table class="three-line-table">
  <thead>...</thead><tbody>...</tbody>
</table>
```

> 若确需卡片视觉容器，`abstract-card` 内只放 `<p>` 段落；指标矩阵本身必须作为顶层独立 `<table>`。

---

## 评分标准

| 违规严重程度 | 扣分 |
|------------|------|
| SI-01 跳级（每处） | -15 |
| SI-02 表格缺结构 | -20 |
| SI-03 列表非法子元素 | -10 |
| SI-04 非法块嵌套 | -15 |
| SI-05 缺 alt（每处） | -5 |
| SI-06 空链接（每处） | -5 |
| SI-07 不可还原 badge（每处） | -20 |
| SI-08 table-in-table 嵌套（每处） | -20 |

初始分 100，扣分后最低 0。综合分 < 75 则该维度 `passed = false`。

## 修正建议格式

```
[SI-0X] {问题描述}，建议 {具体修正方式}
```

示例：
- `[SI-01] <h1> 后直接出现 <h3>，标题层级跳级，请在中间补充 <h2> 层级章节`
- `[SI-02] 第 3 个 <table> 缺少 <thead>，请将第一行 <tr> 移入 <thead> 并将 <td> 改为 <th>`
