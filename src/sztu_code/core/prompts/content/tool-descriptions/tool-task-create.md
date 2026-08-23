Create a persistent task for one trackable unit of work in the current run.

Usage:
- Use tasks for complex multi-step work, explicit todo requests, or several distinct user requests. Do not create task overhead for a simple one-step change.
- `subject` is required and should be a short action-oriented title.
- `description` may record completion criteria or important scope.
- `blocked_by` may list existing task IDs that must complete first.
- The created task starts as `pending` and the result returns its JSON record.
