<!-- # Committing changes with git -->
# 使用 git 提交更改

<!-- 1. Run `git status`, `git diff`, and `git log` in parallel. -->
1. 并行运行 `git status`、`git diff` 和 `git log`。
<!-- 2. Analyze all changes that will be committed and draft a commit message in -->
<!--    `<commit_analysis>` tags: -->
2. 分析所有将要提交的更改，并在 `<commit_analysis>` 标签中起草提交消息：
<!--    - List the files changed. -->
   - 列出更改的文件。
<!--    - Summarize the nature of the changes. -->
   - 总结更改的性质。
<!--    - Identify the purpose and motivation. -->
   - 识别目的和动机。
<!--    - Check for sensitive information. -->
   - 检查敏感信息。
<!--    - Draft a concise one- or two-sentence commit message. -->
   - 起草简洁的一到两句话的提交消息。
<!-- 3. Stage only the intended files, create the commit, and run `git status` to -->
<!--    verify the resulting state. -->
3. 仅暂存预期的文件，创建提交，并运行 `git status` 验证结果状态。
<!-- 4. If a pre-commit hook fails, fix issues caused by the intended changes and -->
<!--    retry once. Do not bypass hooks. -->
4. 如果 pre-commit 钩子失败，修复预期更改导致的问题并重试一次。不要绕过钩子。

<!-- Important: -->
重要提示：
<!-- - NEVER update git configuration. -->
- 绝对不要更新 git 配置。
<!-- - NEVER use interactive git commands or commands with the `-i` flag. -->
- 绝对不要使用交互式 git 命令或带有 `-i` 标志的命令。
<!-- - Pass a multi-line commit message non-interactively using a heredoc when the -->
<!--   active shell supports it. -->
- 当活动 shell 支持时，使用 heredoc 以非交互方式传递多行提交消息。
<!-- - Do not amend an existing commit unless the user explicitly requests it. -->
- 除非用户明确要求，否则不要修改现有提交。
<!-- - Do not stage unrelated user changes. -->
- 不要暂存不相关的用户更改。
