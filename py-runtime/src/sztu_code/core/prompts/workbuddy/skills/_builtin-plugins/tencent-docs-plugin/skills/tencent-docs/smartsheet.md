# smartsheet（智能表格 / 多维表）

- service：`tencent-docs`
- endpoint：`https://docs.qq.com/openapi/mcp`
- 调用：`python3 tencentdocs.py tdoc_call tencent-docs <工具> '{"file_id":"<id>","sheet_id":"<sid>",...}'`

> 上级：[SKILL.md](./SKILL.md)。字段/记录/视图均为批量接口；先 `list_tables` 拿 sheet_id 再操作。
> `commit_changeset` / `fetch` 系 App 内部链路，AI 勿调。

| 工具 | 说明 |
|---|---|
| `smartsheet.add_fields` | 批量新增字段 |
| `smartsheet.add_records` | 批量添加记录 |
| `smartsheet.add_table` | 在文档中新增工作表 |
| `smartsheet.add_view` | 新增视图 |
| `smartsheet.commit_changeset` | 提交智能表的编辑变更 |
| `smartsheet.delete_fields` | 批量删除字段 |
| `smartsheet.delete_records` | 批量删除记录 |
| `smartsheet.delete_table` | 删除指定的工作表 |
| `smartsheet.delete_view` | 删除指定的视图 |
| `smartsheet.fetch` | 打开智能表 |
| `smartsheet.get_client_var` | 获取智能表文档的 clientVar 配置信息 |
| `smartsheet.list_fields` | 列出工作表字段 |
| `smartsheet.list_records` | 分页列出工作表记录 |
| `smartsheet.list_tables` | 列出文档下的工作表 |
| `smartsheet.list_views` | 列出工作表视图 |
| `smartsheet.show_ui` | 展示智能表格交互式 UI，调用此工具后 Host 会在会话中渲染智能表格界面 |
| `smartsheet.update_fields` | 批量更新字段 |
| `smartsheet.update_records` | 批量更新记录 |
