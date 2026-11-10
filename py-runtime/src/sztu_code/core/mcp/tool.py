from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError
from jsonschema.protocols import Validator
from jsonschema.validators import validator_for
from referencing import Registry
from referencing.exceptions import NoSuchResource, Unresolvable

from sztu_code.core.mcp.client import McpClient, McpServerUnavailableError, McpToolDef, McpToolError
from sztu_code.core.mcp.result import McpResultValidationError
from sztu_code.core.tools.base import BaseTool, ToolExecutionState, ToolResult


def _deny_remote_schema(uri: str) -> Any:
    # Never let server-provided schemas initiate network or local file reads.
    raise NoSuchResource(ref=uri)  # type: ignore[call-arg]  # attrs constructor


class McpTool(BaseTool):
    """Preserve MCP semantics without trusting remote hints as local permissions."""

    params_model = None

    def __init__(self, client: McpClient, server_name: str, tool_def: McpToolDef) -> None:
        self._client = client
        self._server_name = server_name
        self._tool_def = tool_def
        self.name = f"{server_name}__{tool_def.name}"
        self.description = tool_def.description or f"MCP tool from {server_name}"
        self.input_schema: dict[str, Any] = (
            tool_def.input_schema or {"type": "object", "properties": {}}
        )
        self._output_validator: Validator | None = None
        if tool_def.output_schema is not None:
            if not isinstance(tool_def.output_schema, dict):
                raise McpResultValidationError("MCP outputSchema must be an object")
            validator_cls = validator_for(
                tool_def.output_schema, default=None,  # type: ignore[arg-type]
            )
            if "$schema" in tool_def.output_schema and validator_cls is None:
                raise McpResultValidationError("Unsupported MCP outputSchema dialect")
            validator_cls = validator_cls or Draft202012Validator
            try:
                validator_cls.check_schema(tool_def.output_schema)
            except SchemaError as exc:
                raise McpResultValidationError("Invalid MCP outputSchema") from exc
            self._output_validator = validator_cls(
                tool_def.output_schema,
                registry=Registry(retrieve=_deny_remote_schema),  # type: ignore[call-arg]
            )

    @property
    def server_name(self) -> str:
        return self._server_name

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        metadata: dict[str, object] = {}
        try:
            result = await self._client.call_tool(self._tool_def.name, dict(params))
            metadata = {"mcp": result.as_metadata()}
            if result.is_error:
                return ToolResult(
                    content=result.render_text(), is_error=True, error_type="runtime_error",
                    metadata={**metadata, "mcp_error_kind": "tool"},
                )
            if self._output_validator is not None:
                if result.structured_content is None:
                    raise McpResultValidationError("outputSchema requires structuredContent")
                try:
                    self._output_validator.validate(result.structured_content)
                except (ValidationError, Unresolvable, RecursionError) as exc:
                    raise McpResultValidationError(
                        "structuredContent violates outputSchema; "
                        "external references are not fetched"
                    ) from exc
            return ToolResult(content=result.render_text(), metadata=metadata)
        except McpResultValidationError as exc:
            return ToolResult(
                content=f"mcp tool '{self.name}' invalid result: {exc}",
                is_error=True, error_type="schema_error",
                metadata={**metadata, "mcp_error_kind": "invalid_result"},
                execution_state=ToolExecutionState.UNKNOWN,
            )
        except (McpServerUnavailableError, McpToolError) as exc:
            kind = "transport" if isinstance(exc, McpServerUnavailableError) else "protocol"
            return ToolResult(
                content=f"mcp tool '{self.name}' {kind} error: {exc}",
                is_error=True, error_type="runtime_error", metadata={"mcp_error_kind": kind},
                execution_state=ToolExecutionState.UNKNOWN,
            )
        except Exception as exc:
            return ToolResult(
                content=f"mcp tool '{self.name}' unexpected error: {exc}",
                is_error=True, error_type="runtime_error",
                metadata={"mcp_error_kind": "unexpected"},
                execution_state=ToolExecutionState.UNKNOWN,
            )
