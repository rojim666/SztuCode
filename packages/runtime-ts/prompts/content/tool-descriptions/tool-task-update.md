
更新现有任务的状态或依赖列表。

使用方法：
- `task_id` 是必需的。
- 工作开始时将状态设置为 `in_progress`，完成时立即设置为 `completed`。
- 使用 `add_blocked_by` 和 `remove_blocked_by` 维护依赖关系。
- 完成任务会自动将其从其他任务的 `blocked_by` 列表中移除。
- 结果以 JSON 形式返回更新后的任务。
