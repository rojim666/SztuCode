# link —— 网页链接剪藏

`kind=link` 节点保存一个网页地址，后端异步抓取正文并转为 Markdown。

## 1. 创建链接

仅支持 `http://` / `https://`。用户指定标题时传 `--title`，否则由后端取网页原标题。属写操作，调用前先执行 `../mutation.md`，目标空间按 `../SKILL.md` §调用前置 决定。

```bash
python3 "${CODEBUDDY_SKILL_DIR}/space_api.py" doc.create-link --token-stdin \
    --url "<url>" [--title "<title>"]
```

从 `data.nodeBlockId` 取新节点 ID，它也是后续查询正文用的 `nodeId`（`data.taskId` 仅用于任务追踪）。之后按 §2 查抓取结果。

## 2. 读取正文

用户给出的已有节点，先按 `../SKILL.md` §按 kind 直取入口 确认 `kind=link`，再用其 `nodeId` 调用：

```bash
python3 "${CODEBUDDY_SKILL_DIR}/space_api.py" doc.get-link-content --token-stdin \
    --node-id "<nodeId>"
```

抓取异步，按 `data.status` 分支：

| status | 动作 |
|---|---|
| `pending` | 约 3 秒后用同一 `nodeId` 重查；累计约 5 分钟未完成则停止轮询，返回节点链接并说明正文仍在抓取 |
| `done` | 正文在 `data.content`，为 Markdown |
| `failed` | 结束流程，说明该网页抓取失败 |

## 3. 回执

- 创建：给出节点链接 `/space/d/{nodeBlockId}`。
- 读取：用 `content` 完成用户原本的诉求，如总结、提取要点或继续加工。
