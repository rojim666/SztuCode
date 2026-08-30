<!-- Perform exact string replacement in an existing UTF-8 text file inside the current workspace. -->
在当前工作区内的现有 UTF-8 文本文件中执行精确字符串替换。

<!-- Usage: -->
使用方法：
<!-- - `path` must be relative to the working directory. -->
- `path` 必须相对于工作目录。
<!-- - `old_string` must match exactly, including whitespace and indentation. -->
- `old_string` 必须精确匹配，包括空白和缩进。
<!-- - By default `old_string` must occur exactly once. Add surrounding context when it is ambiguous, or set `replace_all=true` only when every occurrence should change. -->
- 默认情况下，`old_string` 必须恰好出现一次。当存在歧义时，添加上下文；或仅当所有出现都需要更改时设置 `replace_all=true`。
<!-- - `old_string` and `new_string` must differ. Files larger than 1 MB are rejected. -->
- `old_string` 和 `new_string` 必须不同。大于 1 MB 的文件将被拒绝。
<!-- - Prefer this tool for focused edits. Use `write_file` only for new files or complete rewrites. -->
- 对于重点编辑，优先使用此工具。仅对新文件或完全重写使用 `write_file`。
