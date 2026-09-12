# sheet（本地 Excel 类）编辑接口

上级：[SKILL.md](./SKILL.md)。工具名带 `sheet_` 前缀。

```bash
python3 edsdk.py list sheet
python3 edsdk.py schema <sheet_tool>
python3 edsdk.py call <sheet_tool> file_id=<id> sheet_id=<sid> ...
```

完整工具清单和参数以服务端 `tools/list` / `schema` 实时返回为准；本文只记录 sheet 特有的操作约定。

> ⚠️ 接口列表只用于选工具；真正调用任何 `sheet_*` 工具前，必须先执行
> `python3 edsdk.py schema <工具名>` 获取参数，不要凭列表或记忆填写。
> 复杂参数用 `--json '{...}'`；对参数拿不准时只查本次要用的工具 schema，不要全量拉取。

## 关键约定

- 批量写值优先用 `sheet_set_range_value` 或 `sheet_set_range_value_by_csv`。
  ⚠️ 但这两个工具是“覆盖写”，不具备“插入 / 下移”语义：对已有内容的单元格调用它们，
  会原地替换该格内容。若目标是“新增行 / 列”，见「操作顺序」中的 ⛔ HARD RULE，
  必须先 `sheet_insert_dimension`。
- 写值只改单元格内容，不会清除该格的超链接（`sheet_set_link` 设置的链接会保留）。
  对已有超链接的格写入新文本，会得到「新文本 + 旧链接」的错配状态；
  确需去掉链接时必须显式调 `sheet_clear_link`。
- 批量文本替换用 `sheet_replace`。
- 单元格、区域、行列、样式、图表、透视表、筛选等操作都应先明确目标 `sheet_id` 和范围。
- 图表、透视表、筛选、合并单元格等对象类操作，先读当前状态，再按 schema 更新。

## 坐标规则

- `file_id` 定位工作簿，`sheet_id` 定位子表；不要把路径、工作簿名或子表名当作 ID。
- 行列索引、区域边界按 schema 填写；本地 sheet 工具通常使用 0-based 坐标。
- 普通写值 / 改样式不改变坐标，但会就地覆盖目标格的原有内容；
  超链接、批注等附加数据不随写值清除，可能与新内容错配。
  写值前务必用 `sheet_get_used_range` 确认目标格是否真的为空。
- 插入、删除、移动行列或区域会改变结构，旧坐标、旧范围、对象锚点可能失效，继续操作前先重新读取。

## 操作顺序

### ⛔ HARD RULE — 写值前必须探明目标区域状态

违反下列任一条，都会静默覆盖用户已有数据（含超链接、批注、样式），且难以恢复。

1. **任何 `sheet_set_range_value` / `sheet_set_range_value_by_csv` / `sheet_set_cell_value` 之前**，
   必须先 `sheet_get_used_range` 拿到真实已用区域末行 / 末列。
   禁止用肉眼观察、文件预览、或上一次读取的行数去猜边界 ——
   已用区域常大于“看起来有数据”的范围（隐藏行、样式行、文本为空但有链接的格都算）。
   返回结果的字段名与边界语义（0-based / 1-based、inclusive / exclusive）
   一律以 `edsdk.py schema sheet_get_used_range` 为准，不要直接套用本文示例里的算式。
2. **用户表达“新增 / 添加 / 再加 / 插入 / 追加”行或列时（结构性新增）**，
   必须先 `sheet_insert_dimension` 腾出空间，再写值。
   绝不允许直接对已用区域内的行列调写值工具来“实现新增” —— 那是覆盖，不是新增。
   - 追加到数据末尾：紧接已用区域末行之后的第一个空行
     （若 schema 确认末行字段为 0-based inclusive，则 `index = used_range.end_row + 1`）
   - 在第 N 行前插入：`index = N`（0-based）
   - `count` = 要新增的行数
3. `sheet_insert_dimension` / `sheet_delete_dimension` / `sheet_move_dimension` /
   `sheet_insert_range` / `sheet_delete_range` / `sheet_sort_range` 之后，
   所有旧坐标失效，必须重新 `sheet_get_used_range` + `sheet_get_cell_data`，
   不得沿用结构操作前的行号。
4. 确实需要改写已有内容（用户明确表达“修改 / 替换 / 更正 XX”）时，
   先 `sheet_get_cell_data` 读回目标区域，确认要覆盖的内容与用户意图一致，再写。

**正确姿势（新增两行数据）：**

```bash
# 1. 探测真实边界 —— 不要猜；先查 schema 明确字段名与边界语义
python3 edsdk.py schema sheet_get_used_range
python3 edsdk.py call sheet_get_used_range file_id=<fid> sheet_id=<sid>
#    → 本例中末行字段为 0-based inclusive 且返回 12，即数据实际到 Excel 第 13 行
#      若实际 schema 语义不同（1-based，或表示首个空行的 exclusive 值），
#      请据此换算，不要照抄下面的 +1

# 2. 插入两行（追加到末尾：末行 12 之后的第一个空行 = 13）
python3 edsdk.py schema sheet_insert_dimension
python3 edsdk.py call sheet_insert_dimension file_id=<fid> sheet_id=<sid> \
    dimension_type=row index=13 count=2

# 3. 结构已变，重新读取确认
python3 edsdk.py call sheet_get_used_range file_id=<fid> sheet_id=<sid>

# 4. 写入新腾出的空行（0-based row 13、14）
python3 edsdk.py call sheet_set_range_value file_id=<fid> sheet_id=<sid> \
    values='[{"row":13,"col":0,"value":"张三"}, ...]'

# 5. 保存
python3 edsdk.py call save_file file_id=<fid>
```

**反模式（禁止）：**

```bash
# ❌ 只读前 9 行就断定第 10/11 行为空
python3 edsdk.py call sheet_get_cell_data ... start_row=0 end_row=8
# ❌ 用户说“再加两行”，却直接写第 10/11 行 → 覆盖掉那两行原有的超链接单元格
python3 edsdk.py call sheet_set_range_value ... values='[{"row":9,...},{"row":10,...}]'
```

### 其他顺序约定

- 需要大量写入时，用 `sheet_set_range_value` / `sheet_set_range_value_by_csv`，不要逐格循环调用。
- 需要批量查找替换时，用 `sheet_replace`；调用前查 schema，确认是否按公式、大小写、正则等维度匹配。
- 参与计算、图表、透视表的数据单元格应尽量写成数值类型；纯字符串即使看起来像数字，也可能影响公式、排序、图表和透视表的数据表达。
- `sheet_sort_range` 的排序范围必须覆盖完整数据区（用 `sheet_get_used_range` 校准）；
  范围小于真实数据区会把区外行留在原位，造成数据错位。

## 图表提示

- `sheet_add_chart` / `sheet_update_chart` 调用前先查 schema；复杂参数和不支持类型以 schema description / 接口错误为准。
- `drawing_id` 是图表标识，新增时需唯一，后续更新 / 删除都靠它定位。
- `data_range` / `location` 使用 0-based 行列，`location` 偏移和宽高是像素；数据源避免隐藏行列、无关数据和字符串数字。
- 改过数据源、图表类型或系列方向后，先 `sheet_get_charts` 读回真实系列数量和顺序，再改 `options.series`。
- `options` 是 patch，只传要改的字段；饼图 / 环形图扇区样式写到 `series[0].dataPoints`。

## 对象操作

- 图表、透视表、筛选、合并单元格等对象都应先读当前状态，再按 schema 更新；不要凭旧缓存拼更新参数。
- 透视表更新只适合改已有配置；如果需要换数据源范围，通常删除后重建更清晰。
- 合并单元格、筛选范围、透视表锚点、图表锚点都可能受结构性行列操作影响；结构变化后先重新读取对象列表或详情。

## 接口列表

| 工具 | 说明 |
|---|---|
| `find` | 在表格中搜索文本，支持范围、分页、正则、大小写和公式匹配 |
| `sheet_add_chart` | 在本地表格中添加图表 |
| `sheet_add_conditional_format` | 为指定区域添加条件格式规则 |
| `sheet_add_pivot_table` | 在本地表格中创建透视表 |
| `sheet_add_sheet` | 在本地表格中添加一个新的子表 |
| `sheet_add_table` | 将已有单元格区域转换为结构化表格，返回后端生成的 table ID |
| `sheet_audit_formula_consistency` | 审计某区域内公式结构的一致性：把每个公式归一化为 R1C1（位置无关）后按结构分组 |
| `sheet_calculate_formulas` | 批量试算本地表格中的多个公式 |
| `sheet_calculate_single_formula` | 试算本地表格中的公式 |
| `sheet_clear_border` | 清除本地表格指定区域单元格的边框 |
| `sheet_clear_link` | 清除本地表格指定单元格的超链接 |
| `sheet_clear_range_all` | 清除本地表格指定区域内所有单元格的内容和样式 |
| `sheet_clear_range_cells` | 清除本地表格指定区域内所有单元格的内容 |
| `sheet_clear_range_style` | 清除本地表格指定区域内所有单元格的样式（如字体、颜色、背景色、对齐、数字格式等） |
| `sheet_copy_sheet` | 复制本地表格中的子表，生成一个内容相同的副本子表 |
| `sheet_delete_chart` | 删除本地表格中指定的图表 |
| `sheet_delete_dimension` | 删除本地表格指定位置的行或列 |
| `sheet_delete_range` | 在本地表格指定区域删除单元格，通过删除行或列实现后续单元格的左移或上移 |
| `sheet_delete_sheet` | 删除本地表格中指定的子表 |
| `sheet_get_cell_data` | 获取本地表格指定区域的单元格数据 |
| `sheet_get_cell_style` | 获取本地表格指定区域单元格的样式信息 |
| `sheet_get_charts` | 获取本地表格指定子表下的所有图表信息 |
| `sheet_get_conditional_format` | 获取指定子表的条件格式列表，可按区域过滤 |
| `sheet_get_dimension_size` | 读取本地表格指定行的行高或指定列的列宽，返回单位为像素 |
| `sheet_get_merged_cells` | 获取本地表格指定区域内与该区域相交的合并单元格信息 |
| `sheet_get_object_list` | 获取本地表格指定子表上的对象列表 |
| `sheet_get_pivot_table_detail` | 读取指定透视表的详细配置（数据源、行/列/值/筛选、锚点位置、ID 等） |
| `sheet_get_sheet_info` | 获取本地表格的子表信息 |
| `sheet_get_used_range` | 获取指定子表的已使用区域 |
| `sheet_insert_dimension` | 在本地表格指定位置插入行或列。**用户说“新增 / 添加 / 再加 / 插入 / 追加”行列时必须先用本工具**，见「操作顺序」⛔ HARD RULE |
| `sheet_insert_image` | 在本地表格指定单元格插入一张图片 |
| `sheet_insert_range` | 在本地表格指定区域插入空白单元格，通过插入行或列实现选中区域的右移或下移 |
| `sheet_list_recent_ai_edits` | 列出当前 editor 实例最近通过 MCP 写工具产生的编辑 |
| `sheet_merge_cell` | 合并本地表格指定范围的单元格 |
| `sheet_move_dimension` | 在本地表格中移动一段连续的行或列到新的位置 |
| `sheet_move_sheet` | 移动本地表格中子表的顺序 |
| `sheet_remove_filter` | 移除本地表格的筛选 |
| `sheet_remove_conditional_format` | 删除指定条件格式，或清空子表上的全部条件格式 |
| `sheet_remove_pivot_table` | 删除指定的透视表 |
| `sheet_rename_sheet` | 重命名本地表格中指定的子表 |
| `sheet_replace` | 在本地表格中查找并替换文本 |
| `sheet_revert_revision` | 反向指定 version 的 revision 改动，并提交为一条新 revision |
| `sheet_set_border` | 设置本地表格指定区域单元格的边框样式 |
| `sheet_set_cell_style` | 设置本地表格指定范围单元格的样式 |
| `sheet_set_cell_value` | 设置本地表格指定单元格的值 |
| `sheet_set_data_validation` | 为指定区域或整列设置、更新或清除数据验证规则 |
| `sheet_set_dimension_size` | 批量设置本地表格指定行的行高或指定列的列宽 |
| `sheet_set_dimension_visible` | 批量设置本地表格指定行或列的可见状态 |
| `sheet_set_filter` | 为本地表格指定数据区域设置筛选 |
| `sheet_set_freeze` | 设置本地表格的冻结行列数 |
| `sheet_set_link` | 为本地表格指定单元格设置超链接 |
| `sheet_set_range_value` | 批量设置本地表格多个单元格的值。⚠️ **覆盖写，无插入语义**；对已有内容的格会原地替换且不清超链接，调用前必须 `sheet_get_used_range` 确认目标为空 |
| `sheet_set_range_value_by_csv` | 以CSV格式批量插入数据到本地表格。⚠️ 同上，是**覆盖写**不是结构性插入 |
| `sheet_set_sheet_visible` | 设置本地表格中指定子表的可见状态 |
| `sheet_sort_range` | 对本地表格指定区域按列排序 |
| `sheet_unmerge_cell` | 取消本地表格指定区域的单元格合并 |
| `sheet_unset_freeze` | 删除本地表格指定子表的所有冻结行列 |
| `sheet_update_chart` | 更新本地表格中指定图表的类型、位置、尺寸、数据区域和标题 |
| `sheet_update_conditional_format` | 按 cf_id 更新条件格式的区域和规则 |
| `sheet_update_filter` | 更新本地表格已有筛选的范围和/或列筛选项 |
| `sheet_update_pivot_table` | 更新已有透视表的字段配置（行分组、列分组、数据值、筛选、计算字段） |

> 参数 schema 以服务端 `tools/list` 实时返回为准；上表为一句话摘要。
