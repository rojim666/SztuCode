# manage —— 资料库管理

manage 负责资料库位置、目录、权限、评论、节点移动与重命名、搜索和图片上传。

## 路由

| 用户意图 | 入口 |
|---|---|
| 列出可见资料库 | `space.workspace.list-user-spaces` |
| 创建团队空间 | `space.workspace.create-space` |
| 浏览目录 | `space.workspace.list-node` |
| 查询节点信息 | `space.workspace.node-info` |
| 查询角色或协作成员 | `space.permission.collaborators` |
| 读取节点评论 | `manage/get_node_comments.py` |
| 移动节点 | `space.workspace.move-node` |
| 重命名节点 | `space.workspace.rename-node` |
| 搜索全部资料库中的节点 | `space.searcher.search-nodes` |
| 搜索指定空间或节点的内容 | `manage/rag_search.py` |
| 上传图片 | `manage/upload_image.py` |

`space.*` 接口通过根目录 `space_api.py` 调用；不确定参数时运行 `space_api.py <api-name> --help`。

## 操作

### `space.workspace.list-user-spaces`

```bash
python3 "${CODEBUDDY_SKILL_DIR}/space_api.py" space.workspace.list-user-spaces --token-stdin
```

读取 `data.spaces[]` 的 `spaceId`、`title`、`category`、`role`。按 `category` 分为「我的文档 / 团队空间」；其它值停止处理。默认展示 `title`，用户询问权限时再展示 `role`；无结果时说明未找到资料库位置。

### `space.workspace.create-space`

`--title` 可选；不传时创建未命名团队空间。调用前按 `../mutation.md` 展示最终名称并等待确认。

```bash
python3 "${CODEBUDDY_SKILL_DIR}/space_api.py" space.workspace.create-space --token-stdin --title "我的团队空间"
```

返回 `data.space`；`category=team`，`role=owner`。复用 `spaceId`；展示 `title`（空串称「未命名空间」）和 `/space/s/{spaceId}`，用户询问时再展示原始 ID。

### `space.workspace.list-node`

用户已给出 `spaceId` 并要求梳理、整理或分析内容时，调用 `rag_search.py --space-id <spaceId>`；只有浏览目录结构时调用 `list-node`。

`--space-id` 指定目标空间；`--parent-node-id` 指定父节点。列指定节点的子节点时，同时传入该节点所属的 `spaceId` 和 `parentNodeId`；只有 `nodeId` 时，先用 `node-info` 取 `data.node.spaceId`。两者都不传时列“我的文档”根目录。

```bash
# 列指定空间根目录
python3 "${CODEBUDDY_SKILL_DIR}/space_api.py" space.workspace.list-node --token-stdin --space-id "<spaceId>"

# 列指定节点的子节点
python3 "${CODEBUDDY_SKILL_DIR}/space_api.py" space.workspace.list-node --token-stdin \
    --space-id "<spaceId>" --parent-node-id "<nodeId>"
```

保持 `data.nodes[]` 顺序。浏览使用 `id`、`title`、`kind`、`url`、`nodes`；定位或写入继续保留 `spaceId`、`parentId`。同名节点交给用户消歧；`nodes` 非空时可继续展开。

### `space.workspace.node-info`

传 `--node-id` 或 `/space/d/{nodeId}` 形态的 `--url`；同时传入时以 `--node-id` 为准。`/space/s/{spaceId}` 改用 `rag_search.py --space-id` 或 `list-node --space-id`。

```bash
python3 "${CODEBUDDY_SKILL_DIR}/space_api.py" space.workspace.node-info --token-stdin --node-id "<nodeId>"
python3 "${CODEBUDDY_SKILL_DIR}/space_api.py" space.workspace.node-info --token-stdin --url "https://www.Sztubuddy.cn/space/d/<nodeId>"
```

读取 `data.node`：

- 路由与展示：`id`、`title`、`kind`、`url`
- 写入、移动与后置模块：`spaceId`、`parentId`、`createdBy`、`version`

失败时说明未找到节点或无访问权限。

### `space.permission.collaborators`

空间 ID 或 `/space/s/{spaceId}` 链接传 `--space-id`；节点传 `--node-id`。

```bash
# 查询空间级协作成员
python3 "${CODEBUDDY_SKILL_DIR}/space_api.py" space.permission.collaborators --token-stdin \
    --space-id "<spaceId>"

# 查询节点级协作成员
python3 "${CODEBUDDY_SKILL_DIR}/space_api.py" space.permission.collaborators --token-stdin \
    --node-id "<nodeId>"
```

读取 `data.myRole`、`data.createdBy` 和 `data.collaborators[].{name,uid,role}`。成员优先展示昵称和角色，昵称为空时展示 UID；无成员时说明当前资源暂无协作成员。

### `manage/get_node_comments.py`

默认读取节点的未解决评论；`--discussion-id` 限定单个评论线，`--include-resolved` 包含已解决评论。

```bash
python3 "${CODEBUDDY_SKILL_DIR}/manage/get_node_comments.py" --token-stdin \
    --node-id "<nodeId>"
```

从 `KS_DOC_COMMENTS` 后的 `threads[]` 读取评论线、锚点和 `comments[].plainText`。

### `space.workspace.move-node`

- 移动前用 `node-info` 读取源节点；指定目标目录时也读取目标节点。
- 源节点和目标目录的 `spaceId` 必须一致；用源节点 `parentId` 确认原位置。
- 跨空间移动交给用户在前端完成。

`--node-id` 必填；`--target-parent-id` 不传时移到空间根目录；`--after-node-id` 不传时追加到末尾。

```bash
python3 "${CODEBUDDY_SKILL_DIR}/space_api.py" space.workspace.move-node --token-stdin \
    --node-id "<nodeId>" --target-parent-id "<parentNodeId>"
```

回执说明目标位置，不展示内部节点 ID。

### `space.workspace.rename-node`

`--node-id` 和纯文本 `--title` 必填。同名处理按 `../mutation.md`；接口不支持 `conflictStrategy` 或 `overwrite`。

```bash
python3 "${CODEBUDDY_SKILL_DIR}/space_api.py" space.workspace.rename-node --token-stdin \
    --node-id "<nodeId>" --title "新标题"
```

任意节点均可重命名；网盘文件可传完整文件名，服务端同步节点标题和网盘文件名。回执展示新标题。

### `manage/upload_image.py`（图片上传）

把本地图片或第三方图片 URL 转为可内嵌的公网直链，不创建资料库节点。`<path>` 与 `--url` 二选一；`--file-name` 和 `--content-type` 可选。

本地图片上限 10 MiB；支持 `.png / .jpg / .jpeg / .gif / .webp / .bmp / .svg / .heic / .heif / .tiff`。

```bash
# 本地图片
python3 "${CODEBUDDY_SKILL_DIR}/manage/upload_image.py" --token-stdin ./cover.png

# 第三方图片转公网直链
python3 "${CODEBUDDY_SKILL_DIR}/manage/upload_image.py" --token-stdin \
    --url "https://example.com/foo.png"
```

成功时使用 `KS_IMAGE_UPLOAD_OK` 中的 `url`；回执透传 `KS_USER_REPLY`。

### `space.searcher.search-nodes`

| 搜索范围 | 调用 |
|---|---|
| 我的文档 | 用 `list-user-spaces` 解析唯一的 `category=personal` 空间，调用 `rag_search.py --space-id` |
| 用户指定的某个空间或节点 | 用其 `spaceId` / `nodeId` 调用 `rag_search.py` |
| 明确搜索全部资料库 | 调用 `search-nodes` |

`--query` 必填，使用核心名词；默认只传该参数，复杂问题最多拆成 3 次搜索。`--size` / `--num` 用于分页，`--highlight` 仅在需要高亮摘要时传。

```bash
python3 "${CODEBUDDY_SKILL_DIR}/space_api.py" space.searcher.search-nodes --token-stdin --query "<关键词>"
```

从 `data.items[]` 取 top results，展示 `nodeTitle`、`nodeKind`、`url` 和 `textContent`；`nodeId`、`score`、`locations` 仅用于排序和后续处理。无命中时说明未搜到该关键词。

### `manage/rag_search.py`

在指定空间或节点内搜索内容片段。

```bash
python3 "${CODEBUDDY_SKILL_DIR}/manage/rag_search.py" \
  --token-stdin --query "<问题>" --node-id "<nodeId>"

python3 "${CODEBUDDY_SKILL_DIR}/manage/rag_search.py" \
  --token-stdin --query "<问题>" --space-id "<spaceId>"
```

`--query` 必填，1~128 字；`--space-id` 与 `--node-id` 至少传一个，可重复传入或用逗号分隔。`--limit` 默认 20、最大 100；`--drive-limit` 默认 10。

| 输出 | 用途 |
| --- | --- |
| `KS_RAG_CARDS` | 生成用户回复；使用 `cards[].title/source/snippet/image_urls/chunk_count` |
| `KS_RAG\t<spaceId>\t<nodeId>\t<nodeKind>\t...` | 需要获取命中节点全文时，使用 `nodeId` 和 `nodeKind` 后置路由 |

### 检索结果呈现

使用 `KS_RAG_CARDS` 生成 assistant Markdown。

| 用户意图 | 回复 |
|---|---|
| 查找或打开资料 | 列出 `title` 链接、`chunk_count` 和最高分 `snippet`；有图时展示第一张 |
| 总结、梳理或分析 | 输出正文；关键断言用 `[N]` 标注，并按首次出现顺序列出对应来源 |
| 写汇报、周报或报告 | 完成综合型正文后调用 `doc/create_doc.py` 落库 |

图片放在相关段落。用户视图只使用 `title`、`source`、`snippet`、`image_urls`、`chunk_count` 和引用编号；协议字段与原始 ID 仅用于内部处理。无命中时说明指定范围内没有相关内容。

### 获取命中节点全文

需要全文时，从 `KS_RAG` 取非空 `nodeKind` 和对应 `nodeId`，按 `SKILL.md` 的 kind 表进入对应模块 `entry.md`；`nodeKind` 为空或未覆盖时跳过。
