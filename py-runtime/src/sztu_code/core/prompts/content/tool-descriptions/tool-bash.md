Execute one non-interactive shell command in the current workspace and return combined stdout and stderr.

Usage:
- Reserve this tool for terminal operations that require a shell. Use dedicated file and search tools instead of cat, sed, find, grep, or rg.
- On Windows commands run through Git Bash. Use Unix command and path syntax.
- Commands requiring interactive input will hang until timeout. The timeout defaults to 60 seconds and may be at most 120 seconds.
- Output is limited to 64 KB. A non-zero exit status is returned as an error with captured output.
- Package installation and environment update commands are blocked. Do not use destructive commands or bypass hooks unless explicitly authorized.
- Quote paths containing spaces and keep commands short and focused.
