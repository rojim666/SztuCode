# action 与审阅卡决策

> 何时读取：已按 `entry.md` 选择写入模式并取得最新 content，需要决定 action、`card_op`、summary、pending 卡复用或 `update_title` 时读取。
>
> 本文只负责决策。字段与 Mark 契约见 `content_contract.md`；表格分派见 `tasks/table_edit.md`；CLI 与 schema 见 `edit_core.md`。

## 1. action 选择

按最小改动选择，命中即停止：

| 变化 | action |
|---|---|
| 同类型块内文字或行内样式 | `update` |
| 同一 parent 内移动 | `move` |
| 在锚点前后新增 | `insert_before` / `insert_after` |
| 删除整块 | `delete` |
| 块类型、children、块级属性或跨 parent 移动 | `delete` + `insert_before/insert_after` |
| Code 内容或 language、Mermaid 源码变化 | `delete` + `insert_before/insert_after` |
| 表格或 cell 内变化 | 转 `tasks/table_edit.md` |

约束：

- `update` 保留 block id，不能改变原 block 类型、children 或块级属性。
- 同一锚点连续新增多个块 → 合并到一条 insert action，顶层块间用空行分隔。
- `move` 仅用于同一 parent；跨 parent 使用删除后插入。
- 审阅 `content/new_content` 的 Mark 边界、评论锚点和 Code/Mermaid 例外以 `content_contract.md` 为准。
- 表格 action 不在本文重复定义，以 `tasks/table_edit.md` 为准。

## 2. 审阅卡 `card_op`

审阅 actions 至少包含一个 block action，并在末尾放正好一个 `card_op`：

| 场景 | `card_op` |
|---|---|
| 全新独立修改 | `{"type":"card_op","op":"insert","summary":"...","kind":"agent_review"}` |
| 整篇总评或跨章节全局修改 | `{"type":"card_op","op":"insert","summary":"...","kind":"agent_review_global"}` |
| 同一诉求继续补充或修正上一轮卡片 | `{"type":"card_op","op":"update","discussion_id":"<reviewDiscussionId>","summary":"累积总结"}` |

`card_op=delete` 只保留协议兼容，不作为“仅关闭卡片”流程；没有 block action 时不要调用提交接口。

### 2.1 review ID 与 comment ID

- `reviewDiscussionId`：上一轮 `submit_review_edit.py` 返回的审阅卡 ID，可用于 `card_op=update/delete`。
- `commentDiscussionId`：原评论线 ID，只用于读取评论和内部定位，不能用于 `card_op`。
- 同一诉求的继续、遗漏修正或用户要求调整上一轮修改 → 复用原审阅卡。
- 用户开始无关的新任务 → 新建卡。

### 2.2 pending 块复用

回读块带 `action="insert|delete|update" reviewId="..."`，说明它已挂 pending 审阅卡。本轮又修改该块时：

1. 对该块继续执行 `update` 或 `delete`。
2. 使用 `card_op=update(discussion_id=<该块 reviewId>)` 复用原卡。
3. 禁止新建另一张卡，也不要要求用户先接受或拒绝旧卡。

若多个目标块分属不同 pending 卡，只涉及一张卡时复用它；同时涉及多张卡时拆分提交。pending 块作为修改目标可用；作为无关新块的 `insert_after` 锚点应避免，优先选择不在原卡影响范围内的正常块或使用 `insert_before`。

## 3. summary

`summary` 是用户可见文本，只写“改了什么/为什么改”，长度 1–200 字，并与命令行 `--summary` 语义一致。

允许：

- `补充测试总结`
- `根据评论内容优化引言表述`
- `统一表格列宽说明`

禁止写入：

- 内部字段：`discussionId`、`reviewDiscussionId`、`commentDiscussionId`、`blockId`、`pageId`、`nodeId`、`reviewId`、`commentId`、`authorId`、`targetId`、`anchorBlockId`、`affectedBlockIds`、`updateArgs`、`cardOpArgs`、`pnid`、`selector`、`tag`、`createdAt`、`updatedAt`、`timestamp`，以及校验器覆盖的 snake_case 形式。
- JSON/数组结构、控制字符，以及 `blk_`、`discussion_`、`page_` 等内部 ID。

评论修订需要说明来源时，使用“根据选中评论”“根据评论内容”“根据文档评论”等自然语言，不带评论线 ID。

## 4. 直接编辑

直接编辑复用 §1 的 action 选择，但：

- 禁止 `card_op` 和 `summary`。
- `content/new_content` 是最终正文；具体字段与 Mark 禁止项见 `content_contract.md` §4。
- 表格继续转 `tasks/table_edit.md`。

## 5. `update_title`

`update_title` 只用于 `submit_doc_edit.py` 修改文档节点页面标题，不是修改正文 Heading：

```jsonc
{"type":"update_title","title":"新的文档标题"}
```

约束：无 `id/content`；必须位于 actions 末尾；一次至多一条；标题不超过 200 字符，允许空串。

读取文档后仅在以下情况主动询问是否同步标题：

1. frontmatter 标题缺失或为空。
2. 标题是 `未命名`、`Untitled`、`无标题`、`新建文档`、`新文档`。
3. 本次编辑使文档主题明显偏离原标题。

其他情况不主动询问。用户确认后才追加 `update_title`。

## 6. 决策完成条件

提交前确认：

- 目标 block id 已在最新 content 中验证。
- action 符合最小改动原则；表格已转专用任务。
- 审阅模式已正确选择新建或复用卡，summary 不含内部字段。
- 字段与内容已按 `content_contract.md` 构造；不确定时执行对应脚本 `--dry-run`。
