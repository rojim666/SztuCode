---
name: tencent-saas-docs
description: 【仅企业版账号可用】腾讯文档企业版（saas.docs.qq.com）-在线云文档平台。适用前提：当前用户已开通腾讯文档企业版（SaaS / OneID）；个人 QQ / 微信账号请改用 tencent-docs skill，本 skill 会直接返回 ERROR:identity_mismatch。是企业账号下创建、编辑、管理文档的首选 skill。涉及"新建/创建/编辑/读取/查看/搜索文档"、"企业文档"、"团队文档"、"saas.docs.qq.com"等操作，请优先使用本 skill。支持能力：(1) 创建各类在线文档（文档/Word/Excel/幻灯片/思维导图/流程图/智能表格/收集表）(2) 管理知识库空间（创建空间、查询空间列表）(3) 管理空间节点、文件夹结构 (4) 读取/搜索文档内容 (5) 编辑操作智能表 (6) 编辑操作在线文档 (7) 文件管理（重命名、移动、删除、复制、导入导出）(8) 网页剪藏、本地文件/文档上云。
homepage: https://saas.docs.qq.com/home
---

# 腾讯文档企业版 MCP 使用指南

> 本 skill 面向**腾讯文档企业版**（`saas.docs.qq.com`），通过 MCP 对云端文档进行管理与编辑。

> 🚨 **多 endpoint 架构**：能力分散在 4 个独立 MCP endpoint 上，**调用前认准 service 名**——
> doc / sheet / slide 的精细编辑分别走 **`doc-mcp`** / **`sheet-mcp`** / **`slide-mcp`**，
> 文件管理 / 创建 / 搜索 / 剪藏 / smartcanvas / smartsheet 走主服务 **`tencent-saas-docs`**。
> 4 个 endpoint 共用同一套宿主票据。

## 前置：鉴权 / 调用方式

本 skill 运行在 `tencent-docs-plugin` 插件中，**鉴权完全依赖宿主（如 Workbuddy 连接器）注入的票据**，
不走 OAuth 授权页。所有工具调用一律走 `tencentdocs.py` 的 `tdoc_call` 入口（纯 Python 标准库，跨平台，Windows 无需 bash/curl），由它在调用时通过 HTTP header
即时透传票据到服务端，**不落盘**。详见 [references/auth.md](./references/auth.md)。

首次使用前执行一次环境检查：

```bash
python3 tencentdocs.py tdoc_init
#   READY            → 已就绪，直接干活
#   ERROR:no_token   → 请在宿主（Workbuddy）中完成腾讯文档授权后重试
```

调用任意工具：

```bash
python3 tencentdocs.py tdoc_call <service> <tool> '[json_args]'
```

> 🚨 **调用任何工具前，必须先查它的参数定义，严禁凭记忆/猜测拼参数**：
> ```bash
> python3 tencentdocs.py tdoc_schema <service> <tool>   # 输出该工具描述 + 参数（✓=必填）
> ```
> 按 `tdoc_schema` 返回的参数名/类型/必填项构造 `json_args` 再 `tdoc_call`；需要原始
> JSON Schema 加 `--raw`。工具清单用 `tdoc_list <service>`。

| service | endpoint | 工具范围 |
|---|---|---|
| `tencent-saas-docs` | `https://saas.docs.qq.com/api/v6/open/agent/mcp` | 通用工具（manage / smartcanvas / smartsheet / scrape / 创建类） |
| `doc-mcp` | `https://saas.docs.qq.com/api/v6/doc/mcp` | doc（Word）精细编辑，工具名无 `doc.` 前缀 |
| `sheet-mcp` | `https://saas.docs.qq.com/api/v6/sheet/mcp` | sheet（Excel）精细编辑，工具名无 `sheet.` 前缀 |
| `slide-mcp` | `https://saas.docs.qq.com/api/v6/slide/mcp` | slide（PPT）精细编辑，工具名带 `slide_` 前缀 |

> 查看某 endpoint 的真实工具清单：`python3 tencentdocs.py tdoc_list <service>`；
> 查单个工具的参数定义：`python3 tencentdocs.py tdoc_schema <service> <tool>`。

## 能力总览

### A. 文档列表 / 空间管理 ·（`tencent-saas-docs`）

跨品类的文件与空间管理（增删改、移动、搜索、权限、导入导出、网页剪藏、知识库空间），**不区分文档类型**。
完整工具清单见 [manage.md](./manage.md)；知识库空间见 [references/space_references.md](./references/space_references.md)。

> **`file_id` 的来源在这里** —— 一切内容操作都先在本类工具里拿到目标文档的 `file_id`。

### B. 文档内容操作（按品类分 5 类）

每个品类的具体工具清单、用法、**所属 endpoint** 见对应子文档（编辑 / 创建分开）：

| 品类 | 说明 | service | 编辑 | 创建 |
|---|---|---|---|---|
| **doc** | 在线文档（Word 类） | `doc-mcp` | [doc/edit.md](./doc/edit.md) | [doc/create.md](./doc/create.md) |
| **sheet** | 在线表格（Excel 类） | `sheet-mcp` | [sheet/edit.md](./sheet/edit.md) | [sheet/create.md](./sheet/create.md) |
| **slide** | 幻灯片（PPT 类） | `slide-mcp` | [slide/edit.md](./slide/edit.md) | [slide/create.md](./slide/create.md) |
| **smartcanvas** | 智能文档（Block / MDX） | `tencent-saas-docs` | [smartcanvas.md](./smartcanvas.md) | [smartcanvas.md](./smartcanvas.md) |
| **smartsheet** | 智能表格（多维表） | `tencent-saas-docs` | [smartsheet.md](./smartsheet.md) | [smartsheet.md](./smartsheet.md) |

> ⚠️ **doc / sheet / slide 别用主服务的转发工具**——一律走对应 engine endpoint
> （`doc-mcp` / `sheet-mcp` / `slide-mcp`），主服务的同名转发是阉割子集，能力不全。

### C. 创建类入口 ·（`tencent-saas-docs`）

| 用户意图 / 关键词 | 品类 | 首选创建方法 | 参考 |
|---|---|---|---|
| PPT / 幻灯片 / 演示文稿 | slide | slide 品类创建（🚧 待补充） | [slide/create.md](./slide/create.md) |
| 思维导图 / 脑图 | mind | `create_mind_by_markdown` | [references/diagram_references.md](./references/diagram_references.md) |
| 流程图 / 架构图 | flowchart | `create_flowchart_by_mermaid` | [references/diagram_references.md](./references/diagram_references.md) |
| 报告 / 笔记 / 文章 / 总结 / 纪要 / Markdown | smartcanvas | `create_smartcanvas_by_mdx` | [smartcanvas.md](./smartcanvas.md) |
| 论文 / 公文 / 合同等专业 Word | doc | doc 品类创建 | [doc/create.md](./doc/create.md) |
| 数据表格 / 计算 / 统计（Excel） | sheet | sheet 品类创建 | [sheet/create.md](./sheet/create.md) |
| 结构化数据管理 / 多视图表格 | smartsheet | smartsheet 品类创建 | [smartsheet.md](./smartsheet.md) |
| 收集表 / 表单 | form | `manage.create_file` | [manage.md](./manage.md) |
| **空文件 / 上述品类创建失败的兜底** | — | `manage.create_file` | [manage.md](./manage.md) |

### D. 上云 / 公共能力

| 场景 | 工具 / 脚本 | 参考 |
|---|---|---|
| 本地文件一键上云 | `python3 import_file.py` → `manage.apply_upload` → `manage.complete_upload` → `manage.query_task` | [manage.md](./manage.md) |
| 网页剪藏（URL → 文档） | `manage.scrape_url` → `manage.scrape_progress` | [manage.md](./manage.md) |
| 获取文档内容 / 上传图片 | `manage.get_content` / `manage.upload_image` | [manage.md](./manage.md) |
| 不支持能力上报 | `report_unsupported_feature` | 见下「核心规则」 |

## 核心规则

- **🚨 PPT / 幻灯片编辑强制走 `slide-mcp`**：对**已有 PPT 做编辑修改**时，必须用 `slide-mcp` 的 `slide_*` 工具
  （见 [slide/edit.md](./slide/edit.md)）。**严禁**用 doc / 主服务通用工具改 PPT——它们不支持 slide 内部结构
  （shape_id / page_index / 母版等）。从零创建整份 PPT 见 [slide/create.md](./slide/create.md)（🚧 待补充）。
- **先定品类再选工具**：用 `manage.query_file_info` 或文档链接前缀确定文档类型，再路由到对应品类工具集；
  严禁用 A 品类工具改 B 品类文档。
- **优先批量写入**：对同一文档连续 3 次及以上写入时，必须用批量接口一次提交
  （如 `smartsheet.add_records` / `set_range_value` / 批量插入类），严禁单条循环调用。
- **保存 Markdown 内容**：直接填 `create_smartcanvas_by_mdx` 的 `mdx` 参数，MDX 向下兼容全部 Markdown，无需转换。
- **本地文件落盘**：一律 `python3 import_file.py` → `manage.apply_upload` → `manage.complete_upload` → `manage.query_task`，保留原文件结构，
  不要用 `create_*` 重新生成内容。
- **整理 / 归档 / 转写 / 纪要**：把对话内容落云端时优先 `create_smartcanvas_by_mdx`（排版美观、组件丰富）。
- **URL 链接**：单独走 `manage.scrape_url` → `manage.scrape_progress` 剪藏通路。
- **`node_id` 即 `file_id`**；删除空间节点谨慎（`delete_space_node` 默认仅删当前节点，`all` 递归删子节点）。
- **异步任务用 spawn 子会话轮询**：`scrape_url` 等异步任务推荐 spawn 子会话专职轮询，主会话保持响应。
- **找不到能力先上报**：用户需求无对应工具时，静默调用 `report_unsupported_feature`（`{"feature":"..."}`，走 `tencent-saas-docs`）上报后再说明，不要臆造调用。
- **工具清单以服务端为准**：本文档工具表可能滞后，权威来源是各 endpoint 的 `tdoc_list <service>`。

## 常见错误码

| 错误码 | 类型 | 处理 |
|---|---|---|
| `400001` | 参数校验错误 | 确认 `file_id` / `content` 等参数 |
| `400006` | Token 鉴权失败 | 票据无效/过期，由宿主（Workbuddy）刷新后重试，见 [references/auth.md](./references/auth.md) |
| `400007` | 调用次数已耗尽 | 引导升级专业版：https://saas.docs.qq.com/scenario/saas-website-payment.html |
| `400014` | 需要升级专业版 | 引导升级专业版：https://saas.docs.qq.com/scenario/saas-website-payment.html |
| `-32601` | 接口不存在 | 用 `tdoc_list <service>` 确认工具名 |
| `-32603` | 参数错误 | 确认 `file_id` / `content` 等参数 |
