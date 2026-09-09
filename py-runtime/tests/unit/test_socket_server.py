from __future__ import annotations

import asyncio
import json
import socket

from sztu_code.core.transport.socket_server import SocketServer


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# 功能：验证客户端断开后 SocketServer 调用 broadcaster.unsubscribe(writer) 清理订阅
# 设计：用内联 MockBroadcaster 捕获 unsubscribe 调用并设置 asyncio.Event，避免 sleep 轮询；
#       等待 Event 而非断言调用次数，确保时序正确性而不依赖竞态假设
async def test_broadcaster_unsubscribe_called_on_disconnect() -> None:
    unsubscribed = asyncio.Event()

    class MockBroadcaster:
        def unsubscribe(self, writer: object) -> None:
            unsubscribed.set()

    port = _free_port()
    server = SocketServer("127.0.0.1", port, broadcaster=MockBroadcaster())  # type: ignore[arg-type]
    await server.start()

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.close()
        await writer.wait_closed()

        await asyncio.wait_for(unsubscribed.wait(), timeout=2.0)
    finally:
        await server.stop()


# 功能：验证客户端断连会触发上层生命周期清理回调
# 设计：回调捕获实际 writer 并等待事件，证明 SocketServer 在 finally 中通知 CoreApp，
#       使上层可以按连接归属清理权限审批
async def test_disconnect_handler_called_on_disconnect() -> None:
    disconnected = asyncio.Event()
    writers: list[object] = []

    async def on_disconnect(writer: object) -> None:
        writers.append(writer)
        disconnected.set()

    port = _free_port()
    server = SocketServer("127.0.0.1", port, on_disconnect=on_disconnect)  # type: ignore[arg-type]
    await server.start()

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        del reader
        writer.close()
        await writer.wait_closed()

        await asyncio.wait_for(disconnected.wait(), timeout=2.0)
        assert writers
    finally:
        await server.stop()


# 功能：验证断连回调执行前，会先取消仍在处理中的 RPC handler
# 设计：让 handler 在响应前挂起，客户端 EOF 后由回调确认 handler 已收到取消，
#       覆盖 session.create 尚未返回时的生命周期竞态
async def test_disconnect_cancels_inflight_handlers_before_callback() -> None:
    handler_started = asyncio.Event()
    handler_cancelled = asyncio.Event()
    disconnected = asyncio.Event()
    release = asyncio.Event()

    async def slow_handler(params: dict[str, object]) -> dict[str, bool]:
        del params
        handler_started.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            handler_cancelled.set()
            raise
        return {"ok": True}

    async def on_disconnect(writer: object) -> None:
        del writer
        assert handler_cancelled.is_set()
        disconnected.set()

    port = _free_port()
    server = SocketServer("127.0.0.1", port, on_disconnect=on_disconnect)  # type: ignore[arg-type]
    server.register("slow", slow_handler)
    await server.start()

    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        del reader
        writer.write(
            (
                json.dumps(
                    {"jsonrpc": "2.0", "id": "slow", "method": "slow", "params": {}}
                )
                + "\n"
            ).encode()
        )
        await writer.drain()
        await asyncio.wait_for(handler_started.wait(), timeout=2.0)

        writer.close()
        await writer.wait_closed()
        await asyncio.wait_for(disconnected.wait(), timeout=2.0)
    finally:
        release.set()
        await server.stop()


# 功能：验证不传入 broadcaster 时 SocketServer 仍可正常启动和停止（backward-compatible 默认值）
# 设计：直接实例化 SocketServer(host, port)（无 broadcaster），start/stop 不抛异常即为通过；
#       回归测试确保新参数的默认值 None 不破坏现有调用方
async def test_no_broadcaster_server_starts_and_stops() -> None:
    port = _free_port()
    server = SocketServer("127.0.0.1", port)
    await server.start()
    await server.stop()
