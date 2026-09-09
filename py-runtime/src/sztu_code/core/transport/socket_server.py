from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import partial
from typing import Any

from pydantic import BaseModel, ValidationError

from sztu_code.core.bus.envelope import (
    INTERNAL_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    HandlerError,
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcSuccess,
    make_error,
)
from sztu_code.core.trace.record import TraceRecord
from sztu_code.core.trace.writer import TraceWriter
from sztu_code.core.transport.ipc_broadcaster import IpcEventBroadcaster

logger = logging.getLogger(__name__)

type CommandHandler = Callable[[dict[str, Any]], Awaitable[Any]]
type DisconnectHandler = Callable[[asyncio.StreamWriter], Awaitable[None] | None]

# 每个连接处理协程中，当前正在处理的 writer（供 handler 读取连接上下文）
_writer_var: ContextVar[asyncio.StreamWriter] = ContextVar("_writer_var")


def _now() -> str:
    return datetime.now(UTC).isoformat()


# 返回当前 handler 调用所属连接的 StreamWriter
def get_connection_writer() -> asyncio.StreamWriter:
    return _writer_var.get()

_MAX_LINE_BYTES = 64 * 1024 * 1024  # 64 MB per frame，兼容 MCP 大文件工具结果
_WRITE_DRAIN_TIMEOUT_S = 5.0


class SocketServer:
    def __init__(
        self,
        host: str,
        port: int,
        broadcaster: IpcEventBroadcaster | None = None,
        trace: TraceWriter | None = None,
        on_disconnect: DisconnectHandler | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._handlers: dict[str, CommandHandler] = {}
        self._server: asyncio.AbstractServer | None = None
        self._broadcaster = broadcaster
        self._trace = trace
        self._on_disconnect = on_disconnect
        self._active_writers: set[asyncio.StreamWriter] = set()
        self._handler_tasks: dict[asyncio.StreamWriter, set[asyncio.Task[None]]] = {}

    # 注册一个方法名对应的命令处理函数
    def register(self, method: str, handler: CommandHandler) -> None:
        self._handlers[method] = handler

    # 启动 TCP 服务器；若端口已被占用则退出进程
    async def start(self) -> str:
        try:
            # 直接 bind 是唯一可靠的占用判定。先 connect 再 bind 存在 TOCTOU：
            # Windows 上前一 daemon 被强杀后的短窗口里，connect 可能成功但连接
            # 随即复位，导致新 daemon 误判“已有实例”并退出。
            self._server = await asyncio.start_server(
                self._handle_connection,
                host=self._host,
                port=self._port,
                limit=_MAX_LINE_BYTES,
            )
        except OSError as error:
            raise SystemExit(
                f"cannot start core at {self._host}:{self._port}: {error}"
            ) from error
        return f"{self._host}:{self._port}"

    # 关闭服务器：先断开所有活跃连接，再等待服务器完全关闭（最多 2 秒）
    async def stop(self) -> None:
        if self._server is None:
            return
        for writer in list(self._active_writers):
            try:
                writer.close()
            except Exception:
                pass
        self._server.close()
        try:
            await asyncio.wait_for(self._server.wait_closed(), timeout=2.0)
        except (TimeoutError, asyncio.CancelledError):
            pass

    # 处理单个客户端连接，完成后关闭写流
    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer = writer.get_extra_info("peername", "<unknown>")
        logger.debug("client connected: %s", peer)
        self._active_writers.add(writer)
        try:
            await self._read_loop(reader, writer)
        finally:
            try:
                # Cancel RPC handlers before notifying the owner.  Otherwise a
                # slow handler can bind a session after EOF and evade cleanup.
                await self._cancel_handler_tasks(writer)
            finally:
                self._active_writers.discard(writer)
                if self._broadcaster is not None:
                    self._broadcaster.unsubscribe(writer)
                if self._on_disconnect is not None:
                    try:
                        result = self._on_disconnect(writer)
                        if inspect.isawaitable(result):
                            await result
                    except Exception:
                        logger.exception("disconnect cleanup failed: %s", peer)
                try:
                    writer.close()
                except Exception:
                    pass
                logger.debug("client disconnected: %s", peer)

    # 记录并取消指定连接尚未完成的 RPC handler，避免 EOF 后继续修改生命周期状态
    async def _cancel_handler_tasks(self, writer: asyncio.StreamWriter) -> None:
        tasks = self._handler_tasks.pop(writer, set())
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    # handler 结束后移除连接索引，避免短连接留下任务引用
    def _discard_handler_task(
        self, writer: asyncio.StreamWriter, task: asyncio.Task[None]
    ) -> None:
        tasks = self._handler_tasks.get(writer)
        if tasks is None:
            return
        tasks.discard(task)
        if not tasks:
            self._handler_tasks.pop(writer, None)

    # 持续读取换行分隔的 JSON 行并逐行分发处理
    async def _read_loop(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        while True:
            try:
                line = await reader.readline()
            except asyncio.LimitOverrunError:
                await self._send(writer, make_error(None, INVALID_REQUEST, "Request too large"))
                return

            if not line:
                return

            # 每条命令独立作为 task 执行，避免长时间运行的 handler（如 session.send_message）
            # 阻塞读循环，使 permission.respond 等并发命令能被及时处理
            task = asyncio.create_task(self._handle_line(line, writer))
            self._handler_tasks.setdefault(writer, set()).add(task)
            task.add_done_callback(partial(self._discard_handler_task, writer))

    # 解析单行 JSON-RPC 请求并调用对应 handler，将结果或错误写回客户端
    async def _handle_line(self, line: bytes, writer: asyncio.StreamWriter) -> None:
        try:
            raw: Any = json.loads(line)
        except json.JSONDecodeError as e:
            await self._send(writer, make_error(None, PARSE_ERROR, f"Parse error: {e}"))
            return

        try:
            req = JsonRpcRequest.model_validate(raw)
        except ValidationError as e:
            await self._send(writer, make_error(None, INVALID_REQUEST, "Invalid Request", str(e)))
            return

        if self._trace is not None:
            client_id = str(writer.get_extra_info("peername", "<unknown>"))
            self._trace.emit(
                TraceRecord(
                    ts=_now(),
                    direction="CLIENT→CORE",
                    layer="ipc",
                    kind="command",
                    client_id=client_id,
                    data={"method": req.method, "id": req.id, "params": req.params},
                )
            )

        handler = self._handlers.get(req.method)
        if handler is None:
            await self._send(
                writer,
                make_error(req.id, METHOD_NOT_FOUND, f"Method not found: {req.method}"),
            )
            return

        _writer_var.set(writer)
        try:
            result = await handler(req.params)
        except HandlerError as e:
            await self._send(writer, make_error(req.id, e.code, str(e), e.data))
            return
        except ValidationError as e:
            await self._send(
                writer,
                make_error(req.id, INVALID_REQUEST, "Invalid params", str(e)),
            )
            return
        except Exception as e:
            logger.exception("handler %s raised: %s", req.method, e)
            await self._send(writer, make_error(req.id, INTERNAL_ERROR, "Internal error"))
            return

        result_data: Any = result.model_dump() if isinstance(result, BaseModel) else result
        try:
            await self._send(writer, JsonRpcSuccess(id=req.id, result=result_data))
        except (ConnectionResetError, BrokenPipeError, OSError, TimeoutError):
            logger.debug("client disconnected before response for %s", req.method)

    # 将 pydantic 消息序列化为 JSON 行并写入流，随后刷新缓冲区
    async def _send(self, writer: asyncio.StreamWriter, msg: BaseModel) -> None:
        writer.write(msg.model_dump_json().encode() + b"\n")
        await asyncio.wait_for(writer.drain(), timeout=_WRITE_DRAIN_TIMEOUT_S)
        if self._trace is not None:
            kind = "error" if isinstance(msg, JsonRpcError) else "response"
            client_id = str(writer.get_extra_info("peername", "<unknown>"))
            self._trace.emit(
                TraceRecord(
                    ts=_now(),
                    direction="CORE→CLIENT",
                    layer="ipc",
                    kind=kind,
                    client_id=client_id,
                    data=msg.model_dump(),
                )
            )
