# doc 编辑（在线文档 / Word）

- service：`doc-mcp`
- endpoint：`https://docs.qq.com/api/v6/doc/mcp`
- 调用：`python3 tencentdocs.py tdoc_call doc-mcp <工具> '{"file_id":"<id>",...}'`

> 上级：[../SKILL.md](../SKILL.md)。精细编辑走本 endpoint，工具名无 `doc.` 前缀。创建文档见 [create.md](./create.md)。

> 💡 **大量数据或 Markdown 内容优先使用 `insert_markdown` 一键插入**，再通过其他工具微调格式和样式，避免多次调用单个插入接口（如 `insert_text` / `insert_paragraph` / `insert_image` 等），以减少网络往返和编辑冲突风险。

| 工具 | 说明 |
|---|---|
| `accept_all_revisions` | 接受 Word 文档中的所有修订 |
| `compare_documents` | 对比两个 DOC 文档的内容和格式差异 |
| `copy_format` | 格式刷：将源范围的段落属性和文本属性复制到目标范围 |
| `create_with_markdown` | 用 Markdown 创建文档 |
| `delete_table` | 删除 Word 文档中的整张表格 |
| `find` | 在 Word 文档中查找指定文本 |
| `find_and_replace` | 在 Word 文档中查找所有匹配文本并直接替换为新文本 |
| `get_comments` | 获取 Word 文档中所有批注 |
| `get_images` | 获取 Word 文档中所有图片的信息 |
| `get_last_operable_pos` | 获取 Word 文档正文最后一个可操作位置的索引及前面内容 |
| `get_outline` | 获取 Word 文档大纲结构（标题层级树） |
| `get_paragraph_property` | 读取 DOC 文档指定位置 index 所在「段落」的属性 |
| `get_table_info` | 获取指定位置 idx 所在表格的整体信息 |
| `get_text_property` | 读取 DOC 文档指定位置 index 处生效的文本属性 |
| `insert_attachment` | 在 Word 文档指定位置插入附件 |
| `insert_border` | 在指定位置插入分隔符 |
| `insert_code_block` | 在指定位置直接插入一个代码块 |
| `insert_cols` | 在指定表格中批量插入多列 |
| `insert_comment` | 在 Word 文档指定范围内插入批注（评论） |
| `insert_footer` | 设置页脚文本内容 |
| `insert_footnote` | 在指定位置插入脚注或尾注 |
| `insert_header` | 设置页眉文本内容 |
| `insert_html_content` | 在 Word 文档指定 idx 处插入一段 HTML 富文本 |
| `insert_image` | 在 Word 文档指定位置插入图片 |
| `insert_markdown` | 在 Word 文档指定位置插入 Markdown 格式内容 |
| `insert_math` | 在指定位置插入由 LaTeX 渲染出的数学公式 |
| `insert_normal_link` | 在 Word 文档指定位置插入普通超链接，可指定链接 URL 和显示文本 |
| `insert_numbering` | 在 Word 文档中插入项目列表（编号/项目符号） |
| `insert_page_break` | 在 Word 文档指定位置插入分页符 |
| `insert_paragraph` | 在指定 idx 处插入一个「段落分隔符」（paragraph break） |
| `insert_paragraph_with_text` | 一步插入「带文本的段落」 |
| `insert_rows` | 在指定表格中批量插入多行 |
| `insert_table` | 在 Word 文档指定位置插入表格，需指定行数和列数 |
| `insert_task` | 在 Word 文档指定位置插入一个或多个任务（待办事项） |
| `insert_text` | 在 Word 文档指定位置插入文本 |
| `modify_paragraph` | 修改已有段落的属性 |
| `pre_insert_attachment` | 在 Word 文档中预插入附件，获取上传链接和 object_key |
| `replace_bookmarks` | 替换 Word 文档中书签标记范围的内容 |
| `replace_image` | 替换 Word 文档中的图片 |
| `replace_text` | 替换 Word 文档中指定范围内的文本为新文本 |
| `resolve_document_structure` | 获取文档的结构树 |
| `set_page_number` | 设置页码（在页脚中插入 PAGE 字段） |
| `set_table_layout` | 设置表格的行高 / 列宽 |
| `set_table_properties` | 修改表格属性 |
| `update_text_property` | 更新 Word 文档指定范围内文本的属性（仅修改样式，不改变文档内容长度） |
