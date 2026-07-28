from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Discriminator, Field

from sztu_code.core.session.model import SessionMode, SessionStatus


class PingCommand(BaseModel):
    type: Literal["core.ping"] = "core.ping"
    client: str


class PongResult(BaseModel):
    server_version: str
    uptime_ms: int
    received_at: str  # ISO 8601


class AgentRunCommand(BaseModel):
    type: Literal["agent.run"] = "agent.run"
    goal: str


class AgentRunResult(BaseModel):
    run_id: str


class RunCancelCommand(BaseModel):
    type: Literal["run.cancel"] = "run.cancel"
    run_id: str


class RunCancelResult(BaseModel):
    run_id: str
    status: Literal["cancelling", "not_running"]


class RunGetCommand(BaseModel):
    type: Literal["run.get"] = "run.get"
    run_id: str


class RunGetResult(BaseModel):
    run_id: str
    status: Literal["running", "completed", "cancelled", "unknown"]


class RunReplayCommand(BaseModel):
    type: Literal["run.replay"] = "run.replay"
    run_id: str
    max_events: int = Field(default=2_000, ge=1, le=10_000)


class RunReplayResult(BaseModel):
    run_id: str
    events: list[dict[str, Any]]


class WorkspaceSummary(BaseModel):
    workspace_id: str
    path: str
    name: str


class WorkspaceOpenCommand(BaseModel):
    type: Literal["workspace.open"] = "workspace.open"
    path: str


class WorkspaceOpenResult(BaseModel):
    workspace: WorkspaceSummary


class WorkspaceListCommand(BaseModel):
    type: Literal["workspace.list"] = "workspace.list"


class WorkspaceListResult(BaseModel):
    workspaces: list[WorkspaceSummary]


class WorkspaceStatusCommand(BaseModel):
    type: Literal["workspace.status"] = "workspace.status"
    workspace_id: str


class WorkspaceStatusResult(BaseModel):
    workspace: WorkspaceSummary
    branch: str | None = None
    is_git_repository: bool
    changed_file_count: int


class WorkspaceTreeCommand(BaseModel):
    type: Literal["workspace.tree"] = "workspace.tree"
    workspace_id: str
    path: str = ""
    max_depth: int = Field(default=2, ge=0, le=8)
    max_entries: int = Field(default=300, ge=1, le=1_000)


class WorkspaceTreeResult(BaseModel):
    nodes: list[dict[str, Any]]


class FileReadCommand(BaseModel):
    type: Literal["file.read"] = "file.read"
    workspace_id: str
    path: str


class FileReadResult(BaseModel):
    content: str


class FileSearchCommand(BaseModel):
    type: Literal["file.search"] = "file.search"
    workspace_id: str
    query: str
    max_results: int = Field(default=100, ge=1, le=500)


class FileSearchResult(BaseModel):
    matches: list[dict[str, Any]]


class ChangeSummary(BaseModel):
    path: str
    index_status: str
    worktree_status: str
    run_id: str | None = None
    agent_owned: bool = False
    revertible: bool = False


class ChangeListCommand(BaseModel):
    type: Literal["change.list"] = "change.list"
    workspace_id: str
    run_id: str | None = None


class ChangeListResult(BaseModel):
    changes: list[ChangeSummary]


class ChangeDiffCommand(BaseModel):
    type: Literal["change.diff"] = "change.diff"
    workspace_id: str
    path: str | None = None


class ChangeRevertCommand(BaseModel):
    type: Literal["change.revert"] = "change.revert"
    workspace_id: str
    run_id: str
    paths: list[str] = Field(min_length=1, max_length=200)
    confirm: Literal["revert"]


class ChangeRevertResult(BaseModel):
    reverted_paths: list[str]
    blocked_paths: dict[str, str]


class ChangeDiffResult(BaseModel):
    diff: str


class EventSubscribeCommand(BaseModel):
    type: Literal["event.subscribe"] = "event.subscribe"
    topics: list[str]          # fnmatch 模式，如 ["step.*", "tool.*"]
    scope: str = "global"      # "global" | "run:<run_id>"
    replay_from_run: str | None = None  # 设置则先从 events.jsonl 回放历史再接实时流


class EventSubscribeResult(BaseModel):
    subscription_id: str
    replayed_count: int = 0


class SessionCreateCommand(BaseModel):
    type: Literal["session.create"] = "session.create"
    mode: SessionMode = "chat"
    title: str = ""
    workspace_id: str | None = None


class SessionCreateResult(BaseModel):
    session_id: str
    status: SessionStatus


class SessionSummary(BaseModel):
    session_id: str
    title: str
    mode: SessionMode
    status: SessionStatus
    updated_at: str
    run_count: int
    archived: bool = False
    pinned: bool = False
    workspace_id: str | None = None
    latest_run_id: str | None = None


class SessionListCommand(BaseModel):
    type: Literal["session.list"] = "session.list"
    include_archived: bool = False
    limit: int = Field(default=50, ge=1, le=100)
    cursor: str | None = None


class SessionListResult(BaseModel):
    sessions: list[SessionSummary]
    next_cursor: str | None = None


class SessionRenameCommand(BaseModel):
    type: Literal["session.rename"] = "session.rename"
    session_id: str
    title: str


class SessionRenameResult(BaseModel):
    session: SessionSummary


class SessionArchiveCommand(BaseModel):
    type: Literal["session.archive"] = "session.archive"
    session_id: str


class SessionArchiveResult(BaseModel):
    session: SessionSummary


class SessionPinCommand(BaseModel):
    type: Literal["session.pin"] = "session.pin"
    session_id: str
    pinned: bool


class SessionPinResult(BaseModel):
    session: SessionSummary


class SessionResumeCommand(BaseModel):
    type: Literal["session.resume"] = "session.resume"
    session_id: str


class SessionResumeResult(BaseModel):
    session: SessionSummary


class SessionSendMessageCommand(BaseModel):
    type: Literal["session.send_message"] = "session.send_message"
    session_id: str
    content: str


class SessionSendMessageResult(BaseModel):
    run_id: str


class SessionGetHistoryCommand(BaseModel):
    type: Literal["session.get_history"] = "session.get_history"
    session_id: str


class SessionGetHistoryResult(BaseModel):
    messages: list[dict[str, Any]]


class SessionCloseCommand(BaseModel):
    type: Literal["session.close"] = "session.close"
    session_id: str


class SessionCloseResult(BaseModel):
    status: SessionStatus


class PermissionRespondCommand(BaseModel):
    type: Literal["permission.respond"] = "permission.respond"
    tool_use_id: str
    decision: Literal["allow_once", "always_allow", "deny_once", "always_deny"]


class PermissionRespondResult(BaseModel):
    ok: bool = True


class PermissionSetModeCommand(BaseModel):
    type: Literal["permission.set_mode"] = "permission.set_mode"
    mode: Literal["normal", "accept_edits", "plan", "auto"]


class PermissionSetModeResult(BaseModel):
    ok: bool
    mode: Literal["normal", "accept_edits", "plan", "auto"] | None = None
    error: str | None = None


class SettingsSnapshot(BaseModel):
    provider: Literal["anthropic", "openai"]
    model: str
    router: str
    permission_mode: Literal["normal", "accept_edits", "plan", "auto"]
    applies_at: Literal["next_run"] = "next_run"
    persistent: bool = True


class SettingsGetCommand(BaseModel):
    type: Literal["settings.get"] = "settings.get"


class SettingsGetResult(BaseModel):
    settings: SettingsSnapshot


class SettingsUpdateCommand(BaseModel):
    type: Literal["settings.update"] = "settings.update"
    provider: Literal["anthropic", "openai"] | None = None
    model: str | None = Field(default=None, min_length=1, max_length=200)
    permission_mode: Literal["normal", "accept_edits", "plan", "auto"] | None = None


class SettingsUpdateResult(BaseModel):
    settings: SettingsSnapshot
    updated: list[Literal["provider", "model", "permission_mode"]]


class ProviderStatusCommand(BaseModel):
    type: Literal["provider.status"] = "provider.status"


class ProviderStatusResult(BaseModel):
    provider: Literal["anthropic", "openai"]
    model: str
    api_key_configured: bool
    custom_endpoint_configured: bool
    ready_for_next_run: bool
    mcp_servers: list[dict[str, Any]]
    skills: list[dict[str, str]]


class SessionCompactCommand(BaseModel):
    type: Literal["session.compact"] = "session.compact"
    session_id: str
    focus: str = ""


class SessionCompactResult(BaseModel):
    summary_tokens: int
    saved_tokens: int


# 根据 type 字段决定命令类型的判别联合
Command = Annotated[
    PingCommand
    | AgentRunCommand
    | RunCancelCommand
    | RunGetCommand
    | RunReplayCommand
    | WorkspaceOpenCommand
    | WorkspaceListCommand
    | WorkspaceStatusCommand
    | WorkspaceTreeCommand
    | FileReadCommand
    | FileSearchCommand
    | ChangeListCommand
    | ChangeDiffCommand
    | ChangeRevertCommand
    | EventSubscribeCommand
    | SessionCreateCommand
    | SessionListCommand
    | SessionRenameCommand
    | SessionArchiveCommand
    | SessionPinCommand
    | SessionResumeCommand
    | SessionSendMessageCommand
    | SessionGetHistoryCommand
    | SessionCloseCommand
    | PermissionRespondCommand
    | PermissionSetModeCommand
    | SettingsGetCommand
    | SettingsUpdateCommand
    | ProviderStatusCommand
    | SessionCompactCommand,
    Discriminator("type"),
]
