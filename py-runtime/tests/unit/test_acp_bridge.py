from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from sztu_code.core.acp.bridge import AcpBridge
from sztu_code.core.acp.stdio import serve


class FakeBackend:
    def __init__(self) -> None:
        self.handlers: list[Any] = []
        self.created: list[str] = []
        self.sent: list[tuple[str, str, list[dict[str, Any]] | None]] = []
        self.permissions: list[tuple[str, str]] = []
        self.cancelled: list[str] = []
        self.closed = False
        self.existing: set[str] = set()

    def on_event(self, handler: Any) -> None:
        self.handlers.append(handler)

    async def create_session(self, title: str) -> str:
        self.created.append(title)
        return "daemon-sess-1"

    async def has_session(self, session_id: str) -> bool:
        return session_id in self.existing

    async def send_message(
        self, session_id: str, content: str, images: list[dict[str, Any]] | None = None
    ) -> str:
        self.sent.append((session_id, content, images))
        return "run-1"

    async def respond_permission(self, tool_use_id: str, decision: str) -> None:
        self.permissions.append((tool_use_id, decision))

    async def cancel(self, session_id: str) -> None:
        self.cancelled.append(session_id)

    async def aclose(self) -> None:
        self.closed = True

    async def emit(self, event: dict[str, Any]) -> None:
        for handler in list(self.handlers):
            await handler(event)


class FakeLink:
    def __init__(self, responses: dict[str, dict[str, Any]] | None = None) -> None:
        self.notifications: list[tuple[str, dict[str, Any]]] = []
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self._responses = responses or {}

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        self.notifications.append((method, params))

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.requests.append((method, params))
        return self._responses.get(method, {"outcome": {"outcome": "cancelled"}})

    def updates(self) -> list[dict[str, Any]]:
        return [params["update"] for method, params in self.notifications if method == "session/update"]


async def _wait_until(predicate: Any, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met before timeout")
        await asyncio.sleep(0.01)


class MemoryReader:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)

    async def readline(self) -> bytes:
        if not self._lines:
            return b""
        return self._lines.pop(0)


class MemoryWriter:
    def __init__(self) -> None:
        self.buffer = bytearray()

    def write(self, data: bytes) -> None:
        self.buffer.extend(data)

    async def drain(self) -> None:
        return None

    def messages(self) -> list[dict[str, Any]]:
        text = self.buffer.decode("utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]


async def _new_session(bridge: AcpBridge) -> str:
    await bridge.handle_request(1, "initialize", {"protocolVersion": 1, "clientCapabilities": {}})
    result = await bridge.handle_request(2, "session/new", {"cwd": "/home/me/project", "mcpServers": []})
    return str(result["sessionId"])


def _bridge(backend: FakeBackend, link: FakeLink | None = None, **kwargs: Any) -> AcpBridge:
    # 测试始终注入绑定读取器，避免依赖开发者本机的 ~/.sztu/wechat-bridge.json
    kwargs.setdefault("bound_session_reader", lambda: None)
    return AcpBridge(backend, link or FakeLink(), **kwargs)


async def test_initialize_advertises_v1_capabilities() -> None:
    backend = FakeBackend()
    bridge = _bridge(backend, agent_version="9.9.9")
    result = await bridge.handle_request(0, "initialize", {"protocolVersion": 1})
    assert result["protocolVersion"] == 1
    assert result["agentCapabilities"]["loadSession"] is False
    assert result["agentInfo"] == {"name": "sztu-code", "title": "SztuCode", "version": "9.9.9"}


async def test_new_session_creates_daemon_session() -> None:
    backend = FakeBackend()
    bridge = _bridge(backend)
    session_id = await _new_session(bridge)
    assert session_id == "daemon-sess-1"
    assert backend.created == ["WeChat · project"]


async def test_prompt_streams_updates_and_finishes_turn() -> None:
    backend = FakeBackend()
    link = FakeLink()
    bridge = _bridge(backend, link)
    session_id = await _new_session(bridge)

    task = asyncio.create_task(
        bridge.handle_request(
            3, "session/prompt", {"sessionId": session_id, "prompt": [{"type": "text", "text": "hi"}]}
        )
    )
    await _wait_until(lambda: bool(backend.sent))
    await asyncio.sleep(0.02)

    await backend.emit({"type": "llm.token", "run_id": "run-1", "token": "Hello"})
    await backend.emit(
        {"type": "tool.call_started", "run_id": "run-1", "tool_use_id": "t1", "tool_name": "read_file", "params": {}}
    )
    await backend.emit({"type": "tool.call_finished", "run_id": "run-1", "tool_use_id": "t1"})
    await backend.emit({"type": "session.waiting_for_input", "session_id": session_id, "last_run_id": "run-1"})

    assert await task == {"stopReason": "end_turn"}
    assert backend.sent == [("daemon-sess-1", "hi", [])]
    kinds = [update["sessionUpdate"] for update in link.updates()]
    assert kinds == ["agent_message_chunk", "tool_call", "tool_call_update"]
    assert link.updates()[0]["content"]["text"] == "Hello"
    assert link.updates()[1]["kind"] == "read"


async def test_prompt_forwards_images() -> None:
    backend = FakeBackend()
    bridge = _bridge(backend)
    session_id = await _new_session(bridge)
    task = asyncio.create_task(
        bridge.handle_request(
            4,
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [
                    {"type": "text", "text": "look"},
                    {"type": "image", "mimeType": "image/png", "data": "AAAA"},
                ],
            },
        )
    )
    await _wait_until(lambda: bool(backend.sent))
    await backend.emit({"type": "session.waiting_for_input", "session_id": session_id})
    assert await task == {"stopReason": "end_turn"}
    assert backend.sent[0][2] == [{"type": "image", "media_type": "image/png", "data": "AAAA"}]


async def test_permission_request_maps_option_to_decision() -> None:
    backend = FakeBackend()
    link = FakeLink(
        {"session/request_permission": {"outcome": {"outcome": "selected", "optionId": "allow_always"}}}
    )
    bridge = _bridge(backend, link)
    session_id = await _new_session(bridge)
    task = asyncio.create_task(
        bridge.handle_request(
            5, "session/prompt", {"sessionId": session_id, "prompt": [{"type": "text", "text": "run"}]}
        )
    )
    await _wait_until(lambda: bool(backend.sent))
    await asyncio.sleep(0.02)

    await backend.emit(
        {
            "type": "permission.requested",
            "run_id": "run-1",
            "session_id": session_id,
            "tool_use_id": "tu-9",
            "tool_name": "bash",
            "params": {"command": "ls"},
            "param_preview": "ls",
        }
    )
    await _wait_until(lambda: bool(backend.permissions))
    assert backend.permissions == [("tu-9", "always_allow")]
    assert link.requests[0][0] == "session/request_permission"
    assert link.requests[0][1]["options"]

    await backend.emit({"type": "session.waiting_for_input", "session_id": session_id})
    assert await task == {"stopReason": "end_turn"}


async def test_permission_denied_when_client_cancels() -> None:
    backend = FakeBackend()
    bridge = _bridge(backend)  # default outcome is cancelled
    session_id = await _new_session(bridge)
    task = asyncio.create_task(
        bridge.handle_request(
            6, "session/prompt", {"sessionId": session_id, "prompt": [{"type": "text", "text": "x"}]}
        )
    )
    await _wait_until(lambda: bool(backend.sent))
    await asyncio.sleep(0.02)
    await backend.emit(
        {"type": "permission.requested", "run_id": "run-1", "session_id": session_id, "tool_use_id": "tu-1", "tool_name": "bash", "params": {}}
    )
    await _wait_until(lambda: bool(backend.permissions))
    assert backend.permissions == [("tu-1", "deny_once")]
    await backend.emit({"type": "session.waiting_for_input", "session_id": session_id})
    await task


async def test_cancel_marks_turn_cancelled() -> None:
    backend = FakeBackend()
    bridge = _bridge(backend)
    session_id = await _new_session(bridge)
    task = asyncio.create_task(
        bridge.handle_request(
            7, "session/prompt", {"sessionId": session_id, "prompt": [{"type": "text", "text": "x"}]}
        )
    )
    await _wait_until(lambda: bool(backend.sent))
    await asyncio.sleep(0.02)
    await bridge.handle_notification("session/cancel", {"sessionId": session_id})
    assert await task == {"stopReason": "cancelled"}
    assert backend.cancelled == ["daemon-sess-1"]


async def test_prompt_rejects_unknown_session() -> None:
    bridge = _bridge(FakeBackend())
    try:
        await bridge.handle_request(8, "session/prompt", {"sessionId": "nope", "prompt": []})
    except Exception as exc:  # noqa: BLE001
        assert getattr(exc, "code", None) == -32602
    else:  # pragma: no cover - defensive
        raise AssertionError("expected invalid params error")


async def test_stdio_server_answers_initialize_then_exits() -> None:
    backend = FakeBackend()
    request_line = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": 1}}).encode()
    reader = MemoryReader([request_line + b"\n"])
    writer = MemoryWriter()

    code = await serve(backend, reader=reader, writer=writer, version="1.2.3")

    assert code == 0
    messages = writer.messages()
    assert messages[0]["id"] == 1
    assert messages[0]["result"]["protocolVersion"] == 1
    assert messages[0]["result"]["agentInfo"]["version"] == "1.2.3"
    assert backend.closed is True


async def test_stdio_server_reports_error_for_unknown_method() -> None:
    backend = FakeBackend()
    request_line = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "bogus", "params": {}}).encode()
    reader = MemoryReader([request_line + b"\n"])
    writer = MemoryWriter()
    await serve(backend, reader=reader, writer=writer)
    message = writer.messages()[0]
    assert message["error"]["code"] == -32601


async def test_new_session_reuses_bound_wechat_session() -> None:
    backend = FakeBackend()
    backend.existing.add("bound-sess")
    bridge = _bridge(backend, bound_session_reader=lambda: "bound-sess")

    assert await _new_session(bridge) == "bound-sess"
    # 复用绑定会话时不应再创建新会话
    assert backend.created == []


async def test_new_session_falls_back_when_bound_session_is_missing() -> None:
    backend = FakeBackend()
    bridge = _bridge(backend, bound_session_reader=lambda: "deleted-sess")

    assert await _new_session(bridge) == "daemon-sess-1"
    assert backend.created == ["WeChat · project"]
