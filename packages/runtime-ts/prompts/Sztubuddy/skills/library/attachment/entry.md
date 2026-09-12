# attachment —— 节点附件

附件挂在某个已有节点（doc / page / database）下，跟随该节点存在，不在目录树中单独占位。独立成节点、可单独打开分享的文件走 `../drive/entry.md`。

## 能力

| 意图 | 命令 | 必填 | 成功输出 |
|---|---|---|---|
| 给已有节点挂附件 | `attachment/attachment.py upload` | `--node-id` `<path>` | `KS_ATTACHMENT_UPLOAD_OK <json>` |
| 取附件下载链接 | `attachment/attachment.py download` | `--node-id` `--attachment-id` | `KS_ATTACHMENT_DOWNLOAD <json>` |

上传属写操作，调用前先执行 `../mutation.md`。

## 1. 上传附件

```bash
python3 "${CODEBUDDY_SKILL_DIR}/attachment/attachment.py" upload --token-stdin \
    --node-id <nb_xxx> <path> [--file-name 名.pdf]
```

| 参数 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `--node-id` | 是 | — | 附件所属节点 |
| `<path>` | 是 | — | 本地文件绝对路径（用户显式给出，勿自行遍历） |
| `--file-name` | 否 | basename | 展示名 |

大小上限由服务端校验，本地不预判；被拒后不分片重试。

成功输出字段：

| 字段 | 说明 |
|---|---|
| `node_id` | 与入参一致 |
| `attachment_id` | 附件唯一标识，下载时必传，需保存 |
| `file_name` | 文件名 |
| `file_size` | 文件大小（字节） |
| `file_type` | MIME type，如 `application/pdf`、`image/png` |
| `media_type` | 附件大类：`image` / `video` / `audio` / `file` |

写入 database 的 `attachment` 列时，这些字段可直接映射为一个 `AttachmentItem`，字段对应见 `../database/params-reference.md` §AttachmentItem。

## 2. 取附件下载链接

```bash
python3 "${CODEBUDDY_SKILL_DIR}/attachment/attachment.py" download --token-stdin \
    --node-id <nb_xxx> --attachment-id <att_xxx>
```

`--attachment-id` 来自 §1 返回值，`--node-id` 与上传时一致。

输出含 `node_id`、`attachment_id`、`download_url`。`download_url` 是短期预签名链接，取到后立即下载；回执透传 `KS_USER_REPLY`，不展开完整链接。
