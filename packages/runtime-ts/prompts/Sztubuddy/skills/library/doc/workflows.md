# 工作流示例（library doc）

> 何时读取：规则已确定，只需要可复制命令、actions 模板或示例索引。
>
> 本文不是规则来源；示例真身在 `scripts/examples/*.json`，由 `verify_examples.py` 做 dry-run 自检。action、字段、组件和表格规则分别以 `action_decision.md`、`content_contract.md`、`doc_references.md`、`tasks/table_edit.md` 为准。

## 1. 示例文件索引

| 场景 | 示例文件 |
|---|---|
| 整块改写 | `scripts/examples/example_C_rewrite_block.json` |
| 块内部分文字替换 | `scripts/examples/example_C2_partial_replace.json` |
| 改变块类型 | `scripts/examples/example_D_change_block_type.json` |
| 修改标题块文字 | `scripts/examples/example_E_edit_heading.json` |
| 复用上一轮审阅卡 | `scripts/examples/example_F_reuse_card.json` |
| 全局总评卡 | `scripts/examples/example_G_global_review.json` |
| 划词修订 | `scripts/examples/example_word_selection.json` |
| 评论修订 | `scripts/examples/example_comment_revision.json` |

自检：

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/doc/scripts/examples/verify_examples.py"
```

成功输出 `KS_EXAMPLES_SELFCHECK_OK`。

## 2. 通用命令模板

客户端模式命令包含 `--token-stdin`；沙箱模式使用同一业务参数，删掉 token 管道与 `--token-stdin`。

### 2.1 读取文档

```bash
printf '%s' "$TOKEN" | python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/doc/get_doc_reviews.py" \
  --token-stdin --page-id "<pageId>"
```

### 2.2 审阅提交

```bash
printf '%s' "$TOKEN" | python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/doc/submit_review_edit.py" \
  --token-stdin --page-id "<pageId>" \
  --summary "<用户可见修改摘要>" --actions-file /tmp/actions.json
```

### 2.3 审阅 dry-run

```bash
printf '%s' "$TOKEN" | python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/doc/submit_review_edit.py" \
  --token-stdin --page-id "<pageId>" \
  --summary "验证 actions" --actions-file /tmp/actions.json --dry-run
```

### 2.4 直接编辑提交

```bash
printf '%s' "$TOKEN" | python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/doc/submit_doc_edit.py" \
  --token-stdin --page-id "<pageId>" --actions-file /tmp/actions.json
```

### 2.5 直接编辑 dry-run（沙箱模式）

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/doc/submit_doc_edit.py" \
  --page-id "<pageId>" \
  --actions-file /tmp/actions.json --dry-run
```

## 3. 最小 actions 模板

### 3.1 审阅：块内 update

```jsonc
[
  {
    "type": "update",
    "id": "<blockId>",
    "old_content": "<Paragraph>旧内容</Paragraph>",
    "new_content": "<Paragraph><Mark ar=\"delete\">旧内容</Mark><Mark ar=\"insert\">新内容</Mark></Paragraph>"
  },
  {"type": "card_op", "op": "insert", "summary": "改写过期描述", "kind": "agent_review"}
]
```

### 3.2 审阅：新增块

```jsonc
[
  {"type": "insert_after", "id": "<anchorBlockId>", "content": "<Paragraph>新增说明。</Paragraph>"},
  {"type": "card_op", "op": "insert", "summary": "补充说明", "kind": "agent_review"}
]
```

### 3.3 审阅：复用上一轮卡片

```jsonc
[
  {
    "type": "update",
    "id": "<blockId>",
    "old_content": "<Paragraph>上一版内容</Paragraph>",
    "new_content": "<Paragraph><Mark ar=\"delete\">上一版内容</Mark><Mark ar=\"insert\">修正后内容</Mark></Paragraph>"
  },
  {"type": "card_op", "op": "update", "discussion_id": "<reviewDiscussionId>", "summary": "继续修正该段表述"}
]
```

### 3.4 直接编辑：追加内容

```jsonc
[
  {"type": "insert_after", "id": "", "content": "<Paragraph>新增记录。</Paragraph>"}
]
```

### 3.5 直接编辑：更新标题

```jsonc
[
  {"type": "insert_after", "id": "", "content": "<Heading level=\"1\">项目背景</Heading>\n\n<Paragraph>本项目旨在...</Paragraph>"},
  {"type": "update_title", "title": "季度产品规划"}
]
```

`update_title` 仅直接编辑模式支持，必须位于 actions 末尾，且一次至多 1 条。

## 4. 划词 / 评论修订流程骨架

### 4.1 划词修订

```bash
printf '%s' "$TOKEN" | python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/doc/get_doc_reviews.py" \
  --token-stdin --page-id "<pageId>"

printf '%s' "$TOKEN" | python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/doc/submit_review_edit.py" \
  --token-stdin --page-id "<pageId>" \
  --summary "根据划词内容优化表述" --actions-file /tmp/actions.json
```

注意：划词修订不调用 `get_node_comments.py`；`blockId` 仍必须回读验证。完整规则见 `revision_flows.md`。

### 4.2 评论修订

```bash
printf '%s' "$TOKEN" | python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/manage/get_node_comments.py" \
  --token-stdin --node-id "<pageId>" --discussion-id "<commentDiscussionId>"

printf '%s' "$TOKEN" | python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/doc/get_doc_reviews.py" \
  --token-stdin --page-id "<pageId>"

printf '%s' "$TOKEN" | python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/doc/submit_review_edit.py" \
  --token-stdin --page-id "<pageId>" \
  --summary "根据评论内容优化表述" --actions-file /tmp/actions.json
```

注意：这里的 `discussionId` 是原评论线 ID，只用于拉评论；`card_op=update` 只能使用审阅卡片 `reviewDiscussionId`。完整规则见 `revision_flows.md`。
