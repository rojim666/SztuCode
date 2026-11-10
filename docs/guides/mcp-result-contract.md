# Python MCP 工具结果契约

Python runtime 的 stdio/TCP MCP 工具现在保留结构化结果，而不是只提取文本。

- `isError: true` 明确映射为失败，不会被当作成功，也不会因为服务端提示自动重试。
- `structuredContent` 同时保存在 `ToolResult.metadata.mcp` 和模型可见文本中。
- `content` 保留原始顺序与数据。文本直接展示；资源链接仅展示，不自动读取；图片、音频、嵌入资源及未知类型给出显式不支持提示，原始载荷仍在 metadata 中。
- 服务端声明 `outputSchema` 时，成功结果必须提供符合 schema 的 `structuredContent`。未声明方言时使用 JSON Schema 2020-12；已声明的已知方言按其规则验证，未知方言拒绝注册。
- 本地 schema 引用可以解析。外部 HTTP/file 引用不会触发读取；无法验证的结果按 schema 错误处理。
- 工具失败、JSON-RPC 错误、传输错误、格式/schema 错误通过 `mcp_error_kind` 区分。无法确认远端是否已经执行时保留 `UNKNOWN` 执行状态，不承诺安全重试。
- 工具发现按服务端原子提交。连接、初始化、发现或 schema 注册失败会关闭连接，不留下半注册工具。关闭管理器时清空工具缓存。
- `CancelledError` 继续向上传播。服务端的只读/幂等提示不会提升本地权限。

本次改动借鉴 [DeepSeek Harness MCP client](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/mcp/mcp-client) 的结果保真、显式降级与生命周期原则，不表示已经实现其全部能力。

## 验证

```bash
cd py-runtime
uv sync --group dev
uv run pytest tests/unit/test_mcp_tool.py tests/unit/test_mcp_contract.py -q
uv run ruff check src/sztu_code/core/mcp tests/unit/test_mcp_tool.py tests/unit/test_mcp_contract.py
uv run mypy src/sztu_code/core/mcp
```

回归覆盖真实本地 stdio 假服务端、混合内容、格式错误、schema 方言与引用、取消传播，以及启动失败清理。无需 API key 或外部 MCP 服务。

## 边界

这不是完整 MCP SDK 替换：协议版本协商、分页工具发现、HTTP transport、多模态模型投影、服务端能力更新、远端取消通知等仍需后续实现。保留在 metadata 中的结果不意味着现有所有 UI/持久化层都会展示它。
