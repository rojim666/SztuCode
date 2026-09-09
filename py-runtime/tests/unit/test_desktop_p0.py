from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from pathlib import Path
from typing import Any, cast

import pytest

from sztu_code.core.app import CoreApp
from sztu_code.core.bus.envelope import HandlerError
from sztu_code.core.permissions.manager import PermissionManager


class _BlockingSessions:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls: list[tuple[str, str, str | None]] = []

    async def get_history(self, session_id: str) -> list[dict[str, object]]:
        assert session_id == "sess-1"
        return []

    async def send_message(
        self,
        session_id: str,
        content: str,
        *,
        run_id: str | None = None,
        images: list[dict[str, Any]] | None = None,
    ) -> str:
        self.calls.append((session_id, content, run_id))
        self.started.set()
        await self.release.wait()
        return run_id or "missing-run-id"


# 功能：验证 session.send_message 在 run 执行期间立即返回 run_id，后续审批命令可复用同一连接进入 daemon。
# 设计：用阻塞的 SessionManager 替身固定 run 生命周期；在它未完成时断言首个响应已返回且第二条消息得到 session busy 错误。
async def test_session_send_handler_returns_before_run_finishes() -> None:
    app = CoreApp()
    sessions = _BlockingSessions()
    app._sessions = sessions  # type: ignore[assignment]

    result = await app._session_send_handler({"session_id": "sess-1", "content": "hello"})
    assert result.run_id
    await asyncio.wait_for(sessions.started.wait(), timeout=1.0)
    assert sessions.calls == [("sess-1", "hello", result.run_id)]

    with pytest.raises(HandlerError, match="session busy"):
        await app._session_send_handler({"session_id": "sess-1", "content": "again"})

    sessions.release.set()
    active_run = app._active_session_runs["sess-1"]
    await asyncio.wait_for(active_run, timeout=1.0)
    with suppress(asyncio.CancelledError):
        for task in app._running_runs:
            task.cancel()


async def test_session_send_handler_reuses_run_for_retried_client_message() -> None:
    app = CoreApp()
    sessions = _BlockingSessions()
    app._sessions = sessions  # type: ignore[assignment]
    params = {
        "session_id": "sess-1",
        "content": "hello once",
        "client_message_id": "client-message-1",
    }

    first = await app._session_send_handler(params)
    retried = await app._session_send_handler(params)
    await asyncio.wait_for(sessions.started.wait(), timeout=1.0)

    assert retried.run_id == first.run_id
    assert sessions.calls == [("sess-1", "hello once", first.run_id)]

    sessions.release.set()
    await asyncio.wait_for(app._active_session_runs["sess-1"], timeout=1.0)


# 功能：验证 run.cancel 能取消活动 session run，并让 run.get 返回 cancelled 终态。
# 设计：复用可阻塞 session 替身，先等待后台任务真正启动再调用 CoreApp 的两个 IPC handler，避免只验证字典状态而遗漏 asyncio 取消链路。
async def test_run_cancel_stops_active_session_run() -> None:
    app = CoreApp()
    sessions = _BlockingSessions()
    app._sessions = sessions  # type: ignore[assignment]

    sent = await app._session_send_handler({"session_id": "sess-1", "content": "stop me"})
    await asyncio.wait_for(sessions.started.wait(), timeout=1.0)
    cancelled = await app._run_cancel_handler({"run_id": sent.run_id})
    assert cancelled.status == "cancelling"
    pending = await app._run_get_handler({"run_id": sent.run_id})
    assert pending.status == "running"

    task = app._active_run_tasks[sent.run_id]
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)

    status = await app._run_get_handler({"run_id": sent.run_id})
    assert status.status == "cancelled"


# 功能：验证 run.cancel 会先拒绝该 run 的待审批请求，再取消运行任务
# 设计：把真实 PermissionManager pending 与可取消的活动 task 同时注入 CoreApp，
#       断言审批 Future 已完成且运行 task 收到取消
async def test_run_cancel_cleans_pending_permissions_before_task_cancel() -> None:
    app = CoreApp()
    manager = PermissionManager(timeout_s=0)
    app._permission_manager = manager

    async def emitter(event: dict[str, Any]) -> None:
        del event

    permission_task = asyncio.create_task(
        manager.check_and_wait(
            tool_use_id="run-cancel-permission",
            tool_name="bash",
            params={"command": "echo"},
            session_id="sess-1",
            event_emitter=emitter,
            run_id="run-1",
        )
    )
    await asyncio.sleep(0)

    run_task = asyncio.create_task(asyncio.sleep(60, result="done"))
    app._track_run("run-1", run_task, "sess-1")

    result = await app._run_cancel_handler({"run_id": "run-1"})

    assert result.status == "cancelling"
    assert await permission_task == (False, "deny_once")
    with pytest.raises(asyncio.CancelledError):
        await run_task


# 功能：验证成功关闭 session 后，会拒绝该 session 遗留的待审批请求
# 设计：使用最小 SessionManager 替身只观察 close 调用，避免把测试耦合到持久化实现
async def test_session_close_cleans_pending_permissions() -> None:
    class _ClosableSessions:
        def __init__(self) -> None:
            self.closed: list[str] = []

        async def close(self, session_id: str) -> None:
            self.closed.append(session_id)

    app = CoreApp()
    manager = PermissionManager(timeout_s=0)
    app._permission_manager = manager
    sessions = _ClosableSessions()
    app._sessions = sessions  # type: ignore[assignment]

    async def emitter(event: dict[str, Any]) -> None:
        del event

    permission_task = asyncio.create_task(
        manager.check_and_wait(
            tool_use_id="session-close-permission",
            tool_name="bash",
            params={"command": "echo"},
            session_id="sess-1",
            event_emitter=emitter,
            run_id="run-1",
        )
    )
    await asyncio.sleep(0)

    result = await app._session_close_handler({"session_id": "sess-1"})

    assert result.status == "closed"
    assert sessions.closed == ["sess-1"]
    assert await permission_task == (False, "deny_once")
    assert manager._session_cancellations == {}


# 功能：验证 session.close 失败时不会改变权限审批生命周期
# 设计：让替身模拟真实 SessionManager 的 SESSION_BUSY，确认 session 未关闭时 pending 仍在；
#       再显式清理测试请求，避免把测试资源泄漏到下一用例
async def test_session_close_cleans_pending_when_close_fails() -> None:
    class _BusySessions:
        async def close(self, session_id: str) -> None:
            del session_id
            raise HandlerError(-32012, "session busy")

    app = CoreApp()
    manager = PermissionManager(timeout_s=0)
    app._permission_manager = manager
    app._sessions = _BusySessions()  # type: ignore[assignment]

    async def emitter(event: dict[str, Any]) -> None:
        del event

    permission_task = asyncio.create_task(
        manager.check_and_wait(
            tool_use_id="session-close-failed-permission",
            tool_name="bash",
            params={"command": "echo"},
            session_id="sess-1",
            event_emitter=emitter,
            run_id="run-1",
        )
    )
    await asyncio.sleep(0)

    with pytest.raises(HandlerError, match="session busy"):
        await app._session_close_handler({"session_id": "sess-1"})

    assert not permission_task.done()
    assert "session-close-failed-permission" in manager._pending
    manager.cancel_session(
        "sess-1", reason="test_cleanup", prevent_new_requests=False
    )
    assert await permission_task == (False, "deny_once")


# 功能：验证成功删除 session 后，会拒绝该 session 遗留的待审批请求
# 设计：使用最小 SessionManager 替身只观察 delete 调用，覆盖 close 之外的删除清理路径
async def test_session_delete_cleans_pending_permissions() -> None:
    class _DeletableSessions:
        def __init__(self) -> None:
            self.deleted: list[str] = []

        async def delete(self, session_id: str) -> None:
            self.deleted.append(session_id)

    app = CoreApp()
    manager = PermissionManager(timeout_s=0)
    app._permission_manager = manager
    sessions = _DeletableSessions()
    app._sessions = sessions  # type: ignore[assignment]

    async def emitter(event: dict[str, Any]) -> None:
        del event

    permission_task = asyncio.create_task(
        manager.check_and_wait(
            tool_use_id="session-delete-permission",
            tool_name="bash",
            params={"command": "echo"},
            session_id="sess-1",
            event_emitter=emitter,
            run_id="run-1",
        )
    )
    await asyncio.sleep(0)

    result = await app._session_delete_handler({"session_id": "sess-1"})

    assert result.session_id == "sess-1"
    assert result.deleted is True
    assert sessions.deleted == ["sess-1"]
    assert await permission_task == (False, "deny_once")
    assert manager._session_cancellations == {}


# 功能：验证断开一个连接不会取消仍由另一连接持有的 session 审批
# 设计：同一 session 由两个连接持有时先断开一个，权限 Future 继续等待；最后一个连接断开
#       后才拒绝请求，覆盖 SocketServer → CoreApp → PermissionManager 的归属链路
async def test_client_disconnect_cancels_session_only_without_other_holders() -> None:
    app = CoreApp()
    manager = PermissionManager(timeout_s=0)
    app._permission_manager = manager

    async def emitter(event: dict[str, Any]) -> None:
        del event

    permission_task = asyncio.create_task(
        manager.check_and_wait(
            tool_use_id="disconnect-session",
            tool_name="bash",
            params={"command": "echo"},
            session_id="sess-1",
            event_emitter=emitter,
            run_id="run-1",
        )
    )
    await asyncio.sleep(0)

    writer_a = cast(asyncio.StreamWriter, object())
    writer_b = cast(asyncio.StreamWriter, object())
    app._connection_sessions[writer_a] = {"sess-1"}
    app._connection_sessions[writer_b] = {"sess-1"}
    app._session_connections["sess-1"] = {writer_a, writer_b}

    app._on_client_disconnect(writer_a)
    await asyncio.sleep(0)
    assert not permission_task.done()

    app._on_client_disconnect(writer_b)
    assert await permission_task == (False, "deny_once")
    assert app._session_connections == {}


# 功能：验证 run.replay 从持久事件文件返回有限且顺序稳定的事件序列。
# 设计：替换 events_file 定位到临时 jsonl，再同时写入有效、空行和损坏行，覆盖客户端恢复状态依赖的过滤与上限逻辑。
async def test_run_replay_reads_persisted_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    event_path = tmp_path / "events.jsonl"
    event_path.write_text(
        "\n".join([
            json.dumps({"type": "run.started", "run_id": "run-replay"}),
            "not-json",
            json.dumps({"type": "plan.updated", "run_id": "run-replay", "items": []}),
        ]) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("sztu_code.core.app.events_file", lambda _run_id: event_path)

    result = await CoreApp()._run_replay_handler({"run_id": "run-replay", "max_events": 1})

    assert result.run_id == "run-replay"
    assert result.events == [{"type": "run.started", "run_id": "run-replay"}]


# 功能：验证 permission.set_mode 走类型化协议并同步更新后端策略状态。
# 设计：注入真实 PermissionManager 后调用 handler，断言返回值与 manager 当前值一致，排除只变更客户端标签而未影响审批机制的假实现。
async def test_permission_set_mode_updates_permission_manager(tmp_path: Path) -> None:
    app = CoreApp()
    app._permission_manager = PermissionManager(policy_file=tmp_path / "policy.toml")

    result = await app._permission_set_mode_handler({"mode": "plan"})

    assert result.ok is True
    assert result.mode == "plan"
    assert app._permission_manager.get_mode().value == "plan"
