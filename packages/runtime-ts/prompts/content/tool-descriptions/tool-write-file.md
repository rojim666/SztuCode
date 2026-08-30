<!-- Write UTF-8 text to a file inside the current workspace. The tool creates missing parent directories and either creates the file or completely overwrites an existing file. -->
将 UTF-8 文本写入当前工作区内的文件。该工具会创建缺失的父目录，并创建文件或完全覆盖现有文件。

<!-- Usage: -->
使用方法：
<!-- - `path` must be relative to the working directory; absolute paths and `..` traversal are rejected. -->
- `path` 必须相对于工作目录；绝对路径和 `..` 遍历将被拒绝。
<!-- - Content is limited to 1 MB. -->
- 内容限制为 1 MB。
<!-- - Prefer `edit_file` for targeted changes to an existing file. Use `write_file` for new files or intentional complete rewrites. -->
- 对现有文件的针对性更改优先使用 `edit_file`。对新文件或有意完全重写使用 `write_file`。
<!-- - Read an existing file before overwriting it so user changes are not lost. -->
- 在覆盖现有文件之前先读取它，以免丢失用户更改。
<!-- - Do not create documentation or unrelated files unless the task requires them. -->
- 除非任务需要，否则不要创建文档或不相关的文件。
