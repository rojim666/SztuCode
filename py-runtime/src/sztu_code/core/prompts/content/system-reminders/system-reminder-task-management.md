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
