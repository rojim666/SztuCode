# 普通文字块编辑

> 适用：已有文档中普通 `Paragraph`、`Heading`、列表、Todo 等文字块的增删改移、直接追加，以及批量文字替换或删除。

## 1. 最短流程

1. 按 `../entry.md` 判定审阅式编辑或直接编辑，并执行 `../../mutation.md`。
2. 调 `get_doc_reviews.py` 获取最新 content，定位并验证目标 `blockId`。
3. 选择最小 action：
   - 改块内文字或样式 → `update`。
   - 前后新增 → `insert_before` / `insert_after`；文末追加可用 `insert_after(id="")`。
   - 删除整块 → `delete`。
   - 同一 parent 内移动 → `move`。
   - 块类型、children 或块级属性变化 → 转 `complex_edit.md`。
4. 不确定时先对对应 submit 脚本使用 `--dry-run`。
5. 正式提交；成功后原样透传 `KS_USER_REPLY`。

## 2. 构造 actions

`update` 必须包含：

```jsonc
{"type":"update","id":"<blockId>","old_content":"<修改前完整块>","new_content":"<修改后完整块>"}
```

- `old_content` 必须来自最新回读，只用于本地防丢校验。
- `new_content` 必须是同类型的一个完整组件块；不能只写文字片段，也不能借 `update` 改块类型。
- `insert_before` / `insert_after` 的 `content` 使用组件块；同一位置连续新增多个块时写在一条 action 中，以空行分隔。
- `delete`、`move`、`update` 不填写 `content`。

### 审阅式编辑

- action 与审阅卡按 `../action_decision.md` 构造。
- `content/old_content/new_content`、Mark 和评论锚点按 `../content_contract.md` 构造。
- 回读块带 `action="..." reviewId="..."`，或本轮继续调整上一张卡 → 按 `../action_decision.md` §2.2 复用原卡。

### 直接编辑

- 禁止 `card_op`、`summary` 和 `<Mark ar>`；`content/new_content` 是最终正文。
- 仅在需要同步修改文档页面标题时，按 `../action_decision.md` §5 判断是否在末尾追加 `update_title`。

## 3. 批量替换或删除

- 先搜索完整 content，排除 frontmatter、`ReviewSummary`、`reviewId`、`action=` 等元数据命中。
- 替换目标或删除语义不明确 → 先询问，不猜测替换词或删除范围。
- 多个正文块命中 → 一次 submit，分别生成 block action；审阅模式仍只追加一条 `card_op`。
- 全文或多章节修改 → 读取 `../batch_replace_sop.md`。

## 4. 按条件深读

| 条件 | 读取 |
|---|---|
| 不确定 action、card_op、pending 卡或标题更新 | `../action_decision.md` |
| 不确定字段边界、Mark 或评论锚点 | `../content_contract.md` |
| 不确定 CLI、schema、dry-run 或 stdout | `../edit_core.md` |
| 非基础组件、Code/Mermaid、块结构变化 | `complex_edit.md` |
| 表格或 cell 内目标 | `table_edit.md` |
| 脚本失败 | `../error_handling.md` |
