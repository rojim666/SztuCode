from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from sztu_code.core.config import McpServerConfig
from sztu_code.core.mcp.client import McpClient, McpToolDef, McpToolError
from sztu_code.core.mcp.result import McpCallResult, McpResultValidationError
from sztu_code.core.mcp.server import McpServerManager
from sztu_code.core.mcp.tool import McpTool
from sztu_code.core.tools.base import ToolExecutionState, ToolPermission


def make_tool(response: dict, schema: dict | None = None) -> McpTool:
    client = McpClient()
    client._call = AsyncMock(return_value=response)
    return McpTool(client, "fixture", McpToolDef("sample", "Test", output_schema=schema))


async def test_structured_content_preserved_and_visible() -> None:
    value = {"count": 3, "items": ["中文", "b"]}
    result = await make_tool({"structuredContent": value}).invoke({})
    assert not result.is_error
    assert result.metadata["mcp"]["structuredContent"] == value
    assert '"count": 3' in result.content and "中文" in result.content


async def test_tool_error_skips_success_schema_and_never_retries() -> None:
    tool = make_tool({"isError": True, "content": [{"type": "text", "text": "denied"}]},
                     {"type": "object", "required": ["count"]})
    result = await tool.invoke({})
    assert result.is_error and result.content == "denied"
    assert result.metadata["mcp_error_kind"] == "tool"
    assert not result.retryable and not tool.is_retry_safe({})
    assert tool.required_permission == ToolPermission.WORKSPACE_WRITE


async def test_empty_error_is_visible() -> None:
    result = await make_tool({"isError": True}).invoke({})
    assert result.is_error and result.content


async def test_mixed_content_keeps_order_and_unsupported_payload_in_metadata() -> None:
    blocks = [{"type": "text", "text": "first"},
              {"type": "image", "data": "PRIVATE_PAYLOAD", "mimeType": "image/png"},
              {"type": "resource_link", "uri": "file:///never-fetch", "name": "sample"},
              {"type": "audio", "data": "PRIVATE_AUDIO"},
              {"type": "resource", "resource": {"text": "PRIVATE_RESOURCE"}},
              {"type": "text", "text": "last"}]
    result = await make_tool({"content": blocks}).invoke({})
    assert not result.is_error
    assert result.content.startswith("first\n") and result.content.endswith("last")
    assert "PRIVATE_" not in result.content
    assert "not supported" in result.content and "file:///never-fetch" in result.content
    assert result.metadata["mcp"]["content"] == blocks


@pytest.mark.parametrize("response", [
    {"content": {}}, {"content": [None]}, {"content": [{}]},
    {"content": [{"type": "text"}]}, {"content": [{"type": "resource_link"}]},
    {"structuredContent": []}, {"structuredContent": None},
    {"isError": "false"}, {"isError": 1},
])
async def test_malformed_response_is_schema_error(response: dict) -> None:
    result = await make_tool(response).invoke({})
    assert result.is_error and result.error_type == "schema_error"
    assert result.execution_state == ToolExecutionState.UNKNOWN


@pytest.mark.parametrize("response", [{}, {"structuredContent": {}}, {"structuredContent": {"n": "bad"}}])
async def test_output_schema_enforced(response: dict) -> None:
    result = await make_tool(response, {
        "type": "object", "required": ["n"], "properties": {"n": {"type": "integer"}},
    }).invoke({})
    assert result.is_error and result.error_type == "schema_error"


async def test_local_schema_refs_work() -> None:
    result = await make_tool({"structuredContent": {"n": 3}}, {
        "properties": {"n": {"$ref": "#/$defs/n"}}, "$defs": {"n": {"type": "integer"}},
    }).invoke({})
    assert not result.is_error


@pytest.mark.parametrize("uri", ["https://invalid.test/schema", "file:///etc/passwd"])
async def test_external_schema_refs_are_not_fetched(uri: str) -> None:
    result = await make_tool({"structuredContent": {}}, {"$ref": uri}).invoke({})
    assert result.is_error and "not fetched" in result.content


@pytest.mark.parametrize("schema", [{"type": "invalid"}, {"$schema": "https://invalid.test/custom"}])
def test_invalid_schema_rejected_before_execution(schema: dict) -> None:
    with pytest.raises(McpResultValidationError):
        make_tool({}, schema)


async def test_declared_draft7_keywords_are_enforced() -> None:
    result = await make_tool({"structuredContent": {"a": 1}}, {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object", "dependencies": {"a": ["b"]},
    }).invoke({})
    assert result.is_error and result.error_type == "schema_error"
    assert result.metadata["mcp"]["structuredContent"] == {"a": 1}


def test_metadata_is_deep_copied() -> None:
    response = {"content": [{"type": "text", "text": "safe"}]}
    result = McpCallResult.from_response(response)
    response["content"][0]["text"] = "changed"
    result.as_metadata()["content"][0]["text"] = "also changed"
    assert result.render_text() == "safe"


async def test_protocol_error_distinct_from_tool_error() -> None:
    tool = make_tool({})
    tool._client._call = AsyncMock(side_effect=McpToolError("bad request"))
    result = await tool.invoke({})
    assert result.metadata["mcp_error_kind"] == "protocol"
    assert result.execution_state == ToolExecutionState.UNKNOWN


async def test_cancellation_propagates() -> None:
    tool = make_tool({})
    tool._client._call = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await tool.invoke({})


async def test_list_tools_preserves_schema() -> None:
    client = McpClient()
    client._call = AsyncMock(return_value={"tools": [{"name": "sample", "outputSchema": {"type": "object"}}]})
    assert (await client.list_tools())[0].output_schema == {"type": "object"}


def fake_client(definitions: list[McpToolDef]) -> McpClient:
    client = McpClient()
    client.list_tools = AsyncMock(return_value=definitions)
    client.close = AsyncMock()
    return client


async def test_invalid_discovery_is_atomic_and_closes_client() -> None:
    client = fake_client([McpToolDef("ok", "ok"), McpToolDef("bad", "bad", output_schema={"type": "invalid"})])
    manager = McpServerManager()
    manager._connect = AsyncMock(return_value=client)
    config = McpServerConfig(name="fixture", command="unused")
    await manager.start_all([config])
    assert manager.get_tools() == []
    assert manager.statuses([config])[0]["status"] == "unavailable"
    client.close.assert_awaited_once()
    await manager.stop_all()
    client.close.assert_awaited_once()


async def test_cancelled_discovery_closes_and_propagates() -> None:
    client = fake_client([])
    client.list_tools = AsyncMock(side_effect=asyncio.CancelledError())
    manager = McpServerManager()
    manager._connect = AsyncMock(return_value=client)
    with pytest.raises(asyncio.CancelledError):
        await manager.start_all([McpServerConfig(name="fixture", command="unused")])
    client.close.assert_awaited_once()
    assert manager.get_tools() == []


async def test_start_idempotent_stop_clears_cache() -> None:
    client = fake_client([McpToolDef("ok", "ok")])
    manager = McpServerManager()
    manager._connect = AsyncMock(return_value=client)
    config = McpServerConfig(name="fixture", command="unused")
    await manager.start_all([config])
    await manager.start_all([config])
    assert len(manager.get_tools()) == 1
    manager._connect.assert_awaited_once()
    await manager.stop_all()
    assert manager.get_tools() == []
    assert manager.statuses([config])[0]["tool_count"] == 0
    client.close.assert_awaited_once()


@pytest.mark.parametrize("failure", [RuntimeError("initialize failed"), asyncio.CancelledError()])
async def test_partial_connection_is_closed(failure: BaseException) -> None:
    client = fake_client([])
    client.connect_stdio = AsyncMock(side_effect=failure)
    with patch("sztu_code.core.mcp.server.McpClient", return_value=client):
        with pytest.raises(type(failure)):
            await McpServerManager()._connect(McpServerConfig(name="fixture", command="unused"))
    client.close.assert_awaited_once()


async def test_real_stdio_server_contract(tmp_path: Path) -> None:
    server = tmp_path / "server.py"
    server.write_text('''import json, sys
for line in sys.stdin:
    request = json.loads(line)
    if "id" not in request:
        continue
    method = request["method"]
    if method == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {}}
    elif method == "tools/list":
        result = {"tools": [{"name": "count", "outputSchema": {"type": "object", "required": ["count"]}}]}
    elif request["params"]["arguments"].get("fail"):
        result = {"content": [{"type": "text", "text": "failure"}], "isError": True}
    else:
        result = {"content": [{"type": "text", "text": "counted"}], "structuredContent": {"count": 3}}
    print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}), flush=True)
''')
    client = McpClient()
    try:
        await client.connect_stdio(sys.executable, ["-u", str(server)])
        tool = McpTool(client, "local", (await client.list_tools())[0])
        success = await tool.invoke({})
        assert not success.is_error
        assert success.metadata["mcp"]["structuredContent"] == {"count": 3}
        failure = await tool.invoke({"fail": True})
        assert failure.is_error and failure.content == "failure"
    finally:
        await client.close()


@pytest.mark.parametrize("envelope", [
    '[]', '{"id":1,"result":null}', '{"id":1,"result":[]}',
    '{"id":1}', '{"id":1,"error":"bad"}',
])
async def test_malformed_wire_envelope_is_contract_error(envelope: str) -> None:
    client = McpClient()
    client._write_line = AsyncMock()
    client._read_line = AsyncMock(return_value=envelope)
    tool = McpTool(client, "fixture", McpToolDef("sample", "Test"))
    result = await tool.invoke({})
    assert result.is_error and result.error_type == "schema_error"
    assert result.metadata["mcp_error_kind"] == "invalid_result"
