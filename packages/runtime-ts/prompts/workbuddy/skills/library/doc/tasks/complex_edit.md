# 复杂组件与结构编辑

> 适用：已有文档中的非基础组件，或修改块类型、children、块级属性、Code 内容/语言、Mermaid 源码。表格走 `table_edit.md`。

## 1. 最短流程

1. 按 `../entry.md` 判定写入模式并执行 `../../mutation.md`。
2. 调 `get_doc_reviews.py` 获取最新 content 和目标 `blockId`。
3. 读取 `../doc_references.md` 中目标组件章节，核对组件名、属性、子元素和展开格式。
4. 按下列边界选择 action。
5. 使用对应 submit 脚本 `--dry-run`；通过后正式提交并透传 `KS_USER_REPLY`。

## 2. action 边界

| 变化 | action |
|---|---|
| 同类型块内文字或行内样式变化 | 返回 `text_block_edit.md`，优先 `update` |
| 块类型、children 或块级属性变化 | `delete` + `insert_before/insert_after` |
| Code 内容或 language 变化 | `delete` + `insert_before/insert_after`，插入完整 `<Code language="...">...</Code>` |
| Mermaid 源码变化 | `delete` + `insert_before/insert_after`，插入完整 `<Mermaid>...</Mermaid>` |
| 表格或 cell 内变化 | 转 `table_edit.md` |

- `update` 不能改变原 block 类型、children 或块级属性。
- `<Mermaid>` 内只写 Mermaid 原始源码，不包 Markdown fenced code，也不做 token 级 `<Mark ar>`。
- 审阅与直接编辑的内容字段和 Mark 边界按 `../content_contract.md`。
- 不手写回读专用的 `id`、`readonly`、`ReviewSummary`、`ReviewCard`、`action` 或 `reviewId`。
- 容器块内部相邻子块之间不要留空行；顶层连续块之间用空行分隔。

## 3. 按条件深读

| 条件 | 读取 |
|---|---|
| 组件语法与属性 | `../doc_references.md` 对应章节 |
| action 选择、card_op 或 pending 卡 | `../action_decision.md` |
| content/new_content、Mark、评论锚点 | `../content_contract.md` |
| 容器解析退化或正式提交差异 | `../server_pitfalls.md` |
| CLI、schema、dry-run 或 stdout | `../edit_core.md` |
| 脚本失败 | `../error_handling.md` |
