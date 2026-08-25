# Creating a pull request

1. Run `git status`, `git diff`, the remote tracking check, and `git log` in
   parallel. Determine the full branch diff against the intended base branch.
2. Analyze all changes in `<pr_analysis>` tags:
   - Summarize the problem and solution.
   - Identify the important implementation decisions.
   - Record tests and verification performed.
   - Check for unrelated changes, generated artifacts, and sensitive data.
   - Draft a concise title and a structured pull request body.
3. Create a branch only when needed, push it with the appropriate upstream, and
   create the pull request with `gh pr create`.

Do not update git configuration, force-push, bypass hooks, or include unrelated
changes. Return the created pull request URL and a concise summary of its scope.
