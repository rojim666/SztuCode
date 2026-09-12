# doc（本地 Word 类）编辑接口

上级：[SKILL.md](./SKILL.md)。工具名带 `doc_` 前缀。

```bash
python3 edsdk.py list doc
python3 edsdk.py schema <doc_tool>
python3 edsdk.py call <doc_tool> file_id=<id> ...
```

完整工具清单和参数以服务端 `tools/list` / `schema` 实时返回为准；本文只记录 doc 特有的操作约定。

> 调用任何 `doc_*` 工具前，必须先执行 `python3 edsdk.py schema <工具名>`，确认必填参数、UTF-16 偏移和区间语义；下面的接口列表只用于选工具。
> 对参数拿不准时一律先查 schema，绝不凭记忆或下表摘要猜参数。复杂参数用 `--json '{...}'`。

批量插入或一次插入大量内容时，优先使用 `doc_insert_markdown`，把多段文本、标题、列表、表格等内容组织成一段 Markdown 一次写入；不要拆成大量 `doc_insert_text` / `doc_insert_paragraph` 调用。

## 位置规则

- 所有 `idx` / `begin` / `end` 都是全文 UTF-16 code unit 偏移，不是字节、行列号、
  段落序号或肉眼字符序号。
- 一个中文 / 英文字母通常各算 1 个 UTF-16 code unit；emoji、表格、字段等结构占位可能占用不同长度。
- 这些坐标不是靠数屏幕字符得出的；底层会包含段落结束符、表格、图片、
  字段等结构占位。
- `paragraph_index` 是人看的“第几段”序号，不能传给 `idx` / `begin` / `end`。
- 字符范围统一是左闭右开 `[begin, end)`，长度为 `end - begin`。直接使用
  `doc_find` 返回的 `begin/end`，不要手算。
- `doc_insert_comment` 的 `range_begin` / `range_end` 是批注锚点坐标，`range_begin==range_end` 表示点锚批注。
- 位置不要猜。优先用 `doc_find` / `doc_resolve_document_structure` / `doc_get_outline` / `doc_get_table_info` 等查询工具拿真实索引，或使用写操作返回值里的真实索引，不要自行推导。

## 坐标使用原则

- 查出来的 `idx` / `begin` / `end` 可以直接回填给写工具，不需要再换算。
- 连续插入时，优先使用上一次写接口返回的 `position` / `last_edit_index` / `end_index` 继续追加。
- 不确定坐标是否还有效：重新查询；不要沿用编辑前缓存的 index。

## 编辑后索引

插入、删除、替换都会让后续内容偏移，编辑前拿到的 `idx` / `begin` / `end` 在写操作后立即失效。

- 连续多处编辑时，每改完一处就重新查询最新索引。
- 多处替换优先用 `doc_find_and_replace`，不要自己手算多个范围连续调用 `doc_replace_text`。
- 如果必须按旧索引批量操作，尽量从文档后部往前处理。

## 接口列表

| 工具 | 说明 |
|---|---|
| `doc_compare_documents` | 对比两个已打开的 DOC 文档的内容和格式差异 |
| `doc_copy_format` | 格式刷：将源范围的段落属性和文本属性复制到目标范围 |
| `doc_delete_comment` | 删除指定批注；最后一条批注删除后同时清理对应锚点，不删除被批注正文 |
| `doc_delete_paragraph` | 删除 idx 所在的整个段落及其段落结束符 |
| `doc_find` | 查找文本所在位置，返回所有匹配位置的 begin/end 索引及上下文 |
| `doc_find_and_replace` | 查找并替换文本 |
| `doc_get_comments` | 获取 DOC 文档中所有批注 |
| `doc_get_images` | 获取 DOC 文档中所有图片的信息 |
| `doc_get_last_operable_pos` | 获取DOC文档正文最后一个可操作位置的索引，以及该位置前面最多10个字符的内容 |
| `doc_get_outline` | 获取DOC文档大纲,可以获取到文档标题、标题下内容范围 |
| `doc_get_paragraph_property` | 读取 DOC 文档指定位置 idx 所在「段落」的属性 |
| `doc_get_section_property` | 读取指定节的页面属性、范围及总节数 |
| `doc_get_text_property` | 读取 DOC 文档指定位置 idx 处生效的文本属性 |
| `doc_insert_border` | 在指定位置插入分隔符 |
| `doc_insert_comment` | 插入批注 |
| `doc_insert_footer` | 设置页脚文本内容 |
| `doc_insert_footnote` | 在指定位置插入脚注或尾注 |
| `doc_insert_header` | 设置页眉文本内容 |
| `doc_insert_html_content` | 在指定 idx 处插入一段 HTML 富文本 |
| `doc_insert_image` | 在指定位置插入图片 |
| `doc_insert_markdown` | 在指定位置插入 Markdown 格式内容 |
| `doc_insert_math` | 在指定位置插入数学公式 |
| `doc_insert_normal_link` | 插入普通链接 |
| `doc_insert_page_break` | 在指定位置插入分页符 |
| `doc_insert_section_break` | 在指定位置插入分节符，完整继承原节属性，可选下一页、下一栏、连续、偶数页或奇数页 |
| `doc_insert_paragraph` | 在指定 idx 处插入一个「段落分隔符」（paragraph break） |
| `doc_insert_paragraph_with_text` | 一步插入「带文本的段落」 |
| `doc_insert_text` | 在指定位置插入文本 |
| `doc_list_recent_ai_edits` | 列出当前 editor 实例最近通过 MCP 写工具产生的编辑 |
| `doc_modify_paragraph` | 修改已有段落的属性 |
| `doc_modify_section` | 修改指定节的页面尺寸、页边距、起始类型等属性 |
| `doc_replace_image` | 替换文档中已有图片为新图片 |
| `doc_replace_text` | 替换range范围内的文本为指定文本 |
| `doc_resolve_document_structure` | 获取文档结构树 |
| `doc_revert_revision` | 反向指定版本号(target_version)的 revision 改动 |
| `doc_set_page_number` | 设置页码（在页脚中插入 PAGE 字段） |
| `doc_to_image` | 将本地 DOC/DOCX 渲染为逐页 PNG 图片；直接传文件路径，无需先打开 |
| `doc_undo_ai_edit` | 根据最近 AI 编辑记录中的 version 撤销指定编辑 |
| `doc_update_text_property` | 更新指定字符范围内的文本属性 |

### Table 相关工具

> 操作表格前建议先读 [table.md](./doc/table.md)：选型决策树 + 铁律 + 字段语义，最少调用次数、最低 token 消耗。
>
> 操作表格前优先用 `doc_list_tables` / `doc_get_table_info` 拿到 `table_id`，后续操作用 `table_id` 定位最稳；`table_id` 拿不到再退回 `idx`。

| 工具 | 说明 |
|---|---|
| **查询** | |
| `doc_list_tables` | 列出文档所有表格摘要（拿 table_id） |
| `doc_get_table_info` | 查询单张表格完整信息（含 cells） |
| **插入** | |
| `doc_insert_table` | 插入空表格，返回 table_id |
| `doc_insert_table_row` | 插入单行（可同时填内容） |
| `doc_insert_table_rows` | 批量多位置插入多行 |
| `doc_insert_table_column` | 插入单列（可同时填内容） |
| `doc_insert_table_cols` | 批量多位置插入多列 |
| **删除** | |
| `doc_delete_table_row` | 删除一行 |
| `doc_delete_table_column` | 删除一列 |
| `doc_delete_table` | 删除整张表格 |
| **合并 / 拆分** | |
| `doc_merge_table_cells` | 合并单元格 |
| `doc_unmerge_table_cells` | 拆分单元格 |
| **设置内容 / 属性** | |
| `doc_set_table_cells` | 批量设置单元格内容与样式（文本/格式/链接/图片） |
| `doc_set_table_properties` | 修改表格属性与布局（边框/对齐/宽度/内边距/行高列宽） |


> 参数 schema 以服务端 `tools/list` 实时返回为准；上表为一句话摘要。
