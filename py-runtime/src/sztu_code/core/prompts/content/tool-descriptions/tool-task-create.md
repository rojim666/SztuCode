<!-- Create a persistent task for one trackable unit of work in the current run. -->
在当前运行中为一个可追踪的工作单元创建持久任务。

<!-- Usage: -->
使用方法：
<!-- - Use tasks for complex multi-step work, explicit todo requests, or several distinct user requests. Do not create task overhead for a simple one-step change. -->
- 对复杂的多步工作、明确的待办请求或多个不同的用户请求使用任务。不要为简单的单步更改创建任务开销。
<!-- - `subject` is required and should be a short action-oriented title. -->
- `subject` 是必需的，应该是一个简短的面向行动的标题。
<!-- - `description` may record completion criteria or important scope. -->
- `description` 可以记录完成标准或重要范围。
<!-- - `blocked_by` may list existing task IDs that must complete first. -->
- `blocked_by` 可以列出必须先完成的现有任务 ID。
<!-- - The created task starts as `pending` and the result returns its JSON record. -->
- 创建的任务初始状态为 `pending`，结果返回其 JSON 记录。
