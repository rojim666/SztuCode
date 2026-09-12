# smartcanvas（智能文档 / MDX）

- service：`tencent-docs`
- endpoint：`https://docs.qq.com/openapi/mcp`
- 调用：`python3 tencentdocs.py tdoc_call tencent-docs <工具> '{"file_id":"<id>",...}'`

> 上级：[SKILL.md](./SKILL.md)。内容为 MDX；先 read/find 拿 Block，再 edit。
> 创建用 `create_smartcanvas_by_mdx`（走 `tencent-docs`）。
> MDX 语法规范见 [smartcanvas/mdx_references.md](./smartcanvas/mdx_references.md)；
> 参考模板位于插件根共享目录：`../../shared/smartcanvas/template/`。

| 工具 | 说明 |
|---|---|
| `create_smartcanvas_by_mdx` | 通过 MDX 创建智能文档（创建入口，不支持 `parent_id`） |
| `smartcanvas.edit` | 编辑智能文档 |
| `smartcanvas.find` | 根据文本搜索智能文档中的Block，返回匹配Block的ID和MDX格式内容 |
| `smartcanvas.get_top_level_pages` | 查询文档的顶层页面列表 |
| `smartcanvas.read` | 获取智能文档指定页面的MDX格式内容，支持分页读取，用于阅读和理解文档全文 |

> 用户要保存/上传 Markdown 内容时，直接填 `create_smartcanvas_by_mdx` 的 `mdx` 参数——MDX 向下兼容全部 Markdown，无需转换。
