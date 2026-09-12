---
name: brief-compose
description: |
  短篇文档创作（目标篇幅 <1000 字）：从零撰稿 → 生成 HTML → html-to-docx 转 .docx → present_files 预览。
category: capability
tags: [brief-compose, short-form, html-to-docx, docx]
disable-user-invocation: true
---

# brief-compose Skill

**何时走**：无已有文档 + 创作动词（写/起草/撰写/生成/重写）+ 模型判断目标篇幅 <1000 字。

> **⛔ 工作流锁定**：一旦判定任务属于本 skill，**无视**其他 skill 与子 Agent，**严格按本文从头到尾执行**；无需再读其他skill。

---

## 篇幅判据

创作动词已命中、且非编辑意图时，满足任一即走本工作流：

- 用户给出 X 字且 X < 1000
- 「短篇 / 千字以内 / 简版」等表述
- 体裁为简介 / 通知 / 备忘录 / 工作小结等典型短篇

显式长篇（≥1000 字、万字、研报、论文等）→ 未命中本 skill，回到 `tdoc-orchestrator` SKILL.md 走常规编排。
---

## 原则

1. **强制流程（速览）**（完整命令见文末「强制流程」）：
   - ① 撰稿 + 生成 HTML
   - ② 调用 html-to-docx 转换
   - ③ `present_files`
2. **中间产物不展示**：`.html` 不得 `present_files`、不得在回复里贴 HTML 正文；只有最终 `.docx` 可展示。
3. **失败如实报错**：HTML 无 `<body>` → 终止并提示；用户明确要求新建空白文档时允许转换；其他创作请求若 body 无可渲染正文，必须重新生成 HTML。**禁止**静默降级到常规 full_pipeline 编排。
4. **最终交付**：`.docx` 生成后**必须立即** `present_files` 打开预览，无例外。
5. **输出路径**：工作流开始时调用 `resolve_output_docx_path.py`，将返回的 `output_docx_path` 用于 html-to-docx 与 `present_files`。

---

## 输出路径（`output_docx_path`）

```bash
python3 <plugin_root>/scripts/wb/local/resolve_output_docx_path.py \
  --workspace <workspace> \
  [--user-path "<路径>"] [--filename "<主题>.docx"]
```

**不传 `--request-id`**（brief-compose 不走 pipeline 隔离目录）。默认落盘 `<workspace>/output/<文件名>.docx`。

## HTML 生成

按用户创作指令撰写正文，输出**完整 HTML 文件**（`<!DOCTYPE html>`、`<head>` 含 `charset`、内嵌 `<style>` 均可，UTF-8、无 BOM）。篇幅控制在用户给出的 X 字以内。

**最低要求**：必须有 `<body>` 且含实际正文；用户明确要求新建空白文档时例外。其他创作请求若生成后 body 无可渲染正文，必须重新生成 HTML，禁止转换或交付空 docx。

**其余版式**（标题层级、段落样式、是否用表格分栏等）由模型自行决定，无固定骨架。

### 字体与字号建议

字号请用 **`pt`（磅）**，**不要用 `px`**。`html-to-docx` 按 pt 写入 Word；常见误用 `13px` 在 Word 里约 **9.5pt**，正文偏小。

| 层级 | 建议字号 | 建议字体 |
|------|----------|----------|
| 正文 `p` / `li` / `td` | **12pt**（默认） | 宋体 / SimSun |
| 一级标题 `h1` | 18–22pt | 黑体 / SimHei |
| 二级标题 `h2` | 14–16pt | 黑体 / SimHei |
| 三级标题 `h3` | 12–14pt | 黑体 / SimHei |
| 辅助说明、落款 | 10–10.5pt | 宋体 / SimSun |

- 用户未指定字号时，正文**默认 12pt**，不要小于 **10.5pt**。
- 因转换器**块级 CSS 不继承**（见下节），`font-size` / `font-family` 须写在各 `p`、`h1`、`h2`、`li`、`td` 等块级元素上，不要只写在 `body` 上。

```

---

## HTML → docx 转换约束（仅引擎硬限制）

以下规则来自 `html-to-docx` 转换器能力边界；**违反会导致 docx 排版错乱或信息丢失**，其余 HTML/CSS 写法不受限。

### 1. 禁止 Grid / 定义列表

- **禁** `display:grid` / `grid-template-*` → 多列对齐改用 `<table>`
- **禁** `<dl>/<dt>/<dd>` → 键值对改用两列 `<table>`

### 2. 块级 CSS 不继承

转换器**不做**块级样式继承。父元素上的 `text-align` / `font-family` / `color` / `font-size` **不会**下发到子 `<p>` / `<h1>` 等；需要生效的样式请写在各块级元素自身上。

### 3. `<hr>` 装饰线

`<hr>` 在 docx 中只能变成**满版下边框**，无法保留居中短线/定宽装饰线；不要用 `<hr>` 做标题区装饰分隔。

### 4. 左边框段落

带 `border-left` 的块，文字开头加 `&nbsp;&nbsp;`（Word 左边框无可靠间距）。

### 5. 多段落底纹块

整块底纹 + 多段落富文本 → 用裸单列 `<table><tr><td>…</td></tr></table>`，不要用多个 `<div>` 拼底纹。

### 6. 分节 / 页眉页脚（仅需要时）

- 需要分页结构：顶层 `<section role="...">`（无 section 则单节）
- 需要页码/页眉：`<style>` 内 `@page` 子集（`counter(page)` / `counter(pages)` / `string-set` + `STYLEREF`）
- **不支持** `@page :first`、`@page { size }` 等扩展语法（忽略 + warning）
- 需要封面时用户须明确要求；配合 `@page cover { … content: none }` + `section[role="cover"] { page: cover; }`

### 7. 可选扩展标签（用了才需遵守其契约）

| 标签 / 属性 | 说明 |
|-------------|------|
| `<div data-component="callout\|divider\|section-marker\|data-card">` | 装饰组件 |
| `<span data-docx-field="..." data-placeholder="...">` | 转 docx 书签；同 HTML 内唯一，匹配 `^[A-Za-z][A-Za-z0-9_-]{0,63}$` |
| `<meta name="docx-page-size" content="A4">` | 声明页面尺寸（默认 A4） |

---

## html-to-docx 转换

```bash
bash <plugin_root>/scripts/wb/local/setup-html-to-docx.sh
export HTML_TO_DOCX_PY="${HTML_TO_DOCX_VENV:-$HOME/.venv-html-to-docx}/bin/python"
cd <plugin_root>/skills/html-to-docx/scripts
"$HTML_TO_DOCX_PY" -m html_to_docx convert \
  "<html绝对路径>" \
  -o "<output_docx_path>" \
  --page-size A4
```

- `<plugin_root>` = 本 plugin 根目录（`tencent-docx/`）
- **禁止**使用系统 `python` / `python3`；依赖在托管 venv 内
- 成功 stdout：`{"success": true, "docx_path": "...", "warnings": []}`
- 失败 stderr：含 `error` 与可选 `markdown_fallback`

| CLI 参数 | 默认 | 说明 |
|----------|------|------|
| `--page-size` | `A4` | `A4` / `Letter` / `A3` |
| `--orientation` | `portrait` | `portrait` / `landscape` |
| `--margin-top/bottom/left/right` | 2.54 / 2.54 / 3.17 / 3.17 cm | 页边距 |

私有化 / 无外网环境、脚本首跑失败 → 见 `<plugin_root>/skills/html-to-docx/SKILL.md` 镜像配置；否则提示用户手动另存。

---

## 强制流程

```
① 确定 output_docx_path（调用 resolve_output_docx_path.py，§输出路径）并预建父目录
② 撰稿 + 生成 HTML
   · 按用户创作指令撰写正文，自行排版
   · 遵守上文「字体与字号建议」与「HTML → docx 转换约束」
   · 写入与 docx 同目录的 <主题>.html（中间产物）

③ HTML → DOCX
   · 按上文命令执行 html-to-docx，-o 指向 output_docx_path

④ 强制预览
   · 🔒 立即 present_files 打开 output_docx_path
```

```json
{ "files": ["<output_docx_path>"] }
```

未 `present_files` 即结束 = 工作流未完成。

---

## 异常处理

| 场景 | 处理 |
|------|------|
| HTML 无 `<body>` | 终止，提示用户 |
| 用户明确要求新建空白文档且 body 无可渲染正文 | 允许转换 |
| 其他创作请求且 body 无可渲染正文 | 重新生成 HTML，禁止交付空 docx |
| html-to-docx 失败 | 返回源 HTML 路径 + `markdown_fallback`（若有），提示手动另存 |
| 用户事后要改内容/样式 | 属**下一轮请求**，转 `tencent-docs-routing` |
| 用户事后要全文重新美化 | 未命中本 skill，回到 `tdoc-orchestrator` SKILL.md 走 `beautify_only` |
