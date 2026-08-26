Review a GitHub pull request with code analysis. Use the `gh` CLI to fetch the PR
metadata, changed files, commits, checks, and diff. Read the relevant repository
code around each change before evaluating it.

Prioritize concrete bugs, security vulnerabilities, behavioral regressions, and
missing tests. Avoid style-only feedback unless it causes a correctness or
maintenance risk. Verify each candidate finding against the current diff and
existing safeguards before reporting it.

Return structured review feedback ordered by severity. Each finding must include
the affected file and line, the observed behavior, why it is a problem, and an
actionable fix. If there are no findings, say so and identify any remaining test
gaps or residual risk.
