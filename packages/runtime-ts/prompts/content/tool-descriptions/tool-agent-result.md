获取通过 `spawn_agent(run_in_background=true)` 启动的后台子代理的状态或最终结果。

使用方法：
- 传入 `spawn_agent` 返回的精确 `run_id`。
- 当子代理运行时，工具返回 `still running`；完成时返回最终文本；如果运行未知、被取消或失败，则返回错误。
- 不要将此用于前台子代理，因为它们的结果由 `spawn_agent` 直接返回。
