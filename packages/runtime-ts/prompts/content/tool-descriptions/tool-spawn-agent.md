
为一个独立的任务生成一个隔离的子代理。子代理接收静态系统提示和提供的 `prompt`，但不接收父对话历史。

使用方法：
- 提供简洁的 3-5 个词的 `description`，以及包含子代理所需所有细节的完整提示。
- `subagent_type` 选择角色：coder、tester、reviewer、planner、explore、plan 或 executor。为空时默认为 coder。
- 仅对真正独立的工作使用 `run_in_background=true`；它会返回用于 `agent_result` 的运行 ID。
- 当需要结果才能继续时，使用默认的前台模式。
- `skill` 可选地为子代理应用代理技能。
- 对于广泛的只读代码库研究，优先使用 Explore 角色。
