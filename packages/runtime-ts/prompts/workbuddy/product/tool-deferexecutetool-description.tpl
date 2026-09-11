Execute a deferred tool by name. Use this to invoke tools discovered via ToolSearch without needing them in the active tools list.

Usage:
- First use ToolSearch to discover a tool and learn its parameter schema
- Then call this tool with the exact tool name and parameters
- Parameters are validated against the tool's schema before execution
- The target tool's permission checks and hooks are applied normally

Example:
DeferExecuteTool({ toolName: "ImageGen", params: { prompt: "a sunset over mountains" } })

Notes:
- If parameter validation fails, a detailed error with the expected schema is returned
- You can skip ToolSearch if you already know the tool name and parameters from a previous turn
- This tool follows standard permission checks (may require approval depending on permissions configuration)
