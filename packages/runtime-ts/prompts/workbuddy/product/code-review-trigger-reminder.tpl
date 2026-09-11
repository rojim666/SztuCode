<system-reminder data-role="code-review-trigger">
The user invoked `/code-review`{{target}} to review code for bugs and quality issues.
{%- if fix %}
The user requested --fix: after the review, apply the findings to the working tree.
{%- endif %}
{%- if comment %}
The user requested --comment: after the review, post findings as inline PR comments.
{%- endif %}

Review the current diff for correctness bugs and reuse/simplification/efficiency cleanups.

## Steps

1. Run `git diff` (or `git diff HEAD` if there are staged changes) to see what changed. If a specific PR number or target is provided, run `gh pr diff <number>` instead.

2. Analyze the changes thoroughly, looking for:
   - **Correctness bugs**: logic errors, off-by-one, null/undefined handling, race conditions, missing error handling
   - **Security issues**: injection vulnerabilities, improper input validation, exposed secrets
   - **Performance problems**: unnecessary work, N+1 patterns, missing concurrency, hot-path bloat
   - **Code quality**: duplicated code, leaky abstractions, parameter sprawl, stringly-typed code
   - **Test coverage gaps**: untested edge cases, missing error path tests

3. For each finding, determine:
   - File and line number
   - Severity (critical / warning / suggestion)
   - One-line summary of the issue
   - A concrete failure scenario (how/when this would actually break or cause harm)
   - Suggested fix

4. Call the `ReportFindings` tool once with all findings (most-severe first), mapping each to
   `file` (path + line), `summary` (one-line issue + suggested fix), and `failureScenario`
   (the concrete scenario from step 3). If `ReportFindings` is not available, present findings
   ranked most-severe first in prose instead, grouped by file when multiple findings share a file.
{%- if fix %}

After the review, apply all fixable findings to the working tree directly.
{%- endif %}
{%- if comment %}

After the review, post each finding as an inline PR comment using `gh api` or `gh pr review`.
{%- endif %}
</system-reminder>
