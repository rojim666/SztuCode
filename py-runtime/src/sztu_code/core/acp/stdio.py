"""stdio transport for the ACP agent server.

The client (the OpenClaw WeChat channel plugin) launches this process and speaks
newline-delimited JSON-RPC 2.0 over stdin/stdout. Only valid ACP messages may be
written to stdout; logs go to stderr.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any, Protocol

from sztu_code.core.acp import protocol as p
from sztu_code.core.acp.backend import AgentBackend
from sztu_code.core.acp.bridge import AcpBridge

logger = logging.getLogger(__name__)


class PipeReader(Protocol):
    async def readline(self) -> bytes: ...


class PipeWriter(Protocol):
    def write(self, data: bytes) -> None: ...

    async def drain(self) -> None: ...


class StdinReader:
    """Async line reader over ``sys.stdin.buffer`` backed by a worker thread."""

    async def readline(self) -> bytes:
        return await asyncio.to_thread(sys.stdin.buffer.readline)


class StdoutWriter:
    def write(self, data: bytes) -> None:
        sys.stdout.buffer.write(data)

    async def drain(self) -> None:
        sys.stdout.buffer.flush()


class StdioLink:
    """ACP client link over newline-delimited JSON-RPC on a pipe pair."""

    def __init__(self, reader: PipeReader, writer: PipeWriter) -> None:
        self._reader = reader
        self._writer = writer
        self._pending: dict[int | str, asyncio.Future[dict[str, Any]]] = {}
        self._next_id = 0
        self._write_lock = asyncio.Lock()

    async def _write(self, message: dict[str, Any]) -> None:
        payload = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        async with self._write_lock:
            self._writer.write(payload.encode("utf-8") + b"\n")
            await self._writer.drain()

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        await self._write(p.notification(method, params))

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        message_id = self._next_id
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[message_id] = future
        await self._write(p.request(message_id, method, params))
        message = await future
        if "error" in message:
            err = message["error"]
            raise p.AcpError(int(err.get("code", p.INTERNAL_ERROR)), str(err.get("message", "")))
        result = message.get("result")
        return result if isinstance(result, dict) else {}

    # Resolve a pending agent->client request when the client answers.
    def _resolve_pending(self, message: dict[str, Any]) -> bool:
        if "method" in message:
            return False
        message_id = message.get("id")
        if not isinstance(message_id, (int, str)):
            return True
        future = self._pending.pop(message_id, None)
        if future is not None and not future.done():
            future.set_result(message)
        return True

    async def run(self, bridge: AcpBridge) -> None:
        """Read messages until stdin closes, dispatching each concurrently."""
        tasks: set[asyncio.Task[None]] = set()
        try:
            while True:
                line = await self._reader.readline()
                if not line:
                    break
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    message = json.loads(stripped)
                except ValueError:
                    await self._write(p.error(None, p.PARSE_ERROR, "invalid JSON"))
                    continue
                if not isinstance(message, dict):
                    await self._write(p.error(None, p.INVALID_REQUEST, "message must be an object"))
                    continue
                if self._resolve_pending(message):
                    continue
                task = asyncio.create_task(self._handle_incoming(bridge, message))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
        finally:
            # On stdin EOF the client is terminating. Give in-flight handlers a
            # short grace period to flush their response, then cancel the rest.
            if tasks:
                _done, pending = await asyncio.wait(tasks, timeout=2.0)
                for task in pending:
                    task.cancel()
            for future in self._pending.values():
                if not future.done():
                    future.cancel()
            self._pending.clear()

    async def _handle_incoming(self, bridge: AcpBridge, message: dict[str, Any]) -> None:
        method = message.get("method")
        if not isinstance(method, str):
            await self._write(p.error(message.get("id"), p.INVALID_REQUEST, "missing method"))
            return
        params = message.get("params")
        if not isinstance(params, dict):
            params = {}
        if "id" in message:
            message_id = message["id"]
            try:
                result = await bridge.handle_request(message_id, method, params)
                await self._write(p.success(message_id, result))
            except p.AcpError as exc:
                await self._write(p.error_from(message_id, exc))
            except Exception as exc:  # noqa: BLE001 - never leak a traceback to stdout
                logger.exception("ACP request %s failed", method)
                await self._write(p.error(message_id, p.INTERNAL_ERROR, str(exc)))
        else:
            await bridge.handle_notification(method, params)


async def serve(
    backend: AgentBackend,
    *,
    reader: PipeReader | None = None,
    writer: PipeWriter | None = None,
    version: str = "0.0.1",
    agent_name: str = "sztu-code",
) -> int:
    """Run the ACP stdio server until the client closes stdin.

    ``initialize`` never touches the backend, so the server answers the
    handshake even before the SztuCode core daemon is reachable; the daemon is
    contacted lazily on ``session/new``.
    """
    link = StdioLink(reader or StdinReader(), writer or StdoutWriter())
    bridge = AcpBridge(backend, link, agent_version=version, agent_name=agent_name)
    try:
        await link.run(bridge)
    finally:
        await bridge.aclose()
        await backend.aclose()
    return 0
