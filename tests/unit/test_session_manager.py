from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from sztu_code.core.bus.envelope import HandlerError
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import LlmResponse, UsageStats
from sztu_code.core.runner import RunOutcome
from sztu_code.core.session.manager import SESSION_CLOSED, SESSION_NOT_FOUND, SessionManager
from sztu_code.core.session.model import RunStats, Session
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
        steering_queue: asyncio.Queue[dict[str, object]] | None = None,
    ) -> RunOutcome:
        assert run_id is not None
        assert session is not None
        assert store is not None
        self.goal = goal
        self.system_prompt_override = system_prompt_override
        self.tool_whitelist = tool_whitelist
        self.workspace_root = workspace_root
        self.steering_queue = steering_queue
        store.append_messages(
            session.id,
            [{"role": "assistant", "content": [{"type": "text", "text": f"done {goal}"}]}],
            run_id,
        )
        return RunOutcome(status="success", result="done", reason=None)


# 功能：验证运行中的会话可接收 steer 消息并发布带 run_id 的追加事件
# 设计：用暂停 runner 保持会话锁和 steer 队列存活，直接检查 FIFO 消息与事件投影后再释放任务
async def test_steer_message_reaches_active_runner_queue(tmp_path: Path) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    captured: dict[str, object] = {}
    events: list[object] = []
    bus = EventBus()

    # 收集会话事件，验证 UI 能按 session_id 和 run_id 定位追加指令
    async def collect(event: object) -> None:
        events.append(event)

    class _SteeringRunner:
        # 暂停运行并暴露 manager 注入的 steer 队列
        async def run_and_capture(self, goal: str, **kwargs: object) -> RunOutcome:
            captured["queue"] = kwargs["steering_queue"]
            started.set()
            await release.wait()
            return RunOutcome(status="success", result="done", reason=None)

    bus.subscribe(collect)
    manager = SessionManager(SessionStore(tmp_path), lambda: _SteeringRunner(), bus)  # type: ignore[arg-type]
    session = await manager.create("chat")
    run_task = asyncio.create_task(manager.send_message(session.id, "first"))
    await started.wait()

    run_id = await manager.steer_message(session.id, "follow up")
    queue = captured["queue"]
    assert isinstance(queue, asyncio.Queue)
    assert queue.get_nowait() == {"role": "user", "content": "follow up"}
    assert any(
        getattr(event, "type", "") == "session.message_steered"
        and getattr(event, "run_id", "") == run_id
        for event in events
    )

    release.set()
    await run_task


class _SummaryProvider:
    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> LlmResponse:
        return LlmResponse(
            stop_reason="end_turn",
            text="""\
## 1. Original Goal
manual compact
## 2. Completed Steps
- step
## 3. Key Constraints & Discoveries
- none
## 4. Current File State
- none
## 5. Remaining TODOs
- continue
## 6. Critical Data
- none
""",
            usage=UsageStats(input_tokens=100, output_tokens=10),
        )


# 功能：验证 create 会创建等待输入的 session、写入 meta 并发布 session.created 事件
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

    assert session.status == "waiting_for_input"
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
    assert {k: v for k, v in messages[0].items() if k != "ts"} == {"role": "user", "content": "hello"}
    assert messages[0]["ts"]
    assert messages[1]["role"] == "assistant"
    history = await manager.get_history(session.id)
    assert history[0]["run_id"] == run_id


# 功能：验证 run 执行期间 session 状态为 active，结束后回落为 waiting_for_input
# 设计：用带信号量的 runner 把 run 暂停在中途，在暂停点断言内存与磁盘状态均为 active，放行后断言回落
async def test_send_message_sets_active_during_run_then_waiting(tmp_path: Path) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()

    class _PausingRunner:
        async def run_and_capture(self, goal: str, **kwargs: object) -> RunOutcome:
            entered.set()
            await release.wait()
            return RunOutcome(status="success", result="done", reason=None)

    store = SessionStore(tmp_path)
    manager = SessionManager(store, lambda: _PausingRunner(), EventBus())  # type: ignore[arg-type]
    session = await manager.create("chat")

    task = asyncio.create_task(manager.send_message(session.id, "hello"))
    await asyncio.wait_for(entered.wait(), timeout=5)
    assert session.status == "active"
    assert store.read_meta(session.id).status == "active"

    release.set()
    await asyncio.wait_for(task, timeout=5)
    assert session.status == "waiting_for_input"


# 功能：验证重启后把磁盘遗留的 active 状态归一化为 waiting_for_input
# 设计：手工把 meta 改为 active 模拟运行中崩溃，重启 manager 后断言状态回落且已持久化
async def test_restore_normalizes_stale_active(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    first_manager = SessionManager(store, lambda: _Runner(), EventBus())  # type: ignore[arg-type]
    session = await first_manager.create("chat", "crash")

    meta_path = store.session_dir(session.id) / "meta.json"
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    data["status"] = "active"
    meta_path.write_text(json.dumps(data), encoding="utf-8")

    restarted = SessionManager(store, lambda: _Runner(), EventBus())  # type: ignore[arg-type]
    listed, _ = await restarted.list_sessions(include_archived=True)
    restored = next(item for item in listed if item.id == session.id)
    assert restored.status == "waiting_for_input"
    assert store.read_meta(session.id).status == "waiting_for_input"


# 功能：验证 send_message 带 images 时把用户消息存为多模态内容块（文本 + 图片 base64）
# 设计：传一条图片内容块断言 thread 首条消息为 [text, image] 结构，确保回放/重连时模型仍能看到图片
async def test_send_message_stores_image_content_blocks(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    manager = SessionManager(store, lambda: _Runner(), EventBus())  # type: ignore[arg-type]
    session = await manager.create("chat")

    run_id = await manager.send_message(
        session.id,
        "describe this image",
        images=[{"media_type": "image/png", "data": "aGVsbG8="}],
    )

    assert run_id
    messages = store.read_messages(session.id)
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == [
        {"type": "text", "text": "describe this image"},
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": "aGVsbG8="},
        },
    ]


# 功能：验证切换会话读取历史时会从完成事件恢复尚未写入 meta 的运行统计
# 设计：在 manager 已加载 session 后再落入 run.finished，模拟旧后台产生的数据，无需重启即可自愈
async def test_get_history_backfills_run_stats_without_restart(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    manager = SessionManager(store, lambda: _Runner(), EventBus())  # type: ignore[arg-type]
    session = await manager.create("chat")
    session.run_ids.append("run-1")
    store.write_meta(session)
    events = store.runs_dir(session.id) / "run-1" / "events.jsonl"
    events.parent.mkdir(parents=True)
    events.write_text(
        '{"type":"run.finished","total_input_tokens":120,"total_output_tokens":30,"elapsed_s":2.5}\n',
        encoding="utf-8",
    )

    await manager.get_history(session.id)

    assert manager.get_run_stats(session.id) == {
        "run-1": RunStats(input_tokens=120, output_tokens=30, elapsed_s=2.5).to_dict()
    }
    assert store.read_meta(session.id).run_stats == session.run_stats


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


async def test_delete_removes_session_from_memory_and_disk(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    manager = SessionManager(store, lambda: _Runner(), EventBus())  # type: ignore[arg-type]
    session = await manager.create("chat", "delete me")
    await manager.send_message(session.id, "hello")

    await manager.delete(session.id)

    assert not store.session_dir(session.id).exists()
    listed, _ = await manager.list_sessions(include_archived=True)
    assert listed == []


# 功能：验证手动 compact 会发布 context.compacted、写 summary 文件并覆盖 thread
async def test_manual_compact_writes_summary_event_and_file(tmp_path: Path) -> None:
    events: list[object] = []
    bus = EventBus()

    async def collect(event: object) -> None:
        events.append(event)

    bus.subscribe(collect)
    store = SessionStore(tmp_path)
    manager = SessionManager(
        store,
        lambda: _Runner(),  # type: ignore[arg-type]
        bus,
        provider=_SummaryProvider(),  # type: ignore[arg-type]
    )
    session = await manager.create("chat")
    store.append_message(session.id, "user", "a" * 200)
    store.append_message(session.id, "assistant", "b" * 200)

    result = await manager.compact(session.id)

    assert result.saved_tokens > 0
    assert "context.compacting" in [getattr(e, "type", None) for e in events]
    assert "context.compacted" in [getattr(e, "type", None) for e in events]
    assert len(list(store.session_dir(session.id).glob("summary_*.md"))) == 1
    messages = store.read_messages(session.id)
    assert messages[0]["role"] == "user"
    assert "Original Goal" in messages[0]["content"]


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


# 功能：显式技能调用应保留基础系统提示，并且不把完整技能正文再次拼成用户目标
# 设计：工作区放置带参数的技能，以可观察 runner 分别断言 goal、system prompt 与工具白名单。
async def test_skill_invocation_keeps_base_prompt_without_goal_duplication(tmp_path: Path) -> None:
    workspace = tmp_path / "project"
    skill_dir = workspace / ".sztu" / "skills" / "inspect"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: inspect\ndescription: Inspect a path\nallowed_tools:\n  - read_file\n"
        "---\nInspect $ARGUMENTS carefully.\n",
        encoding="utf-8",
    )
    runner = _Runner()
    store = SessionStore(tmp_path / "sessions")
    manager = SessionManager(
        store,
        lambda: runner,  # type: ignore[arg-type]
        EventBus(),
        workspace_resolver=lambda workspace_id: workspace,
    )
    session = await manager.create("chat", workspace_id="ws-project")

    await manager.send_message(session.id, "/inspect src/app.py")

    assert runner.goal == "src/app.py"
    assert runner.system_prompt_override is not None
    assert "## Active skill: inspect" in runner.system_prompt_override
    assert "Inspect src/app.py carefully." in runner.system_prompt_override
    assert "# Environment" in runner.system_prompt_override
    assert runner.tool_whitelist == ["read_file"]


# 功能：验证第九章内建斜杠命令会加载专用提示词并仅把参数作为任务目标
# 设计：用可观察 runner 调用 /security-review，断言基础提示、工作流正文、目标和工具范围
async def test_builtin_slash_command_loads_indexed_prompt(tmp_path: Path) -> None:
    runner = _Runner()
    store = SessionStore(tmp_path / "sessions")
    manager = SessionManager(store, lambda: runner, EventBus())  # type: ignore[arg-type]
    session = await manager.create("chat")

    await manager.send_message(session.id, "/security-review origin/main")

    assert runner.goal == "origin/main"
    assert runner.system_prompt_override is not None
    assert "## Active slash command: /security-review" in runner.system_prompt_override
    assert "HIGH-CONFIDENCE security" in runner.system_prompt_override
    assert "# Environment" in runner.system_prompt_override
    assert runner.tool_whitelist is None
