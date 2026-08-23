Read an excerpt from progressively disclosed agent memory when the system prompt shows only a memory index instead of full content.

Usage:
- `layer` is required and must be `global`, `project`, or `session`.
- Prefer a specific case-insensitive `query` to find relevant text.
- Use `offset` pagination only when exact surrounding content is needed.
- `limit` defaults to 1600 characters and may be at most 4000.
- This tool reads the memory snapshot for the current run; it does not modify memory.
