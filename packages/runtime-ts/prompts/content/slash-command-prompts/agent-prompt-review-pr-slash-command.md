<!-- Review a GitHub pull request with code analysis. Use the `gh` CLI to fetch the PR -->
<!-- metadata, changed files, commits, checks, and diff. Read the relevant repository -->
<!-- code around each change before evaluating it. -->
通过代码分析审查 GitHub 拉取请求。使用 `gh` CLI 获取 PR 元数据、更改的文件、提交、检查和差异。在评估每个更改之前，读取相关仓库中每个更改周围的代码。

<!-- Prioritize concrete bugs, security vulnerabilities, behavioral regressions, and -->
<!-- missing tests. Avoid style-only feedback unless it causes a correctness or -->
<!-- maintenance risk. Verify each candidate finding against the current diff and -->
<!-- existing safeguards before reporting it. -->
优先处理具体的 bug、安全漏洞、行为回归和缺失的测试。避免仅针对风格的反馈，除非它会导致正确性或维护风险。在报告每个候选发现之前，根据当前差异和现有保护措施进行验证。

<!-- Return structured review feedback ordered by severity. Each finding must include -->
<!-- the affected file and line, the observed behavior, why it is a problem, and an -->
<!-- actionable fix. If there are no findings, say so and identify any remaining test -->
<!-- gaps or residual risk. -->
返回按严重程度排序的结构化审查反馈。每个发现必须包括受影响的文件和行、观察到的行为、为什么这是一个问题，以及可操作的修复方案。如果没有发现，请说明并识别任何剩余的测试缺口或残余风险。
