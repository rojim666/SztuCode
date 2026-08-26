# User permission modes

- Suggest (`normal`): operations follow normal policy evaluation and request
  confirmation when they are not automatically allowed.
- Auto-edit (`accept_edits`): workspace editing operations are automatically
  allowed; other operations continue through normal permission checks.
- YOLO / Full auto (`auto`): tool calls are automatically approved by the
  permission manager.
- Plan (`plan`, SztuCode extension): only read-only tools are allowed; writing and
  command execution are blocked.

These descriptions explain the modes. The deterministic `PermissionManager`, not
the language model, is authoritative for whether a tool call is allowed.
