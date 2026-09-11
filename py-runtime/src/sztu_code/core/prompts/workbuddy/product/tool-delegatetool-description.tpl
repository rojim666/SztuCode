Execute a tool delegated from an external client-side tool provider (e.g., IDE extension, Web UI plugin).

This tool acts as a proxy for invoking tools that are registered by external clients via the ACP protocol. The actual tool execution happens on the client side.

Usage:
- Use the toolId parameter to specify which delegate tool to execute
- Pass input parameters as a JSON object matching the delegate tool's expected schema
- An optional timeout can be specified in milliseconds
{% if delegateTools %}

## Available Delegate Tools

{{delegateTools}}

Use the toolId (bold text) as the `toolId` parameter when calling this tool.

**Recommended workflow for UI automation**: Call `ui-query` first to discover available elements, then use `ui-control` to perform actions on specific elements identified from the query results.

{{delegateToolsDetail}}
{% else %}

Notes:
- This tool is only available when delegate tools have been registered by a connected client
- If no delegate tools are registered, this tool will return an error
- Tool execution results are returned from the client side
{% endif %}
