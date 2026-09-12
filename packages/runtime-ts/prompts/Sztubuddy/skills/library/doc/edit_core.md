# Doc 脚本 API

> 何时读取：不确定 CLI 参数、actions schema、dry-run 或 stdout 协议。action 决策见 `action_decision.md`；字段与 Mark 契约见 `content_contract.md`；组件语法见 `doc_references.md`。
>
> 下列命令默认是客户端模式；沙箱模式使用相同业务参数，但删除 token 管道和 `--token-stdin`。

## 1. 读取最新文档

```bash
printf '%s' "$TOKEN" | python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/doc/get_doc_reviews.py" \
  --token-stdin --page-id "<pageId>"
```

成功：

```text
KS_DOC_REVIEWS	<pageId>	<byteSize>	<url>
<content 文本>
```

失败：stdout 单行 JSON `{"error":"<脱敏原因>"}`；兼容空 stdout，按失败处理。

## 2. 提交审阅

```bash
printf '%s' "$TOKEN" | python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/doc/submit_review_edit.py" \
  --token-stdin --page-id "<pageId>" \
  --summary "<用户可见摘要>" --actions-file actions.json
```

| 参数 | 要求 |
|---|---|
| `--token-stdin` | 客户端模式必填，沙箱模式禁用；业务 payload 也走 stdin 时，token 占第一行 |
| `--page-id` | 必填；页面 ID 映射按 `entry.md` |
| `--summary` | 必填，1–200 字；与 `card_op.summary` 语义一致 |
| `--actions-json` / `--actions-file` / `--actions-stdin` | 三选一 |
| `--dry-run` | 仅本地校验和 body 翻译，不发 HTTP，不产生审阅卡 |

成功：

```text
KS_DOC_REVIEW_SUBMIT	<discussionId>	<anchorBlockId>	<affectedCount>
{"discussionId":"...","anchorBlockId":"...","anchorUrl":"...","affectedBlockIds":[...]}
KS_USER_REPLY	<用户回执>
```

Dry-run：

```text
KS_DOC_REVIEW_DRYRUN	<N>	actions=ok
{"dryRun":true,"actionsCount":N,"pageId":"...","createReviewCard":true}
```

正式成功后原样透传 `KS_USER_REPLY`。不要自拼链接、泄露 `discussionId`，也不要把审阅建议描述为已落正文。

## 3. 直接编辑

```bash
printf '%s' "$TOKEN" | python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/doc/submit_doc_edit.py" \
  --token-stdin --page-id "<pageId>" --actions-file actions.json
```

参数与审阅脚本相同，但没有 `--summary`。直接编辑不产生审阅卡，内容契约见 `content_contract.md` §4。

成功：

```text
KS_DOC_EDIT_SUBMIT	<anchorBlockId>	<affectedCount>
{"anchorBlockId":"...","anchorUrl":"...","affectedBlockIds":[...]}
KS_USER_REPLY	<用户回执>
```

Dry-run：

```text
KS_DOC_EDIT_DRYRUN	<N>	actions=ok
{"dryRun":true,"actionsCount":N,"pageId":"...","mode":"edit"}
```

失败：stdout 单行 JSON error；空 stdout 同样按失败处理。

## 4. 创建整篇文档

`create_doc.py` 固定提交 Markdown，禁止混入 Sztubuddy 组件。创建任务边界见 `tasks/read_create.md`。

```bash
# 默认创建位置
printf '%s' "$TOKEN" | python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/doc/create_doc.py" \
  --token-stdin --title "<标题>" --content "<完整 Markdown>"

# 指定空间或父节点
printf '%s' "$TOKEN" | python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/doc/create_doc.py" \
  --token-stdin --title "<标题>" --space-id "<spaceId>" --parent-id "<parentId>" \
  --content-file /path/to/doc.content

# 本地自检
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/doc/create_doc.py" \
  --title "<标题>" --content "<完整 Markdown>" --dry-run
```

| 参数 | 要求 |
|---|---|
| `--title` | 必填 |
| `--space-id` / `--parent-id` | 可选；缺省使用默认创建位置 |
| `--content` / `--content-file` | 二选一，内容为完整 Markdown |
| `--dry-run` | 本地校验非空、编码、大小及组件禁用项，不发 HTTP |

```text
KS_DOC_CREATE	<nodeBlockId>	<nodeKind>	<url>	<failedCount>	<fatalCount>
KS_DOC_CREATE_DRYRUN	<contentBytes>	content=ok
```

`failedCount` 或 `fatalCount` 大于 0 表示文档已创建但内容可能不完整，必须提示用户打开核对。

## 5. actions schema

| type | 字段 |
|---|---|
| `insert_before` | `id`, `content` |
| `insert_after` | `id`, `content`；`id=""` 表示文末 |
| `delete` | `id` |
| `update` | `id`, `old_content`, `new_content`；可选 `allow_drop_comment`, `drop_comment_reason` |
| `move` | `id` + `after_id`/`before_id` 二选一 |
| `card_op` | `op` 及对应分支字段；仅审阅模式，必须在末尾且正好一条 |
| `update_title` | `title`；仅直接编辑模式，必须在末尾且至多一条 |

详细字段契约见 `content_contract.md`；action、`card_op`、summary 与 `update_title` 决策见 `action_decision.md`；表格目标限制见 `tasks/table_edit.md`。

## 6. dry-run 边界

Dry-run 能校验本地 schema、body 翻译、组件顶层结构、Mark 边界和评论锚点防丢，但不具备正式提交的远端目标类型与解析上下文。复杂组件仍需按 `doc_references.md` 构造；表格按 `tasks/table_edit.md` 分派；正式解析异常见 `server_pitfalls.md`。
