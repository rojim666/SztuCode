from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sztu_code.core.bus.envelope import HandlerError
from sztu_code.core.bus.events import (
    SessionClosedEvent,
    SessionCreatedEvent,
    SessionMessageReceivedEvent,
    SessionResumedEvent,
    SessionWaitingForInputEvent,
    SkillInvokedEvent,
)
from sztu_code.core.events.bus import EventBus
from sztu_code.core.runs import new_run_id
from sztu_code.core.session.model import Session, SessionMode
from sztu_code.core.session.store import SessionStore
from sztu_code.core.skills.loader import SkillLoader

if TYPE_CHECKING:
    from sztu_code.core.llm.base import LLMProvider
    from sztu_code.core.runner import AgentRunner

SESSION_NOT_FOUND = -32010
SESSION_CLOSED = -32011
SESSION_BUSY = -32012


# 返回当前 UTC 时间的 ISO 8601 字符串
def _now() -> str:
    return datetime.now(UTC).isoformat()


class SessionManager:
    # 初始化会话管理器，接入文件存储、runner 工厂、事件总线和可选的 LLM provider（用于手动压缩）
    def __init__(
        self,
        store: SessionStore,
        runner_factory: Callable[[], AgentRunner],
        bus: EventBus,
        provider: LLMProvider | None = None,
        workspace_resolver: Callable[[str], Path] | None = None,
    ) -> None:
        self._store = store
        self._runner_factory = runner_factory
        self._bus = bus
        self._provider = provider
        self._workspace_resolver = workspace_resolver
        restored = self._store.list_sessions(include_archived=True)
        self._sessions: dict[str, Session] = {session.id: session for session in restored}
        self._locks: dict[str, asyncio.Lock] = {
            session.id: asyncio.Lock() for session in restored
        }
        self._skill_loader = SkillLoader()

    def set_provider(self, provider: LLMProvider | None) -> None:
        self._provider = provider

    # 创建新 session 并写入 meta.json
    async def create(
        self,
        mode: SessionMode,
        title: str = "",
        workspace_id: str | None = None,
    ) -> Session:
        sid = f"sess-{uuid.uuid4().hex[:12]}"
        ts = _now()
        session = Session(
            id=sid,
            mode=mode,
            status="active",
            title=title,
            created_at=ts,
            updated_at=ts,
            run_ids=[],
            workspace_id=workspace_id,
        )
        self._sessions[sid] = session
        self._locks[sid] = asyncio.Lock()
        self._store.write_meta(session)
        await self._bus.publish(SessionCreatedEvent(session_id=sid, mode=mode, ts=ts))
        return session

    # 处理用户消息，追加 thread 并启动一次 agent run
    async def send_message(self, sid: str, content: str, *, run_id: str | None = None) -> str:
        session = self._get_session(sid)
        lock = self._locks[sid]
        if lock.locked():
            raise HandlerError(SESSION_BUSY, "session busy")

        async with lock:
            if session.status == "closed":
                raise HandlerError(SESSION_CLOSED, "session already closed")

            if session.status == "waiting_for_input":
                await self._bus.publish(SessionResumedEvent(session_id=sid, ts=_now()))

            self._store.append_message(sid, "user", content)
            await self._bus.publish(
                SessionMessageReceivedEvent(session_id=sid, content=content, ts=_now())
            )

            if not session.title:
                session.title = content[:40]

            run_id = run_id or new_run_id()
            session.run_ids.append(run_id)
            session.updated_at = _now()
            self._store.write_meta(session)

            # Skill 解析：检测 "/" 前缀，展开为系统提示覆盖和工具白名单
            goal = content
            system_prompt_override: str | None = None
            tool_whitelist: list[str] | None = None
            if content.startswith("/"):
                parts = content[1:].split(None, 1)
                skill_name = parts[0]
                arguments = parts[1] if len(parts) > 1 else ""
                skill = self._skill_loader.resolve(skill_name)
                if skill is not None:
                    goal = self._skill_loader.render_prompt(skill, arguments)
                    system_prompt_override = skill.system_prompt_template
                    tool_whitelist = skill.allowed_tools or None
                    await self._bus.publish(
                        SkillInvokedEvent(
                            skill_name=skill_name,
                            arguments=arguments,
                            run_id=run_id,
                            ts=_now(),
                        )
                    )

            runner = self._runner_factory()
            workspace_root = (
                self._workspace_resolver(session.workspace_id)
                if session.workspace_id is not None and self._workspace_resolver is not None
                else None
            )
            try:
                await runner.run_and_capture(
                    goal,
                    run_id=run_id,
                    session=session,
                    store=self._store,
                    system_prompt_override=system_prompt_override,
                    tool_whitelist=tool_whitelist,
                    workspace_root=workspace_root,
                )
            except asyncio.CancelledError:
                session.updated_at = _now()
                if session.mode == "chat":
                    session.status = "waiting_for_input"
                    await self._bus.publish(
                        SessionWaitingForInputEvent(
                            session_id=sid,
                            last_run_id=run_id,
                            ts=session.updated_at,
                        )
                    )
                else:
                    session.status = "closed"
                    await self._bus.publish(
                        SessionClosedEvent(session_id=sid, ts=session.updated_at)
                    )
                self._store.write_meta(session)
                raise

            session.updated_at = _now()
            if session.mode == "one_shot":
                session.status = "closed"
                await self._bus.publish(SessionClosedEvent(session_id=sid, ts=session.updated_at))
            else:
                session.status = "waiting_for_input"
                await self._bus.publish(
                    SessionWaitingForInputEvent(
                        session_id=sid,
                        last_run_id=run_id,
                        ts=session.updated_at,
                    )
                )
            self._store.write_meta(session)
            return run_id

    # 关闭指定 session 并更新 meta.json
    async def close(self, sid: str) -> None:
        session = self._get_session(sid)
        lock = self._locks[sid]
        if lock.locked():
            raise HandlerError(SESSION_BUSY, "session busy")
        async with lock:
            session.status = "closed"
            session.updated_at = _now()
            self._store.write_meta(session)
            await self._bus.publish(SessionClosedEvent(session_id=sid, ts=session.updated_at))

    # 从内存索引和磁盘完整删除指定 session
    async def delete(self, sid: str) -> None:
        self._get_session(sid)
        lock = self._locks[sid]
        if lock.locked():
            raise HandlerError(SESSION_BUSY, "session busy")
        async with lock:
            self._store.delete(sid)
            self._sessions.pop(sid, None)
            self._locks.pop(sid, None)

    # 手动压缩指定 session 的 thread，将摘要持久化写入 thread.jsonl
    async def compact(self, sid: str, focus: str = "") -> Any:
        self._get_session(sid)
        lock = self._locks[sid]
        if lock.locked():
            raise HandlerError(SESSION_BUSY, "session busy")
        if self._provider is None:
            raise HandlerError(-32020, "provider not available for compaction")
        async with lock:
            from sztu_code.core.bus.commands import SessionCompactResult
            from sztu_code.core.compact.compactor import Compactor, _continuation_message
            messages = self._store.read_messages(sid)
            session_dir = self._store.session_dir(sid)
            compactor = Compactor(self._bus, session_dir, sid)
            await compactor.notify_compacting("")
            result = await compactor.compact_messages(messages, self._provider, focus=focus)
            if result is None:
                raise HandlerError(-32021, "compaction failed or not beneficial")
            self._store.write_compacted(sid, [
                {"role": "user", "content": _continuation_message(result.summary_text)},
                {"role": "assistant", "content": "Understood, I'll continue from this summary."},
            ])
            await compactor.record_compaction(run_id="", result=result)
            return SessionCompactResult(
                summary_tokens=result.summary_tokens,
                saved_tokens=max(0, result.original_token_estimate - result.summary_tokens),
            )

    # 读取指定 session 的完整 thread 历史
    async def get_history(self, sid: str) -> list[dict[str, Any]]:
        self._get_session(sid)
        return self._store.read_messages(sid)

    # 返回稳定排序并支持 cursor 分页的 session 摘要列表
    async def list_sessions(
        self,
        *,
        include_archived: bool = False,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[Session], str | None]:
        sessions = [
            session for session in self._sessions.values()
            if include_archived or not session.archived
        ]
        sessions.sort(
            key=lambda session: (not session.pinned, session.updated_at, session.id)
        )
        if cursor is not None:
            try:
                start = next(i + 1 for i, session in enumerate(sessions) if session.id == cursor)
            except StopIteration:
                raise HandlerError(SESSION_NOT_FOUND, "session cursor not found") from None
            sessions = sessions[start:]
        page = sessions[:limit]
        next_cursor = page[-1].id if len(sessions) > len(page) else None
        return page, next_cursor

    # 更新 session 标题，供任务列表的重命名操作使用
    async def rename(self, sid: str, title: str) -> Session:
        session = self._get_session(sid)
        if not title.strip():
            raise HandlerError(-32602, "session title must not be empty")
        session.title = title.strip()
        session.updated_at = _now()
        self._store.write_meta(session)
        return session

    # 将非运行中的 session 标记为归档，保留其历史与可恢复能力
    async def archive(self, sid: str) -> Session:
        session = self._get_session(sid)
        lock = self._locks[sid]
        if lock.locked():
            raise HandlerError(SESSION_BUSY, "session busy")
        session.archived = True
        session.pinned = False
        session.updated_at = _now()
        self._store.write_meta(session)
        return session

    # 固定或取消固定一项未归档任务；固定任务始终显示在最近任务之前
    async def pin(self, sid: str, pinned: bool) -> Session:
        session = self._get_session(sid)
        lock = self._locks[sid]
        if lock.locked():
            raise HandlerError(SESSION_BUSY, "session busy")
        if pinned and session.archived:
            raise HandlerError(-32602, "archived session cannot be pinned")
        session.pinned = pinned
        self._store.write_meta(session)
        return session

    # 恢复已持久化 session，使 chat session 再次进入可输入状态
    async def resume(self, sid: str) -> Session:
        session = self._get_session(sid)
        lock = self._locks[sid]
        if lock.locked():
            raise HandlerError(SESSION_BUSY, "session busy")
        session.archived = False
        if session.mode == "chat":
            session.status = "waiting_for_input"
        session.updated_at = _now()
        self._store.write_meta(session)
        await self._bus.publish(SessionResumedEvent(session_id=sid, ts=session.updated_at))
        return session

    # 从内存索引取 session，不存在时抛 JSON-RPC 结构化错误
    def _get_session(self, sid: str) -> Session:
        session = self._sessions.get(sid)
        if session is None:
            raise HandlerError(SESSION_NOT_FOUND, "session not found")
        return session
