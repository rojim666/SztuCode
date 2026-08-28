from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Discriminator, Field, model_validator

from sztu_code.core.session.model import SessionMode, SessionStatus
from sztu_code.core.workspace.project_profile import ProjectProfile

ApiFormat = Literal[
    "openai_chat_completions",
    "anthropic_messages",
    "openai_responses",
]
ReasoningEffort = Literal["", "low", "medium", "high", "xhigh", "max"]


class ModelRequestSettings(BaseModel):
    max_output_tokens: int = Field(default=8192, ge=1, le=128000)
    temperature: float | None = Field(default=None, ge=0, le=1)
    top_p: float | None = Field(default=None, ge=0, le=1)
    reasoning_effort: ReasoningEffort = ""
    timeout_s: float = Field(default=120.0, gt=0, le=600)
    max_retries: int = Field(default=2, ge=0, le=10)
    context_window: int = Field(default=0, ge=0, le=10_000_000)
    cache_control: bool = True


class PingCommand(BaseModel):
    type: Literal["core.ping"] = "core.ping"
    client: str


class PongResult(BaseModel):
    server_version: str
    uptime_ms: int
    received_at: str  # ISO 8601
    capabilities: list[str] = Field(default_factory=list)


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
    archived: bool = False
    pinned: bool = False


class WorkspaceOpenCommand(BaseModel):
    type: Literal["workspace.open"] = "workspace.open"
    path: str


class WorkspaceOpenResult(BaseModel):
    workspace: WorkspaceSummary


class WorkspaceListCommand(BaseModel):
    type: Literal["workspace.list"] = "workspace.list"


class WorkspaceListResult(BaseModel):
    workspaces: list[WorkspaceSummary]


class WorkspaceArchiveCommand(BaseModel):
    type: Literal["workspace.archive"] = "workspace.archive"
    workspace_id: str


class WorkspaceArchiveResult(BaseModel):
    workspace: WorkspaceSummary


class WorkspacePinCommand(BaseModel):
    type: Literal["workspace.pin"] = "workspace.pin"
    workspace_id: str
    pinned: bool


class WorkspacePinResult(BaseModel):
    workspace: WorkspaceSummary


class WorkspaceRenameCommand(BaseModel):
    type: Literal["workspace.rename"] = "workspace.rename"
    workspace_id: str
    name: str = Field(min_length=1, max_length=120)


class WorkspaceRenameResult(BaseModel):
    workspace: WorkspaceSummary


class WorkspaceResumeCommand(BaseModel):
    type: Literal["workspace.resume"] = "workspace.resume"
    workspace_id: str


class WorkspaceResumeResult(BaseModel):
    workspace: WorkspaceSummary


class WorkspaceDeleteCommand(BaseModel):
    type: Literal["workspace.delete"] = "workspace.delete"
    workspace_id: str
    confirm: Literal["delete"]  # 必须显式传 delete，防止误删

class WorkspaceDeleteResult(BaseModel):
    workspace_id: str
    deleted: bool = True


class WorkspaceStatusCommand(BaseModel):
    type: Literal["workspace.status"] = "workspace.status"
    workspace_id: str


class WorkspaceStatusResult(BaseModel):
    workspace: WorkspaceSummary
    branch: str | None = None
    is_git_repository: bool
    changed_file_count: int


class WorkspaceProfileCommand(BaseModel):
    type: Literal["workspace.profile"] = "workspace.profile"
    workspace_id: str
    refresh: bool = False


class WorkspaceProfileResult(BaseModel):
    profile: ProjectProfile


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
    encoding: str = "UTF-8"
    binary: bool = False
    truncated: bool = False
    media_base64: str | None = None
    mime_type: str | None = None


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
    additions: int = 0  # 该文件新增行数
    deletions: int = 0  # 该文件删除行数


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
    run_id: str | None = None


class ChangeRevertCommand(BaseModel):
    type: Literal["change.revert"] = "change.revert"
    workspace_id: str
    run_id: str
    paths: list[str] = Field(min_length=1, max_length=200)
    confirm: Literal["revert"]


class ChangeRevertResult(BaseModel):
    reverted_paths: list[str]
    blocked_paths: dict[str, str]


class ChangeStageCommand(BaseModel):
    type: Literal["change.stage"] = "change.stage"
    workspace_id: str
    paths: list[str] = Field(min_length=1, max_length=200)


class ChangeStageResult(BaseModel):
    staged_paths: list[str]


class ChangeUnstageCommand(BaseModel):
    type: Literal["change.unstage"] = "change.unstage"
    workspace_id: str
    paths: list[str] = Field(min_length=1, max_length=200)


class ChangeUnstageResult(BaseModel):
    unstaged_paths: list[str]


class ChangeDiscardCommand(BaseModel):
    type: Literal["change.discard"] = "change.discard"
    workspace_id: str
    paths: list[str] = Field(min_length=1, max_length=200)
    confirm: Literal["discard"]


class ChangeDiscardResult(BaseModel):
    discarded_paths: list[str]


class GitCommitCommand(BaseModel):
    type: Literal["git.commit"] = "git.commit"
    workspace_id: str
    message: str = Field(min_length=1, max_length=500)


class GitCommitResult(BaseModel):
    commit_hash: str


class GitHistoryCommand(BaseModel):
    type: Literal["git.history"] = "git.history"
    workspace_id: str
    limit: int = Field(default=100, ge=1, le=200)
    skip: int = Field(default=0, ge=0)


class GitHistoryResult(BaseModel):
    commits: list[dict[str, Any]]
    has_more: bool = False


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
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_elapsed_s: float = 0.0


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


class SessionForkCommand(BaseModel):
    type: Literal["session.fork"] = "session.fork"
    session_id: str
    title: str = ""


class SessionForkResult(BaseModel):
    session: SessionSummary


class MessageImageBlock(BaseModel):
    type: Literal["image"] = "image"
    media_type: str  # 图片 MIME 类型，如 image/png
    data: str  # base64 编码的图片数据


class SessionSendMessageCommand(BaseModel):
    type: Literal["session.send_message"] = "session.send_message"
    session_id: str
    content: str
    images: list[MessageImageBlock] = Field(default_factory=list)
    client_message_id: str | None = Field(default=None, max_length=128)


class SessionSendMessageResult(BaseModel):
    run_id: str


class SessionSteerMessageCommand(BaseModel):
    type: Literal["session.steer_message"] = "session.steer_message"
    session_id: str
    content: str
    images: list[MessageImageBlock] = Field(default_factory=list)


class SessionSteerMessageResult(BaseModel):
    run_id: str
    status: Literal["accepted"] = "accepted"


class SessionGetHistoryCommand(BaseModel):
    type: Literal["session.get_history"] = "session.get_history"
    session_id: str


class SessionGetHistoryResult(BaseModel):
    messages: list[dict[str, Any]]
    run_stats: dict[str, dict[str, int | float]] = Field(default_factory=dict)
    context_injections: list[dict[str, Any]] = Field(default_factory=list)


class SessionCloseCommand(BaseModel):
    type: Literal["session.close"] = "session.close"
    session_id: str


class SessionCloseResult(BaseModel):
    status: SessionStatus


class SessionDeleteCommand(BaseModel):
    type: Literal["session.delete"] = "session.delete"
    session_id: str


class SessionDeleteResult(BaseModel):
    session_id: str
    deleted: bool = True


class PermissionRespondCommand(BaseModel):
    type: Literal["permission.respond"] = "permission.respond"
    tool_use_id: str
    run_id: str
    session_id: str
    decision: Literal["allow_once", "always_allow", "deny_once", "always_deny"]


class PermissionRespondResult(BaseModel):
    ok: bool = True


class UserQuestionOption(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class UserQuestionItem(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    header: str | None = Field(default=None, max_length=40)
    question: str = Field(min_length=1, max_length=1_000)
    options: list[UserQuestionOption] = Field(default_factory=list, max_length=8)
    multi_select: bool = False

    # 拒绝重复选项标签，确保 selected 可以无歧义地回指原选项
    @model_validator(mode="after")
    def validate_unique_option_labels(self) -> UserQuestionItem:
        labels = [option.label for option in self.options]
        if len(labels) != len(set(labels)):
            raise ValueError("question option labels must be unique")
        return self


class UserQuestionAnswer(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    selected: list[str] = Field(default_factory=list, max_length=8)
    custom: str | None = Field(default=None, max_length=4_000)


class UserQuestionPending(BaseModel):
    rpc_id: str
    session_id: str
    run_id: str
    questions: list[UserQuestionItem]


class UserQuestionRespondCommand(BaseModel):
    type: Literal["question.respond"] = "question.respond"
    rpc_id: str
    session_id: str
    answers: list[UserQuestionAnswer] = Field(min_length=1, max_length=3)


class UserQuestionRespondResult(BaseModel):
    ok: bool = True


class UserQuestionPendingCommand(BaseModel):
    type: Literal["question.pending"] = "question.pending"
    session_id: str | None = None


class UserQuestionPendingResult(BaseModel):
    pending: list[UserQuestionPending]


class PermissionSetModeCommand(BaseModel):
    type: Literal["permission.set_mode"] = "permission.set_mode"
    mode: Literal["normal", "accept_edits", "plan", "auto"]


class PermissionSetModeResult(BaseModel):
    ok: bool
    mode: Literal["normal", "accept_edits", "plan", "auto"] | None = None
    error: str | None = None


class SettingsSnapshot(ModelRequestSettings):
    provider: Literal["anthropic", "openai"]
    api_format: ApiFormat = "anthropic_messages"
    model: str
    router: str
    permission_mode: Literal["normal", "accept_edits", "plan", "auto"]
    base_url: str = ""  # 自定义端点（不含凭证），供客户端展示当前生效地址
    applies_at: Literal["next_run"] = "next_run"
    persistent: bool = True


class SettingsGetCommand(BaseModel):
    type: Literal["settings.get"] = "settings.get"


class SettingsGetResult(BaseModel):
    settings: SettingsSnapshot


class SettingsUpdateCommand(BaseModel):
    type: Literal["settings.update"] = "settings.update"
    provider: Literal["anthropic", "openai"] | None = None
    api_format: ApiFormat | None = None
    model: str | None = Field(default=None, min_length=1, max_length=200)
    base_url: str | None = Field(default=None, max_length=2000)
    api_key: str | None = Field(default=None, min_length=1, max_length=4000)
    permission_mode: Literal["normal", "accept_edits", "plan", "auto"] | None = None
    max_output_tokens: int | None = Field(default=None, ge=1, le=128000)
    temperature: float | None = Field(default=None, ge=0, le=1)
    top_p: float | None = Field(default=None, ge=0, le=1)
    reasoning_effort: ReasoningEffort | None = None
    timeout_s: float | None = Field(default=None, gt=0, le=600)
    max_retries: int | None = Field(default=None, ge=0, le=10)
    context_window: int | None = Field(default=None, ge=0, le=10_000_000)
    cache_control: bool | None = None


class SettingsUpdateResult(BaseModel):
    settings: SettingsSnapshot
    updated: list[str]


class ProviderStatusCommand(BaseModel):
    type: Literal["provider.status"] = "provider.status"


class SkillSummary(BaseModel):
    id: str
    name: str
    display_name: str
    description: str
    short_description: str
    source: str
    scope: Literal["system", "personal", "workspace"]
    path: str
    plugin: str | None = None
    enabled: bool = True
    icon: str | None = None
    brand_color: str | None = None
    allow_implicit_invocation: bool = True


class PluginSummary(BaseModel):
    id: str
    name: str
    description: str
    version: str
    source: Literal["personal", "workspace"]
    path: str
    skills: list[str]
    installed: bool = True
    display_name: str
    brand_color: str | None = None
    enabled: bool = True


class MarketplaceSummary(BaseModel):
    id: str
    name: str
    display_name: str
    source: str
    kind: Literal["default", "git", "local"]
    root_path: str
    ref: str = ""
    sparse_paths: list[str]
    plugin_count: int
    updated_at: str = ""
    removable: bool = False
    updatable: bool = False


class MarketplacePluginSummary(BaseModel):
    id: str
    marketplace_id: str
    marketplace_name: str
    name: str
    display_name: str
    description: str
    version: str
    category: str
    publisher: str
    installation: str
    authentication: str
    installed: bool = False
    installed_plugin_id: str | None = None


class SkillListCommand(BaseModel):
    type: Literal["skill.list"] = "skill.list"
    workspace_id: str | None = None


class SkillListResult(BaseModel):
    skills: list[SkillSummary]


class SkillInstallCommand(BaseModel):
    type: Literal["skill.install"] = "skill.install"
    source_path: str = Field(min_length=1, max_length=4000)
    scope: Literal["personal", "workspace"] = "personal"
    workspace_id: str | None = None


class SkillInstallResult(BaseModel):
    skill: SkillSummary


class SkillSetEnabledCommand(BaseModel):
    type: Literal["skill.set_enabled"] = "skill.set_enabled"
    skill_id: str = Field(min_length=1, max_length=500)
    enabled: bool
    workspace_id: str | None = None


class SkillSetEnabledResult(BaseModel):
    skill: SkillSummary


class PluginListCommand(BaseModel):
    type: Literal["plugin.list"] = "plugin.list"
    workspace_id: str | None = None


class PluginListResult(BaseModel):
    plugins: list[PluginSummary]


class PluginInstallCommand(BaseModel):
    type: Literal["plugin.install"] = "plugin.install"
    source_path: str = Field(min_length=1, max_length=4000)
    scope: Literal["personal", "workspace"] = "personal"
    workspace_id: str | None = None


class PluginInstallResult(BaseModel):
    plugin: PluginSummary


class PluginSetEnabledCommand(BaseModel):
    type: Literal["plugin.set_enabled"] = "plugin.set_enabled"
    plugin_id: str = Field(min_length=1, max_length=500)
    enabled: bool
    workspace_id: str | None = None


class PluginSetEnabledResult(BaseModel):
    plugin: PluginSummary


class PluginUninstallCommand(BaseModel):
    type: Literal["plugin.uninstall"] = "plugin.uninstall"
    plugin_id: str = Field(min_length=1, max_length=500)
    workspace_id: str | None = None
    confirm: Literal["uninstall"]


class PluginUninstallResult(BaseModel):
    plugin_id: str


class PluginCatalogCommand(BaseModel):
    type: Literal["plugin.catalog"] = "plugin.catalog"
    workspace_id: str | None = None


class PluginCatalogResult(BaseModel):
    marketplaces: list[MarketplaceSummary]
    plugins: list[MarketplacePluginSummary]


class PluginMarketplaceAddCommand(BaseModel):
    type: Literal["plugin.marketplace_add"] = "plugin.marketplace_add"
    source: str = Field(min_length=1, max_length=4000)
    git_ref: str = Field(default="", max_length=500)
    sparse_paths: list[str] = Field(default_factory=list, max_length=32)
    workspace_id: str | None = None


class PluginMarketplaceAddResult(BaseModel):
    marketplace: MarketplaceSummary


class PluginMarketplaceRefreshCommand(BaseModel):
    type: Literal["plugin.marketplace_refresh"] = "plugin.marketplace_refresh"
    marketplace_id: str | None = Field(default=None, max_length=500)
    workspace_id: str | None = None


class PluginMarketplaceRefreshResult(BaseModel):
    marketplaces: list[MarketplaceSummary]


class PluginMarketplaceRemoveCommand(BaseModel):
    type: Literal["plugin.marketplace_remove"] = "plugin.marketplace_remove"
    marketplace_id: str = Field(min_length=1, max_length=500)
    workspace_id: str | None = None
    confirm: Literal["remove"]


class PluginMarketplaceRemoveResult(BaseModel):
    marketplace_id: str


class PluginCatalogInstallCommand(BaseModel):
    type: Literal["plugin.catalog_install"] = "plugin.catalog_install"
    catalog_plugin_id: str = Field(min_length=1, max_length=1000)
    scope: Literal["personal", "workspace"] = "personal"
    workspace_id: str | None = None


class PluginCatalogInstallResult(BaseModel):
    plugin: PluginSummary


class ProviderStatusResult(BaseModel):
    provider: Literal["anthropic", "openai"]
    api_format: ApiFormat = "anthropic_messages"
    model: str
    api_key_configured: bool
    custom_endpoint_configured: bool
    ready_for_next_run: bool
    mcp_servers: list[dict[str, Any]]
    skills: list[SkillSummary]


class CcswitchProviderSummary(BaseModel):
    id: str
    name: str
    base_url: str
    model: str
    has_api_key: bool
    is_current: bool


class ProviderCcswitchListCommand(BaseModel):
    type: Literal["provider.ccswitch_list"] = "provider.ccswitch_list"


class ProviderCcswitchListResult(BaseModel):
    providers: list[CcswitchProviderSummary]


class ProviderCcswitchApplyCommand(BaseModel):
    type: Literal["provider.ccswitch_apply"] = "provider.ccswitch_apply"
    provider_id: str = Field(min_length=1, max_length=200)


class ProviderCcswitchApplyResult(BaseModel):
    settings: SettingsSnapshot
    updated: list[Literal["provider", "model", "base_url"]]


class ModelProfileSummary(ModelRequestSettings):
    id: str
    name: str
    vendor: str
    provider: Literal["anthropic", "openai"]
    api_format: ApiFormat = "anthropic_messages"
    model: str
    base_url: str = ""
    has_api_key: bool
    is_current: bool
    builtin: bool = False


class ModelProfileListCommand(BaseModel):
    type: Literal["provider.model_list"] = "provider.model_list"


class ModelProfileListResult(BaseModel):
    models: list[ModelProfileSummary]


class ModelProfileProbe(ModelRequestSettings):
    vendor: str = Field(default="Custom", min_length=1, max_length=100)
    provider: Literal["anthropic", "openai"] | None = None
    api_format: ApiFormat = "anthropic_messages"
    model: str = Field(min_length=1, max_length=200)
    base_url: str = Field(default="", max_length=2000)
    api_key: str | None = Field(default=None, max_length=4000)
    keyless: bool = False


class ModelProfileSaveCommand(ModelProfileProbe):
    type: Literal["provider.model_save"] = "provider.model_save"
    id: str | None = Field(default=None, max_length=100)
    name: str = Field(min_length=1, max_length=100)


class ModelProfileSaveResult(BaseModel):
    settings: SettingsSnapshot
    models: list[ModelProfileSummary]


class ModelProfileSelectCommand(BaseModel):
    type: Literal["provider.model_select"] = "provider.model_select"
    model_id: str = Field(min_length=1, max_length=100)


class ModelProfileSelectResult(BaseModel):
    settings: SettingsSnapshot
    models: list[ModelProfileSummary]


class ModelProfileDeleteCommand(BaseModel):
    type: Literal["provider.model_delete"] = "provider.model_delete"
    model_id: str = Field(min_length=1, max_length=100)


class ModelProfileDeleteResult(BaseModel):
    models: list[ModelProfileSummary]


class ModelTestCommand(ModelProfileProbe):
    type: Literal["provider.model_test"] = "provider.model_test"


class ModelTestResult(BaseModel):
    success: bool
    api_format: ApiFormat
    model: str
    elapsed_ms: float
    time_to_first_token_ms: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None


class ModelBenchmarkCommand(ModelProfileProbe):
    type: Literal["provider.model_benchmark"] = "provider.model_benchmark"
    samples: int = Field(default=3, ge=1, le=10)


class ModelBenchmarkResult(BaseModel):
    api_format: ApiFormat
    model: str
    samples: int
    successful: int
    failed: int
    min_ms: float | None = None
    median_ms: float | None = None
    p95_ms: float | None = None
    max_ms: float | None = None
    average_ttft_ms: float | None = None
    errors: list[str] = Field(default_factory=list)


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
    | WorkspaceArchiveCommand
    | WorkspacePinCommand
    | WorkspaceRenameCommand
    | WorkspaceResumeCommand
    | WorkspaceDeleteCommand
    | WorkspaceStatusCommand
    | WorkspaceProfileCommand
    | WorkspaceTreeCommand
    | FileReadCommand
    | FileSearchCommand
    | ChangeListCommand
    | ChangeDiffCommand
    | ChangeRevertCommand
    | ChangeStageCommand
    | ChangeUnstageCommand
    | ChangeDiscardCommand
    | GitCommitCommand
    | GitHistoryCommand
    | EventSubscribeCommand
    | SessionCreateCommand
    | SessionListCommand
    | SessionRenameCommand
    | SessionArchiveCommand
    | SessionPinCommand
    | SessionResumeCommand
    | SessionForkCommand
    | SessionSendMessageCommand
    | SessionSteerMessageCommand
    | SessionGetHistoryCommand
    | SessionCloseCommand
    | SessionDeleteCommand
    | PermissionRespondCommand
    | UserQuestionRespondCommand
    | UserQuestionPendingCommand
    | PermissionSetModeCommand
    | SettingsGetCommand
    | SettingsUpdateCommand
    | ProviderStatusCommand
    | SkillListCommand
    | SkillInstallCommand
    | SkillSetEnabledCommand
    | PluginListCommand
    | PluginInstallCommand
    | PluginSetEnabledCommand
    | PluginUninstallCommand
    | PluginCatalogCommand
    | PluginMarketplaceAddCommand
    | PluginMarketplaceRefreshCommand
    | PluginMarketplaceRemoveCommand
    | PluginCatalogInstallCommand
    | ProviderCcswitchListCommand
    | ProviderCcswitchApplyCommand
    | ModelProfileListCommand
    | ModelProfileSaveCommand
    | ModelProfileSelectCommand
    | ModelProfileDeleteCommand
    | ModelTestCommand
    | ModelBenchmarkCommand
    | SessionCompactCommand,
    Discriminator("type"),
]
