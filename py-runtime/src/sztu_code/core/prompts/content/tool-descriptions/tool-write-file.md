Write UTF-8 text to a file inside the current workspace. The tool creates missing parent directories and either creates the file or completely overwrites an existing file.

Usage:
- `path` must be relative to the working directory; absolute paths and `..` traversal are rejected.
- Content is limited to 1 MB.
- Prefer `edit_file` for targeted changes to an existing file. Use `write_file` for new files or intentional complete rewrites.
- Read an existing file before overwriting it so user changes are not lost.
- Do not create documentation or unrelated files unless the task requires them.
