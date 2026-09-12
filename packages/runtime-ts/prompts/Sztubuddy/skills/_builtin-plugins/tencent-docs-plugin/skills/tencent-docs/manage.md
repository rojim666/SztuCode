# 文档列表 / 空间管理

- service：`tencent-docs`
- endpoint：`https://docs.qq.com/openapi/mcp`
- 调用：`python3 tencentdocs.py tdoc_call tencent-docs <工具> '{...}'`

> 上级：[SKILL.md](./SKILL.md)。跨品类文件/空间管理，`file_id` 的来源。导入/导出为异步轮询链路。
> 知识库空间的字段/节点细节见 [references/space_references.md](./references/space_references.md)。

| 工具 | 说明 |
|---|---|
| `create_space` | 创建空间 |
| `create_space_node` | 在空间树中创建新节点 |
| `delete_space_node` | 删除空间中的指定节点 |
| `get_content` | 获取文档完整内容 |
| `manage.async_import` | 异步导入文档 |
| `manage.copy_file` | 生成副本 |
| `manage.create_file` | 创建在线腾讯文档文件 |
| `manage.delete_file` | 删除首页列表文件到回收站以及删除空间内的节点文件 |
| `manage.export_file` | 导出文档，支持根据文档ID将文档导出到本地，然后返回导出任务ID |
| `manage.export_progress` | 查询导出进度，根据导出任务task_id查询任务进度 |
| `manage.folder_list` | 拉取指定目录下的文件与文件夹列表 |
| `manage.get_privilege` | 根据文件id或空间id查询文件或空间的权限 |
| `manage.import_progress` | 查询导入进度，根据导入任务task_id查询任务进度 |
| `manage.move_file` | 移动文件到首页文件夹 |
| `manage.move_file_to_space` | 移动文件到空间内 |
| `manage.pre_import` | 预导入文档 |
| `manage.query_file_info` | 查询在线腾讯文档基础信息 |
| `manage.query_folder_meta` | 查询指定文件夹的meta信息 |
| `manage.recent_online_file` | 查询腾讯云文档最近浏览列表，提供多种排序方式和分页查询 |
| `manage.rename_file_title` | 重命名文档标题 |
| `manage.search_file` | 根据关键字搜索腾讯文档列表 |
| `manage.set_privilege` | 根据文件id或空间id设置文件或空间的权限 |
| `ocr.extract` | 识别单张图片中的文字内容 |
| `ocr.toexcel` | 将图片内容识别并生成在线表格 |
| `ocr.toword` | 将图片内容识别并生成在线文档 |
| `query_space_list` | 获取用户的知识库空间列表 |
| `query_space_node` | 查询空间节点树结构 |
| `scrape_progress` | 查询网页剪藏任务进度并自动创建文档，与scrape_url配合使用 |
| `scrape_url` | 网页剪藏：当用户发送、分享或提到任何网页URL链接时 |
| `upload_image` | 上传图片 |

> OCR 的图片来源路由、本地图片用 `node ocr.js` 的细节见 [references/ocr_references.md](./references/ocr_references.md)。
