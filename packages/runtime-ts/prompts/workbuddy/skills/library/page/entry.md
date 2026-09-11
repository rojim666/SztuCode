# page —— 数据页面品类入口


## 模块定位

- **HTML 解析**：抽取表单 / 列表字段，输出 canonical schema（含 needs_database level）
- **HTML 改造**：为页面接入 database 数据读写能力，使表单可提交入库、列表可从 database 动态拉取
- **HTML 上传**：单文件 / zip 包导入到资料库，挂载到指定父节点
- **Page 编辑**：拉取已托管 Page 产物，基于事务只上传改动文件并提交新版本
- **联动建表**：为数据页联动建表 / 变更 schema / 读写记录，使页面与 database 打通

## 与其它模块的关系

| 模块 / 能力 | 关系 |
| --- | --- |
| `database` 模块 | page 跨模块调用完成建表 / schema 变更 / 记录读写，用法以 `../database/entry.md` 为准；**禁止**复制其逻辑 |
| `manage` 模块 | 共享 `library/_common.py`（runtime 分派 / token 读取 / HTTP / URL 拼接 / 脱敏 / 退出）；页面评论读取复用 `manage/get_node_comments.py`；在线 HTML 里的第三方图片托管复用 `manage/upload_image.py --url`（见 §2 图片托管） |

## 生成类请求总入口：默认在线 page 与静态/动态总闸

用户提出「生成 HTML / 做个网页 / 做汇报 / 出报告 / 做分析页 / 可视化 / 做单页应用」等**从零生成一个可看页面**的诉求，且未点名外部产品、未明确只要本地文件时，默认终态是**资料库在线 page**——本地 HTML 只是中间产物，停在「已生成到本地 `/Users/...html`」视为任务未完成。本模块只承接单页展示页和单页数据应用；建站、多页应用、带路由前端工程交主 agent，不走资料库单页 page。

进入具体流程前，先按业务意图判断是否需要配套 database（**看意图不看字面**：「做个页面给团队看」不等于动态，「做个能随时加条目的清单页」才是动态；静态/动态只决定是否建立配套 database，两者最终都落资料库在线 page）：

| 意图信号 | 判定 | 落地形态 | 入口 |
|---|---|---|---|
| 纯展示：汇报、报告、总结、讲稿、图文长页、可视化叙事，数据只用于讲述、不需持续增删改 | **静态网页** | 单 HTML 长页或演示页，无 database | 已有资料库节点走 §7；无现成节点、本地素材或泛化生成意图走 §8 → `beautify-flow.md`；已有 HTML 走 §9 |
| 需要持续管理数据：看板/dashboard、运营页、名单/清单/台账、卡片墙、有筛选排序，或后续要增删改内容、换图、加条目 | **动态网页（带 database）** | HTML + 配套 database，字段可增删改并与页面双向同步 | 走 §9 → `data-page-flow.md`；字段动态化和图片字段分别见 §11.1、§11.2 |
| 复刻现有 page："做同款 / 照着这个做 / 克隆 / 复刻 / 跟它一样 / 再做一份"，并附带 page 链接 / nodeId / 发布态短链 | **HTML 产物复刻** | 新建等价副本（html + 关联 csv/database），不动源 page | **§4.5 复刻**（`clone-flow.md`）——命中复刻意图**永远优先**走本行，不进 §7 / §8 / §9 |
| 不确定 | 先看有没有「后续改数据 / 换图 / 加条目」信号：有则动态，无则静态；仍不清时默认静态，并告知可按需升级为带数据表的动态版本 | — | — |

> 与「制作可视化 HTML / 本地素材做成页面 / 汇报分享」重叠时，优先走 §8 `beautify-flow.md`，统一执行文档美化、多端自适应（§4）和播放器意图分流（§5），再按上述总闸选择静态或动态链路。已有 HTML 进入 §9 后，另按 §9.2 的技术预判选择具体分支。

## 能力总览

> 各脚本（`parse_html` / `lint_schema` / `lint_database_sdk_usage` / `import_html` / `md_to_html` / Page 事务与发布 / `page_database_relation` 等）的触发时机、命令用法与 stdout 协议，在下方对应流程文档及 §1–§8 正文就近说明，按任务查阅：

| 文档 | 用途 |
| --- | --- |
| `data-page-flow.md` | **数据页分支能力主体**：§0 数据库需求预判询问文案、§1 通用 canonical schema 规则（含 §1.5.5 database 绑定标注·唯一权威、§1.6 字段映射自检 / lint 用法）、§3 改造分支（已有 HTML）阶段步骤 + HTML 改造模板、§5 创建分支（无 HTML）阶段步骤（仅上传不建表，已内联 §9.4） |
| `import-flow.md` | **HTML / ZIP 导入通用流程**：目录打包、`import_html.py` 参数、重导入定位、结果判定、自动预览；各分支上传步骤引用它 |
| `md-to-html-flow.md` | **非 html 节点一键美化能力**：md→html 分支（`kind=doc`，纯美化、无 database）/ csv→html 分支（`kind=database`，只读动态关联原表、禁写回）/ 选择面板硬门 + md_to_html.py + 挂到源节点下 |
| `wbp-presentation-contract.md` | **PPT 演示生成契约**：`--format presentation` 的 WBP native 档结构、属性速查、四区结构、逐字稿规则、`.is-active` 页内动画、设计系统；database 绑定标注引用 `data-page-flow.md` §1.5.5 |
| `edit-flow.md` | 已托管 Page 编辑流程：事务协议、产物下载、改动上传、commit 冲突处理 |
| `clone-flow.md` | **HTML 产物复刻流程**：取产物 + 并行下载 / 依赖探测分流 / 分支 A 纯 HTML 直传 / 分支 B 数据页（复制表 + databaseId 重映射 + 挂载）/ 循环依赖破解 + 并发兜底 |
| `html-parse-spec.md` | HTML 解析策略与 canonical schema 输出规范（9 种策略 + 多策略合并 + 置信度 + canonical 输出格式 + 附录：兜底场景数据源识别优先级） |
| 本文 §6（`page_database_relation.py`） | Page ↔ Database 数据关联绑定管理：查/建立/解除「某 page 引用了哪些 database、某 database 被哪些 page 引用」的关联登记（读写服务端独立关联表，非父子节点·非目录归属） |

---

## 1. 本地解析、校验与导入

根据任务按需读取，不要把全部参考同时加载：

| 任务 | 工具 | 读取 |
|---|---|---|
| 从现有 HTML 推断 canonical schema 与 Database 需求 | `parse_html.py --html <path>` | `html-parse-spec.md` |
| 校验 schema 与 selector | `lint_schema.py` | `data-page-flow.md` §1.6 |
| 校验已绑定 Database 的 HTML SDK 调用 | `lint_database_sdk_usage.py` | `database-sdk-contract.md` |
| 无 HTML、按需求创建数据页 | 跨 `database` 模块建表后生成 HTML | `data-page-flow.md` §5 |
| 新建或重导入 HTML/ZIP | `import_html.py` | `import-flow.md` |

最短调用：

```bash
python3 "${CODEBUDDY_SKILL_DIR}/page/parse_html.py" --html "<page.html>"
python3 "${CODEBUDDY_SKILL_DIR}/page/lint_schema.py" --schema "<canonical-schema-json>" --html "<page.html>"
python3 "${CODEBUDDY_SKILL_DIR}/page/lint_database_sdk_usage.py" --schema-file "<database-schema.json>" --html "<page.html>"
python3 "${CODEBUDDY_SKILL_DIR}/page/import_html.py" "<page.html>"
python3 "${CODEBUDDY_SKILL_DIR}/page/import_html.py" "<page.html>" --databases '[{"id":"<databaseId>"}]' --space-id "<spaceId>"
python3 "${CODEBUDDY_SKILL_DIR}/page/import_html.py" "<page.html>" --space-id "<spaceId>" --parent-id "<parentId>"
```

- **强制前置（在线 HTML 图片托管）**：任何产物是在线 page 的链路，调用 `import_html.py` 前，最终 HTML 必须已过 §2「图片托管」编排 + 自检硬门（无任何指向第三方域的 http/https 外链残留）。这是所有导入入口的统一收口点，不允许任何支路绕过。
- `--node-block-id` 只用于覆盖更新已有节点；编辑已托管 Page 不用它，必须走 §4 增量事务。
- 导入的完整约束（单文件/后缀/大小限制、token、目录打包、`--file-name` 命名兜底、`--databases` / `--space-id` / `--node-block-id` 用法、lint 适用范围、结果判定与自动预览）统一见 `import-flow.md`；`import_html.py` 成功输出 `KS_IMPORT_OK <JSON>`，向用户给返回的 `url`，不回显上传凭证 / 签名 URL / 原始响应。

---

## 2. 图片托管（在线 HTML 交付前置 · 强制）

> **适用范围**：所有要发布成在线 page 的 HTML（§1 导入入口 + §4 编辑已托管 page），在 `import_html.py` 调用前 / 事务提交前必过本节；最终 HTML 不允许残留第三方图源外链。
>
> **存量外链（需求 4.6）**：编辑已托管 page 时，页面里的存量第三方外链一并纳入本节托管；已发布的历史页不主动回改，仅在用户本次编辑、重新提交新版本时顺带托管化。

### 执行铁序

1. **提取** HTML 中所有 `<img>` 标签的静态图片引用（`src` / `srcset`）。
2. **判定每个引用是否第三方外链**：
   - 相对路径 → 跳过（非外链）。
   - `http:` / `https:` / 协议相对 `//` 的绝对链接 → 取其 host 判断：host 含 `codebuddy` 或 `workbuddy` 关键字 = 平台内链，跳过；否则 = 第三方外链，需托管。
3. **转内链**：调用 `manage/upload_image.py --url` 转内链（脚本用法见 `manage/entry.md` §`manage/upload_image.py`（图片上传基础组件）），取返回 `json.url` 回写到对应 `<img>` 的 `src` / `srcset`；不向用户回显上传凭证 / 签名 URL。
4. **失败登记**：转链失败 → 记入失败清单，不静默、不留空白占位（见下方「失败交代」）。

### 交付前自检（硬门 · 收口前必跑）

只针对 `<img>` 标签静态引用：先框定 `<img>` 标签 → 抽 `src`/`srcset` 里的 host → 按 host 过滤平台内链，仍有输出即残留：

```bash
grep -Eoi '<img[^>]+>' "<final.html>" \
  | grep -Eoi "(src|srcset)[[:space:]]*=[[:space:]]*[\"'][^\"']*(https?:)?//[^\"']+" \
  | grep -Eoi "(https?:)?//[^/\"')[:space:]]+" \
  | grep -Eiv 'codebuddy|workbuddy'
```

- **无输出 = 合格** → 放行 `import_html.py` / 事务提交。
- **有输出 = 不合格** → 回炉重跑编排；连续失败进入「失败交代」。
- 范围外（本自检不覆盖，如页面有这类图源需人工/后续脚本处理）：CSS 背景图 `url(...)`、`<source>`、`<video poster>`、JS 动态注入的 `img.src`。

### 失败交代（不静默、不用占位糊弄）

- **用户指定图片**：明确告知哪几张未能托管、原因、页面对应位置如何处理（换一张 / 手动传 / 接受留空）。
- **用户未指定图片**：先尝试找符合主题的可用图；仍失败按上述交代。

---

## 3. 能力 · 读取已托管 Page 内容

### 触发

用户要求读取 / 查看 / 总结 / 定位一个已托管 Page（`kind=web`）的内容，并给出
`nodeId` 或 `/space/d/<nodeId>` 链接时，走本能力。

Page 内容来自静态产物（HTML/CSS/JS）；只读流程直接拉取产物文件。

### 调用形态

```bash
# 1. 查询最新版本与产物列表；可加 --version <版本号> 查询指定版本
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/list_page_artifacts.py" --token-stdin --node-id "<page_node_id>"

# 1'. 查询发布态（对外定格版本）产物列表；固定取 meta.publishVersion，无 --version 入参
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/list_page_publish_artifacts.py" --token-stdin --node-id "<page_node_id>"

# 2. 按 list 响应中的 data.url + artifacts[].path 下载产物到当前任务工作目录
```

下载后在 `<work_dir>` 下的 HTML/CSS/JS 中搜索目标文本；入口 HTML 通常可从
`list_page_artifacts.py` 返回的 `data.artifacts` 判断。

- **编辑态 vs 发布态**：`list_page_artifacts.py` 取的是编辑态最新（或 `--version` 指定）版本，用于读取 / 编辑当前草稿；`list_page_publish_artifacts.py` 取的是**已发布对外的定格版本**（`meta.publishVersion`），用于查看用户实际访问到的发布内容。二者产物结构一致（`data.url` + `data.artifacts[].path`，已过滤内部文件 `janus.data.json`）。
- 若目标 page **从未发布过**，`list_page_publish_artifacts.py` 返回错误码 `Code_ERR_PAGE_NOT_PUBLISHED`（页面尚未发布，非资源不存在）；此时应引导用户先走 §5 `publish_page.py` 发布，或改用 `list_page_artifacts.py` 读编辑态内容。

---

## 4. 能力 · 编辑已托管 Page

### 触发

用户要求修改一个已经导入 / 发布在 WorkBuddy Page 平台上的页面，并给出 `nodeId` 或
`/space/d/<nodeId>` 链接时，走本能力。它不同于 `import_html.py` 的整包重导入：
本流程会基于后端 Page Agent 事务协议，只上传被修改的产物文件。

### 流程文档

编辑已托管 Page 是独立流程，完整协议映射、命令形态、stdout 契约、并发处理与安全边界见 `edit-flow.md`。

入口只负责路由；按 `edit-flow.md` 的标准编辑流程执行。

---

## 4.5 能力 · HTML 产物复刻（clone-flow）

### 触发

用户要求把一个**已存在的已托管 Page** 复刻 / 克隆一份到资料库（"做同款 / 照着这个做一份 /
克隆 / 复刻 / 跟它一样"），并给出该页面的 `/space/d/<nodeId>` 链接、裸 nodeId 或发布态短链
`/p/<nodeId>` 时，走本能力。命中复刻意图的分流硬门见顶部总闸表。

区别于 §1 `import_html`（导入**本地**文件）和 §4 编辑（改**原页面**）：复刻从**远端产物**拉取，
新建一份等价页面，不改动源页面。纯展示页直传复刻；接了 database 的数据页先复制表、
再重映射 databaseId、最后挂载。

### 流程文档

复刻为独立流程，完整分支铁序（分支 A 纯 HTML / 分支 B 数据页）、取产物 + 并行下载、
databaseId 重映射硬门、循环依赖破解与并发兜底见 `clone-flow.md`。

入口只负责路由；`read_file` 读取 `clone-flow.md` 全文后按其执行。

---

## 5. 能力 · 发布 / 取消发布 Page

### 触发

> **发布触发词严格白名单**：仅当用户**明确说「发布」/「部署」**（含 publish / deploy）才执行 `publish_page.py`。「让别人看 / 分享 / 公开」等模糊表述**不触发发布**——协作态链接本身即可分享，此类诉求按 §5.1 引导。

- 明确说「发布」/「部署」 → `publish_page.py`
- 「取消发布 / 下线 / 不要公开了」 → `unpublish_page.py`
- 模糊对外意图但未明说发布 / 部署 → 不发布，走 §5.1

### 调用形态

```bash
# 发布 Page —— 返回公开访问 URL
python3 "${CODEBUDDY_SKILL_DIR}/page/publish_page.py" --token-stdin --node-id "<page_node_id>"

# 取消发布 Page —— 发布链接将不再可访问
python3 "${CODEBUDDY_SKILL_DIR}/page/unpublish_page.py" --token-stdin --node-id "<page_node_id>"
```

- **默认不发布**：所有生成 / 导入 / 复刻链路产出的都是**协作态（编辑态）page**，交付协作态链接 `/space/d/<nodeId>` 即完成（收尾见 `import-flow.md` §8）；发布是独立动作，仅上方触发词命中时才执行。
- 需要对目标节点有管理员权限。
- `publish_page.py` 成功输出 `KS_PAGE_PUBLISH\t<publishUrl>`；向用户回执发布链接。
- `unpublish_page.py` 成功输出 `KS_PAGE_UNPUBLISH\tOK`；向用户确认已取消发布。

### 5.1 模糊发布意图 → 引导，不代替用户发布

用户表达了模糊的对外 / 发布倾向（"让别人也能看""能不能让外面访问""做成网站？"）但**没明说「发布」/「部署」**时：**不自动发布**，先把已生成的协作态链接给他，再说明发布入口。话术示例：

> 资料库 HTML 已经生成，可以在右上角点击发布，部署为独立网站。

仅当用户随后明确回「发布 / 部署」才走本节 `publish_page.py`。

---

## 6. 能力 · Page ↔ Database 关联关系管理

### 触发

维护「某个 page 引用了哪些 database」/「某个 database 被哪些 page 引用」这类关联登记时，走本能力。它读写服务端独立的关联关系表（`page_database_relation`），与 §1 `import_html.py --databases` 在导入时顺带写入的关联同源，可在导入之外单独增查删。三个操作由单一脚本 `page_database_relation.py` 承载，用 `--action` 区分：

| 意图 | `--action` |
|---|---|
| 登记 page 引用了某个 database（"把这个页面和这张表关联起来"） | `link` |
| 查 page 关联了哪些 database / database 被哪些 page 引用（"这个页面用了哪些表""这张表被哪些页面引用"） | `list` |
| 解除某条 page ↔ database 关联（"取消关联""这个页面不再用这张表了"） | `unlink` |

### 调用形态

```bash
# 建立关联（pageId、databaseId 都必填；幂等，重复建立返回 linked=true）
python3 "${CODEBUDDY_SKILL_DIR}/page/page_database_relation.py" --token-stdin --action link \
  --page-id "<page_node_id>" --database-id "<database_id>"

# 查询关联（pageId、databaseId 至少传一个）
#   只传 pageId → 该 page 关联的所有 database
#   只传 databaseId → 引用该 database 的所有 page
#   两者都传 → 精确匹配
python3 "${CODEBUDDY_SKILL_DIR}/page/page_database_relation.py" --token-stdin --action list --page-id "<page_node_id>"
python3 "${CODEBUDDY_SKILL_DIR}/page/page_database_relation.py" --token-stdin --action list --database-id "<database_id>"

# 解除关联（pageId、databaseId 都必填；幂等，关联不存在时 deleted=0）
python3 "${CODEBUDDY_SKILL_DIR}/page/page_database_relation.py" --token-stdin --action unlink \
  --page-id "<page_node_id>" --database-id "<database_id>"
```

- `--page-id` 支持直接传 `nodeId` 或 `/space/d/<nodeId>` 形态链接，脚本自动抽取 `nodeId`。
- 成功时 stdout 直接输出服务端 JSON 信封（`list` 的 `data.relations` 按创建时间倒序，含 `pageId` / `databaseId` / `createdAt` / `updatedAt`）；失败输出 `{"error":"<msg>"}` 后 exit 0，不回显 token / 原始响应。
- 关系登记读新表，不含存量老数据；`link` / `unlink` 均为幂等操作，可安全重复调用。
- 与 `import_html.py --databases` 的关系：导入时传 `--databases` 会顺带写入关联；本能力用于导入之后**单独**补建 / 查询 / 解除关联，不改动 page 产物本身。

---

## 7. 能力 · 把非 html 节点一键美化为 html 节点（md_to_html）

### 触发

用户针对某个**资料库里的非 html 节点**（文档 / 表格）要求"一键美化 / 可视化生成 HTML / 做成汇报页 / 演示"时，走本能力：把该节点美化成一页 html，并作为**原节点的子节点**挂载。按源节点 `kind` 分两条分支（详见 `md-to-html-flow.md`）：

- **md→html**（`kind=doc`）：读节点正文作 md 母本 → `md_to_html.py` 生成自包含 html → 挂到源节点下。**不建、不关联 database**。
- **csv→html**（`kind=database`）：读原表 schema + 数据 → 生成可视化 html，运行时用**只读** `__SMART_PAGE__.database` SDK 从**原表**动态读数渲染（`databaseId`=源节点 id）→ 先 `import_html.py --parent-id + --space-id`（**不传 `--databases`**）挂到源节点下，再单独跑 §6 的 `page_database_relation.py --action link` 建立 csv ↔ html 关联。**只产出可视化只读版本，禁止任何写回原表的操作**。

区别于 §9 子分支（处理用户**已有的 HTML** / 从零创建数据驱动页面）：本能力的输入是**已存在的资料库节点**。

### 入口收紧（防与主 agent 抢生成）

本能力面向**针对某个资料库节点的显式"可视化 / 美化"诉求**，有两个标准入口（命中任一即进）：

**入口 A · 「一键可视化」按钮**：宿主强制 `skill="library"` + `autoSend`，prompt 为固定模式——含「**一键可视化生成 …… HTML …… 页面**」+ 三行 `spaceId:` / `nodeId:` / `kind: doc|database`。

**入口 B · 对话贴资料库链接 + 美化/可视化意图**：用户在对话里给出 WorkBuddy 资料库链接（`www.workbuddy.cn/space/...` / `staging.workbuddy.cn/space/...`，或直接给 `nodeId`），并明确要"**一键美化 / 一键可视化 / 做成汇报页 / 做成演示 / 美化成 PPT**"。此时先从链接解析出 `nodeId` → 用 `manage` 的 `space.workspace.node-info` 仲裁 `kind` → 按 `kind` 路由（与入口 A 一致）。

**品类路由（按 `kind`）**：
- `kind: doc` → **本能力 md→html 分支**：`doc` 模块按 `nodeId` 读正文作 md 母本 → `md_to_html.py`（长页 / 演示格式判定见 `md-to-html-flow.md` §3）。
- `kind: database` → **本能力 csv→html 分支**：读原表生成**只读可视化** html（`md-to-html-flow.md` 分支二）；若用户要的是**可增删改的业务数据页 / 看板**（非只读可视化），则走 §9 / `data-page-flow.md`。视觉基线复用 `wbp-presentation-contract.md` §7。
- `kind: web` → 已是 page 产物，"美化/改样式"走已托管 Page 编辑（`edit-flow.md`），不在本流程。

> **输入是已存在的资料库节点（按钮给 nodeId / 对话给链接），不是本地 md 文件**：第一步按 `nodeId` 读节点内容，**不要**让用户重贴正文。

> **anti-loose 硬判别（防抢生成）**：进本能力须**同时**满足——① 有明确的"可视化 / 美化 / 做成汇报页 / 演示"意图；② 有具体的**资料库节点目标**（按钮 `nodeId` 或对话里的资料库链接 / `nodeId`）。
> 二者缺一——尤其是对话里只泛泛说"做个页面 / 写个 html / 帮我可视化一下"而**没有指向某个资料库节点**——**不进本能力，交主 agent**，避免冲突或重复。

### 流程文档

一键美化为独立流程，完整分支铁序、选择面板硬门、挂载规范、csv 只读契约、安全边界见 `md-to-html-flow.md`。

> 进入本能力的第一步：`read_file` 读取 `md-to-html-flow.md` 全文，然后按 `kind` 走对应分支的执行铁序。**禁止只看本节摘要就开干**——本节只是路由指引，不是执行依据。

> - **md→html 分支**（`md-to-html-flow.md` §1）：净化门 → 选择面板 → 读正文 → `md_to_html.py` → `import_html.py --parent-id=<源节点id>` 挂到源节点下。**无 database 相关步骤**。
> - **csv→html 分支**（`md-to-html-flow.md` §2）：净化门 → 选择面板 → 读原表 schema+样本 → `md_to_html.py` 骨架 → 注入**只读** `db.query` 渲染（`databaseId`=源节点 id，禁 `addRecord`）→ lint → `import_html.py --parent-id=<源节点id> --space-id=<源节点spaceId>`（**不传 `--databases`**）→ `page_database_relation.py --action link` 建立 csv ↔ html 关联。

> 选择面板（场景/受众/风格/格式）是两分支共同的阻塞门；`import_html --parent-id` 挂到源节点下、形成父子关系是必达终态。详见 `md-to-html-flow.md` §1/§2/§3。

---

## 8. 能力 · 素材/意图一键美化生成 page（beautify-flow）

### 触发（比 §7 更前置、入口更宽）

§7 的 md→html 入口**收紧为**「必须指向已存在资料库节点」（按钮 nodeId / 对话贴 space 链接）。
本能力是那条限制的**合法补充入口**，承接「**没有现成节点、但用户要一页可视化 HTML**」的场景：

- **入口甲 · 制作可视化 HTML 意图**（非建站/应用）：用户说「做个可视化 HTML / 报告页 / 分析页 / 汇报页 / 把这段做成好看的页面」。
- **入口乙 · 本地素材 → 生成 HTML**：用户给本地 doc/ppt/pdf/excel/图片（单个或综合素材）并说「生成 HTML / 做成页面 / 美化 / 做成汇报分享」。
- **入口丙 · 明确汇报/分享场景**：要做汇报 / 周月季报 / 复盘 / 述职 / 路演 / 演示并要可分享页面。

### 不进本能力

- 给了**已存在资料库节点** + 可视化意图 → 走 §7（md-to-html-flow 入口 A/B）。
- 要**建站 / 多页应用 / 前端工程** → 交主 agent，不走资料库单页 page。
- 要**编辑已托管 page**（给 page 详情页/发布态链接要改）→ 走 §4 `edit-flow.md`。

### 流程文档

进入本能力后，`read_file` 读取 `beautify-flow.md` 全文，按其执行：
① 意图分流（静态可视化长页 / 动态数据页 / PPT 演示）→ ② 素材抽成 md 母本（依赖宿主读取能力）→
③ 套用文档美化设计规范 + 多端自适应硬约束生成 html → ④ 写入播放器分流标记 →
⑤ 复用 `md-to-html-flow.md` 导入挂载（静态长页 / 演示直接 import_html 导入；动态数据页走 data-page-flow.md 建库+关联）。

> **播放器意图分流**（`beautify-flow.md` §5）：presentation 档带 `data-wbp` → 专业演示播放器（翻页+提词器）；
> page 长页档带 `data-sp-mode="scroll"` → 全屏滚动浏览（无分页/提词器）。分流标记由 `md_to_html.py` 生成时写入。

---

## 9. 分支路由

> 按本节的分支判定选择路径，**只走一条分支**。本 entry.md 只承载路由与入口；
> 数据页各分支的阶段步骤、HTML 改造模板、字段映射约束、自检 checklist 见 `data-page-flow.md`（询问文案 §0、schema 规则 §1、改造分支 §3、创建分支 §5）；
> 各分支最后的**上传步骤统一走独立流程** `import-flow.md`（HTML / ZIP 导入）。
> HTML 解析策略与 canonical schema 输出规范见 `html-parse-spec.md`。

### 9.1 分支判定

```
创建分支 · 无 HTML（需求 → Database → Agent 写 HTML → 上传）
  ← 用户没有现成 HTML，仅描述了页面需求

仅上传 HTML / ZIP（不建表）
  ← 用户【显式】说「只上传 / 只导入 / 不建表」
  ← 或用户给的是 .zip / 文件夹

【其余给了 HTML 的场景】→ 先走 §9.2 数据库需求预判总闸
```

> **关键**：仅上传的触发**收紧为用户显式表达**。只要用户给了 HTML 但没明说"只上传"，一律先过 §9.2 预判。

### 9.2 数据库需求预判（公共总闸）

#### Step 1：调用 parse_html.py

```bash
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/parse_html.py" --html "<path/to/page.html>"
```

> 本次调用结果**全程复用**，后续若用户选择走改造分支，**不再重复调用** parse_html.py。

> **退化契约**：脚本无法工作时输出 `{}`，等同于 `level: "none"`，按 `none` 分支处理。

#### Step 2：按 level 分发

> **不要问技术路径问题**（"接在线表格还是传静态页""要建表吗"）——用户搞不清，也不该让他答。数据管理意图明确就直接做在线版本；只有真分不清才问**业务问题**。

| level | 动作 |
| --- | --- |
| `strong` | 数据管理意图明确（有表单/表格/预留接口）→ **直接走改造分支接数据，不询问**；动手时一句话告知即可（文案见 `data-page-flow.md` §0.1） |
| `medium` | 看不出是"要管理的数据"还是"一次性展示"→ **只问业务意图**（数据要不要随时改/多人维护，文案见 `data-page-flow.md` §0.2），由回复决定走改造分支或仅上传 |
| `weak` | **静默走仅上传**，不打扰用户 |
| `none` | **静默走仅上传**，不打扰用户 |

#### Step 3：识别用户回复（仅 medium 需要）

| 用户意图 | 落地分支 |
| --- | --- |
| 要管理数据（"要 / 随时改 / 多人维护 / 存数据 / 联数据"等） | **改造分支** |
| 就这一版展示（"不用 / 就这一版 / 只保存 / 只上传"等） | **仅上传** |
| 描述了具体字段（≥2 个名词） | **改造分支**，按用户描述构造 schema |
| 描述了页面需求（"帮我做一个报名页"） | **创建分支** |

### 9.3 分支入口

| 分支 | 进入条件 | 详细流程 |
| --- | --- | --- |
| **改造分支** | 用户回复想接数据 | `data-page-flow.md` §3 |
| **仅上传** | 显式仅上传 / weak / none | 见下方 §9.4（直接走 `import-flow.md`，不建表） |
| **创建分支** | 无 HTML，描述需求 | `data-page-flow.md` §5 |

> 改造分支 / 创建分支共用 `data-page-flow.md` §1（canonical schema 规则）；三条分支的上传步骤都走 `import-flow.md`（HTML / ZIP 导入流程，独立通用流程）。仅上传不建表、不涉及 schema，直接走 `import-flow.md`。

### 9.4 仅上传 HTML / ZIP（不建表）

仅上传不建表、不解析 schema，本质是"把本地文件导入资料库"，直接走 `import-flow.md`：

1. 从消息提取本地路径。远程 URL（http/https）**不命中**，引导用户先下载到本地。
2. 判断类型：
   - `.html` / `.htm` / `.zip` 单文件 → 直接进第 3 步
   - 目录 → 先按 `import-flow.md` §2 打成 zip，用 zip 路径继续，导入后 `rm -f` 清理
   - 其它（`.pdf` / `.md` / `.docx`）→ 不命中，引导先转 html 或打 zip
3. `--file-name` 默认**不传**（按 `import-flow.md` §4 兜底）；仅当用户明确指定展示名时才透传。
4. 按 `import-flow.md` 执行（不传 `--databases`）。
5. 回执：
   - 成功有 url：`已导入，访问链接：<url>。`
   - 成功无 url：`已导入，可到资料库中查看（node_block_id: <node_block_id>）。`
   - 失败：按 `error_handling.md` 错误码行动表生成回执。

---

## 10. 全局规则优先级（冲突时按以下顺序仲裁）

| 优先级 | 类别 | 范围 | 示例 |
| --- | --- | --- | --- |
| **P0**（最高） | 安全 / 降级约束 | §12「安全约束」 | 不向用户输出 token / Cookie / 接口原始响应；不向用户展示 token 管道细节（stdin 首行 token、管道写法、JWT 片段、“凭证已传入/已注入”） |
| **P1** | 强制回执 / 输出契约 | 脚本 stdout 协议（`KS_*` 前缀）；canonical schema 字段集合 | parse_html.py 输出的 canonical schema 必须按原结构入下游 |
| **P2** | 用户显式指令 | 用户消息中**明确**表达的偏好 | "用英文字段名"、"只上传，不要建表" |
| **P3** | 自检 checklist | `data-page-flow.md` §1.6「字段映射自检」 | OPTIONS_MAP 必须整段拷贝自脚本输出 |
| **P4** | schema 默认规则 | 字段名中文化、字段排序、选项 ID 由脚本生成 | |
| **P5**（最低） | 体验细节 | 文案风格、emoji、表格列数等 | |

---

## 11. HTML 侧 SDK 调用红线

在 HTML 写 `__SMART_PAGE__.database.*` 时，`databaseId` 必须硬编码（值来自 `create_database.py` 输出）。

```js
window.__SMART_PAGE__.database.query({
  databaseId: 'db_xxx',
});
```

HTML 侧 database SDK 协议详见 `database-sdk-contract.md`；跨模块脚本协议详见 `../database/entry.md`。

---

## 11.1 动态数据页 · database 字段可增删改并同步 html（诉求：字段非写死）

> **原则**：动态数据页（改造分支 / 创建分支）关联的 database 字段**不是写死的**——建表后仍可持续 **新增字段 / 删除字段 / 改字段名·类型 / 改记录**，且变更能同步反映到关联的 html page。

### 字段级变更（schema 演进）

| 变更 | 脚本（database 模块） | html 侧同步方式 |
| --- | --- | --- |
| 新增字段 | `../database/add_database_field.py`（`MINDX_FIELD_ADDED`） | html 侧 SDK 用 `db.getSchema()` **运行时动态读取字段/选项**，不写死；新字段渲染进对应列/卡片模板即生效 |
| 改字段名 / 字段类型 | `../database/update_database_field.py`（改类型或删已有 select/multi_select 选项可能清空存量单元格；团队确认时说明风险，见 `../database/entry.md` §2.2） | 字段名/类型由 `db.getSchema()` 动态读取，页面无需改码 |
| 删除字段 | `../database/delete_database_field.py`（`MINDX_FIELD_DELETED`，不可逆；确认规则按实际目标空间，见 `../database/entry.md` §2.3） | html 侧对缺失字段做空值降级，不报错 |
| 改字段选项（select/multi_select） | `add_database_field` / `update_database_field` 时给 options；已写入的 `option.id` 永久有效不可替换（见 `../database/entry.md` §13） | 选项由 `db.getSchema()` 动态取，页面无需改码 |

> **html 必须动态读 schema，不硬编码字段名之外的元数据**：`databaseId` 硬编码（§11 红线），但**字段列表 / 选项集** 由运行时 `db.getSchema()` 读取（见 `data-page-flow.md §3 阶段 4` / `database-sdk-contract.md`）。这样字段增删改后，页面下次加载即反映最新 schema，无需重生成 html。

### 字段变更后是否要动 html

- **仅改记录值** → 完全不用动 html（`__SMART_PAGE__.database` 运行时读最新值）。
- **新增/删除字段且页面需展示该列** → 若 html 用 `getSchema` 动态渲染表头/字段，通常无需改码；仅当页面是**固定版式**（写死了要展示哪些字段的 DOM 骨架）时，才走 `edit-flow.md` 增量补/删对应 DOM（见 §4，增量事务、非整包覆盖）。

---

## 11.2 图片展示 page · database image 字段链路（诉求：可持续换图）

> **判定**：page **有图片展示需求**时（素材含图 / 用户要「配图 / 图片墙 / 带图的卡片」），关联的 database **必须含 `image` 字段**，图片通过 image 字段映射到 page，支持后续**通过对话上传/更换图片**。

### 建表：含 image 字段

`create_database.py` 的 schema 里加 image 列（见 `../database/entry.md` §1 示例 `"照片": {"image": {}}`），为业务数据页的记录加 image 列，`value` 存图片 src。

### 对话上传图片 → 写入 image 字段 → 映射到 page

```
用户在对话给出本地图片（显式路径）
  │
  ├─(drive/upload_drive_file.py 或 page get-upload-credential + PUT)──> 拿到图片可访问 URL
  │     ← 图片上传复用 drive 模块能力；不把本地绝对路径写进 html/记录
  │
  ├─(database/batch_add_database_records.py 或 batch_update_database_records.py，image 字段填该 URL)──> 写入 database
  │     ← 新图片：add_record；换图：update_record 改对应记录的 image 字段
  │
  └─ html 运行时按字段读 image 字段的 URL → 渲染 <img src>（业务数据页由 db.query 读取后 setAttribute('src')）
```

### 持续换图

- 用户说「把第 N 张图换成这张」→ 定位对应记录 → `batch_update_database_records.py` 用单元素数组改 image 字段 URL → 页面下次加载即更新。
- **不直接手改 html 的 `<img src>`**（会被 SDK 覆盖，且不可持续）——改 database 记录才是持久做法。

> 图片字段值 / FieldValue 形态见 `../database/params-reference.md` §image；上传见 `drive/entry.md`。

---

## 12. 安全约束

- HTML 改造时不在 HTML 中保留明文密钥、Cookie、Token。
- schema 推断有歧义时**不猜测**，展示候选方案让用户选择。
- Page 编辑事务提交冲突时，禁止继续复用旧 transactionId。

---

## 13. 用户回执模板

| 操作 | 成功回执 | 失败回执 |
| --- | --- | --- |
| 仅上传 HTML / ZIP | `已导入，访问链接：<url>。` | 按 `error_handling.md` 错误码行动表生成回执 |
| 全链路 | `全链路完成：Database 已创建（ID: <database_id>），HTML 已改造并上传。访问链接：<url>。` | 按 `error_handling.md` 错误码行动表生成回执 |
| 创建页面 | `页面已创建：Database 已建（ID: <database_id>），HTML 已生成并上传。访问链接：<url>。` | `页面创建失败。` |
| 编辑已托管 Page | `页面已更新，新版本：v<new_version>。` | 按 `error_handling.md` 错误码行动表生成回执 |

被其它模块内部调用时**不单独回执**，直接消费脚本 stdout。

