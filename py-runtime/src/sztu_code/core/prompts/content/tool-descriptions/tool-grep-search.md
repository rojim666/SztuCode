<!-- Search text file contents in the current workspace with a regular expression. Results use `path:line: text` with workspace-relative paths and 1-based line numbers. -->
使用正则表达式在当前工作区中搜索文本文件内容。结果使用 `路径:行号: 文本` 格式，包含工作区相对路径和从 1 开始的行号。

<!-- Usage: -->
使用方法：
<!-- - `pattern` is required. Matching is case-insensitive by default; set `case_sensitive=true` when needed. -->
- `pattern` 是必需的。默认匹配不区分大小写；需要时设置 `case_sensitive=true`。
<!-- - `path` may limit the search to a relative directory or file, and `glob` may filter relative file paths. -->
- `path` 可以将搜索限制为相对目录或文件，`glob` 可以过滤相对文件路径。
<!-- - The tool skips binary files and common dependency/build directories. -->
- 该工具会跳过二进制文件和常见的依赖/构建目录。
<!-- - It reads at most 512 KB per file and returns at most 200 matching lines. -->
- 每个文件最多读取 512 KB，最多返回 200 个匹配行。
<!-- - Use this instead of running grep or rg through `bash`. -->
- 使用此工具而不是通过 `bash` 运行 grep 或 rg。
