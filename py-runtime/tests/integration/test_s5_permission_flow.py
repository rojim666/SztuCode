"""
S5 permission flow integration tests.

No daemon subprocess needed — uses AgentRunner in-process with a mock LLM
provider and the real PermissionManager. BashTool runs real subprocesses, so
commands must be safe (echo, true).
"""
from __future__ import annotations

import asyncio
import json
import socket
from contextlib import suppress
from pathlib import Path

import pytest
from pydantic import BaseModel

from sztu_code.core.app import CoreApp
from sztu_code.core.config import SztuConfig
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import LlmResponse, ToolCallBlock
from sztu_code.core.permissions.manager import PermissionManager
from sztu_code.core.runner import AgentRunner
from sztu_code.core.session.model import Session, SessionMode
from sztu_code.core.transport.socket_server import SocketServer

# ── stub providers ────────────────────────────────────────────────────────────


class _SingleBashProvider:
    """Step 1: bash tool call. Step 2: end_turn."""

    def __init__(self, command: str = "echo hello") -> None:
        self._command = command
        self._step = 0

    async def chat(
        self,
        messages: list[dict],
        tool_schemas: list[dict],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    
        usage_estimator: object | None = None,
    ) -> LlmResponse:
        self._step += 1
        if self._step == 1:
            tc = ToolCallBlock(id="tc1", name="bash", input={"command": self._command})
            return LlmResponse(stop_reason="tool_use", tool_calls=[tc])
        return LlmResponse(stop_reason="end_turn", text="done")


class _TwoBashProvider:
    """Step 1+2: two separate bash calls. Step 3: end_turn."""

    def __init__(self) -> None:
        self._step = 0

    async def chat(
        self,
        messages: list[dict],
        tool_schemas: list[dict],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    
        usage_estimator: object | None = None,
    ) -> LlmResponse:
        self._step += 1
        if self._step == 1:
            tc = ToolCallBlock(id="tc1", name="bash", input={"command": "echo first"})
            return LlmResponse(stop_reason="tool_use", tool_calls=[tc])
        if self._step == 2:
            tc = ToolCallBlock(id="tc2", name="bash", input={"command": "echo second"})
            return LlmResponse(stop_reason="tool_use", tool_calls=[tc])
        return LlmResponse(stop_reason="end_turn", text="done")


# ── helper ────────────────────────────────────────────────────────────────────


def _runner(
    provider: object,
    bus: EventBus,
    manager: PermissionManager,
    tmp_path: Path,
    max_steps: int = 10,
) -> AgentRunner:
    config = SztuConfig()
    config.agent.max_steps = max_steps
    return AgentRunner(
        config,
        bus=bus,
        provider=provider,  # type: ignore[arg-type]
        permission_manager=manager,
        runs_dir=tmp_path / "runs",
    )


# ── tests ─────────────────────────────────────────────────────────────────────


# 功能：验证 allow_once 决策后工具正常执行并写入 tool.call_finished 事件
# 设计：在 permission.requested 事件到达时同步调用 manager.respond("allow_once")；
#       Future 在同一 event-loop turn 内解决，工具随后执行；断言 tool.call_finished 存在且 tool.call_failed 不存在
async def test_permission_allow_once_tool_executes(tmp_path: Path) -> None:
    manager = PermissionManager()
    bus = EventBus()
    event_types: list[str] = []

    async def collect(e: BaseModel) -> None:
        t = getattr(e, "type", "")
        event_types.append(t)
        if t == "permission.requested":
            manager.respond(getattr(e, "tool_use_id", ""), "allow_once")

    bus.subscribe(collect)
    outcome = await _runner(_SingleBashProvider(), bus, manager, tmp_path).run_and_capture(
        "run bash"
    )

    assert "permission.requested" in event_types
    assert "tool.call_finished" in event_types
    assert "tool.call_failed" not in event_types
    assert outcome.status == "success"


# 功能：验证 deny_once 决策后工具不执行，事件流中出现 permission_denied 错误
# 设计：在 permission.requested 时 respond("deny_once")；断言 tool.call_failed 的 error_class 为
#       "permission_denied"，且 tool.call_finished 不出现，确认工具从未被调用
async def test_permission_deny_once_tool_not_executed(tmp_path: Path) -> None:
    manager = PermissionManager()
    bus = EventBus()
    event_types: list[str] = []
    failed_events: list[BaseModel] = []

    async def collect(e: BaseModel) -> None:
        t = getattr(e, "type", "")
        event_types.append(t)
        if t == "permission.requested":
            manager.respond(getattr(e, "tool_use_id", ""), "deny_once")
        if t == "tool.call_failed":
            failed_events.append(e)

    bus.subscribe(collect)
    await _runner(_SingleBashProvider(), bus, manager, tmp_path).run_and_capture("run bash")

    assert "permission.requested" in event_types
    assert "tool.call_failed" in event_types
    assert "tool.call_finished" not in event_types
    assert getattr(failed_events[0], "error_class", None) == "permission_denied"


# 功能：验证 always_allow 决策在 session 内缓存，第二次同名工具不再触发 permission.requested
# 设计：两步 bash 调用；第一次 respond("always_allow")，断言 permission.requested 只出现一次；
#       第二次工具调用命中缓存并直接执行，不挂起 Future
async def test_always_allow_cached_within_session(tmp_path: Path) -> None:
    manager = PermissionManager()
    bus = EventBus()
    perm_requested_count = 0

    async def collect(e: BaseModel) -> None:
        nonlocal perm_requested_count
        if getattr(e, "type", "") == "permission.requested":
            perm_requested_count += 1
            manager.respond(getattr(e, "tool_use_id", ""), "always_allow")

    bus.subscribe(collect)
    outcome = await _runner(_TwoBashProvider(), bus, manager, tmp_path).run_and_capture(
        "run two bash commands"
    )

    assert perm_requested_count == 1
    assert outcome.status == "success"


# 功能：验证 run 在权限审批等待期间被取消时，工具不会执行且 pending 请求会清理
# 设计：使用真实 AgentRunner + PermissionManager，等 permission.requested 到达后取消
#       run；断言没有 tool.call_finished，并确认权限管理器不再保留该请求
async def test_cancelled_permission_wait_does_not_execute_tool(tmp_path: Path) -> None:
    manager = PermissionManager(timeout_s=0)
    bus = EventBus()
    event_types: list[str] = []
    permission_requested = asyncio.Event()

    async def collect(e: BaseModel) -> None:
        event_type = getattr(e, "type", "")
        event_types.append(event_type)
        if event_type == "permission.requested":
            permission_requested.set()

    bus.subscribe(collect)
    task = asyncio.create_task(
        _runner(_SingleBashProvider(), bus, manager, tmp_path)
        .run_and_capture("run bash", run_id="cancelled-permission")
    )
    await asyncio.wait_for(permission_requested.wait(), timeout=1.0)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert manager._pending == {}
    assert "tool.call_finished" not in event_types


# 功能：验证真实 SocketServer → CoreApp → PermissionManager 断连清理链路
# 设计：通过 TCP 请求创建 session，使 CoreApp 记录实际连接；随后挂起同 session 的审批并关闭客户端，
#       断言断连回调拒绝 Future、清空 pending，避免仅凭手工填充连接映射得到假阳性
async def test_client_disconnect_cleans_permission_over_ipc() -> None:
    class _SessionFactory:
        async def create(
            self,
            mode: SessionMode,
            title: str = "",
            workspace_id: str | None = None,
        ) -> Session:
            return Session(
                id="sess-ipc",
                mode=mode,
                status="waiting_for_input",
                title=title,
                created_at="",
                updated_at="",
                workspace_id=workspace_id,
            )

    async def send_recv(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        method: str,
        params: dict[str, object],
    ) -> dict[str, object]:
        request = {
            "jsonrpc": "2.0",
            "id": "session-create",
            "method": method,
            "params": params,
        }
        writer.write((json.dumps(request) + "\n").encode())
        await writer.drain()
        return json.loads(await asyncio.wait_for(reader.readline(), timeout=1.0))

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])

    app = CoreApp()
    manager = PermissionManager(timeout_s=0)
    app._permission_manager = manager
    app._sessions = _SessionFactory()  # type: ignore[assignment]
    server = SocketServer("127.0.0.1", port, on_disconnect=app._on_client_disconnect)
    server.register("session.create", app._session_create_handler)
    permission_task: asyncio.Task[tuple[bool, str]] | None = None

    await server.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        response = await send_recv(reader, writer, "session.create", {"mode": "chat"})
        assert response["result"] == {
            "session_id": "sess-ipc",
            "status": "waiting_for_input",
        }

        pending_started = asyncio.Event()

        async def emitter(event: dict[str, object]) -> None:
            del event
            pending_started.set()

        permission_task = asyncio.create_task(
            manager.check_and_wait(
                tool_use_id="ipc-disconnect",
                tool_name="bash",
                params={"command": "echo"},
                session_id="sess-ipc",
                event_emitter=emitter,
                run_id="run-ipc",
            )
        )
        # 模拟权限请求所属的后台 run 仍在执行，断连后后续 ASK 必须被拒绝。
        app._run_sessions["run-ipc"] = "sess-ipc"
        await asyncio.wait_for(pending_started.wait(), timeout=1.0)
        assert "ipc-disconnect" in manager._pending

        writer.close()
        await writer.wait_closed()
        assert await asyncio.wait_for(permission_task, timeout=1.0) == (False, "deny_once")
        assert manager._pending == {}
        assert app._connection_sessions == {}
        assert app._session_connections == {}

        # 即使后台 run 在断连后继续运行，后续危险调用也不能重新挂起审批。
        assert await manager.check_and_wait(
            tool_use_id="after-ipc-disconnect",
            tool_name="bash",
            params={"command": "echo"},
            session_id="sess-ipc",
            event_emitter=emitter,
            run_id="run-ipc-2",
        ) == (False, "deny_once")
        assert manager._pending == {}

        # 新连接重新绑定 session 后，审批能力恢复。
        reader2, writer2 = await asyncio.open_connection("127.0.0.1", port)
        response2 = await send_recv(reader2, writer2, "session.create", {"mode": "chat"})
        assert response2["result"] == {
            "session_id": "sess-ipc",
            "status": "waiting_for_input",
        }
        reconnected_task = asyncio.create_task(
            manager.check_and_wait(
                tool_use_id="after-ipc-reconnect",
                tool_name="bash",
                params={"command": "echo"},
                session_id="sess-ipc",
                event_emitter=emitter,
                run_id="run-ipc-3",
            )
        )
        await asyncio.sleep(0)
        manager.respond(
            "after-ipc-reconnect",
            "allow_once",
            run_id="run-ipc-3",
            session_id="sess-ipc",
        )
        assert await reconnected_task == (True, "allow_once")
        writer2.close()
        await writer2.wait_closed()
    finally:
        if permission_task is not None and not permission_task.done():
            permission_task.cancel()
            with suppress(asyncio.CancelledError):
                await permission_task
        await server.stop()
