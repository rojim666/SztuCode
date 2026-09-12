Use this tool ONLY when the user explicitly asks to work in a worktree.
This tool creates an isolated git worktree and switches the current session into it.

## When to Use

- The user explicitly says "worktree"
  (e.g., "start a worktree", "work in a worktree", "create a worktree", "use a worktree")

## When NOT to Use

- The user asks to create a branch, switch branches, or work on a different branch — use git commands instead
- The user asks to fix a bug or work on a feature — use normal git workflow unless they specifically mention worktrees
- Never use this tool unless the user explicitly mentions "worktree"

## Requirements

- Must be in a git repository, OR have WorktreeCreate/WorktreeRemove hooks configured in settings.json
- Must not already be in a worktree

## Behavior

- In a git repository: creates a new git worktree inside `.codebuddy/worktrees/` with a new branch based on HEAD
- Outside a git repository: delegates to WorktreeCreate/WorktreeRemove hooks for VCS-agnostic isolation
- Switches the session's working directory to the new worktree
- On session exit, the user will be prompted to keep or remove the worktree
- When `path` is provided: attaches to (switches into) that existing worktree instead of creating a new one. The pre-existing worktree is never removed on exit (always kept), since it was not created by this session.

## Parameters

- `name` (optional): A name for the worktree. If not provided, a random name is generated. Ignored when `path` is provided.
- `branch` (optional): The base branch to create the worktree from. Ignored when `path` is provided.
- `path` (optional): Path to an existing git worktree to attach to instead of creating a new one. Must be a linked worktree of the current repository (not the main working tree); otherwise the tool returns an error.

