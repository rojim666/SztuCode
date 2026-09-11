# doc 创建（在线文档 / Word）

> 上级：[../SKILL.md](../SKILL.md)。本页描述「从零创建 doc 文档」的工具与流程。精细编辑见 [edit.md](./edit.md)。

## 两条创建路径

### 1. 直接用 Markdown 创建（首选，简单快速）

用 `doc-mcp` 的 `create_with_markdown` 一步创建：

```bash
python3 tencentdocs.py tdoc_call doc-mcp create_with_markdown '{"title":"项目周报","markdown":"# 项目周报\n\n..."}'
```

或先用 `manage.create_file`（走 `tencent-docs`）建空 doc，再用 [edit.md](./edit.md) 的 `insert_markdown` 等工具写入内容。

### 2. 专业文档格式套用 / 排版美化（公文 / 合同 / 论文 / 公告等）

当用户需要将纯文本排版成**专业规范的 Word 文档**（公文、合同、通知、论文、散文等）时，
走 `doc_format` 格式套用管线——按场景识别 → 可选样式定制 → LLM 生成结构化内容。

格式模板与 prompt 位于本 skill 内：`./doc_format/`。
**执行前必须阅读** [./doc_format/README.md](./doc_format/README.md)，理解三步工作流，再按其中的 prompt 与模板执行：

- 场景识别 prompt：`./doc_format/prompt/scenario_recognition_prompt.txt`
- 纯文本转结构化 prompt：`./doc_format/prompt/pure_text_system_prompt.txt`
- 样式定制 prompt：`./doc_format/prompt/style_customization_prompt.txt`
- 各场景结构模板：`./doc_format/templates/{general,paper,contract,essay,government}.json`

> 创建后如需进一步精细调整格式 / 表格 / 图片，使用 [edit.md](./edit.md) 的 `doc-mcp` 工具集。
