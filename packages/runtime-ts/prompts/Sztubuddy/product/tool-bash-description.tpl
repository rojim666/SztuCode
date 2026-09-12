Executes a given bash command and returns its output.

The working directory persists between commands, but shell state does not. The shell environment is initialized from the user's profile.

IMPORTANT: The user's default shell is {{defaultShell}}. Generate commands using syntax compatible with this shell.

{% if platform == 'win32' %}
IMPORTANT: On Windows, this tool uses Git Bash. Windows-specific notes:
- Use forward slashes `/` in paths (Git Bash handles conversion automatically)
- Standard Unix commands are available (ls, grep, cat, sed, awk, etc.)
- For Windows-specific operations (registry, services, COM objects, .NET), consider using the PowerShell tool instead
- Avoid CMD-style null redirects (`2>nul`) — use POSIX `2>/dev/null` instead
- Drive paths are accessible as `/c/`, `/d/` etc. (e.g., `/c/Users/name/`)
{% endif %}

IMPORTANT: Avoid using this tool to run `cat`, `head`, `tail`, `sed`, `awk`, or `echo` commands, unless explicitly instructed or after you have verified that a dedicated tool cannot accomplish your task. Instead, use the appropriate dedicated tool as this will provide a much better experience for the user:

- Read files: Use Read (NOT cat/head/tail)
- Edit files: Use Edit (NOT sed/awk)
- Write files: Use Write (NOT echo >/cat <<EOF)
- Communication: Output text directly (NOT echo/printf)

IMPORTANT: Avoid using this tool to run `find`, `grep`, or `rg` commands, unless explicitly instructed or after you have verified that a dedicated tool cannot accomplish your task. Instead, use the appropriate dedicated tool as this will provide a much better experience for the user:

- File search: Use Glob (NOT find or ls)
- Content search: Use Grep (NOT grep or rg)

While the Bash tool can do similar things, it’s better to use the built-in tools as they provide a better user experience and make it easier to review tool calls and give permission.

# Instructions
- If your command will create new directories or files, first use this tool to run `ls` to verify the parent directory exists and is the correct location.
- Always quote file paths that contain spaces with double quotes in your command (e.g., cd "path with spaces/file.txt").
- Try to maintain your current working directory throughout the session by using absolute paths and avoiding usage of `cd`. You may use `cd` if the User explicitly requests it. In particular, never prepend `cd <current-directory>` to a `git` command — `git` already operates on the current working tree, and the compound triggers a permission prompt.
- You may specify an optional timeout in milliseconds (up to {{bashMaxTimeoutMs}}ms). When the command may run longer than a few seconds (installers, build steps, long-running helper binaries, data processing) prefer to **omit the `timeout` parameter entirely** — the system default ({{bashDefaultTimeoutMs}}ms) is controlled by `BASH_DEFAULT_TIMEOUT_MS` and lets the user tune it without editing prompts. Only specify an explicit `timeout` when the command has a known short upper bound (e.g. a quick probe, a health check).
- Non-interactive runs (`--print`/`-p`, `--output-format stream-json`) exit the process as soon as the main agent finishes its turn, even if earlier commands spawned background or long-running child processes. When designing multi-step workflows (skills, scripts that kick off build/analysis pipelines), either await the child process in the foreground (do not `nohup ... &` + return immediately) or plan the turns so the final step collects the artifact/exit status before the agent returns.
- You can use the `run_in_background` parameter to run the command in the background. Prefer setting this to `true` for known long-running commands — installs, builds, image pulls, long tests, servers, etc. Examples: `yarn install/package/build`, `npm install/build`, `pnpm install`, `docker build/pull`, `cargo build`, `make`, `mvn package`, `go build`, `gradle build`. Once backgrounded you will receive a `task_id`; **you do NOT need to poll** — when the command finishes you will be automatically notified via a `<task-notification>` message in your next turn. Use the `TaskOutput` tool only when the notification arrives and you actually need the output. You do not need to use '&' at the end of the command when using this parameter.
- If you forget `run_in_background` on a long command and it hits the foreground timeout, the command will **auto-background instead of being killed** (no SIGTERM, no state loss). The tool result will tell you the new `task_id`; you will receive a `<task-notification>` when it finishes. This covers most long commands; the only exception is `sleep`, which is never auto-backgrounded because its timeout is usually the point of the command.
- When issuing multiple commands:
  - If the commands are independent and can run in parallel, make multiple Bash tool calls in a single message. Example: if you need to run "git status" and "git diff", send a single message with two Bash tool calls in parallel.
  - If the commands depend on each other and must run sequentially, use a single Bash call with '&&' to chain them together.
  - Use ';' only when you need to run commands sequentially but don't care if earlier commands fail.
  - DO NOT use newlines to separate commands (newlines are ok in quoted strings).
- For git commands:
  - For creating commits, use the `/commit` command — it handles git safety protocol, HEREDOC formatting, and pre-commit hook recovery.
  - For committing, pushing, and opening a PR, use the `/commit-push-pr` command.
  - Prefer creating a new commit rather than amending an existing commit.
  - Before running destructive operations (e.g., `git reset --hard`, `git push --force`, `git checkout --`), consider whether there is a safer alternative. Only use destructive operations when they are truly the best approach.
  - Never skip hooks (`--no-verify`) or bypass signing (`--no-gpg-sign`, `-c commit.gpgsign=false`) unless the user has explicitly asked for it. If a hook fails, investigate and fix the underlying issue.
- Avoid unnecessary `sleep` commands:
  - Do not sleep between commands that can run immediately — just run them.
  - If your command is long running and you would like to be notified when it finishes — use `run_in_background`. No sleep needed.
  - Do not retry failing commands in a sleep loop — diagnose the root cause.
  - If waiting for a background task you started with `run_in_background`, you will be automatically notified when it completes — do NOT sleep, poll, or proactively check on its progress.
  - If you must poll an external process, use a check command (e.g. `gh run view`) rather than sleeping first.
  - If you must sleep, keep the duration short (1-5 seconds) to avoid blocking the user.
- For GitHub operations (issues, PR checks, releases, comments), use the `gh` command via the Bash tool. If given a GitHub URL, use `gh` to get the information. Example: view PR comments via `gh api repos/foo/bar/pulls/123/comments`.
