<!-- Update an existing task's status or dependency list. -->
更新现有任务的状态或依赖列表。

<!-- Usage: -->
使用方法：
<!-- - `task_id` is required. -->
- `task_id` 是必需的。
<!-- - Set status to `in_progress` when work starts and `completed` immediately when it finishes. -->
- 工作开始时将状态设置为 `in_progress`，完成时立即设置为 `completed`。
<!-- - Use `add_blocked_by` and `remove_blocked_by` to maintain dependencies. -->
- 使用 `add_blocked_by` 和 `remove_blocked_by` 维护依赖关系。
<!-- - Completing a task automatically removes it from other tasks' `blocked_by` lists. -->
- 完成任务会自动将其从其他任务的 `blocked_by` 列表中移除。
<!-- - The result returns the updated task as JSON. -->
- 结果以 JSON 形式返回更新后的任务。
