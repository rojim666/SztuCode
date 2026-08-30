<!-- Retrieve the status or final result of a background sub-agent started with `spawn_agent(run_in_background=true)`. -->
获取通过 `spawn_agent(run_in_background=true)` 启动的后台子代理的状态或最终结果。

<!-- Usage: -->
使用方法：
<!-- - Pass the exact `run_id` returned by `spawn_agent`. -->
- 传入 `spawn_agent` 返回的精确 `run_id`。
<!-- - The tool returns `still running` while the child is active, the final text when complete, or an error if the run is unknown, cancelled, or failed. -->
- 当子代理运行时，工具返回 `still running`；完成时返回最终文本；如果运行未知、被取消或失败，则返回错误。
<!-- - Do not use this for foreground sub-agents because their result is returned directly by `spawn_agent`. -->
- 不要将此用于前台子代理，因为它们的结果由 `spawn_agent` 直接返回。
