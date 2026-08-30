<!-- Replace a previously saved session note when its fact or decision has changed. The old note is archived so contradictory active notes do not coexist. -->
当先前保存的会话笔记的事实或决策发生变化时，替换该笔记。旧笔记将被归档，以避免矛盾的活动笔记共存。

<!-- Usage: -->
使用方法：
<!-- - `note_id` must come from a prior `note_save` or `note_update` result. -->
- `note_id` 必须来自先前的 `note_save` 或 `note_update` 结果。
<!-- - `content` is the complete updated fact and must be non-empty. -->
- `content` 是完整的更新后事实，必须非空。
<!-- - Use this to correct or supersede existing session knowledge. Use `note_save` for a separate new fact. -->
- 使用此工具更正或取代现有的会话知识。对于独立的新事实使用 `note_save`。
