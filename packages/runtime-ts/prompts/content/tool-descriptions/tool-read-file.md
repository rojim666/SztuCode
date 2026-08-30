<!-- Read the UTF-8 text content of one file inside the current workspace. -->
读取当前工作区内一个文件的 UTF-8 文本内容。

<!-- Usage: -->
使用方法：
<!-- - `path` must be relative to the working directory; absolute paths and `..` traversal are rejected. -->
- `path` 必须相对于工作目录；绝对路径和 `..` 遍历将被拒绝。
<!-- - The tool reads files, not directories. Use `list_dir` for a directory tree. -->
- 该工具读取文件，而不是目录。使用 `list_dir` 获取目录树。
<!-- - Files larger than 512 KB are truncated and marked with `[truncated]`. -->
- 大于 512 KB 的文件将被截断并用 `[已截断]` 标记。
<!-- - Missing files return an error. Use `glob_search` when the exact path is unknown. -->
- 不存在的文件返回错误。当确切路径未知时使用 `glob_search`。
<!-- - Read relevant existing files before proposing or applying changes. -->
- 在提议或应用更改之前，先读取相关的现有文件。
