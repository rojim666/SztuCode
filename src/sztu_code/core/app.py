from __future__ import annotations

import asyncio
import datetime
import fnmatch
import json
import logging
import os
import signal
import time
from datetime import UTC
from functools import partial
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

import sztu_code
from sztu_code.core.bus.commands import (
    AgentRunCommand,
    AgentRunResult,
    ChangeDiffCommand,
    ChangeDiffResult,
    ChangeListCommand,
    ChangeListResult,
    ChangeRevertCommand,
    ChangeRevertResult,
    ChangeSummary,
    EventSubscribeCommand,
    EventSubscribeResult,
    FileReadCommand,
    FileReadResult,
    FileSearchCommand,
    FileSearchResult,
    PermissionRespondCommand,
    PermissionRespondResult,
    PermissionSetModeCommand,
    PermissionSetModeResult,
    PongResult,
    ProviderStatusCommand,
    ProviderStatusResult,
    RunCancelCommand,
    RunCancelResult,
    RunGetCommand,
    RunGetResult,
    RunReplayCommand,
    RunReplayResult,
    SessionArchiveCommand,
    SessionArchiveResult,
    SessionCloseCommand,
    SessionCloseResult,
    SessionCompactCommand,
    SessionCompactResult,
    SessionCreateCommand,
    SessionCreateResult,
    SessionGetHistoryCommand,
    SessionGetHistoryResult,
    SessionListCommand,
    SessionListResult,
    SessionPinCommand,
    SessionPinResult,
    SessionRenameCommand,
    SessionRenameResult,
    SessionResumeCommand,
    SessionResumeResult,
    SessionSendMessageCommand,
    SessionSendMessageResult,
    SessionSummary,
    SettingsGetCommand,
    SettingsGetResult,
    SettingsSnapshot,
    SettingsUpdateCommand,
    SettingsUpdateResult,
    WorkspaceListCommand,
    WorkspaceListResult,
    WorkspaceOpenCommand,
    WorkspaceOpenResult,
    WorkspaceStatusCommand,
    WorkspaceStatusResult,
    WorkspaceSummary,
    WorkspaceTreeCommand,
    WorkspaceTreeResult,
)
from sztu_code.core.bus.envelope import EventPushEnvelope, HandlerError
from sztu_code.core.changes import (
    active_manifest_changes,
    load_manifest,
    revert_manifest_changes,
)
from sztu_code.core.config import SztuConfig, get_config, save_client_settings
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm import create_provider
from sztu_code.core.logging_setup import setup_logging
from sztu_code.core.mcp.server import McpServerManager
from sztu_code.core.permissions.manager import PermissionManager
from sztu_code.core.permissions.policy import PermissionMode
from sztu_code.core.permissions.storage import load_policy_file
from sztu_code.core.runner import AgentRunner
from sztu_code.core.runs import events_file, new_run_id
from sztu_code.core.session import SessionManager, SessionStore
from sztu_code.core.session.manager import SESSION_BUSY
from sztu_code.core.session.model import Session
from sztu_code.core.skills.loader import SkillLoader
from sztu_code.core.trace.record import TraceRecord
from sztu_code.core.trace.writer import TraceWriter
from sztu_code.core.transport.ipc_broadcaster import IpcEventBroadcaster
from sztu_code.core.transport.socket_server import SocketServer, get_connection_writer
from sztu_code.core.workspace import WorkspaceManager
from sztu_code.core.workspace.manager import Workspace

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.datetime.now(UTC).isoformat()


class CoreApp:
    def __init__(self) -> None:
        self._start_time = time.monotonic()
        self._bus = EventBus()
        self._broadcaster: IpcEventBroadcaster | None = None
        self._trace: TraceWriter | None = None
        self._config: SztuConfig | None = None
        self._running_runs: set[asyncio.Task[Any]] = set()
        self._active_run_tasks: dict[str, asyncio.Task[str]] = {}
        self._run_status: dict[str, str] = {}
        self._active_session_runs: dict[str, asyncio.Task[str]] = {}
        self._sessions: SessionManager | None = None
        self._permission_manager: PermissionManager | None = None
        self._mcp_manager: McpServerManager | None = None
        self._workspaces: WorkspaceManager | None = None

    # 将内部 Session 转换为稳定的 IPC 摘要模型
    @staticmethod
    def _session_summary(session: Session) -> SessionSummary:
        return SessionSummary(
            session_id=session.id,
            title=session.title,
            mode=session.mode,
            status=session.status,
            updated_at=session.updated_at,
            run_count=len(session.run_ids),
            archived=session.archived,
            pinned=session.pinned,
            workspace_id=session.workspace_id,
            latest_run_id=session.run_ids[-1] if session.run_ids else None,
        )

    # 将内部 Workspace 转换为客户端可渲染的稳定摘要
    @staticmethod
    def _workspace_summary(workspace: Workspace) -> WorkspaceSummary:
        return WorkspaceSummary(
            workspace_id=workspace.id,
            path=workspace.path,
            name=workspace.name,
        )

    # 跟踪后台 run 任务，以支持客户端查询与安全取消
    def _track_run(self, run_id: str, task: asyncio.Task[str]) -> None:
        self._running_runs.add(task)
        self._active_run_tasks[run_id] = task
        self._run_status[run_id] = "running"
        task.add_done_callback(partial(self._on_run_finished, run_id))

    # 记录 run 终态并清理活动索引，防止后台异常变成未观察任务
    def _on_run_finished(self, run_id: str, task: asyncio.Task[str]) -> None:
        self._running_runs.discard(task)
        if self._active_run_tasks.get(run_id) is task:
            self._active_run_tasks.pop(run_id, None)
        if task.cancelled():
            self._run_status[run_id] = "cancelled"
            return
        try:
            task.result()
        except Exception:
            self._run_status[run_id] = "completed"
            logger.exception("run failed run_id=%s", run_id)
        else:
            self._run_status[run_id] = "completed"

    # 处理 core.ping 请求，返回服务版本、运行时长和接收时间
    async def _ping_handler(self, params: dict[str, Any]) -> PongResult:
        client = params.get("client", "unknown")
        logger.debug("ping from %s", client)
        return PongResult(
            server_version=sztu_code.__version__,
            uptime_ms=int((time.monotonic() - self._start_time) * 1000),
            received_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

    # 将 EventBus 事件写入 trace（作为 EventBus 订阅者）
    async def _trace_event_handler(self, event: BaseModel) -> None:
        assert self._trace is not None
        event_dict = event.model_dump()
        self._trace.emit(
            TraceRecord(
                ts=_now(),
                direction="CORE",
                layer="event",
                kind="event",
                run_id=event_dict.get("run_id"),
                data=event_dict,
            )
        )

    # 启动一次 agent run：异步创建 AgentRunner 并立即返回 run_id
    async def _agent_run_handler(self, params: dict[str, Any]) -> AgentRunResult:
        assert self._sessions is not None
        cmd = AgentRunCommand.model_validate(params)
        session = await self._sessions.create(mode="one_shot", title=cmd.goal[:40])
        run_id = new_run_id()
        run_task = asyncio.create_task(
            self._sessions.send_message(session.id, cmd.goal, run_id=run_id)
        )
        self._track_run(run_id, run_task)
        return AgentRunResult(run_id=run_id)

    # 创建 chat 或 one_shot session，并返回 session_id
    async def _session_create_handler(self, params: dict[str, Any]) -> SessionCreateResult:
        assert self._sessions is not None
        cmd = SessionCreateCommand.model_validate(params)
        if cmd.workspace_id is not None:
            assert self._workspaces is not None
            try:
                self._workspaces.get(cmd.workspace_id)
            except ValueError as error:
                raise HandlerError(-32602, str(error)) from error
        session = await self._sessions.create(
            mode=cmd.mode, title=cmd.title, workspace_id=cmd.workspace_id
        )
        return SessionCreateResult(session_id=session.id, status=session.status)

    # 返回按最近活动排序的 session 列表，供任务历史侧栏使用
    async def _session_list_handler(self, params: dict[str, Any]) -> SessionListResult:
        assert self._sessions is not None
        cmd = SessionListCommand.model_validate(params)
        sessions, next_cursor = await self._sessions.list_sessions(
            include_archived=cmd.include_archived,
            limit=cmd.limit,
            cursor=cmd.cursor,
        )
        return SessionListResult(
            sessions=[self._session_summary(session) for session in sessions],
            next_cursor=next_cursor,
        )

    # 重命名 session 并返回更新后的任务摘要
    async def _session_rename_handler(self, params: dict[str, Any]) -> SessionRenameResult:
        assert self._sessions is not None
        cmd = SessionRenameCommand.model_validate(params)
        session = await self._sessions.rename(cmd.session_id, cmd.title)
        return SessionRenameResult(session=self._session_summary(session))

    # 归档 session 并返回更新后的任务摘要
    async def _session_archive_handler(self, params: dict[str, Any]) -> SessionArchiveResult:
        assert self._sessions is not None
        cmd = SessionArchiveCommand.model_validate(params)
        session = await self._sessions.archive(cmd.session_id)
        return SessionArchiveResult(session=self._session_summary(session))

    # 固定状态由 daemon 持久化，客户端刷新后仍能保持任务分组
    async def _session_pin_handler(self, params: dict[str, Any]) -> SessionPinResult:
        assert self._sessions is not None
        cmd = SessionPinCommand.model_validate(params)
        session = await self._sessions.pin(cmd.session_id, cmd.pinned)
        return SessionPinResult(session=self._session_summary(session))

    # 恢复 session 并返回可重新打开的任务摘要
    async def _session_resume_handler(self, params: dict[str, Any]) -> SessionResumeResult:
        assert self._sessions is not None
        cmd = SessionResumeCommand.model_validate(params)
        session = await self._sessions.resume(cmd.session_id)
        return SessionResumeResult(session=self._session_summary(session))

    # 打开本地工作区并记录为最近项目
    async def _workspace_open_handler(self, params: dict[str, Any]) -> WorkspaceOpenResult:
        assert self._workspaces is not None
        cmd = WorkspaceOpenCommand.model_validate(params)
        try:
            workspace = self._workspaces.open(cmd.path)
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        return WorkspaceOpenResult(workspace=self._workspace_summary(workspace))

    # 返回最近打开的本地工作区
    async def _workspace_list_handler(self, params: dict[str, Any]) -> WorkspaceListResult:
        assert self._workspaces is not None
        WorkspaceListCommand.model_validate(params)
        workspaces = self._workspaces.list_recent()
        return WorkspaceListResult(
            workspaces=[self._workspace_summary(workspace) for workspace in workspaces]
        )

    # 返回工作区 Git 分支与未提交修改摘要
    async def _workspace_status_handler(self, params: dict[str, Any]) -> WorkspaceStatusResult:
        assert self._workspaces is not None
        cmd = WorkspaceStatusCommand.model_validate(params)
        try:
            status = self._workspaces.status(cmd.workspace_id)
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        workspace = status["workspace"]
        assert isinstance(workspace, Workspace)
        changed_file_count = status["changed_file_count"]
        assert isinstance(changed_file_count, int)
        return WorkspaceStatusResult(
            workspace=self._workspace_summary(workspace),
            branch=status["branch"] if isinstance(status["branch"], str) else None,
            is_git_repository=bool(status["is_git_repository"]),
            changed_file_count=changed_file_count,
        )

    # 返回指定工作区子路径的受限目录树
    async def _workspace_tree_handler(self, params: dict[str, Any]) -> WorkspaceTreeResult:
        assert self._workspaces is not None
        cmd = WorkspaceTreeCommand.model_validate(params)
        try:
            nodes = self._workspaces.tree(
                cmd.workspace_id,
                cmd.path,
                max_depth=cmd.max_depth,
                max_entries=cmd.max_entries,
            )
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        return WorkspaceTreeResult(nodes=nodes)

    # 读取工作区内单个文本文件，路径越界时返回结构化参数错误
    async def _file_read_handler(self, params: dict[str, Any]) -> FileReadResult:
        assert self._workspaces is not None
        cmd = FileReadCommand.model_validate(params)
        try:
            file_content = self._workspaces.read_file(cmd.workspace_id, cmd.path)
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        return FileReadResult(
            content=file_content.content,
            encoding=file_content.encoding,
            binary=file_content.binary,
            truncated=file_content.truncated,
            media_base64=file_content.media_base64,
            mime_type=file_content.mime_type,
        )

    # 搜索工作区文本文件并返回受限数量的命中行
    async def _file_search_handler(self, params: dict[str, Any]) -> FileSearchResult:
        assert self._workspaces is not None
        cmd = FileSearchCommand.model_validate(params)
        try:
            matches = self._workspaces.search(
                cmd.workspace_id,
                cmd.query,
                max_results=cmd.max_results,
            )
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        return FileSearchResult(matches=matches)

    # 返回工作区未提交文件摘要，供客户端变更侧栏和测试结果面板使用
    async def _change_list_handler(self, params: dict[str, Any]) -> ChangeListResult:
        assert self._workspaces is not None
        cmd = ChangeListCommand.model_validate(params)
        try:
            changes = self._workspaces.list_changes(cmd.workspace_id)
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        agent_changes = self._agent_change_summaries(cmd.workspace_id, cmd.run_id)
        if cmd.run_id is not None:
            return ChangeListResult(changes=agent_changes)
        owned = {change.path: change for change in agent_changes}
        summaries = [ChangeSummary.model_validate(change) for change in changes]
        return ChangeListResult(
            changes=[owned.get(change.path, change) for change in summaries]
        )

    # 返回工作区或单个文件的只读 Git diff，供客户端审阅器渲染
    async def _change_diff_handler(self, params: dict[str, Any]) -> ChangeDiffResult:
        assert self._workspaces is not None
        cmd = ChangeDiffCommand.model_validate(params)
        try:
            diff = self._workspaces.diff(cmd.workspace_id, cmd.path)
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        return ChangeDiffResult(diff=diff)

    async def _change_revert_handler(self, params: dict[str, Any]) -> ChangeRevertResult:
        assert self._workspaces is not None
        cmd = ChangeRevertCommand.model_validate(params)
        try:
            workspace = self._workspaces.get(cmd.workspace_id)
            manifest_path = self._find_change_manifest(cmd.run_id)
            if manifest_path is None:
                raise ValueError("agent change record not found")
            reverted, blocked = revert_manifest_changes(
                manifest_path, Path(workspace.path), cmd.paths
            )
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        return ChangeRevertResult(reverted_paths=reverted, blocked_paths=blocked)

    def _agent_change_summaries(
        self, workspace_id: str, run_id: str | None
    ) -> list[ChangeSummary]:
        if run_id is None or self._workspaces is None:
            return []
        manifest_path = self._find_change_manifest(run_id)
        manifest = load_manifest(manifest_path) if manifest_path else None
        workspace = self._workspaces.get(workspace_id)
        workspace_path = str(Path(workspace.path).resolve())
        if manifest is None or manifest.get("workspace_path") != workspace_path:
            return []
        changes = active_manifest_changes(manifest, Path(workspace.path))
        return [
            ChangeSummary(
                path=str(change.get("path", "")),
                index_status=" ",
                worktree_status="M",
                run_id=run_id,
                agent_owned=True,
                revertible=bool(change.get("revertible", False)),
            )
            for change in changes
            if isinstance(change, dict) and isinstance(change.get("path"), str)
        ]

    @staticmethod
    def _find_change_manifest(run_id: str) -> Path | None:
        candidate = events_file(run_id).parent / "changes.json"
        if candidate.exists():
            return candidate
        for path in Path("~/.sztu/sessions").expanduser().glob(f"*/runs/{run_id}/changes.json"):
            return path
        return None

    # 启动 session run 并立即返回 run_id，使同一连接能持续接收事件和审批请求
    async def _session_send_handler(self, params: dict[str, Any]) -> SessionSendMessageResult:
        assert self._sessions is not None
        cmd = SessionSendMessageCommand.model_validate(params)
        active_run = self._active_session_runs.get(cmd.session_id)
        if active_run is not None and not active_run.done():
            raise HandlerError(SESSION_BUSY, "session busy")
        await self._sessions.get_history(cmd.session_id)

        run_id = new_run_id()
        run_task = asyncio.create_task(
            self._sessions.send_message(cmd.session_id, cmd.content, run_id=run_id)
        )
        self._active_session_runs[cmd.session_id] = run_task
        self._track_run(run_id, run_task)
        run_task.add_done_callback(partial(self._on_session_run_finished, cmd.session_id))
        return SessionSendMessageResult(run_id=run_id)

    # 清理已结束的 session run，并记录后台执行中未能返回给 RPC 调用方的异常
    def _on_session_run_finished(self, session_id: str, task: asyncio.Task[str]) -> None:
        if self._active_session_runs.get(session_id) is task:
            self._active_session_runs.pop(session_id, None)

    # 请求停止仍在执行的 run；取消由 AgentRunner 转换为可观察的 run.finished 事件
    async def _run_cancel_handler(self, params: dict[str, Any]) -> RunCancelResult:
        cmd = RunCancelCommand.model_validate(params)
        task = self._active_run_tasks.get(cmd.run_id)
        if task is None or task.done():
            return RunCancelResult(run_id=cmd.run_id, status="not_running")
        task.cancel()
        self._run_status[cmd.run_id] = "cancelled"
        return RunCancelResult(run_id=cmd.run_id, status="cancelling")

    # 返回当前进程所知的 run 生命周期状态，供客户端重连后恢复控制状态
    async def _run_get_handler(self, params: dict[str, Any]) -> RunGetResult:
        cmd = RunGetCommand.model_validate(params)
        status = self._run_status.get(cmd.run_id, "unknown")
        return RunGetResult(run_id=cmd.run_id, status=status)  # type: ignore[arg-type]

    # 读取已持久化的运行事件，供客户端在切换或重连后重建工作台状态
    async def _run_replay_handler(self, params: dict[str, Any]) -> RunReplayResult:
        cmd = RunReplayCommand.model_validate(params)
        events = self._read_run_events(cmd.run_id, max_events=cmd.max_events)
        return RunReplayResult(run_id=cmd.run_id, events=events)

    # 返回 session 的完整 Anthropic messages 历史
    async def _session_history_handler(self, params: dict[str, Any]) -> SessionGetHistoryResult:
        assert self._sessions is not None
        cmd = SessionGetHistoryCommand.model_validate(params)
        messages = await self._sessions.get_history(cmd.session_id)
        return SessionGetHistoryResult(messages=messages)

    # 接收客户端权限审批响应，resolve 对应挂起的 Future
    async def _permission_respond_handler(self, params: dict[str, Any]) -> PermissionRespondResult:
        cmd = PermissionRespondCommand.model_validate(params)
        logger.info(
            "permission.respond received tool_use_id=%s decision=%s",
            cmd.tool_use_id, cmd.decision,
        )
        if self._permission_manager is None:
            logger.error("permission.respond: PermissionManager not initialized")
            return PermissionRespondResult()
        self._permission_manager.respond(cmd.tool_use_id, cmd.decision)
        return PermissionRespondResult()

    # 接收客户端权限模式切换请求，设置 PermissionManager 模式并广播事件
    async def _permission_set_mode_handler(self, params: dict[str, Any]) -> PermissionSetModeResult:
        cmd = PermissionSetModeCommand.model_validate(params)
        new_mode = PermissionMode(cmd.mode)
        if self._permission_manager is None:
            return PermissionSetModeResult(ok=False, error="PermissionManager not initialized")
        old_mode = self._permission_manager.get_mode()
        await self._permission_manager.set_mode(new_mode)
        # 广播模式变更事件到所有订阅客户端
        if self._bus is not None:
            from sztu_code.core.bus.events import PermissionModeChangedEvent
            await self._bus.publish(
                PermissionModeChangedEvent(
                    old_mode=old_mode.value,
                    new_mode=new_mode.value,
                    ts=datetime.datetime.now(UTC).isoformat(),
                )
            )
        logger.info("permission mode: %s → %s", old_mode.value, new_mode.value)
        if self._config is not None:
            self._config.permission.mode = new_mode.value
            save_client_settings(self._config)
        return PermissionSetModeResult(ok=True, mode=new_mode.value)

    def _settings_snapshot(self) -> SettingsSnapshot:
        assert self._config is not None
        assert self._permission_manager is not None
        return SettingsSnapshot(
            provider=self._config.llm.provider,  # type: ignore[arg-type]
            model=self._config.llm.default_model,
            router=self._config.llm.router,
            permission_mode=self._permission_manager.get_mode().value,
        )

    async def _settings_get_handler(self, params: dict[str, Any]) -> SettingsGetResult:
        SettingsGetCommand.model_validate(params)
        return SettingsGetResult(settings=self._settings_snapshot())

    async def _settings_update_handler(self, params: dict[str, Any]) -> SettingsUpdateResult:
        assert self._config is not None
        assert self._permission_manager is not None
        cmd = SettingsUpdateCommand.model_validate(params)
        updated: list[Literal["provider", "model", "permission_mode"]] = []
        if cmd.provider is not None and cmd.provider != self._config.llm.provider:
            self._config.llm.provider = cmd.provider
            updated.append("provider")
        if cmd.model is not None and cmd.model != self._config.llm.default_model:
            self._config.llm.default_model = cmd.model
            updated.append("model")
        if cmd.permission_mode is not None:
            current_mode = self._permission_manager.get_mode()
            new_mode = PermissionMode(cmd.permission_mode)
            if new_mode != current_mode:
                await self._permission_manager.set_mode(new_mode)
                from sztu_code.core.bus.events import PermissionModeChangedEvent

                await self._bus.publish(
                    PermissionModeChangedEvent(
                        old_mode=current_mode.value, new_mode=new_mode.value, ts=_now()
                    )
                )
                updated.append("permission_mode")
                self._config.permission.mode = new_mode.value
        if updated:
            save_client_settings(self._config)
        if self._sessions is not None and any(
            field in updated for field in ("provider", "model")
        ):
            key_name = (
                "OPENAI_API_KEY"
                if self._config.llm.provider == "openai"
                else "ANTHROPIC_API_KEY"
            )
            provider = (
                create_provider(self._config)
                if os.environ.get(key_name) and self._config.llm.default_model.strip()
                else None
            )
            self._sessions.set_provider(provider)
        return SettingsUpdateResult(settings=self._settings_snapshot(), updated=updated)

    async def _provider_status_handler(self, params: dict[str, Any]) -> ProviderStatusResult:
        assert self._config is not None
        ProviderStatusCommand.model_validate(params)
        provider = self._config.llm.provider
        api_key_name = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
        endpoint_name = "OPENAI_BASE_URL" if provider == "openai" else "ANTHROPIC_BASE_URL"
        skills = [
            {"name": skill.name, "description": skill.description[:180]}
            for skill in SkillLoader().list_all_skills()
        ]
        mcp_servers = (
            self._mcp_manager.statuses(self._config.mcp.servers)
            if self._mcp_manager is not None
            else []
        )
        return ProviderStatusResult(
            provider=provider,  # type: ignore[arg-type]
            model=self._config.llm.default_model,
            api_key_configured=bool(os.environ.get(api_key_name)),
            custom_endpoint_configured=bool(os.environ.get(endpoint_name)),
            ready_for_next_run=bool(
                os.environ.get(api_key_name) and self._config.llm.default_model.strip()
            ),
            mcp_servers=mcp_servers,
            skills=skills,
        )

    async def _session_compact_handler(self, params: dict[str, Any]) -> SessionCompactResult:
        assert self._sessions is not None
        cmd = SessionCompactCommand.model_validate(params)
        result = await self._sessions.compact(cmd.session_id, cmd.focus)
        return result  # type: ignore[no-any-return]

    # 关闭 session 并返回 closed 状态
    async def _session_close_handler(self, params: dict[str, Any]) -> SessionCloseResult:
        assert self._sessions is not None
        cmd = SessionCloseCommand.model_validate(params)
        await self._sessions.close(cmd.session_id)
        return SessionCloseResult(status="closed")

    # 注册客户端事件订阅，可选先回放 events.jsonl 历史再接收实时流
    async def _subscribe_handler(self, params: dict[str, Any]) -> EventSubscribeResult:
        cmd = EventSubscribeCommand.model_validate(params)
        writer = get_connection_writer()

        replayed_count = 0
        if cmd.replay_from_run is not None:
            replayed_count = await self._replay_events(
                cmd.replay_from_run, writer, cmd.topics
            )

        assert self._broadcaster is not None
        sub_id = self._broadcaster.subscribe(writer, cmd.topics, cmd.scope)
        return EventSubscribeResult(subscription_id=sub_id, replayed_count=replayed_count)

    # 从 events.jsonl 向 writer 回放匹配 topic 的历史事件，返回已回放条数
    async def _replay_events(
        self,
        run_id: str,
        writer: asyncio.StreamWriter,
        topics: list[str],
    ) -> int:
        count = 0
        for event in self._read_run_events(run_id, max_events=10_000):
            event_type: str = event.get("type", "")
            if not any(fnmatch.fnmatch(event_type, p) for p in topics):
                continue
            envelope = EventPushEnvelope(event=event)
            writer.write(envelope.model_dump_json().encode() + b"\n")
            count += 1

        if count:
            await writer.drain()
        return count

    # 从独立 run 或 session run 目录加载有限数量的有效事件字典
    @staticmethod
    def _read_run_events(run_id: str, *, max_events: int) -> list[dict[str, Any]]:
        path = events_file(run_id)
        if not path.exists():
            for candidate in Path("~/.sztu/sessions").expanduser().glob(
                f"*/runs/{run_id}/events.jsonl"
            ):
                path = candidate
                break
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line or len(events) >= max_events:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        return events

    # 启动守护进程：加载配置、初始化日志、启动 trace、启动 TCP 服务器，并等待退出信号
    async def run(self) -> None:
        self._start_time = time.monotonic()
        self._config = get_config()
        setup_logging(self._config)

        if self._config.trace.enabled:
            trace_path = Path(self._config.trace.file).expanduser()
            self._trace = TraceWriter(trace_path)
            await self._trace.start()
            self._bus.subscribe(self._trace_event_handler)

        policy_file = Path("~/.sztu/policy.toml").expanduser()
        self._permission_manager = PermissionManager(
            policy_file=policy_file,
            timeout_s=self._config.permission.timeout_s,
            mode=PermissionMode(self._config.permission.mode),
        )
        logger.info(
            "permission manager: timeout_s=%.1f  persistent=%d entries",
            self._config.permission.timeout_s,
            len(load_policy_file(policy_file)),
        )

        self._broadcaster = IpcEventBroadcaster(trace=self._trace)
        self._bus.subscribe(self._broadcaster.handle)
        sessions_root = Path("~/.sztu/sessions").expanduser()
        store = SessionStore(sessions_root)
        self._workspaces = WorkspaceManager(Path("~/.sztu/workspaces.json"))
        assert self._config is not None
        provider_key_name = (
            "OPENAI_API_KEY"
            if self._config.llm.provider == "openai"
            else "ANTHROPIC_API_KEY"
        )
        compact_provider = (
            create_provider(self._config)
            if os.environ.get(provider_key_name) and self._config.llm.default_model.strip()
            else None
        )

        self._mcp_manager = McpServerManager()
        if self._config.mcp.servers:
            logger.info("mcp: starting %d server(s)", len(self._config.mcp.servers))
            await self._mcp_manager.start_all(self._config.mcp.servers)

        self._sessions = SessionManager(
            store,
            runner_factory=lambda: AgentRunner(
                self._config,  # type: ignore[arg-type]
                bus=self._bus,
                trace=self._trace,
                permission_manager=self._permission_manager,
                mcp_manager=self._mcp_manager,
            ),
            bus=self._bus,
            provider=compact_provider,
            workspace_resolver=lambda workspace_id: Path(
                self._workspaces.get(workspace_id).path  # type: ignore[union-attr]
            ),
        )

        server = SocketServer(
            self._config.host,
            self._config.port,
            self._broadcaster,
            trace=self._trace,
        )
        server.register("core.ping", self._ping_handler)
        server.register("agent.run", self._agent_run_handler)
        server.register("run.cancel", self._run_cancel_handler)
        server.register("run.get", self._run_get_handler)
        server.register("run.replay", self._run_replay_handler)
        server.register("workspace.open", self._workspace_open_handler)
        server.register("workspace.list", self._workspace_list_handler)
        server.register("workspace.status", self._workspace_status_handler)
        server.register("workspace.tree", self._workspace_tree_handler)
        server.register("file.read", self._file_read_handler)
        server.register("file.search", self._file_search_handler)
        server.register("change.list", self._change_list_handler)
        server.register("change.diff", self._change_diff_handler)
        server.register("change.revert", self._change_revert_handler)
        server.register("event.subscribe", self._subscribe_handler)
        server.register("session.create", self._session_create_handler)
        server.register("session.list", self._session_list_handler)
        server.register("session.rename", self._session_rename_handler)
        server.register("session.archive", self._session_archive_handler)
        server.register("session.pin", self._session_pin_handler)
        server.register("session.resume", self._session_resume_handler)
        server.register("session.send_message", self._session_send_handler)
        server.register("session.get_history", self._session_history_handler)
        server.register("session.close", self._session_close_handler)
        server.register("permission.respond", self._permission_respond_handler)
        server.register("permission.set_mode", self._permission_set_mode_handler)
        server.register("settings.get", self._settings_get_handler)
        server.register("settings.update", self._settings_update_handler)
        server.register("provider.status", self._provider_status_handler)
        server.register("session.compact", self._session_compact_handler)

        addr = await server.start()
        logger.info("sztu-code %s listening addr=%s", sztu_code.__version__, addr)
        logger.info("config: %s", self._config)

        loop = asyncio.get_running_loop()
        shutdown = asyncio.Event()
        # add_signal_handler 在 Windows 上不支持，回退到 signal.signal
        try:
            loop.add_signal_handler(signal.SIGINT, shutdown.set)
            loop.add_signal_handler(signal.SIGTERM, shutdown.set)
        except NotImplementedError:
            signal.signal(signal.SIGINT, lambda signum, frame: shutdown.set())
            if hasattr(signal, "SIGTERM"):
                signal.signal(signal.SIGTERM, lambda signum, frame: shutdown.set())

        await shutdown.wait()

        logger.info("shutting down")
        for run_task in list(self._running_runs):
            run_task.cancel()
        if self._running_runs:
            await asyncio.gather(*self._running_runs, return_exceptions=True)
        if self._mcp_manager is not None:
            await self._mcp_manager.stop_all()
        await server.stop()
        if self._trace is not None:
            await self._trace.stop()


# 同步入口：启动 CoreApp 事件循环
def run() -> None:
    asyncio.run(CoreApp().run())
