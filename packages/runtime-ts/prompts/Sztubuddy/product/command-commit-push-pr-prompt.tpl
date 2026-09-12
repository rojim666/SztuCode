## Context

- `git status`: !`git status`
- `git diff HEAD`: !`git diff HEAD`
- `git branch --show-current`: !`git branch --show-current`
- `git diff origin/HEAD...HEAD` (commits since diverged from default): !`git diff origin/HEAD...HEAD`
- `gh pr view --json number 2>/dev/null || true`: !`gh pr view --json number 2>/dev/null || true`

## Git Safety Protocol

- NEVER update the git config
- NEVER run destructive/irreversible git commands (like push --force, hard reset, etc) unless the user explicitly requests them
- NEVER skip hooks (--no-verify, --no-gpg-sign, etc) unless the user explicitly requests it
- NEVER run force push to main/master, warn the user if they request it
- Do not commit files that likely contain secrets (.env, credentials.json, etc)
- Never use git commands with the -i flag (like git rebase -i or git add -i) since they require interactive input which is not supported

## Your task

Analyze all changes that will be included in the pull request, making sure to look at all relevant commits (NOT just the latest commit, but ALL commits that will be included — use the `git diff origin/HEAD...HEAD` output above).

Based on the above changes:

1. Create a new branch if currently on the default branch (use a descriptive name like `feature-name` or `fix-xxx`).

2. Create a single commit with an appropriate message using HEREDOC syntax:

```
git commit -m "$(cat <<'EOF'
Commit message here.{% if settings.includeCoAuthoredBy %}

🤖 Generated with [CodeBuddy Code]

Co-Authored-By: CodeBuddy Code{% endif %}
EOF
)"
```

3. Push the branch to origin (use `-u` on first push).

4. If a PR already exists for this branch (check the `gh pr view` output above), update the PR title and body using `gh pr edit` to reflect the current diff. Otherwise, create a pull request using `gh pr create` with HEREDOC syntax for the body.
   - IMPORTANT: Keep PR titles short (under 70 characters). Use the body for details.

```
gh pr create --title "Short, descriptive title" --body "$(cat <<'EOF'
## Summary
<1-3 bullet points>

## Test plan
[Bulleted markdown checklist of TODOs for testing the pull request...]{% if settings.includeCoAuthoredBy %}

🤖 Generated with [CodeBuddy Code]{% endif %}
EOF
)"
```

You have the capability to call multiple tools in a single response. You MUST do all of the above in a single message.

Return the PR URL when you're done, so the user can see it.
