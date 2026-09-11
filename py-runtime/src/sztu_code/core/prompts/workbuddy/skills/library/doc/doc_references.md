# content 组件参考

> 何时读取：编辑已有文档时遇到非基础组件，或不确定组件属性、子元素和展开格式。`create_doc.py` 只接受 Markdown，不使用本文组件语法。
>
> 本文只维护组件语法。action 选择见 `action_decision.md`；字段与 Mark 契约见 `content_contract.md`；表格任务分派和准入见 `tasks/table_edit.md`；CLI 与 stdout 见 `edit_core.md`。
>
> 按需跳读：容器 §3、Table §6、MathBlock §7、Code §8、Mermaid §9、Mark/Link §10、颜色白名单附录 B。

## 0. 总规则

### 0.1 场景速查

| 场景 | 写法 |
|---|---|
| `create_doc.py` 创建整篇文档 | 只支持 Markdown；禁止写 WorkBuddy 组件标签；组件语法仅用于编辑 / 修订链路 |
| `submit_doc_edit.py` insert / update | 必须用组件 |
| `submit_review_edit.py` insert / update | 必须用组件 |
| 提交写入 `content` / `new_content` | 禁止 frontmatter，禁止手写 `id` |
| 回读整页 content | 可能包含 frontmatter、只读 `id`、`ReviewSummary` |

编辑 / 修订 / 手写组件 content 中，行内样式必须使用 `<Mark>`；禁止用 Markdown 的 `**bold**` / `*italic*` / `~~strike~~` 等行内样式。

### 0.2 可出现组件清单

块级组件：

- `Paragraph`
- `Heading`
- `BlockQuote`
- `Callout`
- `Divider`
- `Image`
- `Todo`
- `BulletedList`
- `NumberedList`
- `MathBlock`
- `Code`
- `Mermaid`

表格组件：

- `Table`
- `TableRow`
- `TableCell`

行内组件：

- `Mark`
- `Link`

只读回显组件：

- `ReviewSummary`
- `ReviewCard`

未知组件禁止生成；`ReviewSummary` / `ReviewCard` 仅回读 content可出现，Agent 不得在提交写入时生成；无法表达时改用已支持组件或向用户说明限制。

### 0.3 属性与语法

- 禁止任意 `{...}` 表达式属性、content expression、ESM `import` / `export`；唯一可写例外是更新时原样保留已有 `Mark.comment={string[]}` 评论锚点。
- 属性值必须使用双引号，例如 `<Heading level="1">`。
- 布尔属性不写值，例如 `<Mark bold>文本</Mark>`、`<Todo checked>任务</Todo>`。
- 禁止写 `bold="true"` / `checked="true"`，也禁止显式写 `false`。
- 提交写入时禁止手写 `id`；`id` 只可能出现在回读 content内容中。
- 颜色属性只能使用附录中的 token，禁止 `#fff`、`rgb(...)` 等 CSS 颜色值。

只读例外：回读 content 中的 `ReviewCard.affectedBlockIds` 可能出现 `{[...]}` 形态，Agent 提交写入时不得生成。

### 0.4 换行与缩进

- 一级缩进固定为 4 个空格；禁止使用 Tab。
- 简单无嵌套文本块可用紧凑写法，例如 `<Paragraph>正文</Paragraph>`、`<Heading level="2">标题</Heading>`、`<Todo>任务</Todo>`、`<BulletedList>列表项</BulletedList>`。
- 复杂结构必须使用展开写法，包括容器块、表格、嵌套列表、一个块内存在多个子块等。
- 块级组件的直接内容行、嵌套子块都必须比开标签多缩进 4 个空格。
- 容器块内部相邻子块之间禁止空行，否则提交解析可能把后续子块识别为代码块字面量。
- `Mark` / `Link` 必须与周围文本处于同一行文本流中，禁止为了排版在句子中间插入换行。

### 0.5 审阅回读属性

块级组件在回读 content时可能带有审阅属性：

- `action`：`insert` / `delete` / `update`
- `reviewId`：关联审阅卡片 discussion id

`action` 与 `reviewId` 必须成对出现。Agent 构造 `content` / `new_content` 时通常不需要手填。

## 1. 页面级属性 Frontmatter

frontmatter 主要是回读整页 content 的形态。Agent 提交写入参数时：

- `submit_doc_edit.py` / `submit_review_edit.py` 的 `content` / `new_content` 禁止包含 frontmatter。
- `create_doc.py` 的标题以 `--title` 入参为准，正文 content 不写 frontmatter。

回读 content示例：

```yaml
---
title: React 学习路线
---
```

允许字段只有 `title`。

正文中允许使用一级标题作为章节标题，但不要在正文开头重复写一个与 frontmatter `title` 相同的一级标题。

## 2. 文本块组件

| 组件 | 用途 | 属性 | 子元素 | 示例 |
|---|---|---|---|---|
| `Paragraph` | 段落 | `textAlign`, `blockColor` | Text / `Mark` / `Link` | `<Paragraph>正文</Paragraph>` |
| `Heading` | 标题 | `level`, `textAlign`, `blockColor` | Text / `Mark` / `Link` | `<Heading level="1">标题</Heading>` |
| `Todo` | 待办项 | `checked`, `blockColor` | Text / `Mark` / `Link` / 子块 | `<Todo checked>完成项</Todo>` |
| `BulletedList` | 无序列表项 | `blockColor` | Text / `Mark` / `Link` / 子块 | `<BulletedList>列表项</BulletedList>` |
| `NumberedList` | 有序列表项 | `blockColor` | Text / `Mark` / `Link` / 子块 | `<NumberedList>第一项</NumberedList>` |

规则：

- `textAlign` 可选值：`left` / `center` / `right`。默认左对齐时不用显式设置。
- `blockColor` 可选值见附录 `BLOCK_COLORS`。
- `Heading.level` 必填，取值字符串 `"1"` 到 `"6"`。
- `Todo.checked` 是布尔属性，写 `<Todo checked>`，不要写 `checked="true"`。
- `Todo` / `BulletedList` / `NumberedList` 的第一个 child 是该项文本；子任务或子列表放在文本之后。
- 每个 `Todo` / `BulletedList` / `NumberedList` 代表一个列表项；连续同类组件组成视觉列表。
- `TableCell` 内的文字、`Mark`、`Link` 必须由 `Paragraph` 承载。

示例：

```xml
<Paragraph textAlign="right">
    <Mark bold>加粗</Mark>普通文本
</Paragraph>
<Heading level="2" blockColor="light_blue">
    小节标题
</Heading>
<Todo>
    任务 1
    <Todo checked>任务 1-1</Todo>
</Todo>
<BulletedList>
    无序列表
    <BulletedList>无序子列表</BulletedList>
</BulletedList>
<NumberedList>
    有序列表
    <NumberedList>有序子列表</NumberedList>
</NumberedList>
```

## 3. 容器块组件

| 组件 | 用途 | 属性 | 子元素 |
|---|---|---|---|
| `BlockQuote` | 引用块 | `textAlign`, `blockColor` | 块级组件 |
| `Callout` | 高亮块 | `icon` | 块级组件 |

规则：

- 容器内相邻子块之间禁止空行。
- `BlockQuote.textAlign` 可选值：`left` / `center` / `right`。
- `BlockQuote.blockColor` 可选值见附录 `BLOCK_COLORS`。
- `Callout` 只允许传 `icon`；禁止传 `blockColor` / `borderColor`。
- 简单引用在 `create_doc.py` 整篇 Markdown 中可用 `>`；编辑 / 修订提交必须用 `<BlockQuote>`。

示例：

```xml
<BlockQuote>
    <Paragraph>引用内容</Paragraph>
</BlockQuote>
<Callout>
    <Heading level="3">提示标题</Heading>
    <Paragraph>提示内容。</Paragraph>
</Callout>
```

## 4. Divider

```xml
<Divider />
```

规则：

- 使用自闭合标签。
- 编辑 / 修订提交必须使用 `<Divider />`。
- `create_doc.py` Markdown 正文可使用 Markdown 的 `---` 表达分割线。

## 5. Image

```xml
<Image src="https://example.com/image.png" alt="示例图片" align="right" />
```

属性：

| 属性 | 要求 | 说明 |
|---|---|---|
| `src` | 必填 | 图片地址字符串 |
| `alt` | 推荐 | 图片说明 |
| `align` | 可选 | `left` / `center` / `right`，默认 `center` |
| `width` | 可选 | 数字字面量字符串，单位 px |
| `height` | 可选 | 数字字面量字符串，单位 px |

规则：

- 编辑 / 修订提交必须使用 `<Image ... />`，不使用 Markdown 图片语法。
- `create_doc.py` Markdown 正文可使用 `![alt](url)`。
- `src` 仅允许 `http://` / `https://`。
- 禁止 `javascript:` / `data:` / `vbscript:` 等可执行或内嵌协议。
- Agent 不主动探测内网 URL；如需访问或校验图片地址，必须遵守 SSRF 防护，拒绝内网、私有网段、特殊地址及 `9.*` / `10.*` / `11.*` / `21.*` / `30.*`。

## 6. Table

```xml
<Table>
    <TableRow>
        <TableCell>
            <Paragraph>cell A1</Paragraph>
        </TableCell>
        <TableCell>
            <Paragraph>cell A2</Paragraph>
        </TableCell>
    </TableRow>
</Table>
```

结构：

- `Table` 子元素只能是 `TableRow`。
- `TableRow` 子元素只能是 `TableCell`。
- `TableCell` 子元素是除 `Table` 外的块级组件。
- `TableRow` / `TableCell` 禁止单独作为顶层内容生成。

规则：

- 本节只适用于 `submit_doc_edit.py` / `submit_review_edit.py` 的组件化 `content/new_content`；`create_doc.py` 禁止使用 `<Table>` 组件。
- 在编辑 / 修订链路的 `content/new_content` 中，表格必须使用组件表达，禁止使用 Markdown 表格语法。
- `create_doc.py` 创建整篇文档只支持 Markdown，普通表格使用 Markdown / GFM 表格；不要改写成 `<Table>...</Table>`。
- `Table` / `TableRow` / `TableCell` 不接受 `readonly` / `id` 属性；`id` 只来自回读 content。
- `TableCell` 内的文字、`Mark`、`Link` 必须包在 `<Paragraph>` 内，禁止直接写 `<TableCell>cell A1</TableCell>`。
- 表格 action 分派和一次性生成边界统一见 `tasks/table_edit.md`。

### 6.1 表格 action 与 helper

表格目标类型、cell 内容修改和结构变更的 action 准入统一以 `tasks/table_edit.md` 为准。

### 6.2 表格结构变更：用 `table_edit_helper.py` 生成新 `<Table>` 组件语法

`table_edit_helper.py` 是不发网络、无需 token 的本地组件生成器，仅支持行列矩阵结构变换。cell 富文本、合并单元格、列宽和表头属性不在其保真范围；是否应使用 helper 先按 `tasks/table_edit.md` 判断。

**支持的算子（--op）**：

| op | 关键参数 | 语义 | 何时用 |
|---|---|---|---|
| `insert_row` | `after_row_index` 或 `before_row_index`（缺省=表尾）；`cells: string[]`（长度必须 = 现表列数） | 插入一行 | 加行 |
| `delete_row` | `row_index` | 删除一行（不能删到只剩 0 行） | 删行 |
| `insert_column` | `after_col_index` 或 `before_col_index`（缺省=表尾）；`cells: string[]`（长度必须 = 现表行数） | 插入一列 | 加列 |
| `delete_column` | `col_index` | 删除一列（不能删到只剩 0 列） | 删列 |
| `set_table` | `cells: string[][]` | 二维数组重建表格矩阵 | 二维结构重排 / 换列数 |

**调用**：

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/doc/table_edit_helper.py" \
    --op insert_row \
    --table-content '<Table>...</Table>' \
    --args '{"after_row_index":1,"cells":["新A","新B","新C"]}'
```

大表可用 `--table-content-file` / `--args-file` 从文件读入。自检：`python3 table_edit_helper.py --self-check`，成功打印 `KS_TABLE_EDIT_HELPER_SELFCHECK_OK`。

**stdout 协议**：

```text
KS_TABLE_EDIT_HELPER_SUCCESS
{"new_table_content": "<Table>...</Table>"}
```

失败：

```text
KS_TABLE_EDIT_HELPER_ERROR
{"code": "<ERR_CODE>", "message": "<脱敏原因>"}
```

常见错误码：`COL_LENGTH_MISMATCH`（新行/列长度与现表不符）、`ROW_INDEX_OUT_OF_RANGE` / `COL_INDEX_OUT_OF_RANGE`（越界）、`UNSUPPORTED_SPAN`（含 rowspan/colspan 合并，规范未定义，脚本拒绝）、`UNSUPPORTED_INLINE_CONTENT`（检测到 Mark/Link 等富文本，脚本拒绝避免丢失样式/链接）、`INVALID_TABLE_CONTENT`（未成对 `<Table>`）、`ROW_LIMIT_EXCEEDED` / `COL_LIMIT_EXCEEDED`（>200 行 / >20 列，防止 LLM 误传爆炸数据）。

`new_table_content` 只返回完整组件文本；后续 action 与提交方式按 `tasks/table_edit.md`、`action_decision.md` 和 `content_contract.md` 处理。

## 7. MathBlock

```xml
<MathBlock>
    $$
    i\hbar\frac{\partial}{\partial t}\Psi(\vec{r},t) = \left[-\frac{\hbar^2}{2m}\nabla^2 + V(\vec{r},t)\right]\Psi(\vec{r},t)
    $$
</MathBlock>
```

属性：

- `width`：可选，数字字面量字符串，单位 px。

规则：

- 编辑 / 修订场景必须使用 `<MathBlock>`。
- `create_doc.py` Markdown 正文可使用 `$math$` / `$$math$$`。
- 子元素只允许一个 markdown math 内容。

## 8. Code

````xml
<Code language="go">
package main
func main() {}
</Code>
````

属性：

- `language`：必填，代码语言标签字符串，例如 `"go"` / `"python"` / `"typescript"` / `"bash"`。

规则：

- 代码块内容按纯文本处理，不写 `Paragraph` / `Mark` / `Link`。
- 换行按原样保留。
- 编辑 / 修订中，新建、插入、替换代码块均使用 `<Code language="...">`。
- 编辑 / 修订中，代码块内容或语言变更禁止 `update`，必须 `delete + insert_before` / `insert_after`。
- `create_doc.py` Markdown 正文可使用 fenced code。

## 9. Mermaid

```xml
<Mermaid>
flowchart TD
    Start([开始]) --> Input[/输入数据/]
    Input --> Validate{数据有效?}
    Validate -->|是| Process[处理数据]
    Validate -->|否| Error[显示错误]
    Process --> Save[(保存到数据库)]
</Mermaid>
```

属性：

- 无（组件本身无自定义属性；回读 content时可能带 `action` / `reviewId` 审阅属性）。

规则：

- `Mermaid` 是叶子块，无嵌套子块；子元素是唯一一段 Mermaid 官方语法源码（纯文本，保留原始换行）。
- 源码仅允许 Mermaid 官方语法子集（`flowchart` / `sequenceDiagram` / `gantt` / `classDiagram` / `stateDiagram` 等）；禁止在源码里混入 Markdown 或其它组件标签，禁止嵌套 `<Mermaid>`。
- `submit_review_edit` / `submit_doc_edit` 修改 Mermaid 块时禁止 `update.new_content=<Mermaid>...</Mermaid>`；必须 `delete(id=原 Mermaid 块)` + `insert_before/insert_after(id=原 Mermaid 块, content=<Mermaid>...改写后完整源码...</Mermaid>)`。
- 编辑 / 修订链路的 `<Mermaid>` 内只能写 Mermaid 原始源码，**禁止再包 Markdown fenced code**；错误：在 `<Mermaid>` 内写 `mermaid` fence 包裹源码；正确：`<Mermaid>\nsequenceDiagram\n...\n</Mermaid>`。
- 用户要求"改 mermaid 图里某个节点"时，Agent 应改写完整 Mermaid 源码后用 `delete + insert_before/insert_after` 替换整块；禁止在 Mermaid 内使用 `<Mark ar="insert|delete|format">` 做 token 级审阅（图表源码是原子单位，token 级标记会污染源码并导致渲染失败）。
- 编辑 / 修订中，新建、插入、替换 Mermaid 块均使用 `<Mermaid>`；`submit_doc_edit.py` / `submit_review_edit.py` 的 `insert_before` / `insert_after.content` 也必须走 `<Mermaid>` 组件承载图表，且 content 禁止 `<Mark ar>` / Markdown fence。
- `create_doc.py` 创建 Mermaid 时优先使用 Markdown fenced code：```` ```mermaid ... ``` ````（与 fenced code block / `$$math$$` 同规则）；这是 Markdown 已支持语法，不要为了创建图表改写成 `<Mermaid>...</Mermaid>`。`<Mermaid>` 仅用于编辑 / 修订链路；create_doc 禁止使用 `<Mermaid>` 组件。

## 10. 行内组件

### 10.1 Mark

用途：带样式文本。

属性：

| 属性 | 类型 / 取值 |
|---|---|
| `bold` | 布尔属性，不写值 |
| `italic` | 布尔属性，不写值 |
| `underline` | 布尔属性，不写值 |
| `strike` | 布尔属性，不写值 |
| `color` | `TEXT_COLORS` |
| `backgroundColor` | `BLOCK_COLORS` |
| `ar` | `insert` / `delete` / `format`，仅 `submit_review_edit` 使用 |
| `comment` | 表达式属性 `comment={["id1","id2"]}`，划词评论 ID 列表；Agent 修改时应原样保留 |

示例：

```xml
<Paragraph><Mark bold>重点内容</Mark><Mark color="yellow">警告</Mark></Paragraph>
<Paragraph><Mark ar="delete">旧文字</Mark><Mark ar="insert">新文字</Mark></Paragraph>
<Paragraph><Mark ar="format" bold>仅样式变化的文字</Mark></Paragraph>
```

规则：

- `Mark` 必须单行书写，开始标签、内容、结束标签在同一行。
- `ar` 三选一互斥，非法值禁止生成。
- `ar="format"` 表达格式变化；样式属性表示最终样式，无样式属性表示清除已有行内格式。
- `ar="insert"` / `ar="delete"` 描述文字本身的增删，是否同时配样式属性都合法。
- 替换写法是旧文字标 `ar="delete"` + 新文字标 `ar="insert"` 两个独立 `Mark` 串联。
- `ar` 在审阅和直接编辑中的使用边界见 `content_contract.md`。

#### 10.1.1 编辑模式边界

`Mark ar` 的 update/insert 边界、评论锚点、嵌套限制和直接编辑禁止项统一以 `content_contract.md` 为准。本节只定义 Mark 组件的属性和语法。

### 10.2 Link

```xml
<Link href="https://example.com">文本</Link>
```

规则：

- `href` 必填。
- `Link` 必须单行书写，开始标签、内容、结束标签在同一行。
- 禁止 `javascript:` / `data:` / `vbscript:` 等可执行或内嵌协议。
- Agent 不主动探测内网 URL；如需访问或校验链接，必须遵守 SSRF 防护，拒绝内网、私有网段、特殊地址及 `9.*` / `10.*` / `11.*` / `21.*` / `30.*`。

## 附录 A：只读回显组件

以下组件只可能出现在回读整页 content 中，Agent 提交写入时不得生成：

- `ReviewSummary`
- `ReviewCard`

`ReviewSummary` 紧随 frontmatter 之后出现；没有 agent_review 卡片时省略。

示例：

```xml
<ReviewSummary>
    <ReviewCard
        discussionId="abcd1234567890abcdef12"
        anchorBlockId="b_xxx"
        affectedBlockIds={["b_xxx", "b_yyy"]}
        summary="把第一段语气改得更专业"
        status="pending"
    />
</ReviewSummary>
```

`ReviewCard.status` 常见值：

- `pending`：等待作者审阅
- `resolved`：已被作者接受 / 拒绝，卡片关闭

## 附录 B：颜色 token

`BLOCK_COLORS` 用于 `blockColor` 和 `Mark.backgroundColor`：

`default`, `grey`, `light_grey`, `dark`, `light_blue`, `blue`, `light_sky_blue`, `sky_blue`, `light_green`, `green`, `light_yellow`, `yellow`, `light_orange`, `orange`, `light_red`, `red`, `light_rose_red`, `rose_red`, `light_purple`, `purple`

`TEXT_COLORS` 用于 `Mark.color`：

`default`, `grey`, `blue`, `sky_blue`, `green`, `yellow`, `orange`, `red`, `rose_red`, `purple`

`BORDER_COLORS` 仅作为历史 / 只读说明保留；Agent 不生成 `Callout.borderColor`。
