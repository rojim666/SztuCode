# SztuCode Python Runtime

This directory contains the Python daemon, CLI, Textual TUI, evaluation code,
tests, and Python project metadata.

Run commands from the repository root with `npm run daemon` or `npm run cli`.
For direct Python development, change into this directory and use `uv run`.

## 资料解析

`read_file` 和桌面聊天附件共用 `src/sztu_code/core/documents.py`，支持 PDF 文本层、
DOCX 正文和表格、XLSX 工作表和单元格、PPTX 文本和表格。解析在本机进行，
不依赖 Poppler、Microsoft Office 或网络服务。XLSX 公式保留表达式，不执行计算。

单个资料最大 20MB，提取正文最多 32K 字符，PDF/PPTX 最多 200 页，
Excel 每个工作表最多 10000 行；达到上限会在正文中明确标注截断。
扫描版 PDF 需要先做 OCR；加密 PDF 需要先解锁。图片、图表和复杂排版不作为文本还原。
旧版 DOC/XLS/PPT 请先转换为 DOCX/XLSX/PPTX。

桌面构建机需安装 `uv`。`desktop/scripts/prepare-runtime.js` 自动使用锁定依赖，
将 Python 解析器和所需运行库打包到桌面资源中，安装客户端的用户无需安装 Python。
单独准备解析器可运行 `node desktop/scripts/prepare-document-parser.js`。
源码开发可运行 `uv sync --project py-runtime --group desktop`，重启 Tauri 后测试附件；
仅刷新前端页面不会加载 Rust 端的更新。

## 办公智能体工具

Python Agent 和桌面端的 TypeScript Agent 均注册了以下工具，核心实现位于
`src/sztu_code/core/office.py`，桌面通过打包的 Python 程序调用同一实现。

- `read_document`：结构化读取 PDF、DOCX、XLSX、PPTX。返回来源位置、文件 SHA256、
  内容块和 `next_offset`。长段落分块，继续翻页可以读取上传预览截断后的内容。
  Word 包含嵌套表格和页眉页脚；Excel 可按工作表读取，保留单元格坐标、类型、
  数字格式和公式表达式；PPT 包含文本、表格、分组文本和演讲备注。
- `create_document`：DOCX 使用 `blocks` 创建标题、正文、列表、表格；XLSX 使用
  `sheets` 创建多工作表；PPTX 使用 `slides` 创建宽屏标题与正文幻灯片及备注。
- `edit_document`：以 `source` 为输入、`path` 为输出另存副本。Word/PPT 支持精确
  文本替换并保留未涉及的文本运行格式，Excel 支持指定工作表/单元格写值和公式。
  `source_sha256` 可检测源文件变化；`expected_matches` 检测替换目标是否符合预期。

写入工具沿用工作区权限和工作流写入范围约束。默认不覆盖已有文件；所有修改在内存中
完成后才保存，重开校验成功后再发布目标文件。`verification=saved_and_reopened`
表示结构校验，`visual_verified=false` 表示没有渲染验证版式。

桌面使用：先选择或创建项目，再上传办公资料并发送需求。发送时原始资料会复制到项目的
`.sztu/attachments/` 下，消息带有供工具继续读取的相对路径。原始文件不被修改。
纯浏览器模式当前仍只有图片/文本附件回退；完整办公附件流程使用 Tauri 桌面客户端。

可以直接提出：

- “读完这份 Word，把结论整理成一份新的项目周报。”
- “核对预算表中的各项金额，列出异常单元格，另存一份修订表。”
- “根据这些资料制作 6 页汇报 PPT，并补充每页演讲备注。”

运行办公回归测试：

```bash
uv run --project py-runtime pytest py-runtime/tests/unit/test_office.py
node desktop/scripts/prepare-document-parser.js
node --import tsx --test packages/runtime-ts/tests/office-tools.test.ts
```

桌面工具 schema 从 `office_contract()` 生成到
`packages/runtime-ts/src/office-contract.ts`；`test_typescript_schema_matches_python`
会验证两端契约一致，修改参数模型时需要同步生成该文件。
