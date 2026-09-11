# 划词与评论修订

> 适用：基于选中文字、指定评论或全文评论修改文档。此任务优先于表格和复杂组件路由。

## 1. 术语边界

- 页面 ID 口径按 `../entry.md`。
- `commentDiscussionId` 是原评论线 ID，只用于读取评论和内部定位。
- `reviewDiscussionId` 是审阅卡 ID，才能用于 `card_op=update/delete`。
- 原评论线 ID 不能当作审阅卡 ID；summary 按 `../action_decision.md` §3 构造。

## 2. 划词修订

输入应包含 `nodeId/pageId + blockId + 修订意图`：

1. 调 `get_doc_reviews.py` 获取最新 content。
2. 验证 `blockId` 存在，并读取完整目标块。
3. 不调用评论读取脚本。
4. 普通文本局部修改优先 `update`：携带完整 `old_content/new_content`，只在变化部分使用 `<Mark ar>`。
5. 提交前检查 pending 卡，随后调用 `submit_review_edit.py`。

## 3. 评论修订

1. 有指定原评论线 ID → 用 `get_node_comments.py --node-id <nodeId> --discussion-id <commentDiscussionId>`；否则拉取全部活跃评论。
2. 从评论正文理解意图，从 `thread.blockId` 取锚点。
3. 调 `get_doc_reviews.py` 验证该 block 在最新 content 中仍存在。
4. 按 `../action_decision.md` 构造审阅 actions 与 summary。
5. 调 `submit_review_edit.py`，成功后透传 `KS_USER_REPLY`。

不能跳过评论读取直接猜测评论意图。resolved 评论默认不处理，除非用户明确要求。

## 4. 审阅 action

- 提交前检查目标块的 pending 状态；新建/复用卡和 summary 统一按 `../action_decision.md`。
- `content/old_content/new_content`、Mark 与评论锚点统一按 `../content_contract.md`。
- 命中表格、Code、Mermaid 或复杂组件时转对应任务文件。

## 5. 按条件深读

| 条件 | 读取 |
|---|---|
| 评论类型、全文评论、锚点或多评论合并 | `../revision_flows.md` |
| card_op、pending 卡、action 或 summary | `../action_decision.md` |
| 评论 Mark 合并、锚点保留或字段契约 | `../content_contract.md` |
| 命中表格或 cell | `table_edit.md` |
| 命中 Code、Mermaid 或复杂组件 | `complex_edit.md` |
| 脚本失败或卡片不可见 | `../error_handling.md` |
