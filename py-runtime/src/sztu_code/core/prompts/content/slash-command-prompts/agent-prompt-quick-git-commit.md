# Committing changes with git

1. Run `git status`, `git diff`, and `git log` in parallel.
2. Analyze all changes that will be committed and draft a commit message in
   `<commit_analysis>` tags:
   - List the files changed.
   - Summarize the nature of the changes.
   - Identify the purpose and motivation.
   - Check for sensitive information.
   - Draft a concise one- or two-sentence commit message.
3. Stage only the intended files, create the commit, and run `git status` to
   verify the resulting state.
4. If a pre-commit hook fails, fix issues caused by the intended changes and
   retry once. Do not bypass hooks.

Important:
- NEVER update git configuration.
- NEVER use interactive git commands or commands with the `-i` flag.
- Pass a multi-line commit message non-interactively using a heredoc when the
  active shell supports it.
- Do not amend an existing commit unless the user explicitly requests it.
- Do not stage unrelated user changes.
