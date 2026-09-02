import { invoke } from "../lib/tauri-shim";
import { IpcClient, IpcRequestError } from "../lib/ipc";

export type Workspace = { workspace_id: string; name: string; path: string; archived: boolean; pinned?: boolean };
export type NativeSettings = {
  autostart: boolean;
  stay_awake: boolean;
  supported: boolean;
  theme: "system" | "light" | "dark";
  wallpaper: "none" | "mist" | "grid" | "paper" | "custom";
};
export type WorkspaceNode = { path: string; name: string; kind: "directory" | "file"; children?: WorkspaceNode[] };
export type FileSearchMatch = { path: string; line: number; preview: string };
export type DetectionEvidence = {
  path: string;
  rule: string;
  detail?: string | null;
  strength: "confirmed" | "supporting" | "weak";
};
export type TechnologyFinding = {
  name: string;
  confidence: "confirmed" | "likely";
  evidence: DetectionEvidence[];
};
export type ValidationCategory = "format" | "static_check" | "unit_test" | "integration_test" | "build";
export type ValidationCommand = {
  category: ValidationCategory;
  command: string;
  working_directory: string;
  reason: string;
  evidence: DetectionEvidence[];
  recommendation_only: true;
};
export type ProjectComponent = {
  path: string;
  languages: TechnologyFinding[];
  frameworks: TechnologyFinding[];
  package_managers: TechnologyFinding[];
  build_tools: TechnologyFinding[];
  evidence: DetectionEvidence[];
  validation_plan: ValidationCommand[];
};
export type ProjectProfile = {
  root_path: string;
  monorepo: boolean;
  projects: ProjectComponent[];
  scan_limited: boolean;
};
export type FileReadResult = {
  content: string; encoding: string; binary: boolean; truncated: boolean;
  media_base64?: string | null; mime_type?: string | null;
};
// 「添加附件」读取结果：图片/二进制给 data_base64，文本给 text_content，超限/失败给 error
export type Attachment = {
  path: string; name: string; size: number;
  mime_type?: string | null; is_text: boolean;
  text_content?: string | null; data_base64?: string | null; error?: string | null;
};
// 随消息发送的图片内容块，字段与 daemon 的 MessageImageBlock 对齐
export type ImageBlock = { media_type: string; data: string };
export type ChangeSummary = {
  path: string; index_status: string; worktree_status: string;
  run_id?: string | null; agent_owned?: boolean; revertible?: boolean;
  additions?: number; deletions?: number;
};
export type GitRef = { name: string; kind: "head" | "remote" | "tag" };
export type GitCommitEntry = {
  hash: string; short_hash: string; parents: string[];
  author: string; date: string; subject: string; is_head: boolean;
  is_outgoing: boolean; refs: GitRef[];
};
export type GitHistoryPage = { commits: GitCommitEntry[]; has_more: boolean };
export type Session = {
  session_id: string; title: string; status: string; updated_at: string;
  archived: boolean; pinned: boolean; workspace_id: string | null; latest_run_id?: string | null;
  total_input_tokens: number; total_output_tokens: number; total_elapsed_s: number;
};
export type RunStats = { input_tokens: number; output_tokens: number; cache_read_input_tokens: number; elapsed_s: number };
export type ContextInjectionRecord = {
  run_id: string; source: string; label: string; chars: number; preview: string; text: string; files?: string[]; ts?: string;
};
export type SessionHistory = {
  messages: unknown[];
  run_stats: Record<string, RunStats>;
  context_injections: ContextInjectionRecord[];
};
export type UserQuestionOption = { label: string; description?: string | null };
export type UserQuestionItem = {
  id: string; header?: string | null; question: string;
  options: UserQuestionOption[]; multi_select: boolean;
};
export type UserQuestionAnswer = { id: string; selected: string[]; custom?: string };
export type PendingUserQuestion = {
  rpc_id: string; session_id: string; run_id: string; questions: UserQuestionItem[];
};
export type ApiFormat = "openai_chat_completions" | "anthropic_messages" | "openai_responses";
export type ModelRequestSettings = {
  api_format: ApiFormat; context_window: number; max_output_tokens: number;
  temperature: number | null; top_p: number | null; reasoning_effort: "" | "low" | "medium" | "high" | "xhigh" | "max";
  timeout_s: number; max_retries: number; cache_control: boolean;
};
export type RuntimeSettings = ModelRequestSettings & { provider: "anthropic" | "openai"; model: string; permission_mode: "normal" | "accept_edits" | "plan" | "auto"; base_url?: string };
export type RuntimeSettingsUpdate = Partial<RuntimeSettings> & { api_key?: string };
export type SkillSummary = {
  id: string; name: string; display_name: string; description: string; short_description: string;
  source: string; scope: "system" | "personal" | "workspace"; path: string; plugin?: string | null;
  enabled: boolean; icon?: string | null; brand_color?: string | null; allow_implicit_invocation: boolean;
};
export type PluginSummary = {
  id: string; name: string; description: string; version: string;
  source: "personal" | "workspace"; path: string; skills: string[]; installed: boolean;
  display_name: string; brand_color?: string | null; enabled: boolean;
};
export type MarketplaceSummary = {
  id: string; name: string; display_name: string; source: string;
  kind: "default" | "git" | "local"; root_path: string; ref: string;
  sparse_paths: string[]; plugin_count: number; updated_at: string;
  removable: boolean; updatable: boolean;
};
export type MarketplacePluginSummary = {
  id: string; marketplace_id: string; marketplace_name: string;
  name: string; display_name: string; description: string; version: string;
  category: string; publisher: string; installation: string; authentication: string;
  installed: boolean; installed_plugin_id?: string | null;
};
export type ProviderStatus = { provider: "anthropic" | "openai"; api_format: ApiFormat; model: string; api_key_configured: boolean; ready_for_next_run: boolean; skills: SkillSummary[]; mcp_servers: Array<{ name: string; status: string; tool_count?: number }> };
export type ModelProfile = ModelRequestSettings & { id: string; name: string; icon: string; vendor: string; provider: "anthropic" | "openai"; model: string; base_url: string; has_api_key: boolean; is_current: boolean; builtin: boolean };
export type ModelProfileInput = ModelRequestSettings & { id?: string; name: string; icon?: string; vendor: string; provider: "anthropic" | "openai"; model: string; base_url: string; api_key?: string; keyless?: boolean };

const client = new IpcClient();
let subscribed = false;
let runtimeConnectionError = "";
const PLUGIN_PROTOCOL_ERROR = "本地服务版本过旧，不支持插件市场。请完全退出旧的 SztuCode daemon 后重新打开客户端。";
const GIT_PROTOCOL_ERROR = "本地服务版本过旧，不支持当前 Git 功能。请完全退出旧的 SztuCode daemon 后重新打开客户端。";
client.onDisconnect(() => { subscribed = false; });
const EVENT_TOPICS = [
  "session.*", "run.*", "step.*", "llm.*", "tool.*", "permission.*",
  "question.*", "plan.*", "test.*", "change.*", "log.*", "subagent.*", "skill.*", "context.*", "denial.*",
];

async function waitForDaemon(): Promise<void> {
  await invoke("daemon_start");
}

export function getRuntimeConnectionError(): string { return runtimeConnectionError; }

export async function getNativeSettings(): Promise<NativeSettings> {
  return await invoke<NativeSettings>("native_settings_get");
}

export async function setNativeSettings(update: {
  autostart?: boolean;
  stayAwake?: boolean;
  theme?: NativeSettings["theme"];
  wallpaper?: NativeSettings["wallpaper"];
}): Promise<NativeSettings> {
  return await invoke<NativeSettings>("native_settings_update", update);
}

export async function sandboxPtyStart(sessionId: string, workspacePath: string, cols: number, rows: number): Promise<void> {
  await invoke("sandbox_pty_start", { sessionId, workspacePath, cols, rows });
}

export async function sandboxPtyWrite(sessionId: string, data: string): Promise<void> {
  await invoke("sandbox_pty_write", { sessionId, data });
}

export async function sandboxPtyResize(sessionId: string, cols: number, rows: number): Promise<void> {
  await invoke("sandbox_pty_resize", { sessionId, cols, rows });
}

export async function sandboxPtyClose(sessionId: string): Promise<void> {
  await invoke("sandbox_pty_close", { sessionId });
}

export async function connectRuntime(): Promise<boolean> {
  try {
    await waitForDaemon();
  } catch (error) {
    runtimeConnectionError = error instanceof Error ? error.message : String(error);
    return false;
  }
  // Rust sidecar 已等待 daemon 就绪后再通知前端，此处仅做轻量重试
  const attempts = 12;
  for (const port of [7438]) {
    for (let attempt = 0; attempt < attempts; attempt += 1) {
      try {
        await client.connect("127.0.0.1", port);
        if (!subscribed) {
          await client.request("event.subscribe", { topics: EVENT_TOPICS, scope: "global" });
          subscribed = true;
        }
        runtimeConnectionError = "";
        return true;
      } catch (error) {
        runtimeConnectionError = error instanceof Error ? error.message : String(error);
        if (attempt + 1 < attempts) await new Promise((resolve) => window.setTimeout(resolve, 250));
      }
    }
  }
  return false;
}

export function onRuntimeEvent(handler: (event: Record<string, unknown>) => void): () => void {
  // Keep legacy UI consumers permissive while the IPC transport validates the
  // discriminated RuntimeEvent union at its boundary.
  return client.onEvent((event) => handler(event as unknown as Record<string, unknown>));
}

export function onRuntimeDisconnect(handler: (reason: string) => void): () => void {
  return client.onDisconnect(handler);
}

export async function listWorkspaces(): Promise<Workspace[]> {
  const result = await client.request("workspace.list");
  return (result.workspaces as Workspace[] | undefined) ?? [];
}

export async function listSessions(includeArchived = true): Promise<Session[]> {
  const result = await client.request("session.list", { limit: 100, include_archived: includeArchived });
  return (result.sessions as Session[] | undefined) ?? [];
}

export async function archiveWorkspace(workspaceId: string): Promise<Workspace> {
  const result = await client.request("workspace.archive", { workspace_id: workspaceId });
  return result.workspace as Workspace;
}

export async function resumeWorkspace(workspaceId: string): Promise<Workspace> {
  const result = await client.request("workspace.resume", { workspace_id: workspaceId });
  return result.workspace as Workspace;
}

export async function deleteWorkspace(workspaceId: string): Promise<void> {
  await client.request("workspace.delete", { workspace_id: workspaceId, confirm: "delete" });
}

export async function createSession(workspace: Workspace | null): Promise<string> {
  const result = await client.request("session.create", { mode: "chat", workspace_id: workspace?.workspace_id });
  return String(result.session_id);
}

export async function sessionHistory(sessionId: string): Promise<SessionHistory> {
  const result = await client.request("session.get_history", { session_id: sessionId });
  return {
    messages: (result.messages as unknown[] | undefined) ?? [],
    run_stats: (result.run_stats as Record<string, RunStats> | undefined) ?? {},
    context_injections: (result.context_injections as ContextInjectionRecord[] | undefined) ?? [],
  };
}

export async function sendPrompt(sessionId: string, message: string, images: ImageBlock[] = [], clientMessageId?: string): Promise<string> {
  const result = await client.request("session.send_message", { session_id: sessionId, content: message, images, client_message_id: clientMessageId });
  return String(result.run_id ?? "");
}

export async function steerPrompt(sessionId: string, message: string, images: ImageBlock[] = []): Promise<string> {
  const result = await client.request("session.steer_message", { session_id: sessionId, content: message, images });
  return String(result.run_id ?? "");
}

export async function renameSession(sessionId: string, title: string): Promise<Session> {
  const result = await client.request("session.rename", { session_id: sessionId, title });
  return result.session as Session;
}

export async function pinSession(sessionId: string, pinned: boolean): Promise<Session> {
  const result = await client.request("session.pin", { session_id: sessionId, pinned });
  return result.session as Session;
}

export async function archiveSession(sessionId: string): Promise<Session> {
  const result = await client.request("session.archive", { session_id: sessionId });
  return result.session as Session;
}

export async function resumeSession(sessionId: string): Promise<Session> {
  const result = await client.request("session.resume", { session_id: sessionId });
  return result.session as Session;
}

export async function closeSession(sessionId: string): Promise<void> {
  await client.request("session.close", { session_id: sessionId });
}

export async function deleteSession(sessionId: string): Promise<void> {
  await client.request("session.delete", { session_id: sessionId });
}

export async function compactSession(sessionId: string, focus = ""): Promise<{ summary_tokens: number; saved_tokens: number; removed_messages?: number; used_model?: boolean }> {
  return await client.request("session.compact", { session_id: sessionId, focus }) as { summary_tokens: number; saved_tokens: number; removed_messages?: number; used_model?: boolean };
}
export async function pinWorkspace(workspaceId: string, pinned: boolean): Promise<Workspace> {
  const result = await client.request("workspace.pin", { workspace_id: workspaceId, pinned }); return result.workspace as Workspace;
}
export async function renameWorkspace(workspaceId: string, name: string): Promise<Workspace> {
  const result = await client.request("workspace.rename", { workspace_id: workspaceId, name }); return result.workspace as Workspace;
}
export async function moveSession(sessionId: string, workspaceId: string | null): Promise<Session> {
  const result = await client.request("session.set_workspace", { session_id: sessionId, workspace_id: workspaceId }); return result.session as Session;
}

export async function replayRun(runId: string): Promise<Record<string, unknown>[]> {
  const result = await client.request("run.replay", { run_id: runId, max_events: 10_000 });
  return (result.events as Record<string, unknown>[] | undefined) ?? [];
}

// 请求停止正在执行的 run；后端取消后通过 run.finished 事件通知前端
export async function cancelRun(runId: string): Promise<string> {
  const result = await client.request("run.cancel", { run_id: runId });
  return String(result.status ?? "");
}

export async function openWorkspace(path: string): Promise<Workspace> {
  const result = await client.request("workspace.open", { path });
  return result.workspace as Workspace;
}

export type WorkspaceStatus = { branch: string | null; is_git_repository: boolean; changed_file_count: number };

export async function workspaceStatus(workspaceId: string): Promise<WorkspaceStatus> {
  const result = await client.request("workspace.status", { workspace_id: workspaceId });
  return {
    branch: typeof result.branch === "string" ? result.branch : null,
    is_git_repository: Boolean(result.is_git_repository),
    changed_file_count: Number(result.changed_file_count ?? 0),
  };
}

export async function getWorkspaceProfile(workspaceId: string, refresh = false): Promise<ProjectProfile> {
  const result = await client.request("workspace.profile", { workspace_id: workspaceId, refresh });
  return result.profile as ProjectProfile;
}

export async function workspaceTree(workspaceId: string, path = "", maxDepth = 1): Promise<WorkspaceNode[]> {
  const result = await client.request("workspace.tree", { workspace_id: workspaceId, path, max_depth: maxDepth, max_entries: 1_000 });
  return (result.nodes as WorkspaceNode[] | undefined) ?? [];
}

export async function searchFiles(workspaceId: string, query: string): Promise<FileSearchMatch[]> {
  const result = await client.request("file.search", { workspace_id: workspaceId, query, max_results: 100 });
  return (result.matches as FileSearchMatch[] | undefined) ?? [];
}

export async function readFile(workspaceId: string, path: string): Promise<FileReadResult> {
  const result = await client.request("file.read", { workspace_id: workspaceId, path });
  return {
    content: String(result.content ?? ""),
    encoding: String(result.encoding ?? "UTF-8"),
    binary: Boolean(result.binary),
    truncated: Boolean(result.truncated),
    media_base64: typeof result.media_base64 === "string" ? result.media_base64 : null,
    mime_type: typeof result.mime_type === "string" ? result.mime_type : null,
  };
}

// 读取「添加附件」选中的本地文件（Tauri 侧），返回逐文件分类结果
export async function readAttachments(paths: string[]): Promise<Attachment[]> {
  return await invoke<Attachment[]>("read_attachment", { paths });
}

export async function listChanges(workspaceId: string, runId?: string | null): Promise<ChangeSummary[]> {
  const result = await client.request("change.list", { workspace_id: workspaceId, run_id: runId ?? null });
  return (result.changes as ChangeSummary[] | undefined) ?? [];
}

export async function changeDiff(workspaceId: string, path?: string, runId?: string | null): Promise<string> {
  const result = await client.request("change.diff", { workspace_id: workspaceId, path: path ?? null, run_id: runId ?? null });
  return String(result.diff ?? "");
}

export async function revertChanges(workspaceId: string, runId: string, paths: string[]): Promise<{ reverted_paths: string[]; blocked_paths: Record<string, string> }> {
  return await client.request("change.revert", { workspace_id: workspaceId, run_id: runId, paths, confirm: "revert" }) as { reverted_paths: string[]; blocked_paths: Record<string, string> };
}

export async function stageChanges(workspaceId: string, paths: string[]): Promise<string[]> {
  const result = await client.request("change.stage", { workspace_id: workspaceId, paths });
  return (result.staged_paths as string[] | undefined) ?? [];
}

export async function getRuntimeSettings(): Promise<RuntimeSettings | null> {
  const result = await client.request("settings.get");
  return (result.settings as RuntimeSettings | undefined) ?? null;
}

export async function setRuntimeSettings(update: RuntimeSettingsUpdate): Promise<RuntimeSettings | null> {
  const result = await client.request("settings.update", update);
  return (result.settings as RuntimeSettings | undefined) ?? null;
}

export async function getProviderStatus(): Promise<ProviderStatus | null> {
  const result = await client.request("provider.status");
  return result as unknown as ProviderStatus;
}

export type CcswitchProvider = {
  id: string; name: string; base_url: string; model: string;
  has_api_key: boolean; is_current: boolean;
};

export async function listCcswitchProviders(): Promise<CcswitchProvider[]> {
  const result = await client.request("provider.ccswitch_list");
  return (result.providers as CcswitchProvider[] | undefined) ?? [];
}

export async function applyCcswitchProvider(providerId: string): Promise<RuntimeSettings | null> {
  const result = await client.request("provider.ccswitch_apply", { provider_id: providerId });
  return (result.settings as RuntimeSettings | undefined) ?? null;
}

export async function listModelProfiles(): Promise<ModelProfile[]> {
  const result = await client.request("provider.model_list");
  return (result.models as ModelProfile[] | undefined) ?? [];
}

export async function saveModelProfile(input: ModelProfileInput): Promise<{ settings: RuntimeSettings; models: ModelProfile[] }> {
  return await client.request("provider.model_save", input) as { settings: RuntimeSettings; models: ModelProfile[] };
}

export async function selectModelProfile(modelId: string): Promise<{ settings: RuntimeSettings; models: ModelProfile[] }> {
  return await client.request("provider.model_select", { model_id: modelId }) as { settings: RuntimeSettings; models: ModelProfile[] };
}

export async function deleteModelProfile(modelId: string): Promise<ModelProfile[]> {
  const result = await client.request("provider.model_delete", { model_id: modelId });
  return (result.models as ModelProfile[] | undefined) ?? [];
}

export async function listSkills(workspaceId?: string | null): Promise<SkillSummary[]> {
  const result = await client.request("skill.list", { workspace_id: workspaceId ?? null });
  return (result.skills as SkillSummary[] | undefined) ?? [];
}

export async function installSkill(sourcePath: string, scope: "personal" | "workspace", workspaceId?: string | null): Promise<SkillSummary> {
  const result = await client.request("skill.install", { source_path: sourcePath, scope, workspace_id: workspaceId ?? null });
  return result.skill as SkillSummary;
}

export async function setSkillEnabled(skillId: string, enabled: boolean, workspaceId?: string | null): Promise<SkillSummary> {
  const result = await client.request("skill.set_enabled", { skill_id: skillId, enabled, workspace_id: workspaceId ?? null });
  return result.skill as SkillSummary;
}

export async function listPlugins(workspaceId?: string | null): Promise<PluginSummary[]> {
  const result = await client.request("plugin.list", { workspace_id: workspaceId ?? null });
  return (result.plugins as PluginSummary[] | undefined) ?? [];
}

export async function installPlugin(sourcePath: string, scope: "personal" | "workspace", workspaceId?: string | null): Promise<PluginSummary> {
  const result = await client.request("plugin.install", { source_path: sourcePath, scope, workspace_id: workspaceId ?? null });
  return result.plugin as PluginSummary;
}

async function requestPluginProtocol(method: string, params: Record<string, unknown>): Promise<Record<string, unknown>> {
  try {
    return await client.request(method, params);
  } catch (reason) {
    if (reason instanceof IpcRequestError && reason.code === -32601) {
      throw new Error(PLUGIN_PROTOCOL_ERROR);
    }
    throw reason;
  }
}

export async function setPluginEnabled(pluginId: string, enabled: boolean, workspaceId?: string | null): Promise<PluginSummary> {
  const result = await requestPluginProtocol("plugin.set_enabled", { plugin_id: pluginId, enabled, workspace_id: workspaceId ?? null });
  return result.plugin as PluginSummary;
}

export async function uninstallPlugin(pluginId: string, workspaceId?: string | null): Promise<void> {
  await requestPluginProtocol("plugin.uninstall", { plugin_id: pluginId, workspace_id: workspaceId ?? null, confirm: "uninstall" });
}

export async function getPluginCatalog(workspaceId?: string | null): Promise<{ marketplaces: MarketplaceSummary[]; plugins: MarketplacePluginSummary[]; supported: boolean }> {
  try {
    const result = await client.request("plugin.catalog", { workspace_id: workspaceId ?? null });
    return {
      marketplaces: (result.marketplaces as MarketplaceSummary[] | undefined) ?? [],
      plugins: (result.plugins as MarketplacePluginSummary[] | undefined) ?? [],
      supported: true,
    };
  } catch (reason) {
    if (reason instanceof IpcRequestError && reason.code === -32601) {
      return { marketplaces: [], plugins: [], supported: false };
    }
    throw reason;
  }
}

export async function addPluginMarketplace(source: string, gitRef: string, sparsePaths: string[], workspaceId?: string | null): Promise<MarketplaceSummary> {
  const result = await requestPluginProtocol("plugin.marketplace_add", { source, git_ref: gitRef, sparse_paths: sparsePaths, workspace_id: workspaceId ?? null });
  return result.marketplace as MarketplaceSummary;
}

export async function refreshPluginMarketplaces(marketplaceId?: string | null, workspaceId?: string | null): Promise<MarketplaceSummary[]> {
  const result = await requestPluginProtocol("plugin.marketplace_refresh", { marketplace_id: marketplaceId ?? null, workspace_id: workspaceId ?? null });
  return (result.marketplaces as MarketplaceSummary[] | undefined) ?? [];
}

export async function removePluginMarketplace(marketplaceId: string, workspaceId?: string | null): Promise<void> {
  await requestPluginProtocol("plugin.marketplace_remove", { marketplace_id: marketplaceId, workspace_id: workspaceId ?? null, confirm: "remove" });
}

export async function installCatalogPlugin(catalogPluginId: string, scope: "personal" | "workspace", workspaceId?: string | null): Promise<PluginSummary> {
  const result = await requestPluginProtocol("plugin.catalog_install", { catalog_plugin_id: catalogPluginId, scope, workspace_id: workspaceId ?? null });
  return result.plugin as PluginSummary;
}

export type ModelTestResult = { success: boolean; elapsed_ms: number; input_tokens: number; output_tokens: number; error?: string | null };
export async function testModelProfile(input: Omit<ModelProfileInput, "id" | "name">): Promise<ModelTestResult> {
  return await client.request("provider.model_test", input) as ModelTestResult;
}

export async function respondPermission(
  toolUseId: string,
  decision: "allow_once" | "always_allow" | "deny_once" | "always_deny",
  runId: string,
  sessionId: string,
): Promise<void> {
  await client.request("permission.respond", {
    tool_use_id: toolUseId,
    decision,
    run_id: runId,
    session_id: sessionId,
  });
}

export async function unstageChanges(workspaceId: string, paths: string[]): Promise<string[]> {
  const result = await client.request("change.unstage", { workspace_id: workspaceId, paths });
  return (result.unstaged_paths as string[] | undefined) ?? [];
}

export async function discardChanges(workspaceId: string, paths: string[]): Promise<string[]> {
  const result = await client.request("change.discard", { workspace_id: workspaceId, paths, confirm: "discard" });
  return (result.discarded_paths as string[] | undefined) ?? [];
}

export async function commitChanges(workspaceId: string, message: string): Promise<string> {
  let result: Record<string, unknown>;
  try {
    result = await client.request("git.commit", { workspace_id: workspaceId, message });
  } catch (reason) {
    if (reason instanceof IpcRequestError && reason.code === -32601) throw new Error(GIT_PROTOCOL_ERROR);
    throw reason;
  }
  return String(result.commit_hash ?? "");
}

export async function gitHistory(workspaceId: string, limit = 100, skip = 0): Promise<GitHistoryPage> {
  let result: Record<string, unknown>;
  try {
    result = await client.request("git.history", { workspace_id: workspaceId, limit, skip });
  } catch (reason) {
    if (reason instanceof IpcRequestError && reason.code === -32601) throw new Error(GIT_PROTOCOL_ERROR);
    throw reason;
  }
  return {
    commits: (result.commits as GitCommitEntry[] | undefined) ?? [],
    has_more: Boolean(result.has_more),
  };
}

export async function listPendingUserQuestions(sessionId?: string | null): Promise<PendingUserQuestion[]> {
  const result = await client.request("question.pending", { session_id: sessionId ?? null });
  return (result.pending as PendingUserQuestion[] | undefined) ?? [];
}

export async function respondUserQuestion(
  pending: Pick<PendingUserQuestion, "rpc_id" | "session_id">,
  answers: UserQuestionAnswer[],
): Promise<void> {
  await client.request("question.respond", {
    rpc_id: pending.rpc_id,
    session_id: pending.session_id,
    answers,
  });
}

export interface ExternalAppInfo {
  id: string;
  name: string;
  icon: string;
  available: boolean;
}

export async function listExternalApps(): Promise<ExternalAppInfo[]> {
  return invoke("list_external_apps");
}

export async function openPathWithApp(path: string, appId: string): Promise<void> {
  await invoke("open_path_with_app", { path, appId });
}
