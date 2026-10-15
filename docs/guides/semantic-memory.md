# 语义搜索和历史笔记

桌面端使用的 TypeScript daemon 提供 `semantic_search`。用自然语言描述想找的逻辑，结果包含文件路径、行号和分数；知道函数名时仍可用 `grep_search`。首次搜索自动建立索引，之后只重新嵌入变更文件。删除、改为二进制或加入 `.gitignore` 的文件会从索引移除。

默认模型为本地 `Xenova/all-MiniLM-L6-v2`，无需云端 API Key。首次使用需要联网下载模型，缓存后可离线运行。首次启动不会下载模型；代码和笔记不会发送到云端嵌入 API。

`memory_read` 增加两个参数：

| 参数 | 用法 |
| --- | --- |
| `query_mode` | `keyword` 只查关键词；`semantic` 按含义查；默认 `hybrid` 合并两种检索的排名 |
| `scope` | 默认 `current` 读取当前会话；`workspace` 配合 `layer="session"` 查询同一工作区其他会话的有效笔记，包括归档会话 |

例如：`memory_read({"layer":"session","query":"之前决定怎么保存事件","query_mode":"hybrid","scope":"workspace"})`。结果标明会话和笔记来源。已被替换的旧笔记、已删除会话和其他工作区的笔记不会出现在结果里；未绑定工作区的临时会话只读自身笔记。

第一次语义查询自动补建已有笔记的向量。此后同一运行内的 `note_save`、`note_update` 自动更新；外部修改和其他会话新增笔记在下次查询时刷新。模型不可用时，`hybrid` 明确提示并返回关键词结果，`semantic` 返回错误；原始笔记仍会保存。

代码索引和记忆索引分别存放在工作区 `.sztu/vector/semantic-index.jsonl`、`memory-index.jsonl`。索引不进入 Git。桌面状态栏可查看代码索引进度、重建和清除；清除只删除代码索引，保留源文件和会话笔记，下次搜索可自动重建。

管理接口均需要 `workspace_id`：`index.status`、`index.stats` 查询状态，`index.build` 后台重建，`index.update` 增量更新 `files` 路径数组，`index.clear` 清除代码索引。后台重建立即返回 `indexing`，客户端继续查询状态直到 `ready` 或 `failed`。

本次补齐的是桌面 TypeScript 链路。Python daemon 和云端嵌入配置不在这组接口的范围内。
