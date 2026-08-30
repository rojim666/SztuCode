
# SztuCode 工具环境

- 传递给内置文件工具的文件路径必须相对于工作目录；不要使用绝对路径。
- 在 Windows 上，`bash` 工具使用 Git Bash 而不是 cmd。请使用 `ls`、`pwd`、`cat` 和 `which`；使用正斜杠；使用 `export VAR=val`、`$VAR`、`/dev/null` 和 `cd path`。不要使用仅 cmd 支持的形式，如 `dir`、`where`、`set VAR=val`、`%VAR%`、`nul` 或 `cd /d X`。
- **不要**使用 pip、npm、apt、brew、conda 或 ensurepip 安装包或修改环境，除非任务明确要求。假设依赖项已经可用。
- 优先使用 `edit_file` 进行定向修改；`write_file` 会重写整个文件。
- 当工具调用失败时，读取错误信息，调整参数并重试。不要重复完全相同的失败调用。
