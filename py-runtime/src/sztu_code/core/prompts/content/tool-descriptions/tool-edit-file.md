Perform exact string replacement in an existing UTF-8 text file inside the current workspace.

Usage:
- `path` must be relative to the working directory.
- `old_string` must match exactly, including whitespace and indentation.
- By default `old_string` must occur exactly once. Add surrounding context when it is ambiguous, or set `replace_all=true` only when every occurrence should change.
- `old_string` and `new_string` must differ. Files larger than 1 MB are rejected.
- Prefer this tool for focused edits. Use `write_file` only for new files or complete rewrites.
