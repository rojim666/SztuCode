---
name: tencent-local-office-edit
description: 通过本地 editor_sdk 实时读写本机磁盘上的 Office/WPS 类型文件——文件打开后用户在编辑器中实时可见，编辑所见即所得，保存用 save_file 即可、不要主动 close_file。适用于本地 doc/docx/dot/wps/wpt、xls/xlsx/xlt/csv/tsv、ppt/pptx/pps/pot 等文件的打开、编辑、保存与新建；含宏格式可打开但宏不执行，et/ett/dps/dpt 不支持。按 doc/sheet/slide 三类调用对应工具，调用任一编辑工具前先用 edsdk.py schema 查它单个的参数、不要凭摘要猜参数。所有操作经本目录 edsdk.py（python3 edsdk.py list/schema/call）封装，端点自动发现、上层无需关心底层细节。触发词：本地文档、本机 docx/xlsx/pptx/wps、Office/WPS 文件、editor_sdk、edsdk.py、本地编辑、实时编辑。
author: Tencent Docs
version: "0.0.5"
---

# 本地 editor_sdk MCP 应用

> 面向**本机磁盘文档**，通过本地 `editor_sdk` 进程的 MCP 服务读写。支持编辑的格式按三个品类归类：
> - **doc**：`.doc` `.dot` `.wps` `.wpt` `.docx` `.dotx` `.docm` `.dotm`
> - **sheet**：`.xls` `.xlt` `.xlsx` `.xltx` `.xlsm` `.xltm` `.csv` `.tsv`
> - **slide**：`.ppt` `.pps` `.pot` `.pptx` `.ppsx` `.potx` `.pptm` `.ppsm` `.potm`
>
> 打开时按文件内容（magic bytes）自动识别品类，扩展名仅作兜底。
> ⚠️ 这是**本地 Office/WPS 文件操作**通道，只操作本机磁盘上的文件。

### 格式限制

- **新建文件**：`create_doc` / `create_sheet` / `create_slide` 使用内置空白模板，分别新建 `.docx` / `.xlsx` / `.pptx`。
- **含宏格式**：`.docm` `.dotm` `.xlsm` `.xltm` `.pptm` `.ppsm` `.potm` 可按对应品类打开和编辑文档结构，但**宏不执行**，剥离宏后可能导致数据或样式差异。
- **不支持的 WPS 专属格式**：`.et` `.ett` `.dps` `.dpt` 当前不支持；需要先用 WPS 客户端另存为 `.xlsx` 或 `.pptx` 后再处理。
- **不属于本 Skill 的编辑范围**：`.xmind` 有独立 Mind Editor 但本目录未暴露 mind MCP 工具；`.pdf` / `.ofd` 仅查看，不提供编辑工具。

## 前置

- `python3`
- 本地 `editor_sdk` 服务已运行（默认从端口 39099 起探测）
- 所有调用都通过本目录的 **`edsdk.py`** 封装脚本完成（HTTP 直连 MCP 端点）：
  ```bash
  python3 edsdk.py list        # 验通：能列出工具即 OK
  ```
  > 未设置 `editor_sdk_port` 时，按顺序探测 `39099` 到 `39108` 共 10 个端口；命中后复用该端点。
  > 如需固定端口：`editor_sdk_port=40001 python3 edsdk.py list`（设置后只访问指定端口）。
  > 如服务启用鉴权，设置 `editor_sdk_token`。

## 🚧 强制流程（违反将导致参数错误 / 调用失败）

对任何 `doc_*` / `sheet_*` / `slide_*` 编辑工具：**渐进式按需查询，不要一次性拉全量 schema**。流程：

1. **读子文档**：如果是Word类任务，必须先读取[doc.md](./doc.md)。
2. **选工具**：从子文档（[doc.md](./doc.md) / [sheet.md](./sheet.md) / [slide.md](./slide.md)）的一句话清单里挑出要用的工具——这一步不需要命令，清单就是索引。
3. **只查该工具 schema**：`python3 edsdk.py schema <工具名>`，直接得到必填项与各字段说明（内部只取这一个工具，不会全量打印）：
   ```bash
   python3 edsdk.py schema doc_insert_text
   ```
4. **调用**：确认 `[✓]` 必填项与各字段语义后再调。

> 用到一个才查一个，没用到的工具不要预先查。未经 `schema` 查询直接拼参数调用，属于流程违规。

调用前自检（缺一不可）：

- ☐ 已对**本次要用的工具**跑过 `edsdk.py schema <工具名>`
- ☐ 已确认全部 `[✓]` 必填字段
- ☐ 已确认位置 / 坐标 / 单位约定（如 doc 的 UTF-16 偏移、slide 的磅(pt)）
- ☐ **【仅 `sheet_*` 写值工具】** 调 `sheet_set_range_value` / `sheet_set_range_value_by_csv` /
  `sheet_set_cell_value` 前，已用 `sheet_get_used_range` 探明真实已用区域边界
  —— 不得用肉眼观察、文件预览或上一次读取的行数去猜边界
- ☐ **【仅 `sheet_*`】** 已按用户意图选对分支（二者选一，见 `sheet.md` HARD RULE）：
  - **新增**（用户表达「新增 / 添加 / 再加 / 插入 / 追加」行或列）→
    已先调 `sheet_insert_dimension` 腾出空间，确认目标区域为空后再写，而不是直接覆盖已用区域
  - **修改**（用户明确表达「修改 / 替换 / 更正 XX」）→
    已先 `sheet_get_cell_data` 读回目标区域，确认要覆盖的内容与用户意图一致后再写

> 若你不确定某工具的必填参数，**默认你没查过**——先 `schema` 再调，不要凭子文档表里的一句话摘要猜参数。

## 约定 —— `edsdk.py` 三条命令

| 命令                                                        | 作用                                                                                   |
| ----------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `python3 edsdk.py list [doc\|sheet\|slide\|common]`         | 列出工具（工具名 + 一句话描述）；可按品类过滤                                          |
| `python3 edsdk.py schema <工具名>`                          | **按需**查单个工具的完整参数（required + 各字段说明）。加 `--raw` 附带原始 inputSchema |
| `python3 edsdk.py call <工具名> [k=v ...] [--json '{...}'] [--json-file args.json]` | 调用工具                                                                               |

入参写法：`key=value`（值优先按 JSON 解析：数字 / 布尔 / 数组 / 对象 / null，失败则当字符串）；
复杂 / 嵌套参数用 `--json '{...}'` 或 `--json-file args.json`（与 `key=value` 合并，同名键以后者为准）。

- **`file_id` 是一切编辑的入口**：先尝试 `get_pool_status`/ `create_*` 拿到工具返回的真实 `file_id`，再调品类工具（见下方强制流程）。`file_id` 是 pool 里实例的 key，**不一定是路径**——见下方「打开文档必须用 `present_files`」说明。
- **品类由文档类型决定**：`doc_*` 只能作用于 doc 文档，依此类推；类型不匹配会报错。
- **编辑后重新读取**：编辑后若要基于文档现状继续操作，先重新读取最新数据；不要沿用编辑前缓存的内容、位置或版本。
- **保存后不要主动关闭**：保存用 `save_file`；不要主动 `close_file`，除非用户明确要求关闭或确实需要释放资源。
- **源码 1:1 对应**：`doc_*` → `server/mcp/doc/`，`sheet_*` → `server/mcp/sheet/`，`slide_*` → `server/mcp/slide/`。

## 工作流：先打开文件，再编辑，最后保存

> ⚠️ **本套操作是实时、可视化的**——文件打开后用户正在实时查看编辑效果。
> **不要主动调 `close_file`**：保存用 `save_file` 即可，关闭会关掉用户正在看的视图、释放编辑器。
> 仅在用户明确要求关闭、或确实需要释放资源时才调 `close_file`。

> ⚠️ **打开文档必须用 `present_files` 工具**：要让用户在预览面板中看到文档，必须调用 `present_files` 把文件呈现给用户——不能只在回复里说「已打开」。`edsdk.py call open_file` **不会**在预览面板里打开文档：`open_file` 只在**后台** editor_sdk 里把文件读进内存，供 Agent 后续 `doc_*` 等工具编辑，**用户界面不会出现这份文档**（与 `present_files` 相反）。
>
> - **前端 / `present_files` → HTTP `/api/open`**：未指定 `file_id` 时服务端生成 **UUID**（如 `5dca3e56-389b-461e-88c6-...`）。之后 `get_pool_status`、以及编辑工具只传 `file_path` 时 `ResolveFileId`，都会反查到这个 UUID。
> - **`create_*`**：返回 `new_doc_...` / `new_sheet_...` 等可读 id。
>
> **`open_file` 与 `doc_*` 的区别**：`doc_*` 在 `file_id` 缺省时会 `ResolveFileId(file_path)`，路径已注册则 **复用已有实例（多为 UUID）**。`open_file` **默认不从 pool 找已有实例**（`open_with_existing` 未传或 `false`）：未显式指定 `file_id` 时 **强制用 `file_path` 字符串本身作 key**（如 `/abs/foo.docx`），从磁盘 **fresh open**（`OpenByChunks` 重读）；纯后台 MCP、无用户预览时，返回的 `file_id` 往往就是路径字符串。用户已在看文档时 **不要默认 `open_file`**——会再开一个与前端 SSE 订阅脱节的实例，看不到实时改动。
>
> **`open_with_existing`（仅 `open_file` 可选）**：默认 `false` = 不管 pool 里有没有同路径文档，都按上文 fresh open。传 `true` = 先问 pool「这个路径是否已打开」：有则 **沿用已有 `file_id`（多为 UUID）** 和内存里的文档，不再从磁盘重开；没有则与默认行为相同。找不到已有实例、或磁盘文件已更新时，服务端会清掉旧实例再重开。仅在 `get_pool_status` 查不到、但你确信该路径已在 pool 里时，才用 `open_file file_path=... open_with_existing=true`。
>
> ⚠️ **`present_files` 之后不要 `open_file`**（尤其默认 fresh open）：`present_files` 会在 editor_sdk 注册实例（**UUID `file_id`**）。此时应 **`get_pool_status` 按路径拿 `file_id`**，或从用户选区取 `file_id`，再直接 `doc_*`。重复默认 `open_file` 会再开实例——上传后用户中途点开侧边栏时尤其常见：模型先 `open_file`（key=路径）在改，用户点开生成 UUID 实例并订阅 UUID stream，模型若仍只用 `file_path` 可能命中「孤儿」路径实例，revision 推到 path stream，页面绑 UUID stream → **看不到实时改动**；改完 `save_file` 落盘至少能兜底。
>
> ⚠️ **`present_files` 返回的是文件地址，不是 `file_id`**：不能直接当 `file_id` 传给 `doc_*` / `sheet_*` / `slide_*`。`file_id` 来自 `get_pool_status`（已展示文档）、`create_*` 的返回，或**仅后台、无需用户预览**时 `open_file` 的返回值。传 `file_path` 给编辑工具时须与注册时 **字符串完全一致**（`./x.docx` ≠ `/abs/x.docx`）；`get_pool_status` 的 `file_path` 过滤会做规范化，编辑工具反查 **不会**。

```bash
# 1. 在预览面板呈现给用户（硬约束：必须调用 present_files）
present_files 工具：把 /abs/a.docx 在预览面板中打开给用户看
# 2. 从 pool 拿真实 file_id（不要 open_file）
python3 edsdk.py call get_pool_status --json '{"file_path":"<同上路径>"}'
#    → 在 editors 里取 file_id（多为 UUID）；后续编辑一律用这个 file_id，不再拼路径

# 3. 编辑（按品类调用，见下方子文档；调用前先 schema 查参数）
python3 edsdk.py schema doc_insert_text
python3 edsdk.py call doc_insert_text file_id=<上一步返回的 file_id> idx=0 text="hi"

# 4. 保存（file_path 省略则覆盖原文件）—— 到此即可，不要主动 close
python3 edsdk.py call save_file file_id=<上一步返回的 file_id>
```

> **`get_pool_status` 未命中时**（`present_files` 后偶发游离实例或尚未注册）：
> 1. 先再次尝试 `present_files`，然后用与 `present_files` **相同**的路径字符串再查一次；
> 2. 仍无则 `open_file file_path=... open_with_existing=true`（**不要**默认 fresh `open_file`）；
> 3. 仍失败再与用户确认路径。

## 通用工具（文件 / 会话管理，无品类前缀）

这些是**入口工具**，所有品类共用；具体编辑接口见各子文档。

| 工具 | 必填 | 说明 |
|---|---|---|
| `open_file` | `file_path`；可选 `open_with_existing`（默认 `false`）、`file_type`（`doc`/`sheet`/`slide`，可省略自动识别）、`password`、`image_dir` | **后台打开**本地文件（仅 editor_sdk 内存，**预览面板不展示**），返回 `file_id`。默认 fresh open（返回的 `file_id` 多为 `file_path` 本身）；`open_with_existing=true` 时复用 pool 里同路径已有实例（`file_id` 多为 UUID）。|
| `get_pool_status` | — | 查看 pool；**`present_files` 之后用它拿 UUID `file_id`**（`file_path` 过滤支持规范化匹配，比编辑工具的路径反查更宽容） |
| `save_file` | — | 保存到本地；`file_path` 省略则覆盖原文件 |
| `close_file` | `file_id` | 关闭编辑器、释放资源。⚠️ **实时可视化场景下不要主动调**——会关掉用户正在看的视图；仅在用户明确要求时调 |
| `create_doc` / `create_sheet` / `create_slide` | — | 从空白模板新建对应类型文档，返回 file_id |
| `shutdown` | — | 关停 editor_sdk 服务 |

## 品类编辑接口（按文档类型进入子文档）
`file_id` 拿到后，按文档类型调对应品类的工具（工具名带品类前缀）：
| 品类      | 文档类型                         | 工具数 | 子文档                 |
| --------- | -------------------------------- | ------ | ---------------------- |
| **doc**   | Word/WPS 文档类（doc/docx/dot/wps/wpt…） | 37     | [doc.md](./doc.md)     |
| **sheet** | Excel 表格类（xls/xlsx/xlt/csv/tsv…）    | 51     | [sheet.md](./sheet.md) |
| **slide** | PPT 演示类（ppt/pptx/pps/pot…）          | 77     | [slide.md](./slide.md) |
