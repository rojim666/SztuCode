# slide 编辑（幻灯片 / PPT）

- service：`slide-mcp`
- endpoint：`https://docs.qq.com/api/v6/slide/mcp`
- 调用：`python3 tencentdocs.py tdoc_call slide-mcp <工具> '{"file_id":"<id>","page_index":0,...}'`

> 上级：[../SKILL.md](../SKILL.md)。精细编辑走本 endpoint，工具名带 `slide_` 前缀；坐标单位磅(pt)；插入形状须设 fill/border 颜色。AI 一键生成整份 PPT 见 [create.md](./create.md)。

> 💡 **批量操作优先**（如 `slide_add_shapes` / `slide_add_texts` / `slide_add_line_shapes` / `slide_add_slides`），避免多次调用单个操作接口，减少网络往返和编辑冲突。

| 工具 | 说明 |
|---|---|
| `slide_add_anim` | 为指定幻灯片中的某个形状添加动画效果 |
| `slide_add_chart` | 在指定幻灯片上添加图表 |
| `slide_add_comment` | 在指定幻灯片上添加批注锚点 |
| `slide_add_datetime` | 在指定幻灯片插入日期时间占位符 |
| `slide_add_footer` | 在指定幻灯片添加或移除页脚占位符 |
| `slide_add_image` | 在指定幻灯片插入一张图片 |
| `slide_add_line_shape` | 在指定幻灯片插入一根线形 / 方向性箭头线条 |
| `slide_add_line_shapes` | 批量在同一幻灯片插入多根线形 / 方向性箭头线条 |
| `slide_add_notes` | 为指定幻灯片创建演讲者备注页并写入文本内容 |
| `slide_add_page_number` | 在指定幻灯片插入页码占位符 |
| `slide_add_page_with_jsx` | 通过 JSX 代码生成一页幻灯片并插入到指定位置 |
| `slide_add_section` | 在指定位置添加新节 |
| `slide_add_shape` | 在指定幻灯片插入一个普通形状 |
| `slide_add_shapes` | 批量在同一幻灯片插入多个形状 |
| `slide_add_slide` | 在演示文稿中插入一张新幻灯片 |
| `slide_add_slides` | 在同一位置批量插入多张幻灯片，所有页共用同一布局模板 |
| `slide_add_table` | 在指定幻灯片页创建空表格，page_index 从 0 开始计数 |
| `slide_add_text` | 在指定幻灯片插入一个文本框 |
| `slide_add_texts` | 批量在同一张幻灯片插入多个文本框 |
| `slide_append_notes_text` | 在指定幻灯片的备注页（演讲者备注）末尾追加文本 |
| `slide_append_text` | 向指定 shape 文本末尾追加文本 |
| `slide_change_chart_type` | 更改指定图表类型 |
| `slide_delete_table_cols` | 从表格 shape 中删除一列或多列，从 index 指定的列开始 |
| `slide_delete_table_rows` | 从表格 shape 中删除一行或多行，从 index 指定的行开始 |
| `slide_delete_text` | 删除指定 shape 文本区间 |
| `slide_duplicate_slide` | 深拷贝一张或多张幻灯片 |
| `slide_find_replace_text` | 在指定页查找并替换文本 |
| `slide_find_text` | 在演示文稿中查找文本 |
| `slide_get_chart_info` | 获取指定图表结构信息 |
| `slide_get_comments` | 获取全部批注或指定页批注 |
| `slide_get_design` | 读取当前文档已经持久化的 DESIGN.md 设计契约 |
| `slide_get_group_info` | 获取指定 group shape 的子 shape 列表 |
| `slide_get_info` | 获取演示文稿元数据：幻灯片总数、有序 slide_ids、幻灯片尺寸 |
| `slide_get_master_info` | 获取演示文稿中母版页的详细信息 |
| `slide_get_notes_text` | 读取指定幻灯片的备注页（演讲者备注）文本 |
| `slide_get_page_info` | 获取指定幻灯片上所有形状的摘要信息和动画列表 |
| `slide_get_sections` | 获取演示文稿中的全部节 |
| `slide_get_shape_info` | 查询指定幻灯片中某个形状的详细信息 |
| `slide_get_table_info` | 查询指定幻灯片中指定表格 |
| `slide_get_text` | 获取指定 shape 的文本内容与样式区间 |
| `slide_get_themes` | 获取当前演示文稿中嵌入的所有主题列表 |
| `slide_group_shapes` | 将同一页多个 shape 组合成 group shape |
| `slide_insert_table_cols` | 在表格 shape 中插入一列或多列 |
| `slide_insert_table_rows` | 在表格 shape 中插入一行或多行 |
| `slide_insert_text` | 在指定 shape 文本位置插入文本 |
| `slide_list_anim_types` | 列出所有支持的动画类型 |
| `slide_list_builtin_themes` | 列出服务端所有内置（预置）主题 |
| `slide_merge_table_cells` | 合并表格 shape 中的矩形单元格区域 |
| `slide_modify_comment` | 修改指定批注分组的文本 / 作者 |
| `slide_move_anim` | 移动指定形状的动画在序列中的位置 |
| `slide_move_section` | 移动指定节到新的节序号位置 |
| `slide_move_slide` | 将一个或多个幻灯片页面移动至演示文稿中的新位置 |
| `slide_remove_anim` | 移除指定形状的某个动画 |
| `slide_remove_comment` | 删除指定批注分组 |
| `slide_remove_section_with_slides` | 删除指定节，同时删除节内的所有幻灯片（不可恢复） |
| `slide_remove_sections` | 删除一个或多个节但保留节内幻灯片 |
| `slide_remove_shapes` | 从指定幻灯片删除一个或多个形状 |
| `slide_remove_slide` | 删除指定位置的幻灯片 |
| `slide_rename_section` | 修改指定节的名称 |
| `slide_reorder_shape` | 调整指定形状的 z-order 层级 |
| `slide_reorder_shapes_in_group` | 调整分组内子 shape 层级 |
| `slide_reply_comment` | 向已有批注分组追加一条回复 |
| `slide_set_anim_properties` | 修改指定形状某个动画的类型和方向 |
| `slide_set_anim_trigger` | 修改指定形状某个动画的触发方式 |
| `slide_set_cell_text` | 向表格 shape 的单个单元格写入纯文本 |
| `slide_set_default_font` | 设置演示文稿默认字体 |
| `slide_set_design` | 持久化 AI 产出的 DESIGN.md 到当前文档（TTL 24h） |
| `slide_set_notes_text` | 设置或覆盖指定幻灯片的备注页（演讲者备注）文本 |
| `slide_set_page_properties` | 设置幻灯片页面级属性，包括背景填充（纯色/图片/渐变）和可见性 |
| `slide_set_shape_properties` | 修改幻灯片中一个或多个形状的属性 |
| `slide_set_slide_size` | 设置演示文稿页面尺寸 |
| `slide_set_text` | 替换指定 shape 的文本内容 |
| `slide_set_text_property` | 在不修改文本内容的前提下 |
| `slide_set_theme` | 设置演示文稿的主题 |
| `slide_ungroup_shapes` | 解散指定 group shape |
| `slide_unmerge_table_cells` | 取消表格 shape 中指定矩形区域的单元格合并 |
| `slide_update_chart_axis` | 更新单根坐标轴属性 |
| `slide_update_chart_data` | 替换指定图表的内嵌数据 |
| `slide_update_chart_data_labels` | 控制图表数据标签的显示项/位置/数字格式/字体 |
| `slide_update_chart_gridlines` | 控制图表主网格线显示 |
| `slide_update_chart_legend` | 更新图表图例位置/字体 |
| `slide_update_chart_series_style` | 更新指定系列的填充/线条/标记样式 |
| `slide_update_chart_title` | 更新图表标题文本/字体/可见性 |
| `slide_update_group_shape_properties` | 更新分组视觉或变换属性 |
