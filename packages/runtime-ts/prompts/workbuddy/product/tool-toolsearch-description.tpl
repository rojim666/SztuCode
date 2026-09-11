Load tool schemas before invoking deferred tools.

Deferred tools are NOT directly callable — use ToolSearch to load their schema, then DeferExecuteTool to invoke.

## Lookup modes

1. Exact (preferred): `tool_names: ["ImageGen"]` — use when you know the tool name.
2. Search: `queries: ["image generation"]` — use when unsure which tool fits.

## Rules
- Known tool name → use `tool_names`, never guess parameters without loading schema.
- Found tools are invoked via DeferExecuteTool with validated parameters.


The following deferred tools are available via ToolSearch. Their schemas are NOT loaded — calling them directly will fail with InputValidationError. Use ToolSearch with `tool_names` to load schemas before calling them:

{% if toolSearchDeferredTools %}

<available_deferred_tools>
{{toolSearchDeferredTools}}
</available_deferred_tools>
{% endif %}
