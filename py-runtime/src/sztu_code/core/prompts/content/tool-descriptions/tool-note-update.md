Replace a previously saved session note when its fact or decision has changed. The old note is archived so contradictory active notes do not coexist.

Usage:
- `note_id` must come from a prior `note_save` or `note_update` result.
- `content` is the complete updated fact and must be non-empty.
- Use this to correct or supersede existing session knowledge. Use `note_save` for a separate new fact.
