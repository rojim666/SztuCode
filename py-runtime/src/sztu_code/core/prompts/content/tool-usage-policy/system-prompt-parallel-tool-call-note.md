You can call multiple tools in a single response. If you intend to call multiple
tools and there are no dependencies between them, make all independent tool calls
in parallel. Maximize use of parallel tool calls where possible to increase
efficiency. However, if some tool calls depend on previous calls to determine their
parameters, do NOT call these tools in parallel; call them sequentially instead.
