from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from pathlib import Path

import pytest

from sztu_code.core.app import CoreApp
from sztu_code.core.bus.envelope import HandlerError
from sztu_code.core.permissions.manager import PermissionManager
from sztu_code.desktop.app import SztuCodeDesktop


# 功能：验证 legacy 桌面端使用 daemon 实际发布的 tool.call_started/tool.call_finished 事件名。
# 设计：绕过 Tk 窗口创建，仅替换事件处理回调并直接路由事件，精确覆盖曾导致工具卡片永不更新的协议漂移。
def test_desktop_routes_current_tool_event_names() -> None:
    app = object.__new__(SztuCodeDesktop)
    app._session_id = "sess-1"
    started: list[dict[str, object]] = []
    finished: list[dict[str, object]] = []
    app._handle_tool_started = started.append
    app._handle_tool_finished = finished.append

    app._handle_event({"type": "tool.call_started", "session_id": "sess-1"})
    app._handle_event({"type": "tool.call_finished", "session_id": "sess-1"})

    assert [event["type"] for event in started] == ["tool.call_started"]
    assert [event["type"] for event in finished] == ["tool.call_finished"]


# 功能：验证带 session_id 的其他会话事件不会污染当前桌面会话。
# 设计：向当前实例投递不同 session_id 的工具事件，断言渲染回调完全未执行，覆盖重连后全局订阅的隔离边界。
def test_desktop_ignores_events_for_another_session() -> None:
    app = object.__new__(SztuCodeDesktop)
    app._session_id = "sess-current"
    received: list[dict[str, object]] = []
    app._handle_tool_started = received.append

    app._handle_event({"type": "tool.call_started", "session_id": "sess-other"})

    assert received == []


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

    task = app._active_run_tasks[sent.run_id]
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)

    status = await app._run_get_handler({"run_id": sent.run_id})
    assert status.status == "cancelled"


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
