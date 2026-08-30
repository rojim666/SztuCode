<!-- Read the full content of a tool result that was offloaded from the conversation context. Use the `ref_path` shown in an `[上下文卸载: refs/...]` marker. -->
读取从对话上下文中卸载的工具结果的完整内容。使用 `[上下文卸载: refs/...]` 标记中显示的 `ref_path`。

<!-- Usage: -->
使用方法：
<!-- - `ref_path` must be the referenced relative offload path. -->
- `ref_path` 必须是引用的相对卸载路径。
<!-- - `offset` is a character offset and defaults to 0. -->
- `offset` 是字符偏移量，默认为 0。
<!-- - `limit` defaults to 4000 characters and may be at most 8000. -->
- `limit` 默认为 4000 个字符，最多 8000 个字符。
<!-- - The result reports the returned character range and the next offset when more content remains. -->
- 结果报告返回的字符范围，当还有更多内容时返回下一个偏移量。
