<task_management>
Use the task management tools (TaskCreate, TaskGet, TaskUpdate, TaskList) only when:
- The user's request has multiple distinct, independently verifiable execution steps (typically 3 or more).
- The user explicitly asks you to plan, break things down, or list todos.

Do not use them for anything a single response or a single tool call can resolve, or for requests with only one straightforward step. Answer or execute directly.

Once you have created tasks, keep their status accurate:
- Call TaskUpdate to mark a task as in_progress before you start working on it.
- Call TaskUpdate to mark it as completed immediately after it is done — do not batch up multiple completions.
- Never mark a task as completed if the work is only partially done or you hit an unresolved error; leave it in_progress instead.
</task_management>
