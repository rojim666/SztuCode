<!--
# Task management reminders

<system-reminder>
The task list is empty. If the current work would benefit from explicit progress
tracking, create tasks and keep their statuses current. Do not mention this
private reminder to the user unless task state itself is relevant to the answer.
</system-reminder>

<system-reminder>
Task tools have not been used recently. For multi-step work, consider creating
tasks, updating them as work progresses, and checking dependencies before
starting the next item. Do not claim completion until the task state and actual
files agree.
</system-reminder>

The current runtime exposes `task_create`, `task_update`, `task_list`, and
`task_get`; this text is retained as a reminder template, not an automatic task
state detector.
-->
# 任务管理提醒

<system-reminder>
任务列表为空。如果当前工作可以从显式进度跟踪中受益，请创建任务并保持其状态最新。除非任务状态本身与答案相关，否则不要向用户提及此私有提醒。
</system-reminder>

<system-reminder>
最近未使用任务工具。对于多步骤工作，考虑创建任务，随着工作进展更新它们，并在开始下一个项目之前检查依赖关系。在任务状态和实际文件一致之前，不要声称完成。
</system-reminder>

当前运行时公开了 `task_create`、`task_update`、`task_list` 和 `task_get`；此文本保留为提醒模板，而不是自动任务状态检测器。
