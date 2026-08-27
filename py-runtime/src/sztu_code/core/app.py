from __future__ import annotations

import asyncio
import datetime
import fnmatch
import json
import logging
import os
import signal
import statistics
import time
import uuid
from datetime import UTC
from functools import partial
from pathlib import Path
from typing import Any, cast

import httpx
from pydantic import BaseModel

import sztu_code
from sztu_code.core.bus.commands import (
    AgentRunCommand,
    AgentRunResult,
    ApiFormat,
    CcswitchProviderSummary,
    ChangeDiffCommand,
    ChangeDiffResult,
    ChangeDiscardCommand,
    ChangeDiscardResult,
    ChangeListCommand,
    ChangeListResult,
    ChangeRevertCommand,
    ChangeRevertResult,
    ChangeStageCommand,
    ChangeStageResult,
    ChangeSummary,
    ChangeUnstageCommand,
    ChangeUnstageResult,
    EventSubscribeCommand,
    EventSubscribeResult,
    FileReadCommand,
    FileReadResult,
    FileSearchCommand,
    FileSearchResult,
    GitCommitCommand,
    GitCommitResult,
    GitHistoryCommand,
    GitHistoryResult,
    MarketplacePluginSummary,
    MarketplaceSummary,
    ModelBenchmarkCommand,
    ModelBenchmarkResult,
    ModelProfileDeleteCommand,
    ModelProfileDeleteResult,
    ModelProfileListCommand,
    ModelProfileListResult,
    ModelProfileSaveCommand,
    ModelProfileSaveResult,
    ModelProfileSelectCommand,
    ModelProfileSelectResult,
    ModelProfileSummary,
    ModelTestCommand,
    ModelTestResult,
    PermissionRespondCommand,
    PermissionRespondResult,
    PermissionSetModeCommand,
    PermissionSetModeResult,
    PluginCatalogCommand,
    PluginCatalogInstallCommand,
    PluginCatalogInstallResult,
    PluginCatalogResult,
    PluginInstallCommand,
    PluginInstallResult,
    PluginListCommand,
    PluginListResult,
    PluginMarketplaceAddCommand,
    PluginMarketplaceAddResult,
    PluginMarketplaceRefreshCommand,
    PluginMarketplaceRefreshResult,
    PluginMarketplaceRemoveCommand,
    PluginMarketplaceRemoveResult,
    PluginSetEnabledCommand,
    PluginSetEnabledResult,
    PluginSummary,
    PluginUninstallCommand,
    PluginUninstallResult,
    PongResult,
    ProviderCcswitchApplyCommand,
    ProviderCcswitchApplyResult,
    ProviderCcswitchListCommand,
    ProviderCcswitchListResult,
    ProviderStatusCommand,
    ProviderStatusResult,
    ReasoningEffort,
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
    SessionDeleteCommand,
    SessionDeleteResult,
    SessionForkCommand,
    SessionForkResult,
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
    SessionSteerMessageCommand,
    SessionSteerMessageResult,
    SessionSummary,
    SettingsGetCommand,
    SettingsGetResult,
    SettingsSnapshot,
    SettingsUpdateCommand,
    SettingsUpdateResult,
    SkillInstallCommand,
    SkillInstallResult,
    SkillListCommand,
    SkillListResult,
    SkillSetEnabledCommand,
    SkillSetEnabledResult,
    SkillSummary,
    UserQuestionPendingCommand,
    UserQuestionPendingResult,
    UserQuestionRespondCommand,
    UserQuestionRespondResult,
    WorkspaceArchiveCommand,
    WorkspaceArchiveResult,
    WorkspacePinCommand,
    WorkspacePinResult,
    WorkspaceDeleteCommand,
    WorkspaceDeleteResult,
    WorkspaceListCommand,
    WorkspaceListResult,
    WorkspaceOpenCommand,
    WorkspaceOpenResult,
    WorkspaceProfileCommand,
    WorkspaceProfileResult,
    WorkspaceResumeCommand,
    WorkspaceResumeResult,
    WorkspaceRenameCommand,
    WorkspaceRenameResult,
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
    manifest_file_diff,
    revert_manifest_changes,
)
from sztu_code.core.config import (
    SztuConfig,
    get_config,
    load_model_profiles,
    normalize_api_format,
    provider_for_api_format,
    save_client_settings,
)
from sztu_code.core.events.bus import EventBus
from sztu_code.core.interaction.user_questions import UserQuestionManager
from sztu_code.core.llm import create_provider
from sztu_code.core.llm.ccswitch import get_ccswitch_provider, list_ccswitch_providers
from sztu_code.core.logging_setup import setup_logging
from sztu_code.core.mcp.server import McpServerManager
from sztu_code.core.permissions.manager import PermissionManager
from sztu_code.core.permissions.policy import PermissionMode
from sztu_code.core.permissions.storage import load_policy_file
from sztu_code.core.plugins import Marketplace, MarketplaceManager, MarketplacePlugin
from sztu_code.core.run_store import RunStore
from sztu_code.core.runner import AgentRunner
from sztu_code.core.runs import events_file, new_run_id
from sztu_code.core.session import SessionManager, SessionStore
from sztu_code.core.session.manager import SESSION_BUSY
from sztu_code.core.session.model import Session
from sztu_code.core.skills.loader import Plugin, Skill, SkillLoader
from sztu_code.core.trace.record import TraceRecord
from sztu_code.core.trace.writer import TraceWriter
from sztu_code.core.transport.ipc_broadcaster import IpcEventBroadcaster
from sztu_code.core.transport.socket_server import SocketServer, get_connection_writer
from sztu_code.core.workspace import WorkspaceManager
from sztu_code.core.workspace.manager import Workspace

logger = logging.getLogger(__name__)

# opencode Zen 免费模型（免 key，OpenAI 兼容端点）内置 profile
_OPENCODE_ZEN_BASE_URL = "https://opencode.ai/zen/v1"
_OPENCODE_ZEN_FREE_MODELS: list[str] = [
    "deepseek-v4-flash-free",
    "ling-3.0-flash-free",
    "nemotron-3-ultra-free",
    "north-mini-code-free",
    "longcat-2.0-free",
    "mimo-v2.5-free",
    "laguna-s-2.1-free",
]
_OPENCODE_ZEN_PROFILES: list[dict[str, Any]] = [
    {
        "id": f"builtin-opencode-zen-{model}",
        "name": model,
        "vendor": "opencode",
        "provider": "openai",
        "model": model,
        "base_url": _OPENCODE_ZEN_BASE_URL,
        "api_key": "",
        "keyless": True,
        "builtin": True,
    }
    for model in _OPENCODE_ZEN_FREE_MODELS
]


def _now() -> str:
    return datetime.datetime.now(UTC).isoformat()


# 判断当前模型凭证是否可用；指定专用变量后不回退到其他供应商的通用密钥
def _llm_api_key_configured(config: SztuConfig, fallback_name: str) -> bool:
    if config.llm.keyless:
        return True  # 免 key 端点（如 opencode Zen）无需凭证
    if config.llm.api_key:
        return True
    if config.llm.api_key_env:
        return bool(os.environ.get(config.llm.api_key_env))
    return bool(os.environ.get(fallback_name))


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
        self._client_message_runs: dict[tuple[str, str], str] = {}
        self._active_session_runs: dict[str, asyncio.Task[str]] = {}
        self._run_store: RunStore | None = None
        self._sessions: SessionManager | None = None
        self._permission_manager: PermissionManager | None = None
        self._user_question_manager = UserQuestionManager(self._bus)
        self._mcp_manager: McpServerManager | None = None
        self._workspaces: WorkspaceManager | None = None

    # 将内部 Session 转换为稳定的 IPC 摘要模型
    @staticmethod
    def _session_summary(session: Session) -> SessionSummary:
        stats = list(session.run_stats.values())
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
            total_input_tokens=sum(item.input_tokens for item in stats),
            total_output_tokens=sum(item.output_tokens for item in stats),
            total_elapsed_s=sum(item.elapsed_s for item in stats),
        )

    # 将内部 Workspace 转换为客户端可渲染的稳定摘要
    @staticmethod
    def _workspace_summary(workspace: Workspace) -> WorkspaceSummary:
        return WorkspaceSummary(
            workspace_id=workspace.id,
            path=workspace.path,
            name=workspace.name,
            archived=workspace.archived,
            pinned=workspace.pinned,
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
            if self._run_store is not None:
                self._run_store.finish(run_id, status="cancelled", reason="cancelled")
            return
        try:
            task.result()
        except Exception:
            self._run_status[run_id] = "completed"
            logger.exception("run failed run_id=%s", run_id)
            if self._run_store is not None:
                self._run_store.finish(run_id, status="completed", reason="error")
        else:
            self._run_status[run_id] = "completed"
            if self._run_store is not None:
                self._run_store.finish(run_id, status="completed")

    # 处理 core.ping 请求，返回服务版本、运行时长和接收时间
    async def _ping_handler(self, params: dict[str, Any]) -> PongResult:
        client = params.get("client", "unknown")
        logger.debug("ping from %s", client)
        return PongResult(
            server_version=sztu_code.__version__,
            uptime_ms=int((time.monotonic() - self._start_time) * 1000),
            received_at=datetime.datetime.now(datetime.UTC).isoformat(),
            capabilities=[
                "plugin.lifecycle.v1",
                "plugin.marketplace.v1",
                "git.basic.v1",
            ],
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
        if self._run_store is not None:
            self._run_store.start(run_id, goal=cmd.goal, session_id=session.id)
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

    # Fork a persisted session through the session layer; Agent runtime remains unchanged.
    async def _session_fork_handler(self, params: dict[str, Any]) -> SessionForkResult:
        assert self._sessions is not None
        cmd = SessionForkCommand.model_validate(params)
        session = await self._sessions.fork(cmd.session_id, cmd.title)
        return SessionForkResult(session=self._session_summary(session))

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

    # 归档本地项目，保持会话数据完整但不再显示在活跃项目列表中
    async def _workspace_archive_handler(self, params: dict[str, Any]) -> WorkspaceArchiveResult:
        assert self._workspaces is not None
        cmd = WorkspaceArchiveCommand.model_validate(params)
        try:
            workspace = self._workspaces.archive(cmd.workspace_id)
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        return WorkspaceArchiveResult(workspace=self._workspace_summary(workspace))

    async def _workspace_pin_handler(self, params: dict[str, Any]) -> WorkspacePinResult:
        assert self._workspaces is not None
        cmd = WorkspacePinCommand.model_validate(params)
        try:
            workspace = self._workspaces.pin(cmd.workspace_id, cmd.pinned)
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        return WorkspacePinResult(workspace=self._workspace_summary(workspace))

    async def _workspace_rename_handler(self, params: dict[str, Any]) -> WorkspaceRenameResult:
        assert self._workspaces is not None
        cmd = WorkspaceRenameCommand.model_validate(params)
        try:
            workspace = self._workspaces.rename(cmd.workspace_id, cmd.name)
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        return WorkspaceRenameResult(workspace=self._workspace_summary(workspace))

    # 恢复已归档项目，使其重新出现在项目侧栏
    async def _workspace_resume_handler(self, params: dict[str, Any]) -> WorkspaceResumeResult:
        assert self._workspaces is not None
        cmd = WorkspaceResumeCommand.model_validate(params)
        try:
            workspace = self._workspaces.resume(cmd.workspace_id)
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        return WorkspaceResumeResult(workspace=self._workspace_summary(workspace))

    # 删除项目：校验 confirm 后删除绑定会话并从项目列表移除（保留磁盘文件）
    async def _workspace_delete_handler(self, params: dict[str, Any]) -> WorkspaceDeleteResult:
        assert self._workspaces is not None
        cmd = WorkspaceDeleteCommand.model_validate(params)
        if cmd.confirm != "delete":
            raise HandlerError(-32602, "workspace.delete requires confirm='delete'")
        if self._sessions is not None:
            sessions, _ = await self._sessions.list_sessions(include_archived=True)
            for session in sessions:
                if session.workspace_id == cmd.workspace_id:
                    await self._sessions.delete(session.id)
        try:
            self._workspaces.delete(cmd.workspace_id)
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        return WorkspaceDeleteResult(workspace_id=cmd.workspace_id)

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

    # 返回工作区离线检测出的结构化项目画像，refresh 仅重新读取磁盘而不执行建议命令
    async def _workspace_profile_handler(self, params: dict[str, Any]) -> WorkspaceProfileResult:
        assert self._workspaces is not None
        cmd = WorkspaceProfileCommand.model_validate(params)
        try:
            profile = self._workspaces.profile(cmd.workspace_id, refresh=cmd.refresh)
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        return WorkspaceProfileResult(profile=profile)

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

    # 返回工作区或单个文件的只读 Git diff，供客户端审阅器渲染；带 run_id 时优先基于
    # 该 run 的改动前快照生成 diff，使已提交/已回滚的改动仍可回看，无法生成时回退 Git diff
    async def _change_diff_handler(self, params: dict[str, Any]) -> ChangeDiffResult:
        assert self._workspaces is not None
        cmd = ChangeDiffCommand.model_validate(params)
        try:
            if cmd.run_id and cmd.path is not None:
                manifest_path = self._find_change_manifest(cmd.run_id)
                if manifest_path is not None:
                    workspace = self._workspaces.get(cmd.workspace_id)
                    snapshot_diff = manifest_file_diff(
                        manifest_path, Path(workspace.path), cmd.path
                    )
                    if snapshot_diff is not None:
                        return ChangeDiffResult(diff=snapshot_diff)
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

    # 将指定文件加入 git 暂存区（审核"接受"）
    async def _change_stage_handler(self, params: dict[str, Any]) -> ChangeStageResult:
        assert self._workspaces is not None
        cmd = ChangeStageCommand.model_validate(params)
        try:
            staged = self._workspaces.stage(cmd.workspace_id, cmd.paths)
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        return ChangeStageResult(staged_paths=staged)

    async def _change_unstage_handler(self, params: dict[str, Any]) -> ChangeUnstageResult:
        assert self._workspaces is not None
        cmd = ChangeUnstageCommand.model_validate(params)
        try:
            paths = self._workspaces.unstage(cmd.workspace_id, cmd.paths)
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        return ChangeUnstageResult(unstaged_paths=paths)

    async def _change_discard_handler(self, params: dict[str, Any]) -> ChangeDiscardResult:
        assert self._workspaces is not None
        cmd = ChangeDiscardCommand.model_validate(params)
        try:
            paths = self._workspaces.discard(cmd.workspace_id, cmd.paths)
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        return ChangeDiscardResult(discarded_paths=paths)

    async def _git_commit_handler(self, params: dict[str, Any]) -> GitCommitResult:
        assert self._workspaces is not None
        cmd = GitCommitCommand.model_validate(params)
        try:
            commit_hash = self._workspaces.commit(cmd.workspace_id, cmd.message.strip())
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        return GitCommitResult(commit_hash=commit_hash)

    async def _git_history_handler(self, params: dict[str, Any]) -> GitHistoryResult:
        assert self._workspaces is not None
        cmd = GitHistoryCommand.model_validate(params)
        try:
            page = self._workspaces.history(cmd.workspace_id, cmd.limit + 1, cmd.skip)
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        return GitHistoryResult(
            commits=page[:cmd.limit],
            has_more=len(page) > cmd.limit,
        )

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
        valid = [
            change
            for change in changes
            if isinstance(change, dict) and isinstance(change.get("path"), str)
        ]
        paths = [str(change["path"]) for change in valid]
        numstat = self._workspaces.diff_numstat(workspace_id, paths) if paths else {}
        return [
            ChangeSummary(
                path=str(change.get("path", "")),
                index_status=" ",
                worktree_status="M",
                run_id=run_id,
                agent_owned=True,
                revertible=bool(change.get("revertible", False)),
                additions=numstat.get(str(change.get("path", "")), (0, 0))[0],
                deletions=numstat.get(str(change.get("path", "")), (0, 0))[1],
            )
            for change in valid
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
        if cmd.client_message_id:
            existing_run_id = self._client_message_runs.get(
                (cmd.session_id, cmd.client_message_id)
            )
            if existing_run_id is not None:
                return SessionSendMessageResult(run_id=existing_run_id)
        active_run = self._active_session_runs.get(cmd.session_id)
        if active_run is not None and not active_run.done():
            try:
                await asyncio.wait_for(asyncio.shield(active_run), timeout=0.1)
            except TimeoutError as error:
                raise HandlerError(SESSION_BUSY, "session busy") from error
            except asyncio.CancelledError:
                # 被用户停止的上一轮同样已结束，可继续接受排队消息
                if not active_run.cancelled():
                    raise
            except Exception:
                # 上一轮失败也已经完成清理，不应阻止排队的下一轮启动
                pass
        run_id = new_run_id()
        if self._run_store is not None:
            self._run_store.start(run_id, goal=cmd.content, session_id=cmd.session_id)
        if cmd.client_message_id:
            self._client_message_runs[(cmd.session_id, cmd.client_message_id)] = run_id
        run_task = asyncio.create_task(
            self._sessions.send_message(
                cmd.session_id,
                cmd.content,
                run_id=run_id,
                images=[image.model_dump() for image in cmd.images],
            )
        )
        self._active_session_runs[cmd.session_id] = run_task
        self._track_run(run_id, run_task)
        run_task.add_done_callback(partial(self._on_session_run_finished, cmd.session_id))
        return SessionSendMessageResult(run_id=run_id)

    # 将追加消息投递给运行中会话的 steer 收件箱
    async def _session_steer_handler(self, params: dict[str, Any]) -> SessionSteerMessageResult:
        assert self._sessions is not None
        cmd = SessionSteerMessageCommand.model_validate(params)
        run_id = await self._sessions.steer_message(
            cmd.session_id,
            cmd.content,
            images=[image.model_dump() for image in cmd.images],
        )
        return SessionSteerMessageResult(run_id=run_id)

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
        # 优先内存中的活动状态；重启后回退到持久化 RunStore，避免误报 unknown
        status: str | None = self._run_status.get(cmd.run_id)
        if status is None and self._run_store is not None:
            record = self._run_store.get(cmd.run_id)
            status = record.status if record is not None else None
        if status is None:
            status = "unknown"
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
        return SessionGetHistoryResult(
            messages=messages,
            run_stats=self._sessions.get_run_stats(cmd.session_id),
            context_injections=self._sessions.get_context_injections(cmd.session_id),
        )

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
        self._permission_manager.respond(
            cmd.tool_use_id,
            cmd.decision,
            cmd.run_id,
            cmd.session_id,
        )
        return PermissionRespondResult()

    # 接收结构化问题回答，校验后恢复 ask_user_question 所在的工具调用
    async def _user_question_respond_handler(
        self, params: dict[str, Any]
    ) -> UserQuestionRespondResult:
        cmd = UserQuestionRespondCommand.model_validate(params)
        try:
            await self._user_question_manager.respond(
                rpc_id=cmd.rpc_id,
                session_id=cmd.session_id,
                answers=cmd.answers,
            )
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        return UserQuestionRespondResult()

    # 返回 daemon 内仍在等待回答的问题，供客户端刷新或重连后恢复输入接管态
    async def _user_question_pending_handler(
        self, params: dict[str, Any]
    ) -> UserQuestionPendingResult:
        cmd = UserQuestionPendingCommand.model_validate(params)
        return UserQuestionPendingResult(
            pending=self._user_question_manager.list_pending(cmd.session_id)
        )

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
            api_format=self._config.llm.api_format,  # type: ignore[arg-type]
            model=self._config.llm.default_model,
            router=self._config.llm.router,
            permission_mode=self._permission_manager.get_mode().value,
            base_url=self._config.llm.base_url,
            context_window=self._config.llm.context_window,
            max_output_tokens=self._config.llm.max_output_tokens,
            temperature=self._config.llm.temperature,
            top_p=self._config.llm.top_p,
            reasoning_effort=self._config.llm.reasoning_effort,  # type: ignore[arg-type]
            timeout_s=self._config.llm.timeout_s,
            max_retries=self._config.llm.max_retries,
            cache_control=self._config.llm.cache_control,
        )

    def _model_profile_summaries(
        self, profiles: list[dict[str, Any]], active_id: str
    ) -> list[ModelProfileSummary]:
        return [
            ModelProfileSummary(
                id=str(item.get("id", "")),
                name=str(item.get("name", "")),
                vendor=str(item.get("vendor", "")),
                provider=item.get("provider", "anthropic"),
                api_format=cast(
                    ApiFormat,
                    normalize_api_format(item.get("api_format"), item.get("provider")),
                ),
                model=str(item.get("model", "")),
                base_url=str(item.get("base_url", "")),
                has_api_key=bool(
                    item.get("keyless")
                    or item.get("api_key")
                    or os.environ.get(str(item.get("api_key_env", "")))
                ),
                is_current=str(item.get("id", "")) == active_id,
                builtin=bool(item.get("builtin")),
                context_window=int(item.get("context_window", 0) or 0),
                max_output_tokens=int(item.get("max_output_tokens", 8192) or 8192),
                temperature=item.get("temperature"),
                top_p=item.get("top_p"),
                reasoning_effort=cast(ReasoningEffort, str(item.get("reasoning_effort", ""))),
                timeout_s=float(item.get("timeout_s", 120) or 120),
                max_retries=int(item.get("max_retries", 2) or 0),
                cache_control=bool(item.get("cache_control", True)),
            )
            for item in profiles
            if item.get("id") and item.get("name") and item.get("model")
        ]

    def _stored_model_profiles(self) -> tuple[list[dict[str, Any]], str]:
        assert self._config is not None
        profiles, active_id = load_model_profiles()
        if not profiles and self._config.llm.default_model.strip():
            active_id = "default"
            profiles = [
                {
                    "id": active_id,
                    "name": self._config.llm.default_model,
                    "vendor": self._config.llm.provider.title(),
                    "provider": self._config.llm.provider,
                    "api_format": self._config.llm.api_format,
                    "model": self._config.llm.default_model,
                    "base_url": self._config.llm.base_url,
                    "api_key": self._config.llm.api_key,
                }
            ]
        # 过滤掉所有内置 profile，再统一追加，保证定义唯一
        builtin_ids = {p["id"] for p in _OPENCODE_ZEN_PROFILES}
        profiles = [item for item in profiles if item.get("id") not in builtin_ids]
        profiles.extend(dict(p) for p in _OPENCODE_ZEN_PROFILES)
        return profiles, active_id

    def _activate_model_profile(self, profile: dict[str, Any]) -> None:
        assert self._config is not None
        self._config.llm.provider = str(profile["provider"])
        self._config.llm.api_format = normalize_api_format(
            profile.get("api_format"), profile.get("provider")
        )
        self._config.llm.provider = provider_for_api_format(self._config.llm.api_format)
        self._config.llm.default_model = str(profile["model"])
        self._config.llm.base_url = str(profile.get("base_url", ""))
        self._config.llm.api_key = str(profile.get("api_key", ""))
        self._config.llm.api_key_env = str(profile.get("api_key_env", ""))
        self._config.llm.keyless = bool(profile.get("keyless"))
        for name, default in (
            ("context_window", 0),
            ("max_output_tokens", 8192),
            ("max_retries", 2),
        ):
            raw_value = profile.get(name, default)
            setattr(self._config.llm, name, int(default if raw_value is None else raw_value))
        for float_name, float_default in (
            ("temperature", None),
            ("top_p", None),
            ("timeout_s", 120.0),
        ):
            float_value = profile.get(float_name, float_default)
            resolved = float(float_value) if float_value is not None else float_default
            setattr(
                self._config.llm,
                float_name,
                None if resolved is None else float(resolved),
            )
        self._config.llm.reasoning_effort = str(profile.get("reasoning_effort", ""))
        self._config.llm.cache_control = bool(profile.get("cache_control", True))
        if self._sessions is not None:
            key_name = (
                "OPENAI_API_KEY"
                if self._config.llm.provider == "openai"
                else "ANTHROPIC_API_KEY"
            )

    # 使用极小请求探测配置的端点、凭证和模型是否可用，不写入当前运行配置
            has_key = _llm_api_key_configured(self._config, key_name)
            self._sessions.set_provider(
                create_provider(self._config)
                if has_key and self._config.llm.default_model.strip()
                else None
            )

    async def _probe_model(self, cmd: ModelTestCommand) -> ModelTestResult:
        started = time.perf_counter()
        base_url = cmd.base_url.rstrip("/")
        if not base_url:
            base_url = (
                "https://api.anthropic.com/v1"
                if cmd.api_format == "anthropic_messages"
                else "https://api.openai.com/v1"
            )
        headers: dict[str, str] = {"content-type": "application/json"}
        if not cmd.keyless and cmd.api_key:
            if cmd.api_format == "anthropic_messages":
                headers["x-api-key"] = cmd.api_key
                headers["anthropic-version"] = "2023-06-01"
            else:
                headers["authorization"] = f"Bearer {cmd.api_key}"
        if cmd.api_format == "anthropic_messages":
            url = f"{base_url}/messages"
            body: dict[str, Any] = {
                "model": cmd.model,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "Reply OK."}],
            }
        elif cmd.api_format == "openai_responses":
            url = f"{base_url}/responses"
            body = {"model": cmd.model, "input": "Reply OK.", "max_output_tokens": 1}
        else:
            url = f"{base_url}/chat/completions"
            body = {
                "model": cmd.model,
                "messages": [{"role": "user", "content": "Reply OK."}],
                "max_completion_tokens": 1,
            }
        try:
            async with httpx.AsyncClient(timeout=cmd.timeout_s, trust_env=False) as client:
                response = await client.post(url, headers=headers, json=body)
                response.raise_for_status()
                usage = response.json().get("usage") or {}
            elapsed = (time.perf_counter() - started) * 1000
            return ModelTestResult(
                success=True,
                api_format=cmd.api_format,
                model=cmd.model,
                elapsed_ms=elapsed,
                input_tokens=int(
                    usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0
                ),
                output_tokens=int(
                    usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0
                ),
            )
        except (httpx.HTTPError, ValueError) as error:
            return ModelTestResult(
                success=False,
                api_format=cmd.api_format,
                model=cmd.model,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                error=str(error),
            )

    # 重复运行端点探测并汇总延迟，供模型管理页比较可用性与稳定性
    # 接收单次连通性测试请求并返回可展示的耗时、用量或错误信息
    async def _model_benchmark_handler(self, params: dict[str, Any]) -> ModelBenchmarkResult:
        cmd = ModelBenchmarkCommand.model_validate(params)
        results = [
            await self._probe_model(ModelTestCommand.model_validate(cmd.model_dump()))
            for _ in range(cmd.samples)
        ]
        latencies = sorted(result.elapsed_ms for result in results if result.success)
        errors = [result.error for result in results if result.error]
        index = min(len(latencies) - 1, round((len(latencies) - 1) * .95)) if latencies else 0
        return ModelBenchmarkResult(
            api_format=cmd.api_format,
            model=cmd.model,
            samples=cmd.samples,
            successful=len(latencies),
            failed=cmd.samples - len(latencies),
            min_ms=min(latencies) if latencies else None,
            median_ms=statistics.median(latencies) if latencies else None,
            p95_ms=latencies[index] if latencies else None,
            max_ms=max(latencies) if latencies else None,
            errors=errors,
        )

    async def _model_test_handler(self, params: dict[str, Any]) -> ModelTestResult:
        return await self._probe_model(ModelTestCommand.model_validate(params))
    async def _settings_get_handler(self, params: dict[str, Any]) -> SettingsGetResult:
        SettingsGetCommand.model_validate(params)
        return SettingsGetResult(settings=self._settings_snapshot())

    async def _settings_update_handler(self, params: dict[str, Any]) -> SettingsUpdateResult:
        assert self._config is not None
        assert self._permission_manager is not None
        cmd = SettingsUpdateCommand.model_validate(params)
        updated: list[str] = []
        if cmd.provider is not None and cmd.provider != self._config.llm.provider:
            self._config.llm.provider = cmd.provider
            self._config.llm.api_format = normalize_api_format(None, cmd.provider)
            updated.append("provider")
        if cmd.api_format is not None and cmd.api_format != self._config.llm.api_format:
            self._config.llm.api_format = cmd.api_format
            self._config.llm.provider = provider_for_api_format(cmd.api_format)
            updated.append("api_format")
        if cmd.model is not None and cmd.model != self._config.llm.default_model:
            self._config.llm.default_model = cmd.model
            updated.append("model")
        if cmd.base_url is not None and cmd.base_url != self._config.llm.base_url:
            self._config.llm.base_url = cmd.base_url
            updated.append("base_url")
        if any(field in updated for field in ("provider", "model", "base_url")):
            self._config.llm.api_key_env = ""
            self._config.llm.keyless = False  # 手动改端点不再假定免 key
        if cmd.api_key is not None and cmd.api_key != self._config.llm.api_key:
            self._config.llm.api_key = cmd.api_key
            self._config.llm.api_key_env = ""
            updated.append("api_key")
        for name in (
            "max_output_tokens",
            "temperature",
            "top_p",
            "reasoning_effort",
            "timeout_s",
            "max_retries",
            "context_window",
            "cache_control",
        ):
            value = getattr(cmd, name)
            if value is not None and value != getattr(self._config.llm, name):
                setattr(self._config.llm, name, value)
                updated.append(name)
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
            profiles, active_id = self._stored_model_profiles()
            if any(
                field in updated
                for field in (
                    "provider",
                    "api_format",
                    "model",
                    "base_url",
                    "api_key",
                    "max_output_tokens",
                    "temperature",
                    "top_p",
                    "reasoning_effort",
                    "timeout_s",
                    "max_retries",
                    "context_window",
                    "cache_control",
                )
            ):
                current = next(
                    (item for item in profiles if item.get("id") == active_id), None
                )
                if current is None:
                    active_id = uuid.uuid4().hex
                    current = {"id": active_id}
                    profiles.append(current)
                current.update(
                    {
                        "name": self._config.llm.default_model,
                        "vendor": self._config.llm.provider.title(),
                        "provider": self._config.llm.provider,
                        "api_format": self._config.llm.api_format,
                        "model": self._config.llm.default_model,
                        "base_url": self._config.llm.base_url,
                        "api_key": self._config.llm.api_key,
                        "max_output_tokens": self._config.llm.max_output_tokens,
                        "temperature": self._config.llm.temperature,
                        "top_p": self._config.llm.top_p,
                        "reasoning_effort": self._config.llm.reasoning_effort,
                        "timeout_s": self._config.llm.timeout_s,
                        "max_retries": self._config.llm.max_retries,
                        "context_window": self._config.llm.context_window,
                        "cache_control": self._config.llm.cache_control,
                    }
                )
            save_client_settings(
                self._config,
                models=profiles,
                active_model_id=active_id,
            )
        if self._sessions is not None and any(
            field in updated
            for field in (
                "provider",
                "api_format",
                "model",
                "base_url",
                "api_key",
                "max_output_tokens",
                "temperature",
                "top_p",
                "reasoning_effort",
                "timeout_s",
                "max_retries",
                "context_window",
                "cache_control",
            )
        ):
            key_name = (
                "OPENAI_API_KEY"
                if self._config.llm.provider == "openai"
                else "ANTHROPIC_API_KEY"
            )
            credential_configured = _llm_api_key_configured(self._config, key_name)
            provider = (
                create_provider(self._config)
                if credential_configured and self._config.llm.default_model.strip()
                else None
            )
            self._sessions.set_provider(provider)
        return SettingsUpdateResult(settings=self._settings_snapshot(), updated=updated)

    # 为可选工作区创建技能加载器，确保目录扫描不依赖 daemon 启动目录
    def _skill_loader_for_workspace(self, workspace_id: str | None) -> SkillLoader:
        if workspace_id is None:
            return SkillLoader()
        if self._workspaces is None:
            raise ValueError("workspace manager is not initialized")
        workspace = self._workspaces.get(workspace_id)
        return SkillLoader(project_root=Path(workspace.path))

    # 将内部技能对象转换为稳定且可校验的目录协议模型
    @staticmethod
    def _skill_summary(skill: Skill) -> SkillSummary:
        return SkillSummary(
            id=skill.id,
            name=skill.name,
            display_name=skill.display_name or skill.name,
            description=skill.description[:600],
            short_description=(skill.short_description or skill.description)[:240],
            source=skill.source,
            scope=skill.scope,
            path=str(skill.path or ""),
            plugin=skill.plugin,
            enabled=skill.enabled,
            icon=skill.icon,
            brand_color=skill.brand_color,
            allow_implicit_invocation=skill.allow_implicit_invocation,
        )

    # 将内部插件对象转换为桌面端使用的插件摘要
    @staticmethod
    def _plugin_summary(plugin: Plugin) -> PluginSummary:
        return PluginSummary(
            id=plugin.id,
            name=plugin.name,
            description=plugin.description[:600],
            version=plugin.version,
            source=plugin.source,
            path=str(plugin.path),
            skills=list(plugin.skills),
            installed=True,
            display_name=plugin.display_name or plugin.name,
            brand_color=plugin.brand_color,
            enabled=plugin.enabled,
        )

    # 将官方兼容市场源转换为运行时协议摘要
    @staticmethod
    def _marketplace_summary(marketplace: Marketplace) -> MarketplaceSummary:
        return MarketplaceSummary(
            id=marketplace.id,
            name=marketplace.name,
            display_name=marketplace.display_name,
            source=marketplace.source,
            kind=marketplace.kind,
            root_path=str(marketplace.root_path),
            ref=marketplace.ref,
            sparse_paths=list(marketplace.sparse_paths),
            plugin_count=marketplace.plugin_count,
            updated_at=marketplace.updated_at,
            removable=marketplace.removable,
            updatable=marketplace.updatable,
        )

    # 将市场插件条目与当前安装状态合并为目录摘要
    @staticmethod
    def _marketplace_plugin_summary(
        plugin: MarketplacePlugin,
        installed: dict[str, Plugin],
    ) -> MarketplacePluginSummary:
        current = installed.get(plugin.name)
        return MarketplacePluginSummary(
            id=plugin.id,
            marketplace_id=plugin.marketplace_id,
            marketplace_name=plugin.marketplace_name,
            name=plugin.name,
            display_name=plugin.display_name,
            description=plugin.description[:600],
            version=plugin.version,
            category=plugin.category,
            publisher=plugin.publisher,
            installation=plugin.installation,
            authentication=plugin.authentication,
            installed=current is not None,
            installed_plugin_id=current.id if current is not None else None,
        )

    # 为可选工作区创建插件市场管理器
    def _marketplace_manager_for_workspace(
        self, workspace_id: str | None
    ) -> MarketplaceManager:
        if workspace_id is None:
            return MarketplaceManager()
        if self._workspaces is None:
            raise ValueError("workspace manager is not initialized")
        workspace = self._workspaces.get(workspace_id)
        return MarketplaceManager(project_root=Path(workspace.path))

    # 返回工作区感知的完整技能目录，包括被禁用但仍已安装的条目
    async def _skill_list_handler(self, params: dict[str, Any]) -> SkillListResult:
        cmd = SkillListCommand.model_validate(params)
        try:
            loader = self._skill_loader_for_workspace(cmd.workspace_id)
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        return SkillListResult(
            skills=[
                self._skill_summary(skill)
                for skill in loader.list_all_skills(include_disabled=True)
            ]
        )

    # 将用户选择的本地技能复制到个人或当前工作区目录
    async def _skill_install_handler(self, params: dict[str, Any]) -> SkillInstallResult:
        cmd = SkillInstallCommand.model_validate(params)
        if cmd.scope == "workspace" and cmd.workspace_id is None:
            raise HandlerError(-32602, "workspace scope requires workspace_id")
        try:
            loader = self._skill_loader_for_workspace(cmd.workspace_id)
            skill = loader.install_skill(Path(cmd.source_path), cmd.scope)
        except (OSError, ValueError) as error:
            raise HandlerError(-32602, str(error)) from error
        return SkillInstallResult(skill=self._skill_summary(skill))

    # 持久化技能启停状态，禁用不会删除安装内容
    async def _skill_set_enabled_handler(
        self, params: dict[str, Any]
    ) -> SkillSetEnabledResult:
        cmd = SkillSetEnabledCommand.model_validate(params)
        try:
            loader = self._skill_loader_for_workspace(cmd.workspace_id)
            skill = loader.set_enabled(cmd.skill_id, cmd.enabled)
        except (OSError, ValueError) as error:
            raise HandlerError(-32602, str(error)) from error
        return SkillSetEnabledResult(skill=self._skill_summary(skill))

    # 返回个人和当前工作区已安装的插件及其所含技能
    async def _plugin_list_handler(self, params: dict[str, Any]) -> PluginListResult:
        cmd = PluginListCommand.model_validate(params)
        try:
            loader = self._skill_loader_for_workspace(cmd.workspace_id)
        except ValueError as error:
            raise HandlerError(-32602, str(error)) from error
        return PluginListResult(
            plugins=[self._plugin_summary(plugin) for plugin in loader.list_plugins()]
        )

    # 将本地 Codex 兼容插件复制到个人或当前工作区插件目录
    async def _plugin_install_handler(
        self, params: dict[str, Any]
    ) -> PluginInstallResult:
        cmd = PluginInstallCommand.model_validate(params)
        if cmd.scope == "workspace" and cmd.workspace_id is None:
            raise HandlerError(-32602, "workspace scope requires workspace_id")
        try:
            loader = self._skill_loader_for_workspace(cmd.workspace_id)
            plugin = loader.install_plugin(Path(cmd.source_path), cmd.scope)
        except (OSError, ValueError) as error:
            raise HandlerError(-32602, str(error)) from error
        return PluginInstallResult(plugin=self._plugin_summary(plugin))

    # 返回官方兼容市场源和可安装插件目录
    async def _plugin_catalog_handler(self, params: dict[str, Any]) -> PluginCatalogResult:
        cmd = PluginCatalogCommand.model_validate(params)
        try:
            loader = self._skill_loader_for_workspace(cmd.workspace_id)
            manager = self._marketplace_manager_for_workspace(cmd.workspace_id)
            installed = {plugin.name: plugin for plugin in loader.list_plugins()}
            return PluginCatalogResult(
                marketplaces=[
                    self._marketplace_summary(marketplace)
                    for marketplace in manager.list_marketplaces()
                ],
                plugins=[
                    self._marketplace_plugin_summary(plugin, installed)
                    for plugin in manager.list_plugins()
                ],
            )
        except (OSError, ValueError) as error:
            raise HandlerError(-32602, str(error)) from error

    # 添加 GitHub、Git URL 或本地目录插件市场
    async def _plugin_marketplace_add_handler(
        self, params: dict[str, Any]
    ) -> PluginMarketplaceAddResult:
        cmd = PluginMarketplaceAddCommand.model_validate(params)
        try:
            manager = self._marketplace_manager_for_workspace(cmd.workspace_id)
            marketplace = manager.add(
                cmd.source,
                ref=cmd.git_ref,
                sparse_paths=cmd.sparse_paths,
            )
        except (OSError, ValueError) as error:
            raise HandlerError(-32602, str(error)) from error
        return PluginMarketplaceAddResult(
            marketplace=self._marketplace_summary(marketplace)
        )

    # 刷新一个或全部 Git 插件市场快照
    async def _plugin_marketplace_refresh_handler(
        self, params: dict[str, Any]
    ) -> PluginMarketplaceRefreshResult:
        cmd = PluginMarketplaceRefreshCommand.model_validate(params)
        try:
            manager = self._marketplace_manager_for_workspace(cmd.workspace_id)
            marketplaces = manager.refresh(cmd.marketplace_id)
        except (OSError, ValueError) as error:
            raise HandlerError(-32602, str(error)) from error
        return PluginMarketplaceRefreshResult(
            marketplaces=[self._marketplace_summary(item) for item in marketplaces]
        )

    # 移除显式配置的市场源，默认市场不可移除
    async def _plugin_marketplace_remove_handler(
        self, params: dict[str, Any]
    ) -> PluginMarketplaceRemoveResult:
        cmd = PluginMarketplaceRemoveCommand.model_validate(params)
        try:
            manager = self._marketplace_manager_for_workspace(cmd.workspace_id)
            manager.remove(cmd.marketplace_id)
        except (OSError, ValueError) as error:
            raise HandlerError(-32602, str(error)) from error
        return PluginMarketplaceRemoveResult(marketplace_id=cmd.marketplace_id)

    # 从市场条目安装插件，并在完成后清理远程临时快照
    async def _plugin_catalog_install_handler(
        self, params: dict[str, Any]
    ) -> PluginCatalogInstallResult:
        cmd = PluginCatalogInstallCommand.model_validate(params)
        if cmd.scope == "workspace" and cmd.workspace_id is None:
            raise HandlerError(-32602, "workspace scope requires workspace_id")
        materialized = None
        try:
            loader = self._skill_loader_for_workspace(cmd.workspace_id)
            manager = self._marketplace_manager_for_workspace(cmd.workspace_id)
            catalog_plugin = next(
                (
                    item
                    for item in manager.list_plugins()
                    if item.id == cmd.catalog_plugin_id
                ),
                None,
            )
            if catalog_plugin is None:
                raise ValueError(f"marketplace plugin not found: {cmd.catalog_plugin_id}")
            materialized = manager.materialize_plugin(catalog_plugin.id)
            plugin = loader.install_plugin(
                materialized.path,
                cmd.scope,
                install_name=catalog_plugin.name,
            )
        except (OSError, ValueError) as error:
            raise HandlerError(-32602, str(error)) from error
        finally:
            if materialized is not None:
                manager.cleanup_materialized(materialized)
        return PluginCatalogInstallResult(plugin=self._plugin_summary(plugin))

    # 启用或禁用已安装插件及其捆绑技能
    async def _plugin_set_enabled_handler(
        self, params: dict[str, Any]
    ) -> PluginSetEnabledResult:
        cmd = PluginSetEnabledCommand.model_validate(params)
        try:
            loader = self._skill_loader_for_workspace(cmd.workspace_id)
            plugin = loader.set_plugin_enabled(cmd.plugin_id, cmd.enabled)
        except (OSError, ValueError) as error:
            raise HandlerError(-32602, str(error)) from error
        return PluginSetEnabledResult(plugin=self._plugin_summary(plugin))

    # 卸载用户明确选择的个人或工作区插件
    async def _plugin_uninstall_handler(
        self, params: dict[str, Any]
    ) -> PluginUninstallResult:
        cmd = PluginUninstallCommand.model_validate(params)
        try:
            loader = self._skill_loader_for_workspace(cmd.workspace_id)
            loader.uninstall_plugin(cmd.plugin_id)
        except (OSError, ValueError) as error:
            raise HandlerError(-32602, str(error)) from error
        return PluginUninstallResult(plugin_id=cmd.plugin_id)

    # 返回模型连接状态及兼容旧客户端的默认工作区技能摘要
    async def _provider_status_handler(self, params: dict[str, Any]) -> ProviderStatusResult:
        assert self._config is not None
        ProviderStatusCommand.model_validate(params)
        provider = self._config.llm.provider
        api_key_name = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
        endpoint_name = "OPENAI_BASE_URL" if provider == "openai" else "ANTHROPIC_BASE_URL"
        skills = [
            self._skill_summary(skill)
            for skill in SkillLoader().list_all_skills(include_disabled=True)
        ]
        mcp_servers = (
            self._mcp_manager.statuses(self._config.mcp.servers)
            if self._mcp_manager is not None
            else []
        )
        api_key_configured = _llm_api_key_configured(self._config, api_key_name)
        custom_endpoint_configured = bool(
            self._config.llm.base_url or os.environ.get(endpoint_name)
        )
        return ProviderStatusResult(
            provider=provider,  # type: ignore[arg-type]
            api_format=self._config.llm.api_format,  # type: ignore[arg-type]
            model=self._config.llm.default_model,
            api_key_configured=api_key_configured,
            custom_endpoint_configured=custom_endpoint_configured,
            ready_for_next_run=bool(
                api_key_configured and self._config.llm.default_model.strip()
            ),
            mcp_servers=mcp_servers,
            skills=skills,
        )

    # 返回本机 cc-switch 中可导入的 Anthropic 兼容供应商（掩码凭证）
    async def _provider_ccswitch_list_handler(
        self, params: dict[str, Any]
    ) -> ProviderCcswitchListResult:
        ProviderCcswitchListCommand.model_validate(params)
        return ProviderCcswitchListResult(
            providers=[
                CcswitchProviderSummary(
                    id=item.id,
                    name=item.name,
                    base_url=item.base_url,
                    model=item.model,
                    has_api_key=bool(item.api_key),
                    is_current=item.is_current,
                )
                for item in list_ccswitch_providers()
            ]
        )

    # 将选中的 cc-switch 供应商应用到当前配置并重建 provider
    async def _provider_ccswitch_apply_handler(
        self, params: dict[str, Any]
    ) -> ProviderCcswitchApplyResult:
        assert self._config is not None
        cmd = ProviderCcswitchApplyCommand.model_validate(params)
        provider = get_ccswitch_provider(cmd.provider_id)
        if provider is None:
            raise HandlerError(-32602, f"cc-switch provider not found: {cmd.provider_id}")
        profiles, _ = self._stored_model_profiles()
        self._config.llm.provider = "anthropic"
        self._config.llm.api_format = "anthropic_messages"
        self._config.llm.default_model = provider.model
        self._config.llm.base_url = provider.base_url
        self._config.llm.api_key = provider.api_key
        self._config.llm.api_key_env = ""
        profile_id = f"ccswitch-{provider.id}"
        current = next(
            (item for item in profiles if item.get("id") == profile_id), None
        )
        if current is None:
            current = {"id": profile_id}
            profiles.append(current)
        current.update(
            {
                "name": provider.name,
                "vendor": "cc-switch",
                "provider": "anthropic",
                "api_format": "anthropic_messages",
                "model": provider.model,
                "base_url": provider.base_url,
                "api_key": provider.api_key,
            }
        )
        save_client_settings(
            self._config, models=profiles, active_model_id=profile_id
        )
        if self._sessions is not None:
            self._sessions.set_provider(create_provider(self._config))
        return ProviderCcswitchApplyResult(
            settings=self._settings_snapshot(), updated=["provider", "model", "base_url"]
        )

    async def _model_profile_list_handler(
        self, params: dict[str, Any]
    ) -> ModelProfileListResult:
        ModelProfileListCommand.model_validate(params)
        profiles, active_id = self._stored_model_profiles()
        return ModelProfileListResult(
            models=self._model_profile_summaries(profiles, active_id)
        )

    async def _model_profile_save_handler(
        self, params: dict[str, Any]
    ) -> ModelProfileSaveResult:
        assert self._config is not None
        cmd = ModelProfileSaveCommand.model_validate(params)
        profiles, active_id = self._stored_model_profiles()
        profile_id = cmd.id or uuid.uuid4().hex
        current = next(
            (item for item in profiles if item.get("id") == profile_id), None
        )
        if current is None:
            current = {"id": profile_id}
            profiles.append(current)
        current.update(
            {
                "name": cmd.name,
                "vendor": cmd.vendor,
                "provider": provider_for_api_format(cmd.api_format),
                "api_format": cmd.api_format,
                "model": cmd.model,
                "base_url": cmd.base_url,
                "keyless": cmd.keyless,
                "api_key_env": "",
                "builtin": False,
                "context_window": cmd.context_window,
                "max_output_tokens": cmd.max_output_tokens,
                "temperature": cmd.temperature,
                "top_p": cmd.top_p,
                "reasoning_effort": cmd.reasoning_effort,
                "timeout_s": cmd.timeout_s,
                "max_retries": cmd.max_retries,
                "cache_control": cmd.cache_control,
            }
        )
        if cmd.api_key is not None:
            current["api_key"] = cmd.api_key
        else:
            current.setdefault("api_key", "")
        active_id = profile_id
        self._activate_model_profile(current)
        save_client_settings(
            self._config, models=profiles, active_model_id=active_id
        )
        return ModelProfileSaveResult(
            settings=self._settings_snapshot(),
            models=self._model_profile_summaries(profiles, active_id),
        )

    async def _model_profile_select_handler(
        self, params: dict[str, Any]
    ) -> ModelProfileSelectResult:
        assert self._config is not None
        cmd = ModelProfileSelectCommand.model_validate(params)
        profiles, _ = self._stored_model_profiles()
        profile = next(
            (item for item in profiles if item.get("id") == cmd.model_id), None
        )
        if profile is None:
            raise HandlerError(-32602, f"model profile not found: {cmd.model_id}")
        self._activate_model_profile(profile)
        save_client_settings(
            self._config, models=profiles, active_model_id=cmd.model_id
        )
        return ModelProfileSelectResult(
            settings=self._settings_snapshot(),
            models=self._model_profile_summaries(profiles, cmd.model_id),
        )

    async def _model_profile_delete_handler(
        self, params: dict[str, Any]
    ) -> ModelProfileDeleteResult:
        assert self._config is not None
        cmd = ModelProfileDeleteCommand.model_validate(params)
        profiles, active_id = self._stored_model_profiles()
        profile = next(
            (item for item in profiles if item.get("id") == cmd.model_id), None
        )
        if profile is not None and profile.get("builtin"):
            raise HandlerError(-32602, "cannot delete a built-in model profile")
        if cmd.model_id == active_id:
            raise HandlerError(-32602, "cannot delete the current model profile")
        next_profiles = [
            item for item in profiles if item.get("id") != cmd.model_id
        ]
        if len(next_profiles) == len(profiles):
            raise HandlerError(-32602, f"model profile not found: {cmd.model_id}")
        save_client_settings(
            self._config, models=next_profiles, active_model_id=active_id
        )
        return ModelProfileDeleteResult(
            models=self._model_profile_summaries(next_profiles, active_id)
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

    async def _session_delete_handler(self, params: dict[str, Any]) -> SessionDeleteResult:
        assert self._sessions is not None
        cmd = SessionDeleteCommand.model_validate(params)
        await self._sessions.delete(cmd.session_id)
        return SessionDeleteResult(session_id=cmd.session_id, deleted=True)

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
        # 写入自身 pid，保证 core stop 能正确定位真实 daemon（uv 包装进程的 pid 不可靠）
        _pid_file = Path("~/.sztu/sztu-code.pid").expanduser()
        _pid_file.parent.mkdir(parents=True, exist_ok=True)
        _pid_file.write_text(str(os.getpid()))

        # 启动时对账：把上次崩溃遗留的 running 记录标记为 cancelled，使 run.get 状态与磁盘一致
        self._run_store = RunStore()
        reconciled = self._run_store.reconcile()
        if reconciled:
            logger.info("run store: reconciled %d interrupted run(s)", len(reconciled))

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
        store = SessionStore(
            sessions_root,
            tool_result_limit=self._config.compaction.tool_result_limit,
            tool_result_keep=self._config.compaction.tool_result_keep,
        )
        self._workspaces = WorkspaceManager(Path("~/.sztu/workspaces.json"))
        assert self._config is not None
        provider_key_name = (
            "OPENAI_API_KEY"
            if self._config.llm.provider == "openai"
            else "ANTHROPIC_API_KEY"
        )
        compact_provider = (
            create_provider(self._config)
            if _llm_api_key_configured(self._config, provider_key_name)
            and self._config.llm.default_model.strip()
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
                user_question_manager=self._user_question_manager,
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
        server.register("workspace.archive", self._workspace_archive_handler)
        server.register("workspace.pin", self._workspace_pin_handler)
        server.register("workspace.rename", self._workspace_rename_handler)
        server.register("workspace.resume", self._workspace_resume_handler)
        server.register("workspace.delete", self._workspace_delete_handler)
        server.register("workspace.status", self._workspace_status_handler)
        server.register("workspace.profile", self._workspace_profile_handler)
        server.register("workspace.tree", self._workspace_tree_handler)
        server.register("file.read", self._file_read_handler)
        server.register("file.search", self._file_search_handler)
        server.register("change.list", self._change_list_handler)
        server.register("change.diff", self._change_diff_handler)
        server.register("change.revert", self._change_revert_handler)
        server.register("change.stage", self._change_stage_handler)
        server.register("change.unstage", self._change_unstage_handler)
        server.register("change.discard", self._change_discard_handler)
        server.register("git.commit", self._git_commit_handler)
        server.register("git.history", self._git_history_handler)
        server.register("event.subscribe", self._subscribe_handler)
        server.register("session.create", self._session_create_handler)
        server.register("session.list", self._session_list_handler)
        server.register("session.rename", self._session_rename_handler)
        server.register("session.archive", self._session_archive_handler)
        server.register("session.pin", self._session_pin_handler)
        server.register("session.resume", self._session_resume_handler)
        server.register("session.fork", self._session_fork_handler)
        server.register("session.send_message", self._session_send_handler)
        server.register("session.steer_message", self._session_steer_handler)
        server.register("session.get_history", self._session_history_handler)
        server.register("session.close", self._session_close_handler)
        server.register("session.delete", self._session_delete_handler)
        server.register("permission.respond", self._permission_respond_handler)
        server.register("question.respond", self._user_question_respond_handler)
        server.register("question.pending", self._user_question_pending_handler)
        server.register("permission.set_mode", self._permission_set_mode_handler)
        server.register("settings.get", self._settings_get_handler)
        server.register("settings.update", self._settings_update_handler)
        server.register("provider.status", self._provider_status_handler)
        server.register("skill.list", self._skill_list_handler)
        server.register("skill.install", self._skill_install_handler)
        server.register("skill.set_enabled", self._skill_set_enabled_handler)
        server.register("plugin.list", self._plugin_list_handler)
        server.register("plugin.install", self._plugin_install_handler)
        server.register("plugin.set_enabled", self._plugin_set_enabled_handler)
        server.register("plugin.uninstall", self._plugin_uninstall_handler)
        server.register("plugin.catalog", self._plugin_catalog_handler)
        server.register("plugin.catalog_install", self._plugin_catalog_install_handler)
        server.register("plugin.marketplace_add", self._plugin_marketplace_add_handler)
        server.register("plugin.marketplace_refresh", self._plugin_marketplace_refresh_handler)
        server.register("plugin.marketplace_remove", self._plugin_marketplace_remove_handler)
        server.register("provider.ccswitch_list", self._provider_ccswitch_list_handler)
        server.register("provider.ccswitch_apply", self._provider_ccswitch_apply_handler)
        server.register("provider.model_list", self._model_profile_list_handler)
        server.register("provider.model_save", self._model_profile_save_handler)
        server.register("provider.model_select", self._model_profile_select_handler)
        server.register("provider.model_delete", self._model_profile_delete_handler)
        server.register("provider.model_test", self._model_test_handler)
        server.register("provider.model_benchmark", self._model_benchmark_handler)
        server.register("session.compact", self._session_compact_handler)

        addr = await server.start()
        logger.info("sztu-code %s listening addr=%s", sztu_code.__version__, addr)
        logger.info(
            "config: provider=%s api_format=%s model=%s permission=%s",
            self._config.llm.provider,
            self._config.llm.api_format,
            self._config.llm.default_model,
            self._config.permission.mode,
        )

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


# 支持 python -m sztu_code.core.app 直接拉起 daemon（sztucode 自动启动用）
if __name__ == "__main__":
    run()
