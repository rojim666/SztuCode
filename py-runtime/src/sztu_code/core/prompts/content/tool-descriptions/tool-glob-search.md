<!-- Find files in the current workspace whose relative paths match a glob pattern such as `**/*.py` or `src/**/*.ts`. -->
在当前工作区中查找相对路径匹配 glob 模式（如 `**/*.py` 或 `src/**/*.ts`）的文件。

<!-- Usage: -->
使用方法：
<!-- - `pattern` is required. `path` optionally limits the search to a relative directory or file. -->
- `pattern` 是必需的。`path` 可选地将搜索限制为相对目录或文件。
<!-- - Results are unique, sorted workspace-relative file paths, limited to 200 matches. -->
- 结果是唯一的、已排序的工作区相对文件路径，限制为 200 个匹配项。
<!-- - Dependency and build directories such as `.git`, `.venv`, `node_modules`, `dist`, and `build` are skipped. -->
- 跳过依赖和构建目录，如 `.git`、`.venv`、`node_modules`、`dist` 和 `build`。
<!-- - Use `grep_search` to search file contents. Use an Explore sub-agent only for broader multi-round investigation. -->
- 使用 `grep_search` 搜索文件内容。仅对更广泛的多轮调查使用 Explore 子代理。
