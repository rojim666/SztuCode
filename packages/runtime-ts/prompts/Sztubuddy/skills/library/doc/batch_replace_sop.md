# 批量替换与全局删除

> 何时读取：用户要求“全部 X 换成 Y”“删掉所有 X”“文档里不应出现 X”或跨多个章节统一修改。

## 1. 流程

1. 按 `entry.md` 选择审阅或直接编辑模式，并读取最新 content。
2. 搜索完整 content，排除 frontmatter、`ReviewSummary`、`reviewId`、`action=` 等元数据命中。
3. 列出正文候选位置；替换目标、替换词或删除范围不明确时先询问。
4. 每个命中块按 `action_decision.md` 选择最小 action；字段与 Mark 按 `content_contract.md` 构造。
5. 多块修改放入一次 submit；审阅模式仅在末尾追加一条 `card_op`，跨章节全局修改可选择 `kind=agent_review_global`。
6. 复杂 content 先 dry-run，再正式提交并透传 `KS_USER_REPLY`。

## 2. action 分派

| 场景 | action |
|---|---|
| 修改块内文字或样式 | `update` |
| 删除整个过期块 | `delete` |
| 块类型或结构变化 | `delete` + `insert_before/insert_after` |
| 表格或 cell 命中 | 转 `tasks/table_edit.md` |
| Code、Mermaid 或复杂组件命中 | 转 `tasks/complex_edit.md` |

批量操作仍必须使用最新 block id；不能仅凭标题、摘要或旧缓存构造 actions。
