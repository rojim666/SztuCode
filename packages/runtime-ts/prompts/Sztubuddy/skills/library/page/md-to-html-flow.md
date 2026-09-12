# 一键美化：非 html 节点 → html 节点（挂到原节点下）

> **职责**：把资料库里一个**非 html 节点**一键美化成一页可视化 html，并作为**原节点的子节点**挂载（父子关系）。按源节点 `kind` 分两条分支：
>
> | 源节点 | `kind` | 分支 | database |
> |---|---|---|---|
> | 文档（md 正文） | `doc` | **分支一 · md→html** | **不建、不关联** |
> | 表格（csv 导入的数据表） | `database` | **分支二 · csv→html** | **只读动态关联原表**（禁止任何写操作）；关联走独立的 `page_database_relation.py --action link` 调用（见 entry.md §6），**不用** `import_html --databases` |
>
> - 分支一：纯美化，产出自包含 html，直接挂到源 doc 下。
> - 分支二：美化 + 让 html **运行时动态从原 csv（database）读数渲染**；只做**可视化只读版本**，`databaseId` 硬编码为原表 id，**绝不写回原表**（无 `addRecord`）。

---

## 0. 触发与分支仲裁

### 入口（命中任一即进；须同时满足"美化意图 + 资料库节点目标"）

- **入口 A · 「一键美化」按钮**：宿主强制 `skill="library"` + `autoSend`，prompt 含「一键美化/可视化生成 …… HTML」+ `spaceId:` / `nodeId:` / `kind:`。
- **入口 B · 对话贴链接 + 美化意图**：用户给 `Sztubuddy.cn/space/...`（或 `staging...` / nodeId）+ 明确要「一键美化 / 可视化 / 做成汇报页 / 演示」。

> 缺任一条件即**不属于本文件职责**：只泛泛说"做个页面 / 写个 html"而无资料库节点目标，或源节点不是非 html 节点，均不在本流程范围内。

### kind 仲裁 + 取节点标识（`manage` 的 `space.workspace.node-info`）

> **一次拿全三个值**：`node-info --url <原文档链接>`（仅接受 `/space/d/{nodeId}` 形态；`/space/s/{spaceId}` 是空间不是节点，不适用本流程）一次返回 `kind` / `nodeId` / `spaceId`（见 `manage/entry.md`）。其中 **`spaceId` 是后续 `import_html.py` 挂到源节点下的必备参数**——`parentId` 需与其所属 `spaceId` 配套提交，缺 `spaceId` 服务端无法定位父节点、会回退到默认我的文档目录（挂载失败）。

| `kind` | 路由 |
|---|---|
| `doc` | **分支一**（本文件 §1） |
| `database`（csv 表） | **分支二**（本文件 §2） |
| `web` / `page` | 已是 html page，改样式走 `edit-flow.md`，**不在本流程** |
| 其它 / 目录 | 按 `manage/entry.md` 处理 |

---

## 1. 分支一 · md → html（kind=doc，不涉及 database）

### 执行铁序

```
① 净化门：确认 md 母本只含面向读者的成品内容，剥离 token / 工具轨迹 / 本地绝对路径
② 意图分流（见 §3）：先判纯视图转换 / 汇报 / 其他意图；默认纯视图转换，仅汇报意图才唤起面板取「场景 / 受众 / 风格 / 格式」
③ 读源节点正文：doc 模块按 nodeId 读正文，落为本地 md 母本
④ md_to_html.py 生成自包含 html（汇报意图映射面板回选为 --scene/--audience/--style/--format；纯视图转换默认不传 --scene/--audience，见 §4.0 内容要求）
⑤ import_html.py --parent-id=<源doc节点id> --space-id=<源节点spaceId> 导入，html 挂到源节点下
   （--space-id 取自 §0 node-info 返回；缺它会回退到默认我的文档目录、挂载失败）
```

> 完成即止：**不** `list_page_artifacts`、**不**建 database、**不**注入 SDK、**不**回绑。产物是一页纯静态自包含 html，作为源 doc 的子节点。

### 落库形态

```
doc（源节点，md 正文）
└── html（page 节点）   ← import_html --parent-id=<源doc节点id> --space-id=<源节点spaceId>
```

### 回执前自检

- [ ] 是否按 §3 完成意图分流（默认纯视图转换；汇报意图才唤起面板取场景/受众/风格）？
- [ ] 是否用 `md_to_html.py`（而非手写）生成 html？
- [ ] 是否遵守 §4.0 内容要求（图片零丢失、不掺无关内容、视觉气质随原文）？
- [ ] 交付前已走 `entry.md` §5.5 图片托管流程？
- [ ] 是否 `import_html.py --parent-id + --space-id`（两者配套）挂到源节点下并拿到 `KS_IMPORT_OK` 与访问 url？（缺 `--space-id` 会挂载失败、回退默认目录）

---

## 2. 分支二 · csv → html（kind=database，只读动态关联原表）

> 源 csv 节点即 `database` 节点，其 **nodeId 即 databaseId**。本分支不新建表，让 html 运行时用 `__SMART_PAGE__.database` **只读** SDK 从原表拉数渲染。

### 执行铁序

```
① 净化门：同 §1①
② 意图分流（见 §3）：同 §1②（默认纯视图转换，仅汇报意图唤起面板）
③ 读原表结构与少量样本（不读全表）：
     ../database/get_database_schema.py --database-id=<源节点id>                → 字段名/类型/选项
     ../database/query_database_record.py --database-id=<源节点id> --page-size 5 → 取前几行样本（仅用于判断可视化形态：表/看板/图表）
   据此构造"可视化母本"（图表/看板/卡片布局的 md 骨架，含字段语义，不写死数据行）
④ md_to_html.py 生成 html 骨架（汇报意图参数来自面板；纯视图转换默认不传 --scene/--audience，见 §4.0）
⑤ Agent 注入只读渲染脚本（见 §4）：
     硬编码 DATABASE_ID = <源节点id>；用 db.query / db.getSchema 拉数渲染；
     只读——禁止 addRecord 及任何写 / 改 / 删原表的调用
     数据全部来自运行时读取，禁 mock / fallback 兜底，读不到显示空态提示（见 §5 数据真实性红线）
⑥ lint：../page/lint_database_sdk_usage.py 校验 SDK 调用，并人工确认无 addRecord（见 §4 只读红线）
⑦ import_html.py --parent-id=<源节点id> --space-id=<源节点spaceId>   不传 --databases
     html 挂到源 csv 下；从 KS_IMPORT_OK 取 node_block_id 与 url
     （--space-id 取自 §0 node-info 返回；缺它会回退到默认我的文档目录、挂载失败）
⑧ ⑦ 成功拿到 node_block_id 后，单独建 csv ↔ html 关联（调用形态见 entry.md §6）：
     page_database_relation.py --action link --page-id=<node_block_id> --database-id=<源节点id>
```

### 落库形态

```
database（源节点，csv 表）
└── html（page 节点，可视化只读版）   ← ⑦ --parent-id 决定树形位置
        ├─ ⑧ --action link 登记 pageId=<html节点id> / databaseId=<源节点id>
        └─ 运行时 db.query({databaseId:<源节点id>}) 动态读原表渲染
```

### 回执前自检

- [ ] 意图分流（§3）、`md_to_html.py` 生成、`import_html.py --parent-id + --space-id`（配套）挂载三项是否完成？（缺 `--space-id` 会挂载失败）
- [ ] 是否遵守 §4.0 内容要求（图片零丢失、不掺无关内容、视觉气质随原文）？
- [ ] 交付前已走 `entry.md` §5.5 图片托管流程？
- [ ] html 中 `DATABASE_ID` 是否硬编码为**源节点 id**，数据是否**运行时 `db.query` 动态读取**（非写死）？
- [ ] 是否**只有只读调用**（`query`/`getSchema`/`getRecord`），**无 `addRecord`** 或任何写操作？
- [ ] html 数据是否**全部来自运行时读取**，无任何 mock / fallback 兜底数据？读不到时是否显示空态提示（而非假数据）？
- [ ] 导入时仅传 `--parent-id` + `--space-id`，再用 `page_database_relation.py --action link` 建立 csv ↔ html 关联？

---

## 3. 意图分流（§1/§2 两分支共用）

> §1/§2 执行铁序里的「② 」到这里落地：两条 kind 分支进入本节后，**先按用户意图分流再生成**。
>
> 术语区分：**「分支」=按源节点 kind 分的 §1 md→html / §2 csv→html；「意图」= 本节按用户诉求分的纯视图转换 / 汇报 / 其他**。默认意图是纯视图转换，不再一上来就套汇报面板。

### 3.0 意图判定（按用户输入，命中即定）

| 意图 | 触发 | 生成方式 | 详见 |
|---|---|---|---|
| **纯 html 视图转换**（默认） | 未提任何汇报/演讲诉求，只要求「一键可视化生成 HTML 页面 / 转成网页 / 做成 html / 美化成网页」等 | 忠实把原文转成一页可读 html，**不套汇报骨架、不唤起面板**、气质随原文 | §3.1 |
| **html 汇报** | 用户明确提到汇报 / 演讲 / PPT 化 / 演示 / 幻灯片 / 路演 / pitch / 述职 / 复盘汇报等 | 唤起结构化选择面板取「场景/受众/风格/格式」，走汇报骨架生成 | §3.2 |
| **其他意图** | 用户给出上述之外的明确诉求（如「做成产品介绍页 / 落地页 / 数据看板 / 简历页 / 按某风格做」等） | **按用户要求生成即可**，不强套汇报或固定模板 | §3.3 |

> 判定优先级：用户显式意图 > 默认。分不清是纯视图转换还是汇报时，默认纯视图转换，可一句话告知"也可做成汇报/演示版，需要的话告诉我"，不擅自套汇报。

### 3.1 纯 html 视图转换（默认意图）

**目标**：把原文（doc 正文 / csv 数据）**忠实、完整**地转成一页排版清晰、可读的 html，**不做汇报改写、不套四区骨架**。

- **不唤起选择面板**，`md_to_html.py` 默认 `--format page`、不传 `--scene`/`--audience`（场景/受众是汇报语义，纯转换用不到）。
- 遵守 §4.0「内容要求」。
- csv 分支（§2）在本意图下同样只做「原表数据的可读可视化视图」，仍遵守 §2 只读红线。

### 3.2 html 汇报意图

> 仅当 §3.0 判为「html 汇报」时，才唤起 Sztubuddy 结构化选择面板取得用户对下列维度的显式回选；未回选不得执行汇报生成。仅当宿主确无面板能力时才退化为文本三问。

```
① 场景：对上汇报 / 对齐决策 / 对外宣讲 / 复盘        （推荐：对上汇报）
② 受众：领导 / 同级 / 客户 / 全员                    （推荐：领导）
③ 风格：商务蓝 / 科技黑 / 清新绿 / 暖橙              （推荐：商务蓝，仅换配色）
④ 格式：翻页演示 / 滚动长页                          （推荐：AI 按内容判）
```

| 维度 | 面板选项 | 映射参数 |
|---|---|---|
| 场景 | 对上汇报 / 对齐决策 / 对外宣讲 / 复盘 | `--scene report/align/pitch/review` |
| 受众 | 领导 / 同级 / 客户 / 全员 | `--audience <文本>`（写页脚元信息） |
| 风格 | 商务蓝 / 科技黑 / 清新绿 / 暖橙 | `--style business/tech/fresh/warm` |
| 格式 | 翻页演示 / 滚动长页 | `--format presentation/page` |

> 推荐项只是默认高亮，**不等于**用户已选；默认值不得静默套用。
> **面板参数是给生成器的路由，不是页面内容**：受众/场景等回选仅按 §4.0「内容要求 2」写入约定的页脚元信息，不得糅进正文叙事。

**格式判定（长页 vs 演示）**

| 判定 | 触发 | 参数 |
|---|---|---|
| **PPT 演示** | 明说 PPT/演示/翻页；或 md 呈「H1 + 3~8 个 ≤150 字的 H2」；或受众=领导+场景=对上汇报 | `--format presentation`（见 §4.1） |
| **滚动长页** | 信息密度高（每节 >300 字/含表格代码）；说"报告页/长页"；无法压到 ≤8 页 | `--format page`（默认） |

### 3.3 其他意图

用户给出汇报之外的明确页面诉求（产品介绍页 / 落地页 / 数据看板 / 简历页 / 指定风格等）时，**按用户要求生成**：不唤起汇报面板、不套汇报骨架，AI 依据用户描述与原文自由组织版式。仍须遵守 §4.0「内容要求」与安全边界（§7）。

---

## 4. 基线生成器 md_to_html.py（纯本地，不触网/不读 token）

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/md_to_html.py" --md "<source.md>" \
  --out "<out.html>" --title "<主题>" --scene report --audience 领导 --style business --format page
```

> `--scene`/`--audience` 仅用于 §3.2 汇报意图；§3.1 纯视图转换默认**不传**（不传则不渲染场景/受众 meta，见 §4.0 内容要求 2）。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--md <path>` | 是 | 本地 md 母本路径 |
| `--out <path>` | 否 | 输出 html；缺省同目录 `<stem>.html` |
| `--title <str>` | 否 | 缺省取 front-matter `title` / 首个 H1 / 文件名 |
| `--scene <str>` | 否 | 仅汇报意图用：`report`/`align`/`pitch`/`review` |
| `--audience <str>` | 否 | 仅汇报意图用：受众提示（写页脚，不改结构） |
| `--style <str>` | 否 | `business`(默认)/`tech`/`fresh`/`warm`，仅换配色 |
| `--format <str>` | 否 | `page`(默认，滚动长页)/`presentation`(WBP 翻页演示) |

- 解析 front-matter → inline md → block md，H1/H2 切卡片，内联全部 css/js 产出**自包含** html。
- **mermaid 代码块**（```` ```mermaid ````）渲染成 `<div class="mermaid">`，加载 mermaid.js 期间显示 loading 占位；页面加载时按需从固定版本 CDN（国内镜像）动态加载画成图；无网/加载失败/超时才退回代码块文本（`data-mermaid-src` 兜底，零丢失；无 JS 环境有 `<noscript>` 兜底）。图内配色/连线/字体通过 `themeVariables` 运行时读取页面 `:root`（`--accent`/`--panel`/`--text` 等）动态套用，随`--style` 主题走、无需预置；外层 `.mermaid` 容器套 `--panel` 背景与圆角融入卡片。长页与演示两种格式均支持。
- 4 套主题仅换皮肤；滚动揭示动效对 `prefers-reduced-motion` 降级。
- 输出契约：成功 `KS_MD2HTML_OK <JSON>`（`{html_path,title,sections,format}`）；失败 `{"error":...}` exit 0。
- 视觉基线（长页/演示通用）见 `wbp-presentation-contract.md` §7；美化设计方法论见 `beautify-flow.md` §3。

### 4.0 内容要求（三种意图通用 · 生成 html 时必守）

1. **图片等资源零丢失**：原文（doc 正文 / md 母本）中的图片、附件引用，转换后必须完整保留并正确渲染，不得丢弃或替换成占位。图片按 `entry.md` §2 图片托管流程转内链后回写，不静默留空。
2. **不掺入与原文无关的内容**：只呈现原文本身的信息。汇报意图中用户所选的**受众 / 场景 / 主题**等面板参数，**只写入约定的页脚元信息区**（`--audience`/`--scene` 的既有落点），**不得**糅进正文标题、段落或叙事里；纯视图转换与其他意图更不得凭空添加原文没有的段落、结论、数据。
3. **视觉气质与配色随原文**：页面的视觉气质、色调、风格应**与原文内容匹配**（原文偏技术则冷色/克制，偏生活/品牌则暖色/活泼等），而非无脑套默认商务蓝。汇报意图以用户所选 `--style` 为准；纯视图转换与其他意图由 AI 依据原文题材选择贴合的配色气质。
4. **尊重用户显式诉求**：用户对内容有补充、增删或明确生成要求时（如新增某段、强调某数据、按某结构/风格组织），以用户指令为准，与之冲突的前 1~3 条默认约束让位；未提及的部分仍守前 1~3 条。

### 4.1 --format presentation（WBP 演示档）

> **何时用**：用户提到「演示 / 汇报 / 演讲 / PPT / 幻灯片 / 路演 / pitch」等场景时，格式判定（§3）走"翻页演示"，`md_to_html.py` 加 `--format presentation`；否则默认 `--format page`（滚动长页）。
>
> **主动询问**：若内容形态**适合演示**（如 H1 + 3~8 个短 section 的分段叙事）但用户**未选**该模式，可一句话询问「这份内容也适合做成翻页演示，是否改为演示模式？」，由用户决定，不擅自切换。

- 产物：`<main data-wbp-deck>` + `<section data-wbp-slide>` 分页；根标记 `<html data-wbp ...>`；每页 `<aside data-wbp-notes>` 逐字稿；不写翻页 JS（容器职责）。
- 切分：H1→cover；H2→section，按 16:9 盒高自动分页（长 section 拆续页）；末页 cta。
- CSS 动画挂 `.is-active` 触发，**不预隐藏元素**（浏览态无 `.is-active`，预隐藏会白屏）。
- 完整契约见 `wbp-presentation-contract.md`。

---

## 5. csv 分支 · 只读动态数据契约（仅分支二）

- **SDK 注入与方法 / 参数 / `FieldValue`**：见 `database-sdk-contract.md`（§1 注入、§2 方法、§4 Query、§6 FieldValue）。
- **动态读取渲染写法**：复用 `data-page-flow.md` §3 阶段 4 **情况 2（数据展示类）** 的 `db.getSchema` + `db.query` 渲染模板——本分支即其特化：`DATABASE_ID` 硬编码为**源 csv 节点 id**，只渲染、不提交。
- **schema / lint 校验**：按 `data-page-flow.md` §1.6 用 `../database/get_database_schema.py`（`--database-id=<源节点id>`）取真实 schema，再跑 `../page/lint_database_sdk_usage.py`。

### 只读红线（本分支唯一强约束，区别于 data-page-flow.md 的读写页）

| 约束 | 说明 |
|---|---|
| **只读方法** | 仅 `db.query` / `db.getSchema` / `db.getRecord`；**禁止 `db.addRecord`** 及任何写/改/删原表调用——本分支只产出可视化只读版本 |
| **databaseId = 源节点 id** | 硬编码为源 csv 节点 id，不新建表、不从别处拼|
| **数据/ schema 动态读取** | 运行时拉原表最新数据与字段渲染，不写死数据行；原表变化后页面重载即刷新 |
| **数据真实性（无 mock/fallback）** | 展示数据全部来自运行时 `db.query`/`db.getSchema`；禁止 mock 示例数据或 fallback 兜底假值，读取失败 / 无数据时显示空态提示（如"暂无数据"），不用假数据填充 |

> `lint_database_sdk_usage.py` 白名单含 `addRecord`，**只读约束需本分支自行把关**：lint 通过后仍须人工确认 html 内无 `addRecord`，且无硬编码示例数据行或 `catch` 里回填的兜底假数据。

---

## 6. 输出契约速查

| 脚本 | 成功 | 失败 |
|---|---|---|
| `md_to_html.py` | `KS_MD2HTML_OK <JSON>` | `{"error":...}` exit 0 |
| `import_html.py` | `KS_IMPORT_OK <JSON>`（含 `node_block_id`/`url`） | 静默 exit 0 |
| `get_database_schema.py` | `{"id","title","properties":[...]}` | `{"error":...}` exit 0 |
| `query_database_record.py` | `{"results":[...],"next_cursor","has_more"}` | `{"error":...}` exit 0 |
| `lint_database_sdk_usage.py` | `MINDX_DBSDK_LINT_OK` | `MINDX_DBSDK_LINT_FAIL <rule> <target>: <reason>` exit 2 |
| `page_database_relation.py` | 服务端 JSON 信封（`link` 含 `linked=true`） | `{"error":...}` exit 0 |

---

## 7. 安全边界

- `md_to_html.py` 纯本地，不触网/不读 token；仅处理用户显式给出的路径，不遍历目录、不接通配符。
- **mermaid 例外**：生成脚本本身仍纯本地不触网；仅产物 html 在浏览器**运行时**按需从固定版本 CDN（国内镜像）加载 mermaid.js 渲染流程图，用 mermaid 默认安全等级（strict）、不启用 htmlLabels，失败退回代码块。除此之外产物不引任何外部资源。
- md→html 渲染对文本做 HTML 转义；html 中不保留任何 token / 密钥。
- 分支二只注入**只读** SDK（`query`/`getSchema`/`getRecord`），仅硬编码 `databaseId`，绝不写回原表；写 DOM 不用 `innerHTML`。
- 网络脚本遵循 `SKILL.md` §调用方式与运行模式（客户端模式 token 走 stdin 首行 + `--token-stdin`）。
