from __future__ import annotations

from pathlib import Path

import pytest

from sztu_code.core.bus.envelope import HandlerError
from sztu_code.core.events.bus import EventBus
from sztu_code.core.runner import RunOutcome
from sztu_code.core.session.manager import SESSION_CLOSED, SESSION_NOT_FOUND, SessionManager
from sztu_code.core.session.model import Session
from sztu_code.core.session.store import SessionStore


class _Runner:
    # 模拟 AgentRunner，将 run 新消息写入 thread 后返回成功
    async def run_and_capture(
        self,
        goal: str,
        *,
        run_id: str | None = None,
        session: Session | None = None,
        store: SessionStore | None = None,
        system_prompt_override: str | None = None,
        tool_whitelist: list[str] | None = None,
        workspace_root: Path | None = None,
    ) -> RunOutcome:
        assert run_id is not None
        assert session is not None
        assert store is not None
        self.workspace_root = workspace_root
        store.append_messages(
            session.id,
            [{"role": "assistant", "content": [{"type": "text", "text": f"done {goal}"}]}],
            run_id,
        )
        return RunOutcome(status="success", result="done", reason=None)


# 功能：验证 create 会创建 active session、写入 meta 并发布 session.created 事件
# 设计：用真实 SessionStore + EventBus 收集事件，覆盖 manager 与 store/bus 的协作边界
async def test_create_session_writes_meta_and_event(tmp_path: Path) -> None:
    events: list[object] = []
    bus = EventBus()

    async def collect(event: object) -> None:
        events.append(event)

    bus.subscribe(collect)
    store = SessionStore(tmp_path)
    manager = SessionManager(store, lambda: _Runner(), bus)  # type: ignore[arg-type]

    session = await manager.create("chat", "title")

    assert session.status == "active"
    assert store.read_meta(session.id).title == "title"
    assert [e.type for e in events] == ["session.created"]  # type: ignore[attr-defined]


# 功能：验证 chat session 处理一条消息后进入 waiting_for_input，并保留 user/assistant thread
# 设计：mock runner 主动追加 assistant 消息，确认 send_message 负责 user 消息、状态流转和 run_id 记录
async def test_send_message_chat_enters_waiting_and_writes_thread(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    manager = SessionManager(store, lambda: _Runner(), EventBus())  # type: ignore[arg-type]
    session = await manager.create("chat")

    run_id = await manager.send_message(session.id, "hello")

    loaded = store.read_meta(session.id)
    assert loaded.status == "waiting_for_input"
    assert loaded.run_ids == [run_id]
    messages = store.read_messages(session.id)
    assert messages[0] == {"role": "user", "content": "hello"}
    assert messages[1]["role"] == "assistant"


# 功能：验证 one_shot session 在单次消息完成后自动 closed
# 设计：复用 mock runner 的成功路径，聚焦 mode 对最终状态的影响，保证 sztu run 的统一路径正确
async def test_one_shot_auto_closes(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    manager = SessionManager(store, lambda: _Runner(), EventBus())  # type: ignore[arg-type]
    session = await manager.create("one_shot")

    await manager.send_message(session.id, "hello")

    assert store.read_meta(session.id).status == "closed"


# 功能：验证不存在的 session_id 返回 session_not_found 错误码
# 设计：直接调用 get_history 的查找路径，断言 HandlerError code，覆盖 IPC handler 可结构化返回错误
async def test_missing_session_raises_handler_error(tmp_path: Path) -> None:
    manager = SessionManager(SessionStore(tmp_path), lambda: _Runner(), EventBus())  # type: ignore[arg-type]
    with pytest.raises(HandlerError) as exc:
        await manager.get_history("missing")
    assert exc.value.code == SESSION_NOT_FOUND


# 功能：验证 closed session 不能继续 send_message
# 设计：先显式 close，再发送消息，断言 session_closed 错误码，覆盖状态机拒绝路径
async def test_closed_session_rejects_message(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    manager = SessionManager(store, lambda: _Runner(), EventBus())  # type: ignore[arg-type]
    session = await manager.create("chat")
    await manager.close(session.id)

    with pytest.raises(HandlerError) as exc:
        await manager.send_message(session.id, "again")
    assert exc.value.code == SESSION_CLOSED


# 功能：验证重启后的 SessionManager 可列出持久化任务，并能归档、恢复已关闭的 chat session。
# 设计：用两个 manager 实例模拟 daemon 重启，分别断言归档过滤、磁盘恢复和 resume 后的可输入状态，覆盖客户端恢复任务的完整路径。
async def test_persisted_session_can_be_listed_archived_and_resumed(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    first_manager = SessionManager(store, lambda: _Runner(), EventBus())  # type: ignore[arg-type]
    first = await first_manager.create("chat", "first")
    second = await first_manager.create("chat", "second")
    await first_manager.close(first.id)
    await first_manager.archive(first.id)

    restarted_manager = SessionManager(store, lambda: _Runner(), EventBus())  # type: ignore[arg-type]
    visible, cursor = await restarted_manager.list_sessions(limit=1)
    assert [session.id for session in visible] == [second.id]
    assert cursor is None

    all_sessions, _ = await restarted_manager.list_sessions(include_archived=True)
    assert {session.id for session in all_sessions} == {first.id, second.id}
    restored = await restarted_manager.resume(first.id)
    assert restored.status == "waiting_for_input"
    assert restored.archived is False
    assert store.read_meta(first.id).status == "waiting_for_input"


async def test_pinned_session_is_persisted_sorted_first_and_unpinned_when_archived(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    manager = SessionManager(store, lambda: _Runner(), EventBus())  # type: ignore[arg-type]
    first = await manager.create("chat", "first")
    second = await manager.create("chat", "second")

    pinned = await manager.pin(first.id, True)
    visible, _ = await manager.list_sessions()

    assert pinned.pinned is True
    assert [session.id for session in visible] == [first.id, second.id]
    await manager.archive(first.id)
    assert store.read_meta(first.id).pinned is False

    restarted = SessionManager(store, lambda: _Runner(), EventBus())  # type: ignore[arg-type]
    archived, _ = await restarted.list_sessions(include_archived=True)
    assert next(session for session in archived if session.id == first.id).pinned is False


# 功能：验证 session 可持久绑定工作区，并在 run 时将解析后的根目录传给 AgentRunner。
# 设计：以可观察的 runner 替身捕获 workspace_root，同时重读 meta，覆盖会话持久化与实际执行上下文两层边界。
async def test_session_workspace_is_persisted_and_passed_to_runner(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    workspace.mkdir()
    runner = _Runner()
    store = SessionStore(tmp_path / "sessions")
    manager = SessionManager(
        store,
        lambda: runner,  # type: ignore[arg-type]
        EventBus(),
        workspace_resolver=lambda workspace_id: workspace if workspace_id == "ws-project" else tmp_path,
    )
    session = await manager.create("chat", workspace_id="ws-project")

    await manager.send_message(session.id, "inspect workspace")

    assert runner.workspace_root == workspace
    assert store.read_meta(session.id).workspace_id == "ws-project"
