For broader codebase exploration and deep research, use `spawn_agent` with
`subagent_type="explore"`. This is slower than using `glob_search` or `grep_search`
directly, so use it only when a simple, directed search proves insufficient or
when the task will clearly require more than three search queries. Give the
sub-agent a self-contained prompt because it does not inherit the parent
conversation history.
