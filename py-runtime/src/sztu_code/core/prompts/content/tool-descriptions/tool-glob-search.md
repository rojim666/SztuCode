Find files in the current workspace whose relative paths match a glob pattern such as `**/*.py` or `src/**/*.ts`.

Usage:
- `pattern` is required. `path` optionally limits the search to a relative directory or file.
- Results are unique, sorted workspace-relative file paths, limited to 200 matches.
- Dependency and build directories such as `.git`, `.venv`, `node_modules`, `dist`, and `build` are skipped.
- Use `grep_search` to search file contents. Use an Explore sub-agent only for broader multi-round investigation.
