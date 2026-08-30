<!-- # Creating a pull request -->
# 创建拉取请求

<!-- 1. Run `git status`, `git diff`, the remote tracking check, and `git log` in -->
<!--    parallel. Determine the full branch diff against the intended base branch. -->
1. 并行运行 `git status`、`git diff`、远程跟踪检查和 `git log`。确定相对于目标基础分支的完整分支差异。
<!-- 2. Analyze all changes in `<pr_analysis>` tags: -->
2. 在 `<pr_analysis>` 标签中分析所有更改：
<!--    - Summarize the problem and solution. -->
   - 总结问题和解决方案。
<!--    - Identify the important implementation decisions. -->
   - 识别重要的实现决策。
<!--    - Record tests and verification performed. -->
   - 记录已执行的测试和验证。
<!--    - Check for unrelated changes, generated artifacts, and sensitive data. -->
   - 检查不相关的更改、生成的工件和敏感数据。
<!--    - Draft a concise title and a structured pull request body. -->
   - 起草简洁的标题和结构化的拉取请求正文。
<!-- 3. Create a branch only when needed, push it with the appropriate upstream, and -->
<!--    create the pull request with `gh pr create`. -->
3. 仅在需要时创建分支，使用适当的上游推送它，并使用 `gh pr create` 创建拉取请求。

<!-- Do not update git configuration, force-push, bypass hooks, or include unrelated -->
<!-- changes. Return the created pull request URL and a concise summary of its scope. -->
不要更新 git 配置、强制推送、绕过钩子或包含不相关的更改。返回创建的拉取请求 URL 及其范围的简洁摘要。
