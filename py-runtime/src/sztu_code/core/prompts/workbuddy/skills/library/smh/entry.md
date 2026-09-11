# smh —— 历史智能媒体库文件

早期资料库用另一套存储放文件，遗留了一批 `kind=smh` 节点。这类节点只支持下载，新文件一律走 `../drive/entry.md`，不得再发起 SMH 上传。

不支持替换内容。需要修改时下载后按新文件上传（走 `../mutation.md` 的新建流程）；只改标题走 `../manage/entry.md`。

## 取下载链接

```bash
python3 "${CODEBUDDY_SKILL_DIR}/smh/get_download_link.py" --token-stdin --node-id <blk_xxx>
```

输出 `KS_SMH_DOWNLOAD <json>`，含 `node_id`、`file_name`、`ext`、`download_url`。`download_url` 是短期预签名链接，取到后立即下载；回执透传 `KS_USER_REPLY`，不展开完整链接。
