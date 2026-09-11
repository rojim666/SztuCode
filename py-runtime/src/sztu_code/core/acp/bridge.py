"""ACP agent bridge: maps ACP sessions onto SztuCode daemon sessions.

The bridge is transport-agnostic. It receives JSON-RPC messages from a
:class:`ClientLink` (implemented over stdio in :mod:`sztu_code.core.acp.stdio`)
and drives an :class:`AgentBackend` (the SztuCode daemon). It is intentionally
free of any socket or process handling so it can be unit-tested directly.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from sztu_code.core.acp import protocol as p
from sztu_code.core.acp.backend import AgentBackend, DaemonUnavailableError
from sztu_code.core.transport.socket_client import IpcError
from sztu_code.core.wechat import read_bound_session_id

logger = logging.getLogger(__name__)


class ClientLink(Protocol):
    """Agent-side handle for sending messages back to the ACP client."""

    async def notify(self, method: str, params: dict[str, Any]) -> None: ...

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class _AcpSession:
    acp_id: str
    daemon_id: str
    cwd: str


class AcpBridge:
    """Serve ACP ``initialize``/``session/*`` methods for a single connection."""

    def __init__(
        self,
        backend: AgentBackend,
        link: ClientLink,
        agent_version: str = "0.0.1",
        agent_name: str = "sztu-code",
        bound_session_reader: Callable[[], str | None] | None = None,
    ) -> None:
        self._backend = backend
        self._link = link
        self._version = agent_version
        self._agent_name = agent_name
        self._read_bound_session = bound_session_reader or read_bound_session_id
        self._sessions: dict[str, _AcpSession] = {}
        self._run_to_session: dict[str, str] = {}
        self._active_turns: dict[str, asyncio.Future[str]] = {}
        self._message_serial = 0
        self._permission_tasks: set[asyncio.Task[None]] = set()
        backend.on_event(self._on_event)

    # ---- request / notification dispatch -----------------------------------

    async def handle_request(
        self, message_id: int | str, method: str, params: dict[str, Any]
    ) -> Any:
        if method == "initialize":
            return self._initialize(params)
        if method == "session/new":
            return await self._new_session(params)
        if method == "session/prompt":
            return await self._prompt(params)
        if method in ("session/load", "session/resume"):
            raise p.AcpError(
                p.METHOD_NOT_FOUND, f"{method} is not supported (loadSession=false)"
            )
        raise p.AcpError(p.METHOD_NOT_FOUND, f"unknown method: {method}")

    async def handle_notification(self, method: str, params: dict[str, Any]) -> None:
        if method == "session/cancel":
            await self._cancel(params)
        elif method == "$/cancel_request":
            # Cancellation of an agent-initiated request to the client. The
            # bridge only sends session/request_permission, which is already
            # resolved through the link; nothing further to do here.
            return
        else:
            logger.debug("ignoring unknown ACP notification: %s", method)

    # ---- ACP methods --------------------------------------------------------

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        # ACP requires the agent to echo the negotiated protocol version.
        return {
            "protocolVersion": p.ACP_PROTOCOL_VERSION,
            "agentCapabilities": {
                "loadSession": False,
                "promptCapabilities": {
                    "image": True,
                    "audio": False,
                    "embeddedContext": False,
                },
            },
            "agentInfo": {
                "name": self._agent_name,
                "title": "SztuCode",
                "version": self._version,
            },
            "authMethods": [],
        }

    async def _new_session(self, params: dict[str, Any]) -> dict[str, Any]:
        cwd = str(params.get("cwd") or "")
        bound_id = await self._bound_session()
        if bound_id is not None:
            self._sessions[bound_id] = _AcpSession(
                acp_id=bound_id, daemon_id=bound_id, cwd=cwd
            )
            return {"sessionId": bound_id}
        title = _session_title(cwd)
        try:
            daemon_id = await self._backend.create_session(title)
        except (DaemonUnavailableError, IpcError, OSError) as exc:
            raise p.AcpError(p.INTERNAL_ERROR, f"failed to create session: {exc}") from exc
        self._sessions[daemon_id] = _AcpSession(acp_id=daemon_id, daemon_id=daemon_id, cwd=cwd)
        return {"sessionId": daemon_id}

    # 微信场景下复用桌面端绑定的会话，让消息落入用户已选的上下文；
    # 绑定缺失或会话已被删除时回退到新建，不让握手失败。
    async def _bound_session(self) -> str | None:
        bound_id = self._read_bound_session()
        if not bound_id:
            return None
        try:
            exists = await self._backend.has_session(bound_id)
        except (DaemonUnavailableError, IpcError, OSError) as exc:
            logger.debug("bound session check failed: %s", exc)
            return None
        if not exists:
            logger.warning(
                "bound WeChat session %s no longer exists; creating a new session", bound_id
            )
            return None
        logger.info("reusing bound WeChat session %s", bound_id)
        return bound_id

    async def _prompt(self, params: dict[str, Any]) -> dict[str, Any]:
        session_id = str(params.get("sessionId") or "")
        session = self._sessions.get(session_id)
        if session is None:
            raise p.AcpError(p.INVALID_PARAMS, f"unknown sessionId: {session_id}")
        if session_id in self._active_turns:
            raise p.AcpError(p.INVALID_REQUEST, "a prompt turn is already in progress")

        text, images = _flatten_prompt(params.get("prompt"))
        if not text and not images:
            raise p.AcpError(p.INVALID_PARAMS, "prompt must contain text or image content")

        loop = asyncio.get_running_loop()
        turn: asyncio.Future[str] = loop.create_future()
        self._active_turns[session_id] = turn
        try:
            run_id = await self._backend.send_message(session.daemon_id, text, images)
        except (DaemonUnavailableError, IpcError, OSError) as exc:
            self._active_turns.pop(session_id, None)
            raise p.AcpError(p.INTERNAL_ERROR, f"failed to send message: {exc}") from exc
        self._run_to_session[run_id] = session_id
        try:
            stop_reason = await turn
        finally:
            self._active_turns.pop(session_id, None)
        return {"stopReason": stop_reason}

    async def _cancel(self, params: dict[str, Any]) -> None:
        session_id = str(params.get("sessionId") or "")
        session = self._sessions.get(session_id)
        if session is None:
            return
        try:
            await self._backend.cancel(session.daemon_id)
        except (IpcError, OSError):
            pass
        self._finish_turn(session_id, p.STOP_CANCELLED)

    # ---- daemon events -> ACP session/update -------------------------------

    async def _on_event(self, event: dict[str, Any]) -> None:
        etype = str(event.get("type", ""))

        if etype == "permission.requested":
            task = asyncio.create_task(self._on_permission(event))
            self._permission_tasks.add(task)
            task.add_done_callback(self._permission_tasks.discard)
            return

        if etype == "session.waiting_for_input":
            self._finish_turn(str(event.get("session_id", "")), p.STOP_END_TURN)
            return

        if etype == "session.closed":
            self._finish_turn(str(event.get("session_id", "")), p.STOP_END_TURN)
            return

        run_id = str(event.get("run_id", ""))
        session_id = self._run_to_session.get(run_id)
        if session_id is None:
            return

        if etype == "llm.token":
            await self._send_update(
                session_id, p.agent_message_chunk(str(event.get("token", "")))
            )
        elif etype == "llm.thinking":
            await self._send_update(
                session_id, p.agent_thought_chunk(str(event.get("thinking", "")))
            )
        elif etype == "tool.call_started":
            raw_input = event.get("params") if isinstance(event.get("params"), dict) else None
            await self._send_update(
                session_id,
                p.tool_call(
                    tool_call_id=str(event.get("tool_use_id", "")),
                    title=str(event.get("tool_name", "tool")),
                    kind=p.tool_kind(str(event.get("tool_name", ""))),
                    status="in_progress",
                    raw_input=raw_input,
                ),
            )
        elif etype == "tool.call_finished":
            await self._send_update(
                session_id,
                p.tool_call_update(str(event.get("tool_use_id", "")), "completed"),
            )
        elif etype == "tool.call_failed":
            await self._send_update(
                session_id,
                p.tool_call_update(str(event.get("tool_use_id", "")), "failed"),
            )
        elif etype == "llm.usage":
            context_window = int(event.get("context_window") or 0)
            if context_window > 0:
                used = int(event.get("input_tokens") or 0) + int(event.get("output_tokens") or 0)
                await self._send_update(session_id, p.usage_update(context_window, used))
        elif etype == "plan.updated":
            entries = [
                {
                    "content": str(item.get("subject", "")),
                    "priority": "medium",
                    "status": str(item.get("status", "pending")),
                }
                for item in event.get("items", [])
                if isinstance(item, dict)
            ]
            if entries:
                await self._send_update(session_id, p.plan_update(entries))
        elif etype == "run.finished":
            self._run_to_session.pop(run_id, None)
            reason = str(event.get("reason") or "")
            stop = p.STOP_CANCELLED if reason == "cancelled" else p.STOP_END_TURN
            self._finish_turn(session_id, stop)

    async def _on_permission(self, event: dict[str, Any]) -> None:
        run_id = str(event.get("run_id", ""))
        session_id = self._run_to_session.get(run_id) or str(event.get("session_id", ""))
        if session_id not in self._sessions:
            return
        tool_use_id = str(event.get("tool_use_id", ""))
        tool_call: dict[str, Any] = {
            "toolCallId": tool_use_id,
            "title": str(event.get("tool_name", "tool")),
            "kind": p.tool_kind(str(event.get("tool_name", ""))),
            "status": "pending",
            "rawInput": event.get("params") if isinstance(event.get("params"), dict) else {},
        }
        options = [
            {"optionId": "allow_once", "name": "Allow once", "kind": p.PERMISSION_ALLOW_ONCE},
            {"optionId": "allow_always", "name": "Always allow", "kind": p.PERMISSION_ALLOW_ONCE},
            {"optionId": "reject_once", "name": "Reject", "kind": p.PERMISSION_REJECT_ONCE},
            {
                "optionId": "reject_always",
                "name": "Always reject",
                "kind": p.PERMISSION_REJECT_ONCE,
            },
        ]
        decision = "deny_once"
        try:
            result = await self._link.request(
                "session/request_permission",
                {"sessionId": session_id, "toolCall": tool_call, "options": options},
            )
            decision = _decision_from_outcome(result.get("outcome"))
        except p.AcpError:
            decision = "deny_once"
        except asyncio.CancelledError:
            decision = "deny_once"
            raise
        except Exception:  # noqa: BLE001 - never leave the daemon waiting
            decision = "deny_once"
        try:
            await self._backend.respond_permission(tool_use_id, decision)
        except (IpcError, OSError):
            logger.warning("failed to deliver permission decision for %s", tool_use_id)

    async def _send_update(self, session_id: str, update: dict[str, Any]) -> None:
        try:
            await self._link.notify("session/update", {"sessionId": session_id, "update": update})
        except Exception:  # noqa: BLE001 - a closed client must not crash the bridge
            logger.debug("dropping update for closed session %s", session_id)

    def _finish_turn(self, session_id: str, stop_reason: str) -> None:
        turn = self._active_turns.get(session_id)
        if turn is not None and not turn.done():
            turn.set_result(stop_reason)

    async def aclose(self) -> None:
        for task in list(self._permission_tasks):
            task.cancel()
        self._permission_tasks.clear()


def _session_title(cwd: str) -> str:
    if not cwd:
        return "WeChat"
    cleaned = cwd.replace("\\", "/").rstrip("/")
    name = cleaned.rsplit("/", 1)[-1] if cleaned else ""
    return f"WeChat · {name}" if name else "WeChat"


def _decision_from_outcome(outcome: Any) -> str:
    if not isinstance(outcome, dict):
        return "deny_once"
    if outcome.get("outcome") != "selected":
        return "deny_once"
    option_id = str(outcome.get("optionId", ""))
    return p.OPTION_TO_DECISION.get(option_id, "deny_once")


def _flatten_prompt(blocks: Any) -> tuple[str, list[dict[str, Any]]]:
    text_parts: list[str] = []
    images: list[dict[str, Any]] = []
    if not isinstance(blocks, list):
        return "", []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            value = block.get("text")
            if isinstance(value, str) and value:
                text_parts.append(value)
        elif btype == "image":
            data = block.get("data")
            mime = block.get("mimeType")
            if isinstance(data, str) and isinstance(mime, str):
                images.append({"type": "image", "media_type": mime, "data": data})
        elif btype == "resource":
            resource = block.get("resource")
            if isinstance(resource, dict) and isinstance(resource.get("text"), str):
                text_parts.append(str(resource["text"]))
    return "\n".join(text_parts).strip(), images
