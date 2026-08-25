Search text file contents in the current workspace with a Python regular expression. Results use `path:line: text` with workspace-relative paths and 1-based line numbers.

Usage:
- `pattern` is required. Matching is case-insensitive by default; set `case_sensitive=true` when needed.
- `path` may limit the search to a relative directory or file, and `glob` may filter relative file paths.
- The tool skips binary files and common dependency/build directories.
- It reads at most 512 KB per file and returns at most 200 matching lines.
- Use this instead of running grep or rg through `bash`.
