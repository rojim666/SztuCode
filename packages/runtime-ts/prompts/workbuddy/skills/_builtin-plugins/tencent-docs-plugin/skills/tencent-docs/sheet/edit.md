# sheet 编辑（在线表格 / Excel）

- service：`sheet-mcp`
- endpoint：`https://docs.qq.com/api/v6/sheet/mcp`
- 调用：`python3 tencentdocs.py tdoc_call sheet-mcp <工具> '{"file_id":"<id>","sheet_id":"<sid>",...}'`

> 上级：[../SKILL.md](../SKILL.md)。精细编辑走本 endpoint，工具名无 `sheet.` 前缀。创建表格见 [create.md](./create.md)。

> 💡 **批量写入优先**：多单元格/区域写入用 `set_range_value` / `set_range_value_by_csv` 一次提交，避免循环单条调用。

| 工具 | 说明 |
|---|---|
| `add_chart` | 在在线表格中添加图表 |
| `add_pivot_table` | 在在线表格中创建透视表 |
| `add_sheet` | 在在线表格中添加一个新的子表 |
| `clear_border` | 清除在线表格指定区域单元格的边框 |
| `clear_link` | 清除在线表格指定单元格的超链接 |
| `clear_range_all` | 清除在线表格指定区域内所有单元格的内容和样式 |
| `clear_range_cells` | 清除在线表格指定区域内所有单元格的内容 |
| `clear_range_style` | 清除在线表格指定区域内所有单元格的样式 |
| `delete_chart` | 删除在线表格中指定的图表 |
| `delete_dimension` | 删除在线表格指定位置的行或列 |
| `delete_range` | 在在线表格指定区域删除单元格，通过删除行或列实现后续单元格的左移或上移 |
| `delete_sheet` | 删除在线表格中指定的子表 |
| `find` | 在表格中搜索指定文本，返回匹配的单元格位置 |
| `get_cell_data` | 获取在线表格指定区域的单元格数据，支持返回CSV格式或结构化单元格数据 |
| `get_cell_style` | 获取在线表格指定区域单元格的样式信息 |
| `get_charts` | 获取在线表格指定子表下的所有图表信息 |
| `get_dimension_size` | 读取在线表格指定行的行高或指定列的列宽，返回单位为像素 |
| `get_merged_cells` | 获取在线表格指定区域内与该区域相交的合并单元格信息 |
| `get_pivot_table_detail` | 读取指定透视表的详细配置（数据源、行/列/值/筛选、锚点位置、ID 等） |
| `get_sheet_info` | 获取在线表格的子表信息 |
| `get_sheet_object_list` | 获取在线表格指定子表上的对象列表 |
| `insert_dimension` | 在在线表格指定位置插入行或列 |
| `insert_image` | 在在线表格指定单元格（row_index / col_index |
| `insert_range` | 在在线表格指定区域插入空白单元格，通过插入行或列实现选中区域的右移或下移 |
| `merge_cell` | 合并在线表格指定范围的单元格 |
| `move_dimension` | 在在线表格中移动一段连续的行或列到新的位置 |
| `move_sheet` | 移动在线表格中子表的顺序 |
| `remove_filter` | 移除在线表格的筛选 |
| `remove_pivot_table` | 删除在线表格中已存在的透视表 |
| `rename_sheet` | 重命名在线表格中指定的子表 |
| `set_border` | 设置在线表格指定区域单元格的边框样式 |
| `set_cell_style` | 设置在线表格指定范围单元格的样式，包括字体、颜色、对齐等 |
| `set_cell_value` | 设置在线表格指定单元格的值，支持文本、数字、布尔等类型 |
| `set_dimension_size` | 设置在线表格指定行的行高或指定列的列宽 |
| `set_filter` | 为在线表格指定数据区域设置筛选 |
| `set_freeze` | 设置在线表格的冻结行列数 |
| `set_link` | 为在线表格指定单元格设置超链接 |
| `set_range_value` | 批量设置在线表格多个单元格的值 |
| `set_range_value_by_csv` | 以CSV格式批量插入数据到在线表格 |
| `sort_range` | 对在线表格指定区域按列排序 |
| `unmerge_cell` | 取消在线表格指定区域的单元格合并 |
| `unset_freeze` | 删除在线表格指定子表的所有冻结行列 |
| `update_chart` | 更新在线表格中指定图表的类型、数据范围、位置尺寸、标题等配置 |
| `update_filter` | 更新在线表格已有筛选的范围和/或列筛选项 |
| `update_pivot_table` | 更新已有透视表的字段配置（行分组、列分组、数据值、筛选、计算字段） |
| `validate_file_data` | 校验在线表格指定版本的数据是否正常（排障专用） |
