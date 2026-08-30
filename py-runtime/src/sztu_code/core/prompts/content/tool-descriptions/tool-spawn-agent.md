<!-- Spawn an isolated sub-agent for a self-contained task. The child receives the static system prompt and the provided `prompt`, but not the parent conversation history. -->
为一个独立的任务生成一个隔离的子代理。子代理接收静态系统提示和提供的 `prompt`，但不接收父对话历史。

<!-- Usage: -->
使用方法：
<!-- - Provide a concise 3-5 word `description` and a complete prompt containing every detail the child needs. -->
- 提供简洁的 3-5 个词的 `description`，以及包含子代理所需所有细节的完整提示。
<!-- - `subagent_type` selects a role: coder, tester, reviewer, planner, explore, plan, or executor. Empty defaults to coder. -->
- `subagent_type` 选择角色：coder、tester、reviewer、planner、explore、plan 或 executor。为空时默认为 coder。
<!-- - Use `run_in_background=true` only for genuinely independent work; it returns a run ID for `agent_result`. -->
- 仅对真正独立的工作使用 `run_in_background=true`；它会返回用于 `agent_result` 的运行 ID。
<!-- - Use the foreground default when the result is required before continuing. -->
- 当需要结果才能继续时，使用默认的前台模式。
<!-- - `skill` optionally applies an Agent Skill to the child. -->
- `skill` 可选地为子代理应用代理技能。
<!-- - Prefer the Explore role for broad read-only codebase research. -->
- 对于广泛的只读代码库研究，优先使用 Explore 角色。
