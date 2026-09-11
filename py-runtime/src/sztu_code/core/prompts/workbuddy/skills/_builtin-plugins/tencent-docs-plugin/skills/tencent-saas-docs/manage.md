# 文档列表 / 空间管理

- service：`tencent-saas-docs`
- endpoint：`https://saas.docs.qq.com/api/v6/open/agent/mcp`
- 调用：`python3 tencentdocs.py tdoc_call tencent-saas-docs <工具> '{...}'`

> 上级：[SKILL.md](./SKILL.md)。跨品类文件/空间管理，`file_id` 的来源。导入/导出为异步轮询链路。
> 知识库空间的字段/节点细节见 [references/space_references.md](./references/space_references.md)。

| 工具 | 说明 |
|---|---|
| `manage.list_file` | 获取文件列表，支持多种列表类型（我的文档、最近浏览、收藏、回收站、共享等） |
| `manage.search_file` | 根据关键字搜索腾讯文档列表 |
| `manage.ai_search_file` | AI 智能文档搜索，理解自然语言意图返回相关文档 |
| `manage.create_file` | 创建在线腾讯文档文件 |
| `manage.get_content` | 获取文档完整内容 |
| `manage.query_file_info` | 查询在线腾讯文档基础信息 |
| `manage.rename_file_title` | 重命名文档标题 |
| `manage.get_privilege` | 根据文件 id 查询文件权限 |
| `manage.set_privilege` | 根据文件 id 设置文件权限 |
| `manage.batch_query_permission` | 批量查询多个文档的权限信息 |
| `manage.move_file` | 移动文件到指定文件夹 |
| `manage.copy_file` | 生成副本 |
| `manage.delete_file` | 删除文件到回收站 |
| `manage.apply_upload` | 申请上传链接，返回 COS 上传地址、obj_key、task_id；客户端上传完成后调 `manage.complete_upload` 完成导入 |
| `manage.complete_upload` | 上传完成回调，触发文件导入为云文档；后续用 `manage.query_task` 轮询导入进度 |
| `manage.query_task` | 查询导入 / 导出 / 转换等异步任务进度 |
| `manage.apply_download` | 申请下载/导出链接，返回临时下载地址 |
| `manage.upload_image` | 上传图片，返回 image_id（用于智能文档、智能表格等图片字段） |
| `manage.scrape_url` | 网页剪藏：将外部网页 URL 抓取并保存为云文档（异步） |
| `manage.scrape_progress` | 查询网页剪藏任务进度，与 `manage.scrape_url` 配合使用 |
| `query_space_list` | 获取知识库空间列表 |
| `create_space` | 创建新的知识库空间 |
| `query_space_node` | 查询空间内节点列表 |
| `create_space_node` | 在空间中创建新节点（文件夹/文档/链接） |
| `delete_space_node` | 删除空间中的指定节点 |
