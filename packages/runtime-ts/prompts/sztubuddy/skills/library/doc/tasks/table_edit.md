# 表格编辑

> 适用：已有文档中新增表格、修改 cell 内容或调整表格结构。新建整篇文档中的表格走 `read_create.md`，使用 Markdown/GFM。

## 1. 最短流程

1. 按 `../entry.md` 判定写入模式并执行 `../../mutation.md`。
2. 调 `get_doc_reviews.py` 获取最新 content。
3. 先判断用户修改的是 cell 内容还是表格结构，再确认目标 block 类型。
4. 按下表构造 actions；复杂组件语法读取 `../doc_references.md` §6。
5. 先使用对应 submit 脚本 `--dry-run`，再正式提交并透传 `KS_USER_REPLY`。

## 2. 准入与动作

| 目标或诉求 | 动作 |
|---|---|
| 修改 cell 内文字、样式、段落或列表 | 定位 cell 内带独立 `blockId` 的子块，按普通 block 执行 `update` / `insert_*` / `delete` |
| 新增完整表格 | 单条 `insert_before` / `insert_after`，`content` 一次写完整 `<Table>...</Table>` |
| 加删行列、改列宽、改表头或二维结构重排 | 对最外层 `<Table>` 执行 `delete` + `insert_after`，插入完整替换后的 `<Table>` |
| 目标为 `<Table>` | 只允许 `delete` / `insert_before` / `insert_after`；禁止 `update` / `move` |
| 目标为 `<TableRow>` / `<TableCell>` | 禁止任何 action；重新定位到最外层 Table 或 cell 内子块 |

- cell 内容级修改不得因锚点或实现困难升级为整表替换。
- 新增表格或结构变更必须一次性生成完整表格，不拆成多轮占位和注入。
- 审阅与直接编辑的 `content/new_content`、Mark 和评论锚点统一按 `../content_contract.md` 构造。

## 3. 结构变更辅助

仅对行列矩阵结构变更，可用 `table_edit_helper.py` 的 `insert_row`、`delete_row`、`insert_column`、`delete_column`、`set_table` 生成新表格。脚本只做本地变换，不发网络、不提交。

列宽、表头等属性变更需手工构造完整 `<Table>`；单个 cell 内容修改不要使用 helper。

## 4. 按条件深读

| 条件 | 读取 |
|---|---|
| 完整表格组件语法、合并单元格、helper 细节 | `../doc_references.md` §6 |
| 容器解析退化或 dry-run 与正式提交差异 | `../server_pitfalls.md` |
| Mark、old/new content 或评论锚点 | `../content_contract.md` |
| action、card_op 或 pending 卡 | `../action_decision.md` |
| 脚本参数与 dry-run | `../edit_core.md` |
