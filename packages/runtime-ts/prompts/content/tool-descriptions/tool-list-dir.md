<!-- List a directory inside the current workspace as a tree, including hidden entries. -->
以树状结构列出当前工作区内的目录，包括隐藏条目。

<!-- Usage: -->
使用方法：
<!-- - `path` is relative to the working directory and defaults to `.`. -->
- `path` 相对于工作目录，默认为 `.`。
<!-- - `max_depth` defaults to 2 and may be from 1 through 4. -->
- `max_depth` 默认为 2，取值范围为 1 到 4。
<!-- - Output is limited to 200 entries and is marked when truncated. -->
- 输出限制为 200 个条目，截断时会标记。
<!-- - Use this for directory structure. Use `glob_search` when looking for files by pattern. -->
- 用于查看目录结构。按模式查找文件时使用 `glob_search`。
