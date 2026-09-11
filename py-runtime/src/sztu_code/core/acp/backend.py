"""Backend abstraction for the ACP bridge.

``AgentBackend`` is the narrow surface the :mod:`sztu_code.core.acp.bridge`
needs. :class:`DaemonBackend` implements it on top of the existing SztuCode core
daemon, so the ACP server reuses the daemon's agent loop instead of
re-implementing it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from sztu_code.core.config import SztuConfig
from sztu_code.core.transport.socket_client import IpcError, SocketClient

EventDict = dict[str, Any]
EventHandler = Callable[[EventDict], Awaitable[None]]

# Topics the ACP bridge needs to render a turn and answer permission prompts.
_SUBSCRIBE_TOPICS = [
    "session.*",
    "run.*",
    "step.*",
    "tool.*",
    "llm.token",
    "llm.thinking",
    "llm.usage",
    "permission.*",
    "question.*",
    "plan.updated",
]


@runtime_checkable
class AgentBackend(Protocol):
    """Minimal agent backend the ACP bridge drives."""

    def on_event(self, handler: EventHandler) -> None: ...

    async def create_session(self, title: str) -> str: ...

    async def has_session(self, session_id: str) -> bool: ...

    async def send_message(
        self, session_id: str, content: str, images: list[dict[str, Any]] | None = None
    ) -> str: ...

    async def respond_permission(self, tool_use_id: str, decision: str) -> None: ...

    async def cancel(self, session_id: str) -> None: ...

    async def aclose(self) -> None: ...


class DaemonUnavailableError(RuntimeError):
    """Raised when the SztuCode core daemon is not reachable."""


class DaemonBackend:
    """``AgentBackend`` that talks to the SztuCode core daemon over IPC."""

    def __init__(self, config: SztuConfig) -> None:
        self._config = config
        self._client = SocketClient(config.host, config.port)
        self._handlers: list[EventHandler] = []
        self._connected = False
        self._loop_task: asyncio.Task[None] | None = None
        # Last run id per daemon session, used to cancel the active turn.
        self._last_run: dict[str, str] = {}

    # Register a callback for daemon events; mirrors SocketClient.on_event.
    def on_event(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    # Connect to the daemon and subscribe to the event topics the bridge maps.
    async def _ensure_connected(self) -> None:
        if self._connected:
            return
        try:
            await self._client.connect()
        except (ConnectionRefusedError, OSError) as exc:
            raise DaemonUnavailableError(
                f"SztuCode core not running ({self._config.host}:{self._config.port}); "
                "start it with `sztu core start`"
            ) from exc
        self._client.on_event(self._dispatch_event)
        self._loop_task = asyncio.create_task(self._client.run_event_loop())
        try:
            await self._client.send_command(
                "event.subscribe", {"topics": _SUBSCRIBE_TOPICS, "scope": "global"}
            )
        except IpcError as exc:
            await self.aclose()
            raise DaemonUnavailableError(f"event.subscribe failed: {exc}") from exc
        self._connected = True

    # Fan out a daemon event to every registered handler without blocking the
    # socket read loop on a slow consumer.
    async def _dispatch_event(self, event: EventDict) -> None:
        for handler in list(self._handlers):
            try:
                await handler(event)
            except Exception:  # noqa: BLE001 - a handler error must not kill the reader
                continue

    async def create_session(self, title: str) -> str:
        await self._ensure_connected()
        result = await self._client.send_command(
            "session.create", {"mode": "chat", "title": title}
        )
        return str(result["session_id"])

    # 检查 daemon 是否仍有该会话，供微信会话绑定复用前做校验
    async def has_session(self, session_id: str) -> bool:
        await self._ensure_connected()
        try:
            result = await self._client.send_command(
                "session.list", {"include_archived": True, "limit": 200}
            )
        except IpcError:
            return False
        sessions = result.get("sessions")
        if not isinstance(sessions, list):
            return False
        return any(
            isinstance(item, dict) and str(item.get("session_id")) == session_id
            for item in sessions
        )

    async def send_message(
        self, session_id: str, content: str, images: list[dict[str, Any]] | None = None
    ) -> str:
        await self._ensure_connected()
        params: dict[str, Any] = {"session_id": session_id, "content": content}
        if images:
            params["images"] = images
        result = await self._client.send_command("session.send_message", params)
        run_id = str(result["run_id"])
        self._last_run[session_id] = run_id
        return run_id

    async def respond_permission(self, tool_use_id: str, decision: str) -> None:
        await self._ensure_connected()
        await self._client.send_command(
            "permission.respond", {"tool_use_id": tool_use_id, "decision": decision}
        )

    async def cancel(self, session_id: str) -> None:
        run_id = self._last_run.get(session_id)
        if not run_id:
            return
        await self._ensure_connected()
        try:
            await self._client.send_command("run.cancel", {"run_id": run_id})
        except IpcError:
            # The run may already have finished between the cancel request and
            # the daemon lookup; treat that as a no-op.
            return

    async def aclose(self) -> None:
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._loop_task = None
        await self._client.close()
        self._connected = False
