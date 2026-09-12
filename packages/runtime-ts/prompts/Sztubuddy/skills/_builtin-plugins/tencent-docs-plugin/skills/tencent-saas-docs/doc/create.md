# doc 创建（在线文档 / Word）

> 上级：[../SKILL.md](../SKILL.md)。本页描述「从零创建 doc 文档」的工具与流程。精细编辑见 [edit.md](./edit.md)。

## 创建路径

### 1. 直接用 Markdown 创建（首选，简单快速）

用 `doc-mcp` 的 `create_with_markdown` 一步创建：

```bash
python3 tencentdocs.py tdoc_call doc-mcp create_with_markdown '{"title":"项目周报","markdown":"# 项目周报\n\n..."}'
```

或先用 `manage.create_file`（走 `tencent-saas-docs`）建空 doc，再用 [edit.md](./edit.md) 的 `insert_markdown` 等工具写入内容。

### 2. 先建空文档再精细写入

```bash
python3 tencentdocs.py tdoc_call tencent-saas-docs manage.create_file '{"title":"项目周报","doc_type":"doc"}'
```

拿到 `file_id` 后用 [edit.md](./edit.md) 的 `doc-mcp` 工具集写入与排版（`insert_markdown` / `insert_table` / `insert_image` 等）。

> 大量内容优先 `insert_markdown` 一键插入，再微调格式，减少网络往返与编辑冲突。
