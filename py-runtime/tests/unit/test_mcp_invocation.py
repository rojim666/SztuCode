from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import ToolCallBlock
from sztu_code.core.mcp.client import McpClient, McpServerUnavailableError, McpToolDef, McpToolError
from sztu_code.core.mcp.tool import McpTool
from sztu_code.core.tools.base import BaseTool, ToolExecutionState, ToolResult
from sztu_code.core.tools.invocation import invoke_tool
from sztu_code.core.tools.registry import ToolRegistry


async def invoke_registered(tool: BaseTool, **kwargs: object) -> ToolResult:
    registry = ToolRegistry()
    registry.register(tool)
    return await invoke_tool(
        registry, ToolCallBlock(id="call", name=tool.name, input={}), EventBus(), "run", **kwargs,
    )


@pytest.mark.parametrize("schema, expected_kind", [
    (None, "tool"), ({"type": "object", "required": ["missing"]}, "invalid_result"),
])
async def test_mcp_error_metadata_survives_production_wrapper(schema: dict | None, expected_kind: str) -> None:
    response = {
        "content": [{"type": "text", "text": "detail"},
                    {"type": "image", "data": "opaque-image", "mimeType": "image/png"}],
        "structuredContent": {"answer": "value"},
        "isError": schema is None,
    }
    client = McpClient()
    client._call = AsyncMock(return_value=response)
    tool = McpTool(client, "fixture", McpToolDef("test", "test", output_schema=schema))
    result = await invoke_registered(tool)
    assert result.is_error
    assert result.metadata["mcp"] == response
    assert result.metadata["mcp_error_kind"] == expected_kind
    assert result.metadata["retry_decision"] == "stop"
    assert result.metadata["tool_retry_safe"] is False
    assert "opaque-image" not in result.content
    assert not result.retryable
    client._call.assert_awaited_once()
    expected_state = ToolExecutionState.COMPLETED if schema is None else ToolExecutionState.UNKNOWN
    assert result.execution_state == expected_state
    assert result.metadata["execution_state"] == expected_state.value


@pytest.mark.parametrize("exception, kind", [
    (McpToolError("bad protocol"), "protocol"),
    (McpServerUnavailableError("offline"), "transport"),
])
async def test_mcp_error_kind_survives_without_canonical_payload(exception: Exception, kind: str) -> None:
    client = McpClient()
    client._call = AsyncMock(side_effect=exception)
    result = await invoke_registered(McpTool(client, "fixture", McpToolDef("test", "test")))
    assert result.metadata["mcp_error_kind"] == kind
    assert "mcp" not in result.metadata
    assert result.metadata["retry_reason"] == "execution_state_is_unknown"


class ResultTool(BaseTool):
    name = "result"
    description = "returns controlled results"
    input_schema = {"type": "object"}
    retry_safe = True

    def __init__(self, responses: list[ToolResult | Exception], clock: list[float] | None = None):
        self.responses = responses
        self.calls = 0
        self.clock = clock

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        self.calls += 1
        if self.clock is not None:
            self.clock[0] += 10
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def transient(metadata: dict[str, object]) -> ToolResult:
    return ToolResult("transient", True, "runtime_error", metadata, retryable=True,
                      execution_state=ToolExecutionState.NOT_STARTED)


async def test_wrapper_metadata_overrides_conflicting_tool_keys_without_mutation() -> None:
    metadata = {"custom": {"value": 1}, "retry_decision": "retry", "retry_reason": "spoof",
                "execution_state": "unknown", "tool_retry_safe": False, "deadline_stage": "spoof"}
    original = ToolResult("failed", True, "schema_error", metadata)
    result = await invoke_registered(ResultTool([original]))
    assert result.metadata["custom"] == {"value": 1}
    assert result.metadata["retry_decision"] == "stop"
    assert result.metadata["retry_reason"] == "error_is_not_explicitly_transient"
    assert result.metadata["execution_state"] == "completed"
    assert result.metadata["tool_retry_safe"] is True
    assert "deadline_stage" not in result.metadata
    assert original.metadata == metadata and original.metadata["retry_decision"] == "retry"


async def test_retry_backoff_deadline_preserves_current_error_metadata() -> None:
    tool = ResultTool([transient({"attempt_payload": "first"})])
    result = await invoke_registered(tool, remaining_s=1.0)
    assert result.metadata["attempt_payload"] == "first"
    assert result.metadata["retry_reason"] == "run_deadline_would_be_exceeded"
    assert tool.calls == 1 and result.execution_state == ToolExecutionState.NOT_STARTED


async def test_retry_does_not_leak_previous_attempt_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sztu_code.core.tools.invocation._RETRY_BASE_S", 0)
    tool = ResultTool([transient({"stale": "first"}), RuntimeError("second")])
    result = await invoke_registered(tool)
    assert tool.calls == 2
    assert "stale" not in result.metadata
    assert result.is_error and "second" in result.content


async def test_last_retry_keeps_only_last_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sztu_code.core.tools.invocation._RETRY_BASE_S", 0)
    tool = ResultTool([transient({"stale": "first"}), transient({"payload": "last"})])
    result = await invoke_registered(tool)
    assert tool.calls == 2
    assert "stale" not in result.metadata and result.metadata["payload"] == "last"
    assert result.metadata["retry_reason"] == "retry_limit_exhausted"


async def test_deadline_after_return_preserves_payload_but_not_success_state() -> None:
    clock = [0.0]
    tool = ResultTool([ToolResult("late", metadata={"payload": "late"})], clock)
    result = await invoke_registered(tool, remaining_s=1.0, clock=lambda: clock[0])
    assert result.is_error and result.error_type == "deadline_exceeded"
    assert result.execution_state == ToolExecutionState.UNKNOWN
    assert result.metadata["payload"] == "late"
    assert result.metadata["retry_reason"] == "run_deadline_exceeded"
    assert tool.calls == 1
