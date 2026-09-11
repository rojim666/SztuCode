---
name: tencent-docs-sheet-generation
description: >
  从零生成 Excel/xlsx 工作簿。当用户请求"创建/生成/新建/做一份/from scratch"
  一个 XLSX 文件、且**没有源 .xlsx/.csv 文件**时使用。支持纯文字需求，也支持
  以 pdf/docx/pptx 附件作为内容参考（由 `extract.py` 抽取为 markdown）。
  本 skill 引导主代理读设计准则后直接写 openpyxl 脚本生成本地 xlsx，并用 recalc 校验公式零错误。
description_en: >
  Create an Excel/XLSX workbook from scratch when the user has no source XLSX or CSV file.
  Supports text-only requirements and PDF, DOCX, or PPTX attachments as content references.
  Guides the main agent to generate the workbook with openpyxl and validate formulas through recalculation.
---

# Excel 生成链路 (tencent-docs-sheet-generation)

本 skill 默认采用 **openpyxl 直写** 范式：主代理读取设计准则与范式后，**直接编写 openpyxl 建表脚本一次性生成整份工作簿**，不委派子代理。最终产出本地 xlsx 文件。

---

## 适用范围与拒绝条件

**适用**：

- 用户**没有提供**任何源 `.xlsx` / `.xls` / `.csv` 文件
- 用户表达明确的"创建/生成/新建/做一份"等意图
- 目标产出是单个 xlsx 工作簿
- 支持将参考素材用于从零生成本地工作簿
- 支持随附**本地** pdf/docx/pptx 附件作为内容参考（如"基于这份 pdf 帮我整理成 Excel"、"按这个 ppt 做一份汇总表"）
- 支持以**在线文档**（`docs.qq.com` 链接 / `file_id`，含跨品类的 doc / slide / 在线 sheet）作内容 / 样式参考（用 MCP 读取，见 Step 2）

**不适用**（routing 已过滤；如确实出现，告知用户并退出本 skill）：

- 用户实际给了源 xlsx / xls / csv（任何编辑场景） → 退出，让 routing 重新决策
- 用户要求生成 docx / pptx / md 等非表格 → 不在本 skill 范围
- **本地**附件类型非 pdf / docx / pptx（如 zip / 图片 / 本地 csv） → 告知用户当前仅支持 pdf / docx / pptx 本地附件（**在线文档参考除外**，走 Step 2 的 MCP 读取）

---



## 执行流程（5 步）

### Step 1: Reasoning & Naming

**核心：推断目标 title，全程不反问用户**。

从用户需求推断两样即可：**展示标题**与**落盘位置**。

- **推断标题**：从用户原话 / 附件名取一个简洁标题；用户明确指定的名字优先，实在无线索用 `workbook_<YYYYMMDD_HHMMSS>`。用户指定的是目录（"放到/放在/保存到"或目录路径）时只取作落盘目录，标题仍独立推断；只有显式文件名路径才拆 dirname/basename，并从 basename 去掉 `.xlsx`（避免 `Q1.xlsx.xlsx`、避免把整条路径当标题）。
- **`<sanitized_title>`**（文件系统用）：对**推断标题**（未截断）做 sanitize——删 `\ / : * ? " < > |`、trim 首尾空格、中间空格转 `_`、≤ 50 字符；只用于文件名 / 目录名，不碰路径分隔符。
- **`<title>`**（展示用）：即推断标题原样，用于 OOXML 显示标题。

产出本地 xlsx，纸面算出（写进脚本的必须是绝对路径）：

- **落盘目录**：用上面从文件名 / 路径拆出的目录；无则默认 cwd。`~` 先展开成绝对路径。
- `<output_xlsx>` = `<落盘目录>/<sanitized_title>.xlsx`（最终交付物）；**已存在则加 `_<YYYYMMDD_HHMMSS>`，不覆盖、不询问**。
- `<work_dir>` = 同目录下的 `.<output_xlsx 的 stem>.ref/`（基名与 `<output_xlsx>` 一致：撞名带了时间戳时同步带上，二者始终配对；存 build.py / extract 产物）。

> Step 1 只做纸面计算；工作目录在 Step 2 创建，其余文件按后续步骤生成。

### Step 2: 附件预处理

先建工作目录（本 skill 落盘的根——Step 2 参考产物、Step 4 的 `build.py` 都在其下）：`mkdir -p "<work_dir>"`。

再判断有无内容参考素材，按来源分流（**无参考 → 直接进 Step 3**）：

| 来源（如何识别） | 动作 |
|---|---|
| 在线文档参考（`docs.qq.com` 链接 / `file_id`，可能是 doc / slide / 别的在线 sheet；作为普通参考素材处理） | 用 MCP 读其**数据 + 样式**（doc 用文档读取工具；sheet 用 `read_table` / `get_cell_ranges` 含样式） |
| 本地 pdf/docx/pptx（消息里的文件路径 +「基于这份 pdf / 参照 docx / 按这个 ppt」等） | 用 `extract.py` 抽取（命令见下），落到 `<work_dir>/reference/<sanitized_input_stem>/`；`<sanitized_input_stem>` 为输入文件去扩展名后按 Step 1 sanitize 规则处理 |
| 本地非 pdf/docx/pptx（zip / 图片 / csv） | 见「不适用」段，不抽取 |

多个参考 → 逐个处理。

**extract.py**（Bash）：

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/excel-generation/scripts/extract.py" \
  "<input_file_absolute_path>" -o "<work_dir>/reference/<sanitized_input_stem>"
```

产物：`content.md`（文本，含图片引用）+ `images/`（原图）+ `thumbnails/`（PNG ≤600px，可直接 Read 看图）。`extract.py` **按需自动装**缺失依赖（勿手动 pip）；exit=0 成功，exit≠0（依赖 / 输入 / 格式问题，装失败为 exit=4）**把 stderr 原样转用户并中止**。

完成后进入 Step 3（参考内容在 Step 3 纳入原型判断）；写脚本时按需回看 `<work_dir>/reference/` 取具体数据。

### Step 3: 读设计准则与范式（动笔前必读）

> ⛔ **硬性规则——写 openpyxl 建表脚本之前，必须先 Read `${CODEBUDDY_PLUGIN_ROOT}/skills/excel-generation/references/schema_principle.md`，无例外。** 不读准则就写代码 = 任务失败。

按序读取，读完即据此直接写 Step 4 的建表代码（不另写设计文档）：

1. **Read `schema_principle.md`**——建表所有设计决策（sheet 结构、列、公式、样式、条件格式、数据策略）以它为准；用户明确要求与之冲突时，以用户要求为准。
2. **识别场景原型**——有参考素材时先纳入其内容（在线参考已在上下文；本地附件先 Read `<work_dir>/reference/<sanitized_input_stem>/content.md`，扫描件 / 图多辅看同目录 `thumbnails/`），据**用户意图 + 参考内容**按其 §1 判定原型。
3. **按 `schema_principle.md §1`「范式文件」列直接 Read `${CODEBUDDY_PLUGIN_ROOT}/skills/excel-generation/references/design_patterns/<范式文件>`，无需预先枚举目录**（组合场景读多个再融合；标"—用通用准则"或未命中则跳过，直接用通用准则）。pattern 是**可改编蓝图**、按需调整不僵化套用，且**只给场景布局/字段增益、绝不复制 `schema_principle` 的具体数值**；防错（公式坐标、布局锚点、空值/除零保护）仍以 `schema_principle` 为准。

### Step 4: 编写并执行 openpyxl 建表脚本

综合已读的准则、pattern 与用户需求，直接写一份 openpyxl 脚本一次性生成整份工作簿（用 Write 工具写入 `<work_dir>/build.py`；工作目录已在 Step 2 建好）。设计细节遵循 `schema_principle` 与命中 pattern、此处不复述；写代码时落实以下**执行机制 + 两条最易漏的防错**：

- **用 openpyxl**；脚本开头做「先 import、缺失才装」的幂等兜底，**不要无条件 `pip install`**（否则重跑循环每轮都白装一次、离线环境还会失败）：

  ```python
  try:
      import openpyxl
  except ImportError:
      import subprocess, sys
      subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "openpyxl>=3.1.0"])
      import openpyxl
  ```
- **颜色格式**：设计准则中的颜色统一采用 CSS `#RRGGBB`。用于 openpyxl 单元格样式或工作表标签色的 CSS 色值字面量只能出现在 `xl_color(...)` 参数内；静态颜色必须在常量定义时一次性转换并使用 `XL_` 前缀，后续直接使用该常量，不在调用点重复转换，禁止手工添加 `00` Alpha。图表颜色不使用本函数，按图表 API 要求传不带 `#` 的六位 RGB：

  ```python
  def xl_color(css_hex: str) -> str:
      value = css_hex.removeprefix("#").upper()
      if len(value) != 6:
          raise ValueError(f"Expected #RRGGBB, got: {css_hex}")
      return "FF" + value

  XL_PRIMARY = xl_color("#4472C4")
  XL_BORDER = xl_color("#BFBFBF")
  thin_side = Side(style="thin", color=XL_BORDER)
  ```
- **公式**用 Excel 公式字符串写入（`ws['B10'] = '=SUM(...)'`），交给 openpyxl 直接落格，**不在 Python 里算好再写死**；**写除法 / 比率公式时，字符串里当场带上分母空值和 0 值保护（§4.1），不能只在注释里写**。
- **复杂表先定坐标锚点**（标题 / 表头 / 数据 / 合计的真实行号），公式坐标、填充范围、条件格式范围都由锚点推导，不套用默认第 2 行（§2.3）。
- **写入 OOXML 标题**：`wb.properties.title = "<title>"`（显示标题）。
- **保存路径**：`wb.save("<output_xlsx>")`（Step 1 的最终交付路径）。
- **代码风格**：简洁、按 sheet/区块分节加简短注释；脚本末尾 `wb.save(...)`。

**执行脚本**（Bash）：

```bash
python3 "<work_dir>/build.py"
```

- exit=0 → 生成成功，进入 Step 5 校验。
- exit≠0 → 读 stderr 定位错误（多为 openpyxl API 用法/坐标问题），**改 `build.py` 后重跑**；openpyxl 安装失败则告知用户 `pip install openpyxl`。

### Step 5: 校验与交付
**本平台：recalc 校验公式零错误**。

**① 重算 + 扫错**（仅工作簿使用公式时执行；无公式则直接进入交付）：

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/excel-generation/scripts/recalc.py" "<output_xlsx>" 60
```

openpyxl 写入的公式只是字符串、**不带缓存值**；重算前这些单元格对 `load_workbook(data_only=True)`、pandas 以及**大多数预览器（含微信/邮件附件预览）** 都读作 `None`（显示空白）。因此含公式时必须重算成功才能交付。

脚本按三层降级补齐缓存值，返回 JSON 时用 `engine` 标明本次实际使用的引擎：

1. `libreoffice` —— 在隔离 profile 中用 LibreOffice 重算（权威引擎）
2. `formulas` —— LibreOffice 不可用时，使用已安装的纯 Python 引擎求值并把值回填进公式单元格（公式本身保留，Excel/WPS 打开后仍可编辑重算）；只有所有公式都得到单值缓存才算成功，多值/动态数组结果会明确失败，避免只回填 spill 首格却误报成功
3. 两者都不可用 → **无法产出缓存值**，按失败返回 `error`

Linux 受限环境中，LibreOffice 层可能因原生 socket shim 未获授权而转入后续降级。**代理不得自行设置 `SHEETAGENT_ENABLE_LO_SOCKET_SHIM=1`**；仅在用户或平台明确授权后才能开启。

`formulas` 缺失时默认不会下载依赖。**代理不得自行添加 `--allow-install`**；仅在用户或平台明确授权从 Python 包源下载依赖后，才能用该参数重跑。

判定只看 JSON，不必关心用了哪个引擎：

- `status=success`（`total_errors=0`）→ 通过，进入交付。
- `status=errors_found` → 按 `error_summary` 的错误类型与定位（`#REF!`/`#DIV/0!`/`#VALUE!`/`#NAME?` 等）**回到 `build.py` 改对应公式（补空值/除零保护、修坐标/引用）后重跑 Step 4，再重算**，直到零错误。
- 返回 **`error` 字段**（而非 `status`）→ 没有得到一套完整缓存值，文件里的公式仍可能空白或不完整，**禁止交付**。按 `error` 内容处置：LibreOffice 不可用且 `formulas` 缺失时，提示用户手动安装，或在获得明确授权后加 `--allow-install` 重跑；LibreOffice 重算超时则调大 timeout 重试；纯 Python 引擎拒绝多值/动态数组结果时，安装 LibreOffice 后重试，或把公式改写成逐格的标量公式。
- **拒绝重算**（`error` 含 `external_link_cells`）→ 工作簿链接了外部工作簿且缓存值已丢失，重算会破坏外链数据。本 skill 从零生成的表不应出现外链；若出现说明公式误用了外部引用，**回 `build.py` 去掉外部工作簿引用后重跑**，不要用 `--force` 强行重算。

**判定纪律（勿凭退出码判断）**：只有返回 `error` 的情况才非零退出，**`errors_found` 的退出码是 0**。所以绝不能把"命令 exit=0"当作通过 —— 必须读 JSON 里的 `status` 与 `total_errors`。

**timeout 语义**：第二个参数是「初始化隔离 profile + 执行重算」的**总预算**（秒），默认脚本内为 30，本流程传 60。只作用于 LibreOffice 层；纯 Python 降级层不受其约束。



**② 交付**：

```
已为您生成 <output_xlsx>，包含 <N> 个工作表：<sheet_names>。
```

---

## 错误处理

| 场景 | 处理 |
|---|---|
| `build.py` 执行 exit≠0 | 读 stderr 定位（openpyxl API / 坐标 / 依赖），改 `build.py` 后重跑；依赖装不上则提示用户手动 `pip install openpyxl` |
| `recalc.py` 报公式错误 | 回 `build.py` 修公式后重跑 Step 4 再重算；反复 3 次仍不过，停下向用户说明具体错误 |
| `recalc.py` 返回 `error` | 没有得到一套完整缓存值，公式在外部预览中可能空白或不完整 → **不得交付**；按 `error` 内容处置（`formulas` 缺失则手动安装，或获得明确授权后加 `--allow-install` 重跑 / LibreOffice 重算超时则调大 timeout / 多值或动态数组结果则安装 LibreOffice 或改写为逐格标量公式 / 外链拒绝回改公式），并向用户说明 |
