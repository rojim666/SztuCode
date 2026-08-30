# 用户权限模式
<!--
# User permission modes
-->

<!--
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
-->
- 建议模式（`normal`）：操作遵循正常的策略评估，在不被自动允许时请求确认。
- 自动编辑模式（`accept_edits`）：工作区编辑操作自动被允许；其他操作继续通过正常权限检查。
- YOLO / 全自动模式（`auto`）：工具调用由权限管理器自动批准。
- 规划模式（`plan`，SztuCode 扩展）：只允许只读工具；写入和命令执行被阻止。

这些描述解释了各个模式。对于工具调用是否被允许，确定性的 `PermissionManager`（权限管理器）而非语言模型才是权威依据。
