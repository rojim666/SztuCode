# content 字段与 Mark 契约

> 何时读取：构造 `submit_review_edit.py` / `submit_doc_edit.py` actions，需要确认 `old_content`、`content`、`new_content`、Mark 或评论锚点时读取。
>
> 本文是内容字段与 Mark 的权威源。action 与 card 决策见 `action_decision.md`；表格分派见 `tasks/table_edit.md`；组件语法见 `doc_references.md`；本地校验实现在 `content_validator.py`。

## 1. 通用字段边界

- `insert_before` / `insert_after`：新块写入 `content`；可包含多个连续顶层块，块间用空行分隔。
- `update`：必须同时携带修改前完整块 `old_content` 与修改后完整块 `new_content`；`content` 必须为空。
- `old_content` 只用于本地 before/after 防丢校验，不会随 actions 提交。
- `new_content` 必须是正好一个与原块同类型的完整组件块；不能是裸文字、Markdown、多块或不同块类型。
- `delete`、`move`、`card_op`、`update_title` 不填写 `content`。
- 编辑与修订链路的 `content/new_content` 使用组件语法；`create_doc.py` 创建整篇文档只使用 Markdown。
- 禁止写入 frontmatter、手写 `id`、`ReviewSummary`、`ReviewCard`、`action` 或 `reviewId`。

## 2. 审阅模式 Mark 边界

- `update.new_content` 必须至少包含一个合法 `<Mark ar="insert|delete|format">`；未变化文字可保持裸写。
- `insert_before/insert_after.content` 禁止 `<Mark ar>`；insert action 已表达块级新增，content 直接写最终新增内容。
- `ar="insert"` 表示新增文字；`ar="delete"` 表示删除文字；替换使用 delete 与 insert 两个相邻 Mark。
- `ar="format"` 用于文字不变的格式变化；按最终样式携带属性，不携带样式属性表示移除已有行内格式。
- 禁止嵌套 `<Mark>`。

示例：

```xml
<Paragraph>保留文字<Mark ar="delete">旧文字</Mark><Mark ar="insert">新文字</Mark></Paragraph>
```

## 3. 评论锚点

原块包含 `<Mark comment={...}>` 时：

- 唯一合法格式是 `comment={["discussion_xxx"]}`：非空 JSON 字符串数组；禁止函数、变量或其他表达式属性。
- insert 禁止创建评论锚点；update 只能保留 `old_content` 已有的 comment ID，禁止凭空新增。
- `new_content` 必须保留全部原 comment ID，并尽量保持原锚点文本范围。
- 同一文字同时有评论、审阅或样式属性 → 合并到一个 Mark，例如：

```xml
<Paragraph>前文<Mark comment={["disc_xxx"]} ar="format" bold>被评论文字</Mark>后文</Paragraph>
```

只有用户明确要求删除对应被评论文本时，才可同时设置 `allow_drop_comment=true` 与非空 `drop_comment_reason`。脚本能阻止 ID 丢失，但不能证明锚点未漂移，因此仍应基于 `old_content` 做最小修改。

## 4. 直接编辑模式

`submit_doc_edit.py` 的 `content/new_content` 是最终正文：

- 禁止 `<Mark ar>`、`card_op`、`summary`、`ReviewSummary` 和 `ReviewCard`。
- `update` 仍必须携带完整 `old_content/new_content`，且不能改变原 block 类型、children 或块级属性。
- 块类型或结构变化使用 `delete + insert_before/insert_after`。

## 5. 原子块与复杂组件

- Code 内容或 language 变化、Mermaid 源码变化禁止 `update`，使用 `delete + insert_before/insert_after`。
- `<Mermaid>` 内只写原始 Mermaid 源码，不包 Markdown fenced code，不插入 Mark。
- 非基础组件的合法属性、子元素和展开格式以 `doc_references.md` 为准。
- 表格目标类型与结构/内容分派以 `tasks/table_edit.md` 为准，不在本文重复定义。
