Update an existing task's status or dependency list.

Usage:
- `task_id` is required.
- Set status to `in_progress` when work starts and `completed` immediately when it finishes.
- Use `add_blocked_by` and `remove_blocked_by` to maintain dependencies.
- Completing a task automatically removes it from other tasks' `blocked_by` lists.
- The result returns the updated task as JSON.
