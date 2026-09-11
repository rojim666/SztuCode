"""ACP (Agent Client Protocol) v1 message helpers.

ACP is the JSON-RPC 2.0 protocol the OpenClaw WeChat channel plugins use to
drive external coding agents over stdio (see ``docs/guides/wechat-openclaw-acp.md``).

This module only builds and parses wire messages; it holds no transport or
session state.
"""

from __future__ import annotations

from typing import Any

JSONRPC_VERSION = "2.0"

# The protocol version advertised in ``initialize``. ACP v1 is the stable
# version implemented by the current OpenClaw/Codex/Claude ACP wrappers.
ACP_PROTOCOL_VERSION = 1

# JSON-RPC 2.0 reserved error codes plus ACP's request-cancelled code.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
REQUEST_CANCELLED = -32800

# ``session/prompt`` stop reasons.
STOP_END_TURN = "end_turn"
STOP_MAX_TOKENS = "max_tokens"
STOP_MAX_TURN_REQUESTS = "max_turn_requests"
STOP_REFUSAL = "refusal"
STOP_CANCELLED = "cancelled"

# ``session/request_permission`` outcome option kinds.
PERMISSION_ALLOW_ONCE = "allow_once"
PERMISSION_ALLOW_ALWAYS = "allow_always"
PERMISSION_REJECT_ONCE = "reject_once"
PERMISSION_REJECT_ALWAYS = "reject_always"

# SztuCode daemon permission decisions keyed by the ACP option id we advertise.
OPTION_TO_DECISION: dict[str, str] = {
    "allow_once": "allow_once",
    "allow_always": "always_allow",
    "reject_once": "deny_once",
    "reject_always": "always_deny",
}

# ACP tool-call kinds accepted by ``session/update``.
TOOL_KIND_READ = "read"
TOOL_KIND_EDIT = "edit"
TOOL_KIND_DELETE = "delete"
TOOL_KIND_MOVE = "move"
TOOL_KIND_SEARCH = "search"
TOOL_KIND_EXECUTE = "execute"
TOOL_KIND_THINK = "think"
TOOL_KIND_FETCH = "fetch"
TOOL_KIND_OTHER = "other"


class AcpError(Exception):
    """Raised by handlers to return a structured JSON-RPC error to the client."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def request(message_id: int | str, method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": message_id, "method": method, "params": params}


def notification(method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "method": method, "params": params}


def success(message_id: int | str | None, result: Any) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": message_id, "result": result}


def error(
    message_id: int | str | None, code: int, message: str, data: Any = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        payload["data"] = data
    return {"jsonrpc": JSONRPC_VERSION, "id": message_id, "error": payload}


def error_from(message_id: int | str | None, exc: AcpError) -> dict[str, Any]:
    return error(message_id, exc.code, exc.message, exc.data)


def session_update(session_id: str, update: dict[str, Any]) -> dict[str, Any]:
    return notification("session/update", {"sessionId": session_id, "update": update})


def agent_message_chunk(text: str, message_id: str | None = None) -> dict[str, Any]:
    update: dict[str, Any] = {
        "sessionUpdate": "agent_message_chunk",
        "content": {"type": "text", "text": text},
    }
    if message_id:
        update["messageId"] = message_id
    return update


def agent_thought_chunk(text: str, message_id: str | None = None) -> dict[str, Any]:
    update: dict[str, Any] = {
        "sessionUpdate": "agent_thought_chunk",
        "content": {"type": "text", "text": text},
    }
    if message_id:
        update["messageId"] = message_id
    return update


def tool_call(
    tool_call_id: str,
    title: str,
    kind: str = TOOL_KIND_OTHER,
    status: str = "pending",
    raw_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    update: dict[str, Any] = {
        "sessionUpdate": "tool_call",
        "toolCallId": tool_call_id,
        "title": title,
        "kind": kind,
        "status": status,
    }
    if raw_input is not None:
        update["rawInput"] = raw_input
    return update


def tool_call_update(
    tool_call_id: str,
    status: str,
    content: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    update: dict[str, Any] = {
        "sessionUpdate": "tool_call_update",
        "toolCallId": tool_call_id,
        "status": status,
    }
    if content is not None:
        update["content"] = content
    return update


def plan_update(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {"sessionUpdate": "plan", "entries": entries}


def usage_update(size: int, used: int) -> dict[str, Any]:
    return {"sessionUpdate": "usage_update", "size": size, "used": used}


# Map a SztuCode tool name onto an ACP tool-call kind for client display.
def tool_kind(tool_name: str) -> str:
    name = tool_name.lower()
    if name in {"read", "read_file", "view", "read_document"}:
        return TOOL_KIND_READ
    if name in {"write", "edit", "edit_file", "write_file", "apply_patch", "create_document"}:
        return TOOL_KIND_EDIT
    if name in {"delete", "remove"}:
        return TOOL_KIND_DELETE
    if name.startswith("search") or name in {"grep_search", "glob_search", "find"}:
        return TOOL_KIND_SEARCH
    if name in {"bash", "shell", "run_command", "terminal"}:
        return TOOL_KIND_EXECUTE
    if name in {"web_fetch", "fetch", "browser"}:
        return TOOL_KIND_FETCH
    return TOOL_KIND_OTHER
