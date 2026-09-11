# page · HTML 产物复刻流程（clone-flow）

> **职责**：从一个「产物来源」复刻出一份等价页面到资料库。来源可以是详情页链接
> `/space/d/{nodeId}`、裸 nodeId，或发布态短链 `/p/{nodeId}`。纯展示页走分支 A（HTML 直传）；
> 接了 database 的数据页走分支 B（先复制表、再重映射 id、最后挂载）。
>
> 由 `entry.md` 编排调用；上传步骤复用 `import-flow.md`，建表 / 导数复用 `../database/entry.md`。
>
> **执行原则**：复刻 = 等价复制，**不解读 HTML 内容是什么、不分析页面功能、不复述页面做什么**。
> 用户没有明确要求"理解 / 总结 / 改造页面内容"时，按本流程铁序 §1→§4 / §5 直接执行到产物落地，
> 不做任何额外的内容解读、功能说明、设计点评。只有用户显式提出"说明这个页面"、"总结内容"、
> "改某处"等诉求时，才在产物落地后按对应能力（读取 / 编辑）处理。
>
> **禁止 publish**：复刻只产出草稿态 page，**绝不调 `publish_page`**。除非用户在本轮**显式**要求
> "发布 / 上线 / publish"，否则复刻完即结束，不做任何发布动作。

## 0. 能力边界与解耦点

复刻只依赖一个**统一的取产物入口**——能拿到 `{产物基址 url, artifacts[].path}` 即可，与产物是否发布态无关：

- 编辑态：`/space/d/{nodeId}`、裸 nodeId（`download_page_artifacts.py` 默认 `--source edit`，底层 `list-page-artifacts`）。
- 发布态：`/p/{nodeId}` 发布态短链或已发布 page（`--source publish`，底层 `list-page-publish-artifacts`，固定取 `meta.publishVersion`）。

> **契约**：本流程只认「取产物函数」的输出形态；编辑态与发布态两个接口输出结构一致（`data.url` + `data.artifacts[].path`），`download_page_artifacts.py` 用 `--source` 统一收口，切换来源零改动。

## 1. 输入归一化

| 输入形态 | 提取规则 |
|---|---|
| `.../space/d/{id}?source=2` | 取 `/space/d/([^/?#]+)`，自动忽略 query |
| `.../p/{id}` | 取 `/p/([^/?#]+)`（发布态短链） |
| 裸 nodeId | 原样 |

归一化由取产物脚本内置，无需 agent 手工处理。

## 2. 取产物到本地目录

> **工作目录必须持久**：`/tmp`（含 `/private/tmp`）在 Bash 调用间不保证持久。
> **必须显式传 `--out-dir` 指向项目工作目录下的子目录**（如 `$CWD/clone_work`），**禁止用脚本默认的 `/tmp`**。
>
> ```bash
> export WORK="$(pwd)/clone_work"   # 落在项目 cwd 下，跨 Bash 调用持久
> mkdir -p "$WORK"
> ```

```bash
# 编辑态（默认）：来源是详情页链接 / 裸 nodeId
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/download_page_artifacts.py" --token-stdin \
  --node-id "<链接或 nodeId>" --out-dir "$WORK/src" [--version <n>] [--concurrency 4]

# 发布态：来源是 /p/<id> 发布态短链或已发布 page（固定取 publishVersion，忽略 --version）
python3 "${CODEBUDDY_PLUGIN_ROOT}/skills/library/page/download_page_artifacts.py" --token-stdin \
  --node-id "<链接或 nodeId>" --source publish --out-dir "$WORK/src" [--concurrency 4]
```

- 内部：按 `--source` 选 `list-page-artifacts`（编辑态）/ `list-page-publish-artifacts`（发布态）取 `data.url` + `data.artifacts[].path` → **并行 GET**（默认并发 4，单文件超时 30s，失败重试 1 次）→ 按相对路径写盘，保持 css/js/img 子目录结构。
- 完整性硬门：入口 HTML 存在、下载数 == 清单数，缺文件即报错，不静默。
- 路径安全：拒绝绝对路径 / `..` 穿越。
- 成功：`KS_ARTIFACTS_OK {"work_dir","entry_html","files":[...]}`；失败 `{"error":...}` exit 0。
- 发布态特有：目标 page 从未发布 → 底层返回 `Code_ERR_PAGE_NOT_PUBLISHED`；引导用户先发布或改用编辑态来源。
- 不回显签名 URL / token。

## 3. 依赖探测分流（纯本地，不发网络请求）

对下载到的**入口 HTML** 本地扫描，**以 databaseId 为主判据**（最可靠；SDK 方法调用因压缩/变量中转等写法可能 grep 匹配不到，只作辅助佐证）：

- 抽取所有 `databaseId: "xxx"` 字面量去重 → 旧表全集 `db_old_set`。**有 databaseId → 分支 B**。
- `db_old_set` 为空 → **分支 A**（纯 HTML）。
- SDK 方法（`.query|.addRecord|.getRecord|.getSchema|.updateRecord|.deleteRecord`）仅作佐证，**不作为分支判据**——匹配不到不代表是分支 A。

**直接用 grep 探测（最稳，推荐）**：

```bash
ENTRY="$WORK/src/index.html"   # §2 返回的 entry_html
# 主判据：抽 databaseId 去重（兼容有/无空格），有输出即分支 B，输出即 db_old_set
grep -o 'databaseId:[[:space:]]*"[^"]*"' "$ENTRY" | grep -oE '"[^"]*"' | tr -d '"' | sort -u
# 佐证（可选，匹配不到不影响判据）
grep -oE '\.(query|addRecord|getRecord|getSchema|updateRecord|deleteRecord)\b' "$ENTRY" | sort -u
```

> 也可用 `parse_html.py`，但**参数必须是 `--html <path>`**（缺 `--html` 会读到空、误判成分支 A）：
> ```bash
> python3 "$CODEBUDDY_SKILL_DIR/page/parse_html.py" --html "$ENTRY"
> ```
> 输出 `existing_databases` / `sdk_calls_found`。

> **顺带取原 title**（分支 A / B 都需要，供步骤 A4 / B9 用作 `--file-name`）：
> - **page 标题**：用 §2 的 `download_page_artifacts.py` 返回的 `data.title`（编辑态/发布态均带）；若缺失再补 `space_api.py space.workspace.node-info --node-id <page_node_id>` 取 `data.title`。
> - **database 标题**：对每个 `db_old_i`，**并行**调 `space_api.py space.workspace.node-info --node-id <db_old_i>` 取 `data.title`，用作该 csv 复刻产物的展示名。
> - **批量并行取 title 范式**（一次取齐所有 db_old 的 title，供 B5 的 DBS 数组使用）：
>   ```bash
>   # 用数组，禁止 for db in $STR（zsh 不做 word-split，整串会被当 1 个元素 → node-info 报 KeyError）
>   DB_OLD_ARR=(db_old_1 db_old_2 db_old_3)   # ...N 张
>   > "$WORK/titles.tsv"
>   for db in "${DB_OLD_ARR[@]}"; do
>     (
>       title=$(printf '%s' "$TOKEN" | python3 "$CODEBUDDY_SKILL_DIR/space_api.py" space.workspace.node-info \
>               --token-stdin --node-id "$db" \
>         | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['node']['title'])")
>       echo "$db|$title" >> "$WORK/titles.tsv"
>     ) &
>   done
>   wait
>   # titles.tsv 每行 "db_old|title"，B5 的 DBS 数组可直接读：DBS=($(cat "$WORK/titles.tsv"))
>   ```
> - **禁止在 B5 脚本内部再单独调 node-info**：title 在 §3 一次性取齐后随 DBS 数组传入 B5，B5 内只做导出+导入。
> - **遍历一律用数组 `"${ARR[@]}"`**：禁止 `for x in $STR` 这种依赖 word-split 的写法，zsh 下不拆分会导致整串被当单个元素、后续脚本 KeyError。

## 4. 分支 A · 纯 HTML 复刻

```
A1 下载目录已就绪（§2），并取到 page 原标题 page_title（§3）
A2 图片托管自检（entry.md §2 硬门；有第三方外链先托管）
A3 多文件 → python3 -m zipfile 打 zip（单 html 可直接传，见 import-flow.md §2）
A4 import_html.py --token-stdin <zip|html> --file-name "<page_title>.html" \
                  [--space-id <目标空间>]   # 不传 --databases、不传 --node-block-id
     → KS_IMPORT_OK {node_block_id, url, file_name}
     file_name 必须显式传，与源 page 同名；不传走 basename 兜底会出现无意义名
A5 收尾：rm -rf "$WORK"（一步清理）
     禁止 present_files 预览 / 写报告文件 / 补跑校验 / publish（同 §5 收尾约束）
     回执凝练：给新 page 的资料库链接 + 提示"可在资料库中查看"即可，不阐述中间流程
```

全部复用 `import_html.py` + `import-flow.md`，无新增能力。

## 5. 分支 B · 数据页复刻

> **循环依赖破解（破法甲）**：`改 HTML 依赖 db_new`（B6←B5）→ 先建 csv；`csv 挂载依赖 page nodeId`（B10←B9）→ 挂载放最后。两处「×N」并行，互不阻塞。
>
> **保留文件名硬门**：所有复刻产物（csv / html）在资料库里的展示名必须与源节点**完全一致**。原 title 通过 §3 一次性取齐，B5.2 / B9 显式传 `--file-name`，禁止依赖脚本兜底（兜底名是路径 basename，会是 `<db_old>.csv` 这种无 title 语义的串）。

### 阶段 B-Ⅰ：并行复制 csv，产出映射

> **强制并行 + 一次跑通（避免重试）**：
> - B5.0 / B5.1 / B5.2 必须在**一条 shell 命令**里 N 路并发，`&` + `wait` 汇合。
> - **禁止分步执行**（先单独取 title、先 `--help` 查用法、先跑单表测试）。
> - **避免重试**：B5 脚本执行失败时，先查 `errors.log` 定位，只重跑失败的那几张表；不盲目全跑。

> **脚本写法硬约束（zsh/bash 兼容）**：
> - **禁止 `declare -A`**（bash 关联数组）：用 `|` 分隔的普通数组。
> - **禁止先单独写 `fetch_titles.py`**：title 在 §3 取齐，B5 内不重取。
> - **禁止先跑 `--help`**：脚本用法已在本文档内联。
> - `--space-id` **可选**：不传走默认空间；只有用户明确指定目标空间时才传。

```
B5.0+B5.1+B5.2  一条并行管道（N 路并发，wait 汇合，一次跑通）：

  export TOKEN="<token>"
  export CODEBUDDY_SKILL_DIR="<library skill 绝对路径>"
  export WORK="<工作目录>"
  mkdir -p "$WORK/csv"
  > "$WORK/mapping.tsv"; > "$WORK/errors.log"

  # DBS 每项 "db_old|title"，直接读 §3 产出的 titles.tsv（兼容 bash/zsh，不用 declare -A）
  DBS=($(cat "$WORK/titles.tsv"))

  for pair in "${DBS[@]}"; do
    db="${pair%%|*}"; title="${pair#*|}"
    (
      # B5.1 导出 CSV（必须提取 content 字段，非整个 JSON）
      printf '%s' "$TOKEN" | python3 "$CODEBUDDY_SKILL_DIR/database/get_database_content.py" \
              --token-stdin --database-id "$db" \
        | python3 -c "import sys,json; sys.stdout.write(json.load(sys.stdin)['content'])" \
        > "$WORK/csv/${db}.csv" 2>>"$WORK/errors.log"
      # B5.2 导入建表+灌数（一次完成）
      new_id=$(printf '%s' "$TOKEN" | python3 "$CODEBUDDY_SKILL_DIR/database/import_csv.py" \
              --token-stdin "$WORK/csv/${db}.csv" --file-name "${title}.csv" \
        | sed -n 's/.*KS_IMPORT_OK .*"node_block_id":"\([^"]*\)".*/\1/p')
      if [ -z "$new_id" ]; then
        echo "IMPORT_FAIL $db" >> "$WORK/errors.log"
      else
        printf '%s\t%s\n' "$db" "$new_id" >> "$WORK/mapping.tsv"   # tab 分隔，与 B6 读取一致
      fi
    ) &
  done
  wait
  # 汇合后检查：mapping.tsv 行数 == N 且 errors.log 为空 → 成功；否则查 errors.log 定位，不盲目重跑
```

**约束**：
- `&` + `wait` 是 shell 原生并行，N 路子进程同时跑，`wait` 阻塞到全部完成。
- 每张表写独立 `mapping.tsv` 行（`printf >> file` 在 shell 并发下是原子的单次 write），**统一 tab 分隔**（`db_old<TAB>db_new`），供 B6 / B10 直接读。
- `get_database_content` 输出 JSON 包装 `{"database_id":...,"content":"<纯CSV>"}`，必须提取 `content` 字段再写盘；直接重定向整个 JSON 会让 import_csv 把 JSON 当 CSV 上传，导致表头污染+数据错位损坏。
- 空值单元格在 content 里是空串，保持原样，不要替换占位符。
- `--file-name` 必传 = 原表标题（随 DBS 数组传入），不传会变成 `<db_old>.csv` 破坏"同名"语义。
- `import_csv` 先落目标空间根，`parent-id` 留到 B10 统一挂（此刻新 page 尚不存在）。
- **失败处理**：检查 `errors.log` 里的 `IMPORT_FAIL`，针对性修复后**只重跑失败的那几张表**，不要重跑全部。

### 阶段 B-Ⅱ：重映射 HTML → 导入 → 挂载

```
B6  # 先从 mapping.tsv 拼出 MAPPING_JSON（tab 分隔的 db_old<TAB>db_new）
    MAPPING_JSON=$(python3 -c "import json,sys;print(json.dumps(dict(l.split() for l in open('$WORK/mapping.tsv'))))")
    python3 "$CODEBUDDY_SKILL_DIR/page/remap_database_ids.py" --html "$WORK/src/<入口HTML>" --mapping "$MAPPING_JSON"
      → 全文精确替换 db_old→db_new（带 id 边界，防子串误伤）；纯本地，无 --token-stdin
      双重硬门：(a) 无残留任何 db_old；(b) 每个 db_new 新增次数 == 对应 db_old 原次数
      不过 → 报错停止，不导入残缺页
B7  图片托管自检（entry.md §2 硬门）
B8  打 zip（HTML + 同目录 css/js/img）；单 html 可直接传
B9  # --databases 从 mapping.tsv 的 db_new 列拼
    DB_JSON=$(python3 -c "import json;print(json.dumps([{'id':l.split()[1]} for l in open('$WORK/mapping.tsv')]))")
    printf '%s' "$TOKEN" | python3 "$CODEBUDDY_SKILL_DIR/page/import_html.py" --token-stdin \
      "$WORK/src/<入口HTML 或 zip>" --file-name "<page_title>.html" --databases "$DB_JSON" [--space-id]
      → KS_IMPORT_OK {node_block_id=nodeId_B, url}；import 顺带写 page↔db_new 关联，省独立 link
      file_name 必传 = 原 page 标题；不传会变成 <entry_html>，破坏"同名"语义
B10 ‖ 并行 ×N move-node（N 路并发，wait 汇合，一次跑通）：

  export NODE_ID_B="<B9 返回的 node_block_id>"
  # DB_NEW_ARR 从 mapping.tsv 第 2 列读（数组遍历，禁止 for x in $STR word-split 陷阱）
  DB_NEW_ARR=($(awk '{print $2}' "$WORK/mapping.tsv"))
  > "$WORK/move_errors.log"
  for new_id in "${DB_NEW_ARR[@]}"; do
    (
      out=$(printf '%s' "$TOKEN" | python3 "$CODEBUDDY_SKILL_DIR/space_api.py" space.workspace.move-node \
            --token-stdin --node-id "$new_id" --target-parent-id "$NODE_ID_B" 2>&1)
      # space_api.py 成功输出 {"api":...,"data":{...}}，失败输出 {"error":...}
      # 成功判据 = 含 "api" 且不含 "error"，禁止用 KS_API_OK / "code":0（那是别的脚本格式）
      if ! echo "$out" | grep -q '"api"' || echo "$out" | grep -q '"error"'; then
        echo "MOVE_FAIL $new_id: $out" >> "$WORK/move_errors.log"
      fi
    ) &
  done
  wait
  → 还原 "csv 挂在 page 下" 的父子结构
  → 检查 move_errors.log 为空即全部成功；不再补跑 node-info 校验（成功判据已准确）

B11 收尾：rm -rf "$WORK"（一条命令清理，不逐个删、不二次确认）→ 回执按下方收尾块格式
```
```

> **B10 强制并行 + 一次跑通**：move-node 用 `&` + `wait`。
> 成功判据 = stdout 含 `"api"` 且不含 `"error"`（**不是** `KS_API_OK` / `"code":0`）。
> `move_errors.log` 为空即全部成功，**不需要补跑 node-info 校验**；有失败项才针对性重跑。

> **收尾（务必凝练）**：
> - **一条 `rm -rf "$WORK"` 清理全部**：中间产物都在 `$WORK` 下，一次删干净，禁止逐文件 `rm -f` 或删前二次 `ls` 确认。
> - **禁止 `present_files` 预览**、**禁止写报告文件**、**禁止补跑额外 Bash 校验**（move 结果已由 B10 `move_errors.log` 判定）、**禁止 publish**。
> - **回执格式（凝练，不阐述中间流程）**：只给三样——
>   1. 复刻后的资料库链接（新 page 的 `/space/d/{nodeId}`）；
>   2. 提示"可在资料库中查看"；
>   3. 一句简单说明"该 HTML 页面与 N 张子 csv 数据表已建立关联"。
>   不复述取产物 / 建表 / remap / 挂载等中间步骤，不列 databaseId 映射表，不做功能点评。

## 6. 并发与安全兜底

- **两层并发**：
  - 脚本内部并发：`download_page_artifacts.py --concurrency 4`（产物下载，默认 4，上限 8）。
  - shell 层并发：B5（取 title + 导出 + 导入）和 B10（move-node）用 `&` + `wait`，N 路子进程同时跑。N ≤ 6 时全量并发；N > 6 时用 `xargs -P 6` 限流到 6，避免打爆后端 QPS。
- `remap_database_ids.py` 默认**全文替换**（最稳、防漏），带 id 边界断言，不误伤 `db_xxxSuffix` 这类子串。
- 全链路不回显 token / 签名 URL / COS header / 原始响应。

## 7. 复用与新增清单

| 项 | 类型 | 用途 |
|---|---|---|
| `download_page_artifacts.py` | 新增 | 列清单 + 并行下载产物到本地 |
| `remap_database_ids.py` | 新增 | HTML databaseId 全局重映射 + 计数校验 |
| `list_page_artifacts.py` | 小改 | nodeId 归一化兼容 `/p/` 发布态短链 |
| `import_html.py` / `import_csv.py` / `get_database_content.py` / `parse_html.py` / `space.workspace.node-info` / `space.workspace.move-node` | 复用 | 零改动（`--file-name` 由本流程显式透传，承载"同名复刻"语义） |
