# drive —— 资料库网盘文件

`kind=drive` 节点在目录树中独立占位，可单独打开和分享。本模块管其上传、内容替换与下载。

- 改名、移动、列目录、搜索 → `../manage/entry.md`
- 挂在某节点下的附件 → `../attachment/entry.md`
- 只需可内嵌页面的图片直链 → `../manage/entry.md` §upload_image

## 能力

| 意图 | 命令 | 必填 | 成功输出 |
|---|---|---|---|
| 上传本地文件为网盘文件 | `drive/upload_drive_file.py` | `<path>` | `KS_DRIVE_UPLOAD_OK <json>` |
| 替换已有文件内容 | 见 §2 | `<path>` `--node-id` | `KS_DRIVE_UPLOAD_OK <json>` |
| 取文件下载链接 | `drive/get_download_link.py` | `--node-id` | `KS_DRIVE_DOWNLOAD <json>` |

上传与替换属写操作，调用前先执行 `../mutation.md`。

## 1. 上传本地文件

```bash
python3 "${CODEBUDDY_SKILL_DIR}/drive/upload_drive_file.py" --token-stdin <path> \
    [--space-id sp_x] [--parent-id blk_y] [--file-name 名.docx]
```

| 参数 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `<path>` | 是 | — | 本地文件绝对路径（用户显式给出，勿自行遍历） |
| `--file-name` | 否 | basename | 展示名 |
| `--space-id` | 否 | 省略时后端落我的文档 | 目标空间 |
| `--parent-id` | 否 | 空间根目录 | 目标目录；传入时须同时传其所属 `--space-id` |

新建上传的目标空间按 `../SKILL.md` §调用前置 决定；替换时以目标节点的实际归属为准。

约束：

- 单文件上限 **100 MiB**，超出直接失败，不分片重试。
- 本入口只收普通文件。`.md` 走 doc、`.csv` 走 database、`.html` / `.zip` 走 page——这些类型导入后是可编辑的在线内容，不是网盘文件。

输出含 `node_block_id`、`file_name`、`ext`、`url`；回执透传 `KS_USER_REPLY`。

## 2. 替换已有文件内容

在保持同一节点、同一链接的前提下更新文件内容。按 `../mutation.md` 执行：

1. `space.workspace.node-info` 确认 `kind=drive`，记录节点 ID、文件名与当前版本标识。
2. 用 §3 下载最新版，原件留作对照基线，在副本上修改，保持原文件名与扩展名。换格式按新建文件处理。
3. 验证改后文件可正常打开。纯文本备 unified diff；Office / PDF / 图片备变更摘要，并列出无法验证的部分。
4. 核对通过后覆盖：

```bash
python3 "${CODEBUDDY_SKILL_DIR}/drive/upload_drive_file.py" --token-stdin \
    <修改后文件绝对路径> --node-id <blk_xxx> --file-name "<原文件名>"
```

`--node-id` 是"替换"与"新建"的唯一区别，必须传。返回的 `node_block_id` 必须仍等于目标节点；成功后复查 `node-info`，确认节点 ID 未变、版本标识已更新。不得用上传同名新文件代替替换——那会多出一份文件，原链接仍指向旧内容。

## 3. 取文件下载链接

```bash
python3 "${CODEBUDDY_SKILL_DIR}/drive/get_download_link.py" --token-stdin --node-id <blk_xxx>
```

输出含 `node_id`、`file_name`、`ext`、`download_url`。`download_url` 是短期预签名链接，取到后立即下载；回执透传 `KS_USER_REPLY`，不展开完整链接。

历史 `kind=smh` 节点走 `../smh/entry.md`。
