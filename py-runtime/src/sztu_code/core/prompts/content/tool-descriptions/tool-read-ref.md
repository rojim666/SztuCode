Read the full content of a tool result that was offloaded from the conversation context. Use the `ref_path` shown in an `[上下文卸载: refs/...]` marker.

Usage:
- `ref_path` must be the referenced relative offload path.
- `offset` is a character offset and defaults to 0.
- `limit` defaults to 4000 characters and may be at most 8000.
- The result reports the returned character range and the next offset when more content remains.
