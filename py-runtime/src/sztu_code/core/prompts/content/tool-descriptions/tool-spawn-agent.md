Spawn an isolated sub-agent for a self-contained task. The child receives the static system prompt and the provided `prompt`, but not the parent conversation history.

Usage:
- Provide a concise 3-5 word `description` and a complete prompt containing every detail the child needs.
- `subagent_type` selects a role: coder, tester, reviewer, planner, explore, plan, or executor. Empty defaults to coder.
- Use `run_in_background=true` only for genuinely independent work; it returns a run ID for `agent_result`.
- Use the foreground default when the result is required before continuing.
- `skill` optionally applies an Agent Skill to the child.
- Prefer the Explore role for broad read-only codebase research.
