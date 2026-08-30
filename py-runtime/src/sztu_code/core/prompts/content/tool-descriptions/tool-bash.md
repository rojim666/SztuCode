<!-- Execute one non-interactive shell command in the current workspace and return combined stdout and stderr. -->
在当前工作区中执行一个非交互式 shell 命令，并返回合并的 stdout 和 stderr。

<!-- Usage: -->
使用方法：
<!-- - Reserve this tool for terminal operations that require a shell. Use dedicated file and search tools instead of cat, sed, find, grep, or rg. -->
- 将此工具保留给需要 shell 的终端操作。使用专用的文件和搜索工具，而不是 cat、sed、find、grep 或 rg。
<!-- - On Windows commands run through Git Bash. Use Unix command and path syntax. -->
- 在 Windows 上，命令通过 Git Bash 运行。使用 Unix 命令和路径语法。
<!-- - Commands requiring interactive input will hang until timeout. The timeout defaults to 60 seconds and may be at most 120 seconds. -->
- 需要交互式输入的命令会挂起直到超时。超时默认 60 秒，最长 120 秒。
<!-- - Output is limited to 64 KB. A non-zero exit status is returned as an error with captured output. -->
- 输出限制为 64 KB。非零退出状态将作为错误返回，并附带捕获的输出。
<!-- - Package installation and environment update commands are blocked. Do not use destructive commands or bypass hooks unless explicitly authorized. -->
- 包安装和环境更新命令被阻止。除非明确授权，否则不要使用破坏性命令或绕过钩子。
<!-- - Quote paths containing spaces and keep commands short and focused. -->
- 引用包含空格的路径，并保持命令简短且专注。
