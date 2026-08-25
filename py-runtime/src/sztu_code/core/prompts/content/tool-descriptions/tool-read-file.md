Read the UTF-8 text content of one file inside the current workspace.

Usage:
- `path` must be relative to the working directory; absolute paths and `..` traversal are rejected.
- The tool reads files, not directories. Use `list_dir` for a directory tree.
- Files larger than 512 KB are truncated and marked with `[truncated]`.
- Missing files return an error. Use `glob_search` when the exact path is unknown.
- Read relevant existing files before proposing or applying changes.
