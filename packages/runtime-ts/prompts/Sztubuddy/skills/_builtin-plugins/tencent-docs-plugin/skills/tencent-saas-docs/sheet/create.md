# sheet 创建（在线表格 / Excel）

> 上级：[../SKILL.md](../SKILL.md)。本页描述「从零创建 sheet 表格」的工具与流程。精细编辑见 [edit.md](./edit.md)。

## 创建流程

1. **建空表格**：用 `manage.create_file`（走 `tencent-saas-docs`）创建 sheet 类型文档，拿到 `file_id`：

   ```bash
   python3 tencentdocs.py tdoc_call tencent-saas-docs manage.create_file '{"title":"销售数据","doc_type":"sheet"}'
   ```

2. **写入数据**：用 [edit.md](./edit.md) 的 `sheet-mcp` 工具集写入。大批量数据优先：
   - `set_range_value` —— 批量写多个单元格/区域
   - `set_range_value_by_csv` —— 以 CSV 一次性灌入

3. **加样式 / 图表 / 透视表**：`set_cell_style` / `set_border` / `add_chart` / `add_pivot_table` 等，详见 [edit.md](./edit.md)。

> 子表默认存在一个；多子表用 `add_sheet`，每次操作通过 `sheet_id` 指定目标子表。
