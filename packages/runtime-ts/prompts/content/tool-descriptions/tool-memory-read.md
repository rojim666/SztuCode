<!-- Read an excerpt from progressively disclosed agent memory when the system prompt shows only a memory index instead of full content. -->
当系统提示仅显示内存索引而非完整内容时，从渐进式披露的代理内存中读取摘录。

<!-- Usage: -->
使用方法：
<!-- - `layer` is required and must be `global`, `project`, or `session`. -->
- `layer` 是必需的，必须为 `global`、`project` 或 `session`。
<!-- - Prefer a specific case-insensitive `query` to find relevant text. -->
- 优先使用特定的不区分大小写的 `query` 来查找相关文本。
<!-- - Use `offset` pagination only when exact surrounding content is needed. -->
- 仅当需要确切的周围内容时使用 `offset` 分页。
<!-- - `limit` defaults to 1600 characters and may be at most 4000. -->
- `limit` 默认为 1600 个字符，最多 4000 个字符。
<!-- - This tool reads the memory snapshot for the current run; it does not modify memory. -->
- 此工具读取当前运行的内存快照；它不会修改内存。
