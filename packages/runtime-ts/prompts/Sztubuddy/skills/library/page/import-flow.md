# page · HTML / ZIP 导入流程

> 把本地 HTML / ZIP 上传到资料库的通用流程。任何需要"导入本地页面文件"的场景（仅上传、改造分支/创建分支阶段 5 上传、演示档/长页导入）都走本流程。
> 由 `entry.md` 编排调用；`data-page-flow.md` 各子分支在"上传"步骤引用本流程。

## 1. 前置约束

> **强制前置 · 图片托管自检（导入统一收口点，不允许任何支路绕过）**：产物是在线 page 的链路，调 `import_html.py` 前，最终 HTML 必须已过 `entry.md` §5.5「图片托管」编排 + 自检硬门——`<img>` 的 `src`/`srcset` 无任何指向第三方域的 http/https 外链残留（平台内链 `codebuddy`/`Sztubuddy` 除外）。未过此门禁止调用导入脚本。执行铁序、自检命令、失败交代见 `entry.md` §5.5。

- 仅接受**单个文件路径**，后缀 `.html` / `.htm` / `.zip`，上限 50 MiB。
  - `.html` / `.htm`：单文件链路。
  - `.zip`：内含至少一个 `.html` / `.htm` 入口 + 同包资源，服务端解压批量落 cos。
- **目录不接受**（脚本 `os.path.isfile` 校验，目录会静默 `exit 0`）。用户给文件夹时按 §2 先打成 zip。
- 一次只处理一个文件，不遍历目录、不接受通配符。
- 服务端按字节流魔数识别 zip / html，与后缀无关；但文件名后缀仍应与内容一致。
- **token**：本地解析 / lint 工具（`parse_html.py` / `lint_schema.py` / `lint_database_sdk_usage.py`）不需要 token；`import_html.py` 等网络脚本按顶层运行模式添加 `--token-stdin`。
- **lint 适用范围**：静态页跳过 Database SDK lint；关联 Database 的页面必须先以服务端真实 schema 跑完两道 lint（见 `data-page-flow.md` §1.6）再导入。

## 2. 目录 → zip 打包（用户给文件夹时必走）

先把目录压成 zip，再传 zip 路径调脚本：

```bash
python3 -m zipfile -c "<out.zip>" "<dir>/"
```

约束：

- zip 内必须至少含一个 `.html` / `.htm` 入口；无入口时先和用户确认，不要打空入口 zip。
- html 引用的 css / js / 字体 / 图片全部打进同一 zip，保持相对路径一致（否则落 cos 后 404）。
- `<out.zip>` 用语义名（`<schema.title>.zip` 或目录 basename），不用 `tmp.zip`。
- `<out.zip>` 是中间产物，导入后 agent 自行 `rm -f` 清理。

完整工作流：

```bash
INPUT_DIR="/Users/xxx/dist"
OUT_ZIP="${TMPDIR:-/tmp}/mindx-import-$$.zip"
python3 -m zipfile -c "$OUT_ZIP" "$INPUT_DIR/"
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/import_html.py" "$OUT_ZIP" --file-name "<显示名.zip>"
rm -f "$OUT_ZIP"
```

用户已给 zip 时：跳过打包，直接按 §3 调脚本。

## 3. 调用导入脚本

```bash
# 默认（推荐）：不传 --file-name，脚本兜底命名
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/import_html.py" "<path-to-file.html>"

# zip 路径：用法同 html
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/import_html.py" "<path-to-file.zip>" --file-name "<显示名.zip>"

# 关联 database（全链路 / 创建页面 阶段 5 必传）
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/import_html.py" "<path-to-file.html>" --file-name "<schema.title>.html" --databases '[{"id":"<database_id>"}]'

# 重导入：带 --node-block-id，覆盖更新既有节点
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/import_html.py" "<path-to-file.html>" --node-block-id "<existing_node_block_id>"

# 重导入 + 重新挂载 database
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/import_html.py" "<path-to-file.html>" --node-block-id "<existing_node_block_id>" --databases '[{"id":"<database_id>"}]'

# 指定目标 space（仅首次导入生效）
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/import_html.py" "<path-to-file.html>" --file-name "<schema.title>.html" --space-id "<target_space_id>"
```

> 目标空间按顶层 `SKILL.md` 调用前置执行。`--space-id` 仅首次导入生效，重导入链路会忽略；显式传 `--parent-id` 时必须同时使用其所属的匹配 `--space-id`。

## 4. `--file-name`

- **默认不传**：脚本会在文件名无语义（`index`/`default`/`untitled`/`temp`/`page`/纯哈希/纯数字/极短名）时，自动从 HTML `<title>`/`<h1>` 抠语义名。
- **仅当有明确语义名要覆盖时才传**：如阶段 5 已有 `schema.title`，传 `--file-name "订单管理.html"`。
- 不要为"和本地文件名一致"而主动传 basename（会让兜底失效）。
- zip 路径不做语义抠取，直接保留传入名 / basename；要语义名需显式传 `--file-name "<语义名>.zip"`。

## 5. `--databases`

- JSON 数组字符串，每元素含 `id`（建 database 返回的 id）。
- 改造分支 / 创建分支阶段 5 上传时**必传**；仅上传不建表可不传。
- 重导入（带 `--node-block-id`）：不传 / 空数组 → 保持原关联；非空数组 → 增量挂载（不覆盖、不解除未列出的）。

## 6. `--node-block-id`（重导入定位）

- **不带** → 首次导入，新建节点，返回新 `nodeBlockId`。
- **带** → 重导入，覆盖更新该节点，沿用既有 node_block_id。

**该带**：当前轮 HTML 改造源于"上一轮 import_html.py 已成功输出过 node_block_id 的同一份原始 HTML"：

- 改造分支 / 创建分支阶段 4 改完 HTML 后用户说"改成 XXX 再传一次"→ 带最近一次的 `node_block_id`
- 仅上传场景用户说"改了重新传"→ 若上下文有上次 `node_block_id` 则带
- 用户主动给出 node_block_id → 按其要求带

**不该带**：

- 任何不同源的 HTML（即使文件名相同/内容相似）→ 会覆盖用户原 page，造成数据丢失
- 首次提到、上下文无 node_block_id → 首次导入

只有本人名下的 page 能重导入，误传他人 node_block_id 会被拒。

## 7. 结果判定

- stdout 出现 `KS_IMPORT_OK <JSON>` → 成功。
  - `<JSON>` 单行对象，含 `node_block_id`、`file_name`、`url`、`publish_url`。
  - 只解析前缀后的 JSON，不按空格拆字段（`file_name` 可能含空格）。
  - 提取 `node_block_id` 和（如有）`url` 用于回执。
- 无该输出 → 失败。
- 不回显 token / uploadUrl / cos header / 原始响应。

## 8. 成功后置动作（打开协作态链接，不发布）

- `<url>` 是**资料库协作态（编辑态）链接**，交付它即完成；**绝不调 `publish_page.py`**，不因"让别人看 / 公开 / 分享"自动发布（发布仅由 `entry.md` §5「发布 / 部署」触发）。
- 解析到非空 `<url>` → **必须**调宿主预览组件打开（优先 `present_files`，旧宿主兼容 `preview_url`），仅传 `<url>` 一个参数，本轮内完成、不等确认；不拼 token / node_block_id、不改用系统浏览器。
- **预览目标只能是资料库 `<url>`**，不把本地 .html 当预览目标。
- 宿主无预览组件 → 跳过、正常回执、不报降级；未解析到 `<url>` → 不预览，走"未拿到 url 的回执文案"。

## 9. 注意事项

- 多文件场景不支持：用户给多个路径时，按顺序逐个单独调脚本，分别给回执。
