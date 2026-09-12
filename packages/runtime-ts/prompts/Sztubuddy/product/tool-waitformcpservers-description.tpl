Wait for MCP servers that are still connecting and whose tools are not
yet in your tool list. Pass `servers` to wait for specific ones, or omit
it to wait for all pending servers.

If the user's request needs tools from a still-connecting server, call this
tool to wait for it. Once it connects, its tools will be added to your tool
list and you can use them directly. Returns ready=true when servers are
ready, ready=false if they failed to connect, need authentication, or are
disabled.

You do not need to ask the user for confirmation to use this tool.
