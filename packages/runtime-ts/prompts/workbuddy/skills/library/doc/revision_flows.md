# 评论修订流程

> 何时读取：`tasks/revision.md` 已确认是评论驱动修订，需要处理评论类型、锚点或多评论合并时读取。划词修订的最短流程已在任务入口内，不在本文重复。

## 1. 评论读取

出现“根据评论修改”“处理评论”或用户提供原评论线 ID 时，先读取评论，再读取最新文档：

```text
1. 有 commentDiscussionId：get_node_comments.py --node-id <nodeId> --discussion-id <commentDiscussionId>
2. 无 commentDiscussionId：get_node_comments.py --node-id <nodeId>
3. 从 comments[].plainText 理解意图，从 thread.blockId 获取锚点。
4. 调 get_doc_reviews.py，验证 blockId 仍存在且内容符合预期。
5. 构造并提交审阅 actions。
```

不能跳过评论读取直接猜测意图。resolved 评论默认不处理，除非用户明确要求包含。

## 2. 评论返回字段

| 字段 | 用途 |
|---|---|
| `discussionId` | 原评论线 ID，即 `commentDiscussionId`；只用于读取评论和内部定位 |
| `blockId` | 评论锚点；提交前必须在最新 content 中验证 |
| `commentType` | `inline` 为划词评论，`block` 为整块评论 |
| `anchorText` | inline 评论的选中文字 |
| `props.pageAnchors[]` | 页面评论扩展锚点，可能含 `pnid`、`selector`、`tag`、`textContent` |
| `comments[].plainText` | 评论正文，修改意图的依据 |

`commentDiscussionId` 不能用作 `card_op.discussion_id`；审阅卡选择、summary 和 pending 复用统一按 `action_decision.md`。

## 3. action 分派

### inline 评论

- 普通文本 → 对完整目标块执行 `update`，精确修改 `anchorText` 对应范围。
- 删除选中文字 → 仅删除对应文本；除非用户明确要求，否则不删除整块。
- 原选区已有 comment Mark → 按 `content_contract.md` 保留评论 ID 并合并 Mark 属性。
- Code、Mermaid、表格目标 → 分别转 `tasks/complex_edit.md` 或 `tasks/table_edit.md`。

### block 评论

- 只改同类型块内文字或样式 → `update`。
- 删除整块 → `delete`。
- 在块前后新增 → `insert_before/insert_after`。
- 改变块类型、children、块级属性、Code 或 Mermaid → 转 `tasks/complex_edit.md`。
- 表格或 cell → 转 `tasks/table_edit.md`。

具体 `old_content/new_content` 与 Mark 边界以 `content_contract.md` 为准。

## 4. 多评论合并

- 多条评论指向同一 `blockId` → 合并为一条 `update`，同时落实各条意图。
- 多条评论指向不同 block → 默认一次 submit、同一张审阅卡；仅在用户明确要求分卡或诉求完全无关时拆分。
- summary 只说明业务修改意图，完整黑名单见 `action_decision.md` §3。
- 目标块已有 pending 卡 → 按 `action_decision.md` §2.2 复用原卡。

## 5. 成功与失败

正式提交成功后原样透传 `KS_USER_REPLY`。评论读取、文档读取或提交返回 JSON error/空 stdout 时停止后续动作，转 `error_handling.md`。
