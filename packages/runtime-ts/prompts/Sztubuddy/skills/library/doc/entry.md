# doc —— 在线文档任务入口

> 处理资料库在线文档（`kind=doc`）的读取、创建、编辑与修订。`kind=web/page`、`database`、`smh/drive` 不走本入口。

## 1. 先选任务

只读取命中的一个任务文件；任务文件明确要求时，才追加读取技术参考。

| 用户任务 | 读取 |
|---|---|
| 查看、摘要、提取原文；新建整篇在线文档 | `tasks/read_create.md` |
| 根据划词或评论修改，包括全文评论修订 | `tasks/revision.md` |
| 新增或修改已有文档中的表格；目标位于表格或 cell 内 | `tasks/table_edit.md` |
| 修改非基础组件、块类型、children、块级属性、Code 或 Mermaid | `tasks/complex_edit.md` |
| 普通文字块增删改移、直接追加、批量文字替换或删除 | `tasks/text_block_edit.md` |
| 脚本失败、stdout 为空、卡片不可见或需要判断重试 | `error_handling.md` |

路由优先级：

1. 新建整篇文档始终走 `tasks/read_create.md`；其中表格、代码和 Mermaid 使用 Markdown，不走已有文档的组件编辑规则。
2. 划词或评论修订始终先走 `tasks/revision.md`；命中表格或复杂组件时，再按该任务文件追加读取。
3. 其余场景按表格 → 复杂组件 → 普通文字块匹配。

## 2. 全局前置条件

- 写操作 → 先执行 `../mutation.md`；是否停下确认由目标空间分类决定。
- 现有文档写操作 → 先用 `get_doc_reviews.py` 读取最新 content，再构造 actions。
- `nodeId` 与 `pageId` 等价，调用 Doc 脚本时传给 `--page-id`。
- `blockId` 必须来自最新回读，或来自用户/上游明确输入且已在最新 content 中验证；禁止猜测、截断或跨文档复用。
- 未确认节点为 `kind=doc` → 不调用 Doc 读写脚本；先仲裁节点类型。

## 3. 写入模式

| 条件 | 模式 |
|---|---|
| 用户要求修订、审阅、提修改建议；或未指定模式但会改、删、替换、移动已有内容 | 审阅式编辑：`submit_review_edit.py` |
| 用户要求直接写入；或未指定模式且只是新增、追加，不影响已有内容 | 直接编辑：`submit_doc_edit.py` |
| 模式、范围或风险冲突且无法从上下文确定 | 先询问 |

## 4. 统一收尾

- 正式写入成功 → 原样透传脚本输出的 `KS_USER_REPLY`，不要自行拼接链接或暴露内部 ID。
- 审阅式编辑 → 说明接受后才落正文；直接编辑 → 说明已即时落正文。
- stdout 为 JSON error 或为空 → 视为失败，不继续后续提交，转 `error_handling.md`。
