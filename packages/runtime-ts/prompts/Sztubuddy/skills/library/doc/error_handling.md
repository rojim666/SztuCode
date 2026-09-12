# 错误处理与回执（library doc）

> 何时读取：脚本 stdout 为空、提交后用户反馈未看到卡片、或需要决定是否重试时读取。

## 1. stdout 协议

失败统一协议：stdout 输出单行 JSON `{"error":"<脱敏错误>"}` 后 `exit 0`。远端 / HTTP 失败使用 `code=<错误码>; msg=<安全业务说明>`；无远端错误码的本地参数校验保留明确文本。只允许透传错误信封中的 `code` 和经公共层脱敏、截断的 `msg`；不得暴露其它响应字段、requestId、请求体、token、Cookie、堆栈、内部路径或完整签名 URL。兼容遗留：stdout 为空也按失败处理。

| 脚本 | 成功首行 | 失败行为 |
|---|---|---|
| `get_doc_reviews.py` | `KS_DOC_REVIEWS\t<pageId>\t<byteSize>\t<url>` | JSON error，exit 0；兼容空 stdout |
| `get_node_comments.py` | `KS_DOC_COMMENTS\t<nodeId>\t<totalThreads>` | JSON error，exit 0；兼容空 stdout |
| `submit_review_edit.py` | `KS_DOC_REVIEW_SUBMIT\t<discussionId>\t<anchorBlockId>\t<affectedCount>` | JSON error，exit 0；兼容空 stdout |
| `submit_review_edit.py --dry-run` | `KS_DOC_REVIEW_DRYRUN\t<N>\tactions=ok` | JSON error，exit 0；兼容空 stdout |
| `create_doc.py` | `KS_DOC_CREATE\t<nodeBlockId>\t<nodeKind>\t<url>\t<failedCount>\t<fatalCount>` | JSON error，exit 0；兼容空 stdout |
| `create_doc.py --dry-run` | `KS_DOC_CREATE_DRYRUN\t<contentBytes>\tcontent=ok` | JSON error，exit 0；兼容空 stdout |
| `submit_doc_edit.py` | `KS_DOC_EDIT_SUBMIT\t<anchorBlockId>\t<affectedCount>` | JSON error，exit 0；兼容空 stdout |
| `submit_doc_edit.py --dry-run` | `KS_DOC_EDIT_DRYRUN\t<N>\tactions=ok` | JSON error，exit 0；兼容空 stdout |

错误后的分类、下一步和重试次数只按 根目录 `error_handling.md` 执行；本文件不维护第二份映射。

## 2. 用户回执模板

成功场景优先原样透传脚本输出的 `KS_USER_REPLY`；下表只在脚本未提供 `KS_USER_REPLY`、需要人工解释或错误恢复时作为降级模板。

| 场景 | 回执 |
|---|---|
| 读取失败 | 按根目录 `error_handling.md`生成回执 |
| 评论读取失败 | 按根目录 `error_handling.md`生成回执 |
| 提交成功 | 「已生成 <N> 处修订建议，点击查看并接受 / 拒绝：<anchorUrl>（接受后才会落到正文）」 |
| 划词提交成功 | 「已按划词内容生成 <N> 处修订建议，点击查看并接受 / 拒绝：<anchorUrl>」 |
| 评论提交成功 | 「已按评论生成 <N> 处修订建议，点击查看并接受 / 拒绝：<anchorUrl>」 |
| 提交失败 | 按根目录 `error_handling.md`生成回执 |
| 直接编辑成功 | 「已直接修改文档正文，影响 <N> 个块。修改已即时生效，无需审阅。」 |
| 仅更新标题成功 | 「已更新文档标题。修改已即时生效，无需审阅。」 |
| 直接编辑失败 | 按根目录 `error_handling.md`生成回执 |
| 创建文档成功 | 「已创建文档：<url>」 |
| 创建文档·部分内容不完整 | 「已创建文档：<url>，但有 <N> 个内容块未完成（其中 <M> 个需人工复核），建议打开核对并补充。」 |
| 创建文档失败 | 按根目录 `error_handling.md`生成回执 |
| 用户问什么时候生效 | 「你接受审阅卡片之后，改动会立即出现在正文中；在那之前，正文保持不变。」 |
| token / 权限失效 | 「当前无法访问该资料库文档，请确认登录态或文档权限。」 |

> **占位符说明**：
> - `<anchorUrl>` = `submit_review_edit.py` 成功后 JSON 输出里的 `anchorUrl` 字段（形如 `…/space/d/{pageId}#{anchorBlockId}`，点开即定位到修订处）。
> - `<N>` = 影响块数（KS 行第 4 段 `affectedCount`，或 JSON `affectedBlockIds` 长度）。
> - 仅提交 `update_title` 时，可能没有 `anchorUrl` 且 `affectedCount=0`，按「仅更新标题成功」回执，不要说影响正文块。
> - 不要把卡片 ID（`discussionId` / `reviewDiscussionId`）写进用户回执；给用户的是查看入口和锚链接。
> - **降级**：若脚本未返回 `anchorUrl`（`anchorBlockId` 缺失，anchorUrl 为空字符串），回执改为「已生成 <N> 处修订建议，请在文档右侧审阅栏查看并接受 / 拒绝」，不要拼出残缺链接。

## 3. Agent 自处理策略

| 现象 | 处理 |
|---|---|
| `get_doc_reviews.py` 输出 JSON error 或 stdout 空 | 不继续 submit；按根目录 `error_handling.md`处理 |
| `get_node_comments.py` 输出 JSON error 或 stdout 空 | 不继续 submit；按根目录 `error_handling.md`处理 |
| `submit_review_edit.py` 命中参数错误，且刚才包含复杂 content | 先用 `--dry-run` 复查本地 schema，再读取 `doc/doc_references.md` 重写 content；修正后最多调用 1 次 |
| `create_doc.py` 输出 JSON error 或 stdout 空 | 不假装创建成功；按根目录 `error_handling.md`处理 |
| `create_doc.py` 返回 `failedCount/fatalCount > 0` | 说明文档已建但内容可能不完整；按「创建文档·部分内容不完整」回执，提示用户打开核对 |
| 用户反馈卡片不见了 / 没看到 | 重新执行 `get_doc_reviews.py` 读取最新 content；若目标块仍带 `action="..." reviewId="..."` 软标 → 卡片其实还在 pending 状态，走「本轮继续调整」路径复用该卡；若目标块无 review 软标（可能已被作者 resolve）→ 才可新建卡 |
| 上一轮已有审阅卡片 `discussionId`，本轮继续调整 | 将该 ID 视为 `reviewDiscussionId`，使用 `card_op=update` 复用该卡；不要新建多张卡。注意：评论修订里的原评论线 `discussionId` 是 `commentDiscussionId`，不能用于复用审阅卡片 |
| 提交返回 msg 含 `block soft-mark conflict` / `already attached to pending review card` / `block-level.*conflict`（语义是逻辑冲突，不是临时故障） | 不原样重试；重新 `get_doc_reviews.py` 读最新 content 提取目标块的 `reviewId`，按 `action_decision.md` §2.2 复用同一张卡后重发 |
| 目标块 id 失效 | 重新读取文档，基于最新 id 重组 actions |
| 任一脚本输出 `code=12100` / `AUTH_REQUIRED` / `401` / `HTTP_401` | 按权限不足处理，直接告知用户，不重试；不向用户说明 token 管道细节 |

## 4. 禁区

- 不要把 stderr、安全 `msg`、错误码、requestId、token、Cookie 原样给用户；面向用户改写为业务说明。
- 不要在失败后无脑原样重试多次。
- 不要在没读到最新 content 的情况下改 id 或猜 id。
- 不要用真实提交做 content 语法探针；必须 `--dry-run`。
