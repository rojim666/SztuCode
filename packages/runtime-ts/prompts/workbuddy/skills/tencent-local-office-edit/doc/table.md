# DOC 表格操作选型指南

> 工具参数以 `tools/list` schema 为准，本文件只讲选型策略和字段语义，不重复抄录 schema。

## 选型决策树

```
操作表格
├─ 拿 table_id / 看有哪些表 → doc_list_tables
├─ 读单表完整内容（已知 table_id）→ doc_get_table_info ⭐（不要 list→get 串联）
├─ 创建表格
│   ├─ 纯文本/简单 → doc_insert_markdown ⭐ 最省 token
│   ├─ 精细样式（底色/边框/字体）→ doc_insert_table → doc_set_table_cells ⭐ 保真最高
│   └─ 空表 → doc_insert_table（返回 table_id）
├─ 追加行/列
│   ├─ N 行 → doc_insert_table_rows（带 cells）⭐ 1 次
│   ├─ N 列 → doc_insert_table_cols（带 cells）⭐ 1 次
│   └─ 仅 1 行/列 → doc_insert_table_row / _column（带 cells）
├─ 改单元格内容/样式 → doc_set_table_cells
├─ 合并/拆分 → doc_merge_table_cells / doc_unmerge_table_cells
├─ 删除 → doc_delete_table_row / _column / doc_delete_table
└─ 改表格属性（边框/列宽/对齐/底纹）→ doc_set_table_properties
```

## 铁律

1. **批量优于循环**：插 N 行/列用批量版（1 次），禁止循环单行版（N 次）。批量版 anchor 基于原始表格，无需跟踪行号漂移。
2. **纯文本表走 Markdown**：`doc_insert_markdown` 比两步法省 75% token。
3. **读单表用 get_table_info**：out token 仅 `list_tables` 的 1/7，不要 `list_tables → get_table_info` 串联。
4. **table_id 优先于 idx**：table_id 不随编辑漂移，idx 会漂移。`doc_insert_table` 返回的 `table_info.id` 即 table_id。`get_table_info` 返回的 `block.id` 若为 `tbl:<begin>:<end>` 形式则**不是**持久 table_id，改用 idx。
5. **共用样式提 common_cell_properties**：`set_table_cells` / `insert_table_row(s)` 支持，公共字号/字体/对齐写一次，cells 只写差异项。某 cell 不想被刷公共样式加 `inherit:false`。

## 创建路线对比

| 路线 | 调用 | token | 样式能力 | 适用 |
|------|------|-------|---------|------|
| `doc_insert_markdown` | 1 | 最少 | 仅 Markdown 语法 | 纯文本表格 |
| `doc_insert_table` → `doc_set_table_cells` | 2 | 中 | Run 级精确控制 | 底色/边框/字体等精细样式 |

## 字段语义

- **text**：不传=保留原文本（只改格式/属性）；传空串=清空；传非空=整体替换。
- **text / property / text_format 三者独立**：互不依赖，只传 property 只改底色边框，只传 text_format 只套格式，同时传先替换文本再套格式。
- **schema 字段引用**：`insert_table_row(s)` / `insert_table_column(cols)` 的 `property` / `text_format` / `horizontal_align` 子对象未在自身 schema 内联，用 description 指向 `doc_set_table_cells` 的同名字段，构造参数时查 `doc_set_table_cells` schema 即可。
