<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  Archive, ArrowLeft, Bot, CalendarClock, ChevronDown, ChevronRight, CirclePlus, CircleUserRound, Ellipsis, Folder, FolderOpen, FolderSearch,
  Globe2, LayoutDashboard, MessageCircle, Minimize2, Monitor, PanelLeftClose, PanelLeftOpen, Plug,
  Plus, Puzzle, RotateCcw, Settings, ShieldCheck, Square, Trash2, Wrench, X,
} from "@lucide/vue";
import { confirm, open as openDialog } from "@tauri-apps/plugin-dialog";
import { getCurrentWindow } from "@tauri-apps/api/window";
import ProjectInspector from "./components/Inspector/ProjectInspector.vue";
import WorkContextPanel from "./components/Inspector/WorkContextPanel.vue";
import SessionActions from "./components/session/SessionActions.vue";
import ChatPortal, { type ChatView } from "./components/Chat/ChatPortal.vue";
import DiffReview from "./components/Diff/DiffReview.vue";
import ExecutionTimeline from "./components/timeline/ExecutionTimeline.vue";
import type { PermissionDecision, PlanItem, TimelineStep, ToolCallEntry } from "./components/timeline/types";
import {
  applyCcswitchProvider, connectRuntime, createSession, deleteWorkspace, getNativeSettings, getProviderStatus, getRuntimeSettings, listCcswitchProviders, listSessions,
  listWorkspaces, onRuntimeDisconnect, onRuntimeEvent, openWorkspace, replayRun, respondPermission,
  resumeWorkspace, sendPrompt, sessionHistory, setNativeSettings, setRuntimeSettings,
  type CcswitchProvider, type ProviderStatus, type RuntimeSettings, type Session, type Workspace,
} from "./services/sztu-runtime";

type Page = "work" | "chat" | "board" | "skills" | "automations" | "webbridge" | "settings" | "diff";
type ReviewContext = { workspaceId: string; runId: string; paths: string[] };
type RuntimeEvent = Record<string, unknown>;
const page = ref<Page>("work");
const chatView = ref<ChatView>("home");
const sidebarCollapsed = ref(window.innerWidth <= 620);
const connected = ref(false);
const loading = ref(true);
const workspaces = ref<Workspace[]>([]);
const workspace = ref<Workspace | null>(null);
const sessions = ref<Session[]>([]);
const activeId = ref<string | null>(null);
const timeline = ref<Map<number, TimelineStep>>(new Map());
const activeRunId = ref<string | null>(null);
const prompt = ref("");
const sending = ref(false);
const projectMenuOpen = ref(false);
const projectActionsOpen = ref<string | null>(null);
const collapsedProjects = ref(new Set<string>());
const inspectorOpen = ref(true);
const inspectorWidth = ref(Math.min(720, Math.max(280, Number(localStorage.getItem("sztu.inspectorWidth")) || 355)));
const attachedFiles = ref<string[]>([]);
const providerStatus = ref<ProviderStatus | null>(null);
const runtimeSettings = ref<RuntimeSettings | null>(null);
const notifications = ref(localStorage.getItem("sztu.notifications") !== "false");
const autostart = ref(false);
const stayAwake = ref(false);
const nativeSettingsAvailable = ref(false);
const nativeSettingsError = ref("");
const webBridgeAllowed = ref(false);
const currentStepByRun = new Map<string, number>();
const reviewCtx = ref<ReviewContext | null>(null);
const ccswitchOpen = ref(false);
const ccswitchLoading = ref(false);
const ccswitchApplying = ref<string | null>(null);
const ccswitchError = ref("");
const ccswitchProviders = ref<CcswitchProvider[]>([]);

const active = computed(() => sessions.value.find((item) => item.session_id === activeId.value) ?? null);
const activeWorkspace = computed(() => workspaces.value.find((item) => item.workspace_id === active.value?.workspace_id) ?? workspace.value);
const activeWorkspaces = computed(() => workspaces.value.filter((item) => !item.archived));
const archivedProjects = computed(() => workspaces.value.filter((item) => item.archived));
const liveSessions = computed(() => sessions.value.filter((item) => !item.archived));
const archivedSessions = computed(() => sessions.value.filter((item) => item.archived));
const recentSessions = computed(() => liveSessions.value.filter((item) => !item.workspace_id).slice(0, 6));
const projects = computed(() => activeWorkspaces.value.map((item) => ({ ...item, tasks: liveSessions.value.filter((task) => task.workspace_id === item.workspace_id).slice(0, 5) })));
const orderedTimeline = computed(() => [...timeline.value.values()].sort((left, right) => left.step - right.step));
// 工作区布局：右侧文件面板宽度走可拖拽的 CSS 变量，收起时退化为单列
const workLayoutStyle = computed(() => {
  if (!inspectorOpen.value || !activeWorkspace.value) return { gridTemplateColumns: "minmax(0, 1fr)" };
  return { gridTemplateColumns: `minmax(0, 1fr) 6px ${inspectorWidth.value}px` };
});
// 拖拽分割线调整左右面板宽度比，并限制最小/最大宽度
function startDividerDrag(event: MouseEvent) {
  event.preventDefault();
  const startX = event.clientX;
  const startWidth = inspectorWidth.value;
  const container = (event.currentTarget as HTMLElement).parentElement;
  const maxWidth = Math.max(280, (container?.clientWidth ?? 1200) - 320); // 左侧对话区至少保留 320
  const minWidth = 280;
  function onMove(ev: MouseEvent) {
    inspectorWidth.value = Math.min(maxWidth, Math.max(minWidth, startWidth + (startX - ev.clientX)));
  }
  function onUp() {
    localStorage.setItem("sztu.inspectorWidth", String(inspectorWidth.value));
    document.body.style.cursor = "";
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
  }
  document.body.style.cursor = "col-resize";
  document.addEventListener("mousemove", onMove);
  document.addEventListener("mouseup", onUp);
}
const skillSuggestions = computed(() => {
  const match = prompt.value.match(/^\/([^\s]*)$/);
  if (!match) return [];
  const query = match[1].toLowerCase();
  return (providerStatus.value?.skills ?? []).filter((skill) => skill.name.toLowerCase().includes(query)).slice(0, 8);
});

type HistoryBlock = Record<string, unknown>;

function entryRole(entry: unknown) { return String((entry as { role?: unknown })?.role ?? "assistant").toLowerCase(); }
function isRecord(value: unknown): value is HistoryBlock { return typeof value === "object" && value !== null && !Array.isArray(value); }
function historyBlocks(entry: unknown): HistoryBlock[] {
  const content = (entry as { content?: unknown })?.content;
  const values = Array.isArray(content) ? content : [content];
  return values.flatMap((value) => {
    if (typeof value === "string") {
      try {
        const parsed: unknown = JSON.parse(value);
        if (isRecord(parsed) && typeof parsed.type === "string") return [parsed];
      } catch { /* Ordinary text is not JSON. */ }
      return value ? [{ type: "text", text: value }] : [];
    }
    return isRecord(value) ? [value] : [];
  });
}
function blockText(block: HistoryBlock): string {
  if (typeof block.text === "string") return block.text;
  if (typeof block.content === "string") return block.content;
  return "";
}
function blockOutput(block: HistoryBlock): string {
  if (typeof block.content === "string") return block.content;
  if (Array.isArray(block.content)) return block.content.map((item) => typeof item === "string" ? item : JSON.stringify(item)).join("\n");
  return block.content ? JSON.stringify(block.content) : "";
}
function emptyStep(step: number): TimelineStep { return { step, status: "thinking", tokens: [], toolCalls: [] }; }
function setStep(step: number, updater: (current: TimelineStep) => TimelineStep) {
  const next = new Map(timeline.value);
  next.set(step, updater(next.get(step) ?? emptyStep(step)));
  timeline.value = next;
}
function stepFor(event: RuntimeEvent): number {
  const runId = String(event.run_id ?? activeRunId.value ?? "");
  const existing = currentStepByRun.get(runId);
  if (existing !== undefined) return existing;
  const fallback = Math.max(1, ...timeline.value.keys(), 0);
  currentStepByRun.set(runId, fallback);
  return fallback;
}
function addUserMessage(content: string) {
  const step = Math.max(0, ...timeline.value.keys()) + 1;
  setStep(step, (current) => ({ ...current, status: "thinking", userMessage: content }));
  return step;
}
function hydrateTimeline(messages: unknown[], runId?: string | null) {
  const next = new Map<number, TimelineStep>();
  let step = 0;
  for (const message of messages) {
    const role = entryRole(message);
    const blocks = historyBlocks(message);
    const text = blocks.filter((block) => String(block.type) === "text").map(blockText).filter(Boolean).join("\n");
    const toolResults = blocks.filter((block) => String(block.type) === "tool_result");
    if (role === "user" && toolResults.length && !text) {
      if (!step) step = 1;
      const current = next.get(step) ?? { ...emptyStep(step), status: "done" };
      const completed = current.toolCalls.map((call) => {
        const result = toolResults.find((item) => String(item.tool_use_id) === call.id);
        return result ? { ...call, status: result.is_error ? "failed" as const : "done" as const, output: blockOutput(result), error: result.is_error ? blockOutput(result) : undefined } : call;
      });
      next.set(step, { ...current, status: "done", runId: runId ?? current.runId, toolCalls: completed });
      continue;
    }
    if (role === "user") {
      step += 1;
      next.set(step, { ...emptyStep(step), status: "done", runId: runId ?? undefined, userMessage: text });
      continue;
    }
    if (!step) step = 1;
    const current = next.get(step) ?? { ...emptyStep(step), status: "done" };
    const thinking = blocks.filter((block) => String(block.type) === "thinking").map((block) => typeof block.thinking === "string" ? block.thinking : "").filter(Boolean).join("\n\n");
    const calls: ToolCallEntry[] = blocks.filter((block) => String(block.type) === "tool_use").map((block) => ({
      id: String(block.id ?? block.tool_use_id ?? crypto.randomUUID()),
      name: String(block.name ?? "工具调用"),
      params: isRecord(block.input) ? block.input : isRecord(block.params) ? block.params : {},
      status: "done",
    }));
    next.set(step, {
      ...current,
      status: "done",
      runId: runId ?? current.runId,
      thinking: [current.thinking, thinking].filter(Boolean).join("\n\n") || undefined,
      finalText: [current.finalText, text].filter(Boolean).join("\n\n") || undefined,
      toolCalls: [...current.toolCalls, ...calls],
    });
  }
  timeline.value = next;
}function applyRuntimeEvent(event: RuntimeEvent) {
  const type = String(event.type ?? "");
  const runId = String(event.run_id ?? "");
  const relatedRunId = String(event.parent_run_id ?? runId);
  const timelineEvent = event.parent_run_id ? { ...event, run_id: relatedRunId } : event;
  if (type === "run.started" && !activeRunId.value && sending.value) activeRunId.value = runId;
  if (type === "session.created" || type === "session.closed" || type === "session.waiting_for_input") {
    void refreshIndex();
    return;
  }
  // 运行事件没有 session_id，只消费由当前会话发送消息返回的 run_id，避免串到其他任务。
  if (!relatedRunId || relatedRunId !== activeRunId.value) return;
  if (type === "step.started") {
    const step = Number(event.step);
    currentStepByRun.set(runId, step);
    setStep(step, (current) => ({ ...current, status: "thinking", runId }));
    return;
  }
  if (type === "llm.token") {
    const step = stepFor(timelineEvent);
    setStep(step, (current) => ({ ...current, status: "thinking", tokens: [...current.tokens, String(event.token ?? "")] }));
    return;
  }
  if (type === "llm.thinking") {
    const step = stepFor(timelineEvent);
    setStep(step, (current) => ({ ...current, thinking: `${current.thinking ?? ""}${String(event.thinking ?? "")}` }));
    return;
  }
  if (type === "llm.usage") {
    const step = stepFor(timelineEvent);
    setStep(step, (current) => ({ ...current, usage: { inputTokens: Number(event.input_tokens ?? 0), outputTokens: Number(event.output_tokens ?? 0), contextPct: Number(event.context_pct ?? 0), model: String(event.model ?? "") } }));
    return;
  }
  if (type === "tool.call_started") {
    const step = stepFor(timelineEvent);
    const call: ToolCallEntry = { id: String(event.tool_use_id), name: String(event.tool_name), params: (event.params as Record<string, unknown>) ?? {}, status: "running" };
    setStep(step, (current) => ({ ...current, status: "acting", toolCalls: [...current.toolCalls.filter((item) => item.id !== call.id), call] }));
    return;
  }
  if (type === "tool.call_finished" || type === "tool.call_failed") {
    const step = stepFor(timelineEvent);
    const callId = String(event.tool_use_id);
    setStep(step, (current) => ({ ...current, status: "observing", toolCalls: current.toolCalls.map((call) => call.id !== callId ? call : { ...call, status: type === "tool.call_finished" ? "done" : "failed", output: type === "tool.call_finished" ? String(event.output ?? "") : undefined, error: type === "tool.call_failed" ? String(event.error_message ?? "工具调用失败") : undefined, elapsedMs: Number(event.elapsed_ms ?? 0) }) }));
    return;
  }
  if (type === "permission.requested") {
    const step = stepFor(timelineEvent);
    const toolUseId = String(event.tool_use_id);
    setStep(step, (current) => ({ ...current, status: "acting", permission: { toolUseId, toolName: String(event.tool_name), preview: String(event.param_preview ?? "等待确认"), status: "pending" }, toolCalls: current.toolCalls.map((call) => call.id === toolUseId ? { ...call, status: "awaiting_permission" } : call) }));
    return;
  }
  if (type === "permission.granted" || type === "permission.denied") {
    const toolUseId = String(event.tool_use_id);
    for (const step of timeline.value.keys()) setStep(step, (current) => current.permission?.toolUseId === toolUseId ? { ...current, permission: { ...current.permission, status: type === "permission.granted" ? "granted" : "denied" } } : current);
    return;
  }
  if (type === "plan.updated") {
    const step = stepFor(timelineEvent);
    setStep(step, (current) => ({ ...current, plan: (event.items as PlanItem[] | undefined) ?? [] }));
    return;
  }
  if (type === "test.result") {
    const step = stepFor(timelineEvent);
    setStep(step, (current) => ({ ...current, tests: [...(current.tests ?? []), { status: String(event.status) === "passed" ? "passed" : "failed", summary: String(event.summary ?? "") }] }));
    return;
  }
  if (type === "change.applied") {
    const step = stepFor(timelineEvent);
    setStep(step, (current) => ({ ...current, changes: [...(current.changes ?? []), { paths: (event.paths as string[] | undefined) ?? [], workspacePath: String(event.workspace_path ?? "") }] }));
    return;
  }
  if (type === "log.line") {
    const step = stepFor(timelineEvent);
    setStep(step, (current) => ({ ...current, logs: [...(current.logs ?? []).slice(-99), { level: String(event.level ?? "INFO"), source: String(event.source ?? "daemon"), message: String(event.message ?? "") }] }));
    return;
  }
  if (type === "subagent.started") {
    const step = stepFor(timelineEvent);
    setStep(step, (current) => ({ ...current, subagents: [...(current.subagents ?? []).filter((agent) => agent.runId !== runId), { runId, description: String(event.description ?? ""), status: "running" }] }));
    return;
  }
  if (type === "subagent.finished") {
    for (const step of timeline.value.keys()) {
      setStep(step, (current) => ({ ...current, subagents: current.subagents?.map((agent) => agent.runId === runId ? { ...agent, status: String(event.status) === "success" ? "success" : "failed" } : agent) }));
    }
    return;
  }
  if (type === "skill.invoked") {
    const step = stepFor(timelineEvent);
    setStep(step, (current) => ({ ...current, skills: [...(current.skills ?? []), { name: String(event.skill_name ?? ""), arguments: String(event.arguments ?? "") }] }));
    return;
  }
  if (type === "step.finished") {
    const step = Number(event.step ?? stepFor(timelineEvent));
    setStep(step, (current) => ({ ...current, status: current.status === "acting" ? "observing" : "done", finalText: current.finalText || current.tokens.join("") }));
    return;
  }
  if (type === "run.finished") {
    for (const step of timeline.value.keys()) setStep(step, (current) => current.status === "done" ? current : { ...current, status: String(event.status) === "success" ? "done" : "failed", finalText: current.finalText || current.tokens.join("") });
    if (runId === activeRunId.value) activeRunId.value = null;
    return;
  }
}

async function refreshIndex(loadHistory = false) {
  connected.value = await connectRuntime();
  if (!connected.value) { loading.value = false; return; }
  const [nextWorkspaces, nextSessions, nextSettings, nextProvider] = await Promise.all([listWorkspaces(), listSessions(), getRuntimeSettings(), getProviderStatus()]);
  workspaces.value = nextWorkspaces; sessions.value = nextSessions; runtimeSettings.value = nextSettings; providerStatus.value = nextProvider;
  workspace.value ??= nextWorkspaces[0] ?? null;
  activeId.value ??= nextSessions.find((item) => !item.archived)?.session_id ?? null;
  if (loadHistory && activeId.value) {
    const latestRunId = sessions.value.find((item) => item.session_id === activeId.value)?.latest_run_id ?? null;
    hydrateTimeline(await sessionHistory(activeId.value), latestRunId);
  }
  loading.value = false;
}
function beginTask(project: Workspace | null = workspace.value) {
  if (!connected.value || sending.value) return;
  projectActionsOpen.value = null;
  workspace.value = project;
  activeId.value = null;
  currentStepByRun.clear();
  timeline.value = new Map();
  activeRunId.value = null;
  page.value = "work";
  prompt.value = "";
}
async function submitTask(content: string, project: Workspace | null = workspace.value) {
  const trimmed = content.trim();
  if (!trimmed || !connected.value || sending.value) return;
  sending.value = true;
  try {
    if (!activeId.value) {
      const sessionId = await createSession(project);
      activeId.value = sessionId;
      currentStepByRun.clear();
      timeline.value = new Map();
      activeRunId.value = null;
      page.value = "work";
      prompt.value = "";
      addUserMessage(trimmed);
      activeRunId.value = await sendPrompt(sessionId, trimmed);
      await refreshIndex(false);
    } else {
      if (active.value?.archived || active.value?.status === "closed") return;
      prompt.value = "";
      addUserMessage(trimmed);
      activeRunId.value = await sendPrompt(activeId.value, trimmed);
    }
  } finally { sending.value = false; }
}
async function chooseTask(id: string) {
  activeId.value = id;
  currentStepByRun.clear();
  runStepBase.clear();
  // 完整历史已含各轮内容，直接 hydrate 展示；replay 会与各 run 的 step 编号冲突导致旧日志混排
  const latestRunId = sessions.value.find((item) => item.session_id === id)?.latest_run_id ?? null;
  hydrateTimeline(await sessionHistory(id), latestRunId);
  activeRunId.value = latestRunId;
  page.value = "work";
}
async function chooseWorkspace(item: Workspace) { workspace.value = item; projectMenuOpen.value = false; const matching = liveSessions.value.find((session) => session.workspace_id === item.workspace_id); if (matching) await chooseTask(matching.session_id); }
function isProjectCollapsed(workspaceId: string) { return collapsedProjects.value.has(workspaceId); }
function toggleProject(workspaceId: string) {
  const next = new Set(collapsedProjects.value);
  if (next.has(workspaceId)) next.delete(workspaceId);
  else next.add(workspaceId);
  collapsedProjects.value = next;
  projectActionsOpen.value = null;
}
async function createProjectTask(item: Workspace) {
  projectActionsOpen.value = null;
  beginTask(item);
}
async function showProjectFiles(item: Workspace) {
  projectActionsOpen.value = null;
  inspectorOpen.value = true;
  workspace.value = item;
  const matching = liveSessions.value.find((session) => session.workspace_id === item.workspace_id);
  if (matching) await chooseTask(matching.session_id);
  else beginTask(item);
}
async function deleteProject(item: Workspace) {
  projectActionsOpen.value = null;
  const ok = await confirm(`删除项目「${item.name}」？将同时删除该项目的会话与上下文，磁盘文件保留。`, { title: "删除项目", kind: "warning" });
  if (!ok) return;
  try {
    await deleteWorkspace(item.workspace_id);
  } catch (error) {
    // 删除失败（如命中安全护栏）时保留列表并提示
    window.alert(error instanceof Error ? error.message : String(error));
    return;
  }
  workspaces.value = workspaces.value.filter((entry) => entry.workspace_id !== item.workspace_id);
  if (workspace.value?.workspace_id === item.workspace_id) {
    workspace.value = workspaces.value[0] ?? null;
    activeId.value = null;
    timeline.value = new Map();
  }
  await refreshIndex(false);
}
async function resumeProject(item: Workspace) {
  projectActionsOpen.value = null;
  const resumed = await resumeWorkspace(item.workspace_id);
  workspaces.value = workspaces.value.map((entry) => entry.workspace_id === resumed.workspace_id ? resumed : entry);
  workspace.value = resumed;
}
function handleSessionClosed(sessionId: string) {
  if (sessionId === activeId.value) closeActiveSession();
  else void refreshIndex(false);
}
async function submit() {
  const content = prompt.value.trim();
  if (!content || sending.value) return;
  if (activeId.value && (active.value?.archived || active.value?.status === "closed")) return;
  await submitTask(content, workspace.value);
}
// 回车直接发送；Ctrl/Shift/Alt + 回车保留默认换行行为，且忽略中文输入法候选确认
function onComposerKeydown(event: KeyboardEvent) {
  if (event.key !== "Enter" || event.isComposing) return;
  if (event.shiftKey || event.ctrlKey || event.metaKey || event.altKey) return;
  event.preventDefault();
  void submit();
}
async function decidePermission(toolUseId: string, decision: PermissionDecision) { await respondPermission(toolUseId, decision); }
// 撤销后清除该 run 的全部改动，使变更卡片随之消失
function handleReverted(runId: string) {
  const next = new Map(timeline.value);
  for (const [step, item] of next) {
    if (item.runId === runId) next.set(step, { ...item, changes: [] });
  }
  timeline.value = next;
  void refreshIndex(false);
}
// 进入代码变更审核页
function handleReview(ctx: ReviewContext) {
  reviewCtx.value = ctx;
  page.value = "diff";
}
function closeReview() {
  reviewCtx.value = null;
  page.value = "work";
  void refreshIndex(false);
}
async function openLocalProject() {
  const selected = await openDialog({ directory: true, multiple: false, title: "打开本地项目" });
  if (typeof selected !== "string") return;
  workspace.value = await openWorkspace(selected);
  await refreshIndex(false);
  beginTask(workspace.value);
}
async function selectAttachments() {
  const selected = await openDialog({ directory: false, multiple: true, title: "添加附件" });
  const paths = typeof selected === "string" ? [selected] : selected ?? [];
  attachedFiles.value = [...new Set([...attachedFiles.value, ...paths])];
  if (paths.length) prompt.value += (prompt.value ? "\n\n" : "") + "附件：\n" + paths.map((path) => "- " + path).join("\n");
}
function chooseSkill(name: string) { prompt.value = "/" + name + " "; }
function closeActiveSession() { activeId.value = null; timeline.value = new Map(); activeRunId.value = null; void refreshIndex(false); }
async function loadNativeSettings() {
  try {
    const settings = await getNativeSettings();
    autostart.value = settings.autostart;
    stayAwake.value = settings.stay_awake;
    nativeSettingsAvailable.value = settings.supported;
    nativeSettingsError.value = "";
  } catch {
    nativeSettingsAvailable.value = false;
  }
}
async function toggleAutostart(event: Event) {
  const enabled = (event.target as HTMLInputElement).checked;
  try {
    const settings = await setNativeSettings({ autostart: enabled });
    autostart.value = settings.autostart;
    nativeSettingsError.value = "";
  } catch (error) {
    nativeSettingsError.value = error instanceof Error ? error.message : String(error);
    (event.target as HTMLInputElement).checked = autostart.value;
  }
}
async function toggleStayAwake(event: Event) {
  const enabled = (event.target as HTMLInputElement).checked;
  try {
    const settings = await setNativeSettings({ stayAwake: enabled });
    stayAwake.value = settings.stay_awake;
    nativeSettingsError.value = "";
  } catch (error) {
    nativeSettingsError.value = error instanceof Error ? error.message : String(error);
    (event.target as HTMLInputElement).checked = stayAwake.value;
  }
}
async function choosePermissionMode(value: RuntimeSettings["permission_mode"]) { const result = await setRuntimeSettings({ permission_mode: value }); if (result) runtimeSettings.value = result; }
async function chooseModel(event: Event) { const model = (event.target as HTMLInputElement).value.trim(); if (!model) return; const result = await setRuntimeSettings({ model }); if (result) runtimeSettings.value = result; }
async function chooseProvider(event: Event) { const provider = (event.target as HTMLSelectElement).value as RuntimeSettings["provider"]; const result = await setRuntimeSettings({ provider }); if (result) runtimeSettings.value = result; }
// 加载本机 cc-switch 中可导入的供应商列表并展开面板
async function loadCcswitchProviders() {
  ccswitchLoading.value = true;
  ccswitchError.value = "";
  try {
    ccswitchProviders.value = await listCcswitchProviders();
    ccswitchOpen.value = true;
  } catch (error) {
    ccswitchError.value = error instanceof Error ? error.message : String(error);
  } finally {
    ccswitchLoading.value = false;
  }
}
// 应用选中的 cc-switch 供应商并刷新运行时设置与状态
async function useCcswitchProvider(providerId: string) {
  ccswitchApplying.value = providerId;
  ccswitchError.value = "";
  try {
    const settings = await applyCcswitchProvider(providerId);
    if (settings) runtimeSettings.value = settings;
    providerStatus.value = await getProviderStatus();
  } catch (error) {
    ccswitchError.value = error instanceof Error ? error.message : String(error);
  } finally {
    ccswitchApplying.value = null;
  }
}
function openPage(next: Page) { page.value = next; projectMenuOpen.value = false; if (next === "chat") chatView.value = "home"; }
async function submitChat(content: string) { await submitTask(content, null); page.value = "chat"; chatView.value = "home"; }
async function minimizeWindow() { await getCurrentWindow().minimize(); }
async function toggleMaximizeWindow() { await getCurrentWindow().toggleMaximize(); }
async function closeWindow() { await getCurrentWindow().close(); }
function toggleSidebar() { sidebarCollapsed.value = !sidebarCollapsed.value; }
function handleGlobalShortcut(event: KeyboardEvent) {
  if (event.ctrlKey && event.key.toLowerCase() === "b") { event.preventDefault(); toggleSidebar(); }
}
let stopEvents: (() => void) | undefined;
let stopDisconnect: (() => void) | undefined;
onMounted(() => {
  window.addEventListener("keydown", handleGlobalShortcut);
  stopDisconnect = onRuntimeDisconnect(() => { connected.value = false; });
  void loadNativeSettings();
  void refreshIndex(true).then(() => { stopEvents = onRuntimeEvent(applyRuntimeEvent); });
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleGlobalShortcut);
  stopEvents?.();
  stopDisconnect?.();
});
watch(page, (next) => { if (next === "skills" || next === "settings") void refreshIndex(false); });
watch(notifications, (enabled) => localStorage.setItem("sztu.notifications", String(enabled)));
</script>

<template>
  <div class="kimi-shell" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
    <header class="kimi-titlebar">
      <div class="nav-toggle-wrap">
        <button class="nav-toggle" type="button" aria-controls="primary-navigation" :aria-expanded="!sidebarCollapsed" :aria-label="sidebarCollapsed ? '\u5c55\u5f00\u5bfc\u822a' : '\u6536\u8d77\u5bfc\u822a'" @click="toggleSidebar">
          <PanelLeftOpen v-if="sidebarCollapsed" :size="16" :stroke-width="1.8" />
          <PanelLeftClose v-else :size="16" :stroke-width="1.8" />
        </button>
        <div class="nav-toggle-tooltip" role="tooltip"><span>{{ sidebarCollapsed ? '\u5c55\u5f00\u5bfc\u822a' : '\u6536\u8d77\u5bfc\u822a' }}</span><kbd>Ctrl</kbd><kbd>B</kbd></div>
      </div>
      <div class="titlebar-drag-region" data-tauri-drag-region @dblclick="toggleMaximizeWindow" />
      <div class="window-actions" aria-label="Window controls">
        <button class="window-action" type="button" title="Minimize" aria-label="Minimize window" @click="minimizeWindow"><Minimize2 :size="15" :stroke-width="1.8" /></button>
        <button class="window-action" type="button" title="Maximize or restore" aria-label="Maximize or restore window" @click="toggleMaximizeWindow"><Square :size="13" :stroke-width="1.8" /></button>
        <button class="window-action window-action--close" type="button" title="Close" aria-label="Close window" @click="closeWindow"><X :size="17" :stroke-width="1.8" /></button>
      </div>
    </header>

    <aside id="primary-navigation" class="kimi-sidebar" :class="{ 'chat-sidebar': page === 'chat' }">
      <div class="mode-switch" role="tablist" aria-label="工作模式">
        <button :class="{ active: page !== 'chat' }" @click="openPage('work')"><Monitor :size="15" />Work</button>
        <button :class="{ active: page === 'chat' }" @click="openPage('chat')"><MessageCircle :size="15" />Chat</button>
      </div>

      <template v-if="page === 'chat'">
        <nav class="primary-nav" aria-label="Chat navigation">
          <button :class="{ active: chatView === 'home' }" @click="chatView = 'home'"><CirclePlus :size="18" />新建会话 <kbd>Ctrl</kbd><kbd>K</kbd></button>
          <button :class="{ active: chatView === 'plugins' }" @click="chatView = 'plugins'"><Plug :size="17" />插件</button>
          <button :class="{ active: chatView === 'automations' }" @click="chatView = 'automations'"><CalendarClock :size="17" />定时任务</button>
          <button :class="{ active: chatView === 'ppt' }" @click="chatView = 'ppt'"><LayoutDashboard :size="17" />PPT</button>
          <button :class="{ active: chatView === 'cluster' }" @click="chatView = 'cluster'"><Bot :size="17" />集群</button>
          <button :class="{ active: chatView === 'research' }" @click="chatView = 'research'"><FolderSearch :size="17" />深度研究</button>
          <button :class="{ active: chatView === 'document' }" @click="chatView = 'document'"><Folder :size="17" />文档</button>
          <button :class="{ active: chatView === 'website' }" @click="chatView = 'website'"><Globe2 :size="17" />网站</button>
          <button :class="{ active: chatView === 'sheet' }" @click="chatView = 'sheet'"><LayoutDashboard :size="17" />表格</button>
          <button @click="chatView = 'plugins'"><Ellipsis :size="17" />更多</button>
        </nav>
        <section class="side-section chat-project-new"><span class="side-label">项目</span><button class="project-row" @click="chatView = 'project'"><Plus :size="17" />新建项目</button></section>
        <section class="side-section conversations"><span class="side-label">对话</span><div v-for="task in recentSessions" :key="task.session_id" class="sidebar-session conversation-session"><button class="conversation-row" :class="{ active: task.session_id === activeId }" @click="chooseTask(task.session_id)"><i :class="{ running: task.status === 'active' }" /><span>{{ task.title || 'Untitled task' }}</span></button></div><p v-if="!recentSessions.length" class="side-empty">历史对话会显示在这里</p></section>
      </template>
      <template v-else><nav class="primary-nav" aria-label="Primary navigation">
        <button :class="{ active: page === 'work' }" @click="beginTask()"><CirclePlus :size="18" />新建任务 <kbd>Ctrl</kbd><kbd>K</kbd></button>
        <button :class="{ active: page === 'board' }" @click="openPage('board')"><LayoutDashboard :size="17" />看板</button>
        <button :class="{ active: page === 'skills' }" @click="openPage('skills')"><Plug :size="17" />插件</button>
        <button :class="{ active: page === 'automations' }" @click="openPage('automations')"><CalendarClock :size="17" />定时任务</button>
        <button :class="{ active: page === 'webbridge' }" @click="openPage('webbridge')"><Globe2 :size="17" />WebBridge</button>
      </nav>

      <section class="side-section project-tree">
        <span class="side-label side-label--action">项目<button title="打开本地目录" aria-label="打开本地目录" @click="openLocalProject"><FolderOpen :size="14" /></button></span>
        <div v-for="item in projects" :key="item.workspace_id" class="project-group">
          <div class="project-row-shell" :class="{ active: item.workspace_id === workspace?.workspace_id }">
            <button class="project-collapse" :title="isProjectCollapsed(item.workspace_id) ? '展开项目' : '收起项目'" :aria-expanded="!isProjectCollapsed(item.workspace_id)" @click="toggleProject(item.workspace_id)">
              <ChevronRight :size="13" :class="{ expanded: !isProjectCollapsed(item.workspace_id) }" />
            </button>
            <button class="project-row" @click="chooseWorkspace(item)"><Folder :size="16" /><span>{{ item.name }}</span></button>
            <button class="side-item-action" title="项目操作" aria-label="项目操作" @click="projectActionsOpen = projectActionsOpen === item.workspace_id ? null : item.workspace_id"><Ellipsis :size="16" /></button>
            <div v-if="projectActionsOpen === item.workspace_id" class="project-action-menu">
              <button @click="createProjectTask(item)"><Plus :size="14" />新建任务</button>
              <button @click="showProjectFiles(item)"><FolderSearch :size="14" />查看项目文件</button>
              <button @click="deleteProject(item)"><Trash2 :size="14" />删除项目</button>
              <button @click="toggleProject(item.workspace_id)"><ChevronRight :size="14" :class="{ expanded: !isProjectCollapsed(item.workspace_id) }" />{{ isProjectCollapsed(item.workspace_id) ? '展开项目' : '收起项目' }}</button>
            </div>
          </div>
          <div class="project-task-list" :class="{ collapsed: isProjectCollapsed(item.workspace_id) }">
            <div class="project-task-list__inner">
              <div v-for="task in item.tasks" :key="task.session_id" class="sidebar-session project-session">
                <button class="project-task" :class="{ active: task.session_id === activeId }" @click="chooseTask(task.session_id)">{{ task.title || 'Untitled task' }}</button>
                <SessionActions :session="task" @changed="refreshIndex(false)" @closed="handleSessionClosed(task.session_id)" />
              </div>
              <p v-if="!item.tasks.length" class="project-empty">暂无任务</p>
            </div>
          </div>
        </div>
        <p v-if="!projects.length" class="side-empty">打开本地工作区后会显示在这里</p>
      </section>
      <section v-if="archivedProjects.length" class="side-section project-tree archived-projects">
        <span class="side-label">已归档项目</span>
        <div v-for="item in archivedProjects" :key="item.workspace_id" class="project-group">
          <div class="project-row-shell">
            <button class="project-row archived-project-row" title="恢复项目" aria-label="恢复项目" @click="resumeProject(item)"><Archive :size="16" /><span>{{ item.name }}</span></button>
            <button class="side-item-action" title="项目操作" aria-label="项目操作" @click="projectActionsOpen = projectActionsOpen === item.workspace_id ? null : item.workspace_id"><Ellipsis :size="16" /></button>
            <div v-if="projectActionsOpen === item.workspace_id" class="project-action-menu">
              <button @click="resumeProject(item)"><RotateCcw :size="14" />恢复项目</button>
              <button @click="deleteProject(item)"><Trash2 :size="14" />删除项目</button>
            </div>
          </div>
        </div>
      </section>
      <section class="side-section conversations">
        <span class="side-label side-label--action">对话<button title="新建对话" aria-label="新建对话" @click="beginTask(null)"><Plus :size="14" /></button></span>
        <div v-for="task in recentSessions" :key="task.session_id" class="sidebar-session conversation-session">
          <button class="conversation-row" :class="{ active: task.session_id === activeId }" @click="chooseTask(task.session_id)"><i :class="{ running: task.status === 'active' }" /><span>{{ task.title || 'Untitled task' }}</span></button>
          <SessionActions :session="task" @changed="refreshIndex(false)" @closed="handleSessionClosed(task.session_id)" />
        </div>
        <p v-if="!recentSessions.length" class="side-empty">历史对话会显示在这里</p>
      </section>

      </template>

      <footer class="sidebar-footer">
        <button class="account"><CircleUserRound :size="23" /><span><b>SztuCode</b><small>{{ connected ? 'Connected' : 'Offline' }}</small></span></button>
        <button class="settings-link" @click="openPage('settings')"><Settings :size="16" /></button>
      </footer>
    </aside>

    <main class="kimi-main" :class="{ 'chat-main': page === 'chat' }">
      <template v-if="page === 'work'">
        <section v-if="active" class="work-page">
          <header class="work-header">
            <button class="workspace-trigger" @click="projectMenuOpen = !projectMenuOpen"><span>{{ activeWorkspace?.name || '未选择项目' }}</span><ChevronDown :size="14" /></button>
            <div v-if="projectMenuOpen" class="project-popover"><button v-for="item in activeWorkspaces" :key="item.workspace_id" @click="chooseWorkspace(item)">{{ item.name }}<small>{{ item.path }}</small></button></div>
            <div class="work-header__tools">
              <SessionActions :session="active" @changed="refreshIndex(false)" @closed="closeActiveSession" />
              <button title="项目文件" :class="{ active: inspectorOpen }" @click="inspectorOpen = !inspectorOpen"><Folder :size="18" /></button>
            </div>
          </header>
          <div class="work-layout" :class="{ 'no-inspector': !inspectorOpen || !activeWorkspace }" :style="workLayoutStyle">
            <section class="task-canvas">
              <div class="task-conversation">
                <div class="task-stream">
                  <div v-if="!orderedTimeline.length" class="task-intro"><span class="agent-orb"><Bot :size="20" /></span><p>任务已经创建。告诉 SztuCode 你希望完成什么，它会在这里展示计划、工具调用与最终结果。</p></div>
                  <ExecutionTimeline :steps="orderedTimeline" :workspace-id="activeWorkspace?.workspace_id ?? undefined" @decide="decidePermission" @reverted="handleReverted" @review="handleReview" />
                </div>
                <form class="kimi-composer" @submit.prevent="submit">
                  <div v-if="skillSuggestions.length" class="skill-completions"><button v-for="skill in skillSuggestions" :key="skill.name" type="button" @click="chooseSkill(skill.name)"><b>/{{ skill.name }}</b><span>{{ skill.description }}</span></button></div>
                  <textarea v-model="prompt" :disabled="active.archived || active.status === 'closed'" :placeholder="active.archived || active.status === 'closed' ? '恢复会话后继续' : '输入消息，键入 / 调用技能'" rows="3" @keydown="onComposerKeydown" />
                  <div v-if="attachedFiles.length" class="attachment-strip"><span v-for="file in attachedFiles" :key="file">{{ file.split(/[\\/]/).pop() }}</span></div>
                  <div class="composer-toolbar"><button type="button" class="round" title="添加附件" @click="selectAttachments"><Plus :size="18" /></button><button type="button" class="permission" @click="choosePermissionMode(runtimeSettings?.permission_mode === 'auto' ? 'normal' : 'auto')"><ShieldCheck :size="15" />{{ runtimeSettings?.permission_mode === 'auto' ? '全部允许' : '标准审批' }}<ChevronDown :size="13" /></button><span class="model-label"><i :class="{ online: providerStatus?.ready_for_next_run }" />{{ runtimeSettings?.model || '未配置模型' }}</span><button class="send" type="submit" :disabled="!prompt.trim() || sending || active.archived || active.status === 'closed'">↑</button></div>
                </form>
              </div>
              <WorkContextPanel :steps="orderedTimeline" :attachments="attachedFiles" :workspace-name="activeWorkspace?.name" :workspace-path="activeWorkspace?.path" />
            </section>
            <template v-if="inspectorOpen && activeWorkspace">
              <div class="layout-divider" role="separator" aria-orientation="vertical" title="拖拽调整面板宽度" @mousedown="startDividerDrag" />
              <ProjectInspector :workspace-id="activeWorkspace.workspace_id" :run-id="active.latest_run_id" />
            </template>
          </div>
        </section>
        <section v-else class="landing-page">
          <div class="kimi-hero"><span class="mascot"><Bot :size="32" /></span><div><h1>让 SztuCode 帮你完成任务</h1><a>本地开发版</a></div></div>
          <form class="kimi-composer landing-composer" @submit.prevent="submit()">
            <div v-if="skillSuggestions.length" class="skill-completions"><button v-for="skill in skillSuggestions" :key="skill.name" type="button" @click="chooseSkill(skill.name)"><b>/{{ skill.name }}</b><span>{{ skill.description }}</span></button></div>
            <textarea v-model="prompt" placeholder="输入消息，键入 / 调用技能" rows="3" @keydown="onComposerKeydown" />
            <div class="composer-toolbar"><button type="button" class="round" title="添加附件" @click="selectAttachments"><Plus :size="18" /></button><button type="button" class="permission"><ShieldCheck :size="15" />标准审批<ChevronDown :size="13" /></button><span /><button class="send" type="submit" :disabled="!connected">↑</button></div>
            <button type="button" class="composer-project" @click="openLocalProject"><FolderOpen :size="15" />打开本地目录作为项目</button>
          </form>
        </section>
      </template>

      <section v-else-if="page === 'chat'"><ChatPortal :view="chatView" :connected="connected" @submit="submitChat" @navigate="chatView = $event" @open-project="openLocalProject" /></section>

      <section v-else-if="page === 'diff'" class="diff-page"><DiffReview v-if="reviewCtx" :workspace-id="reviewCtx.workspaceId" :run-id="reviewCtx.runId" :paths="reviewCtx.paths" @close="closeReview" @changed="refreshIndex(false)" /></section>

      <section v-else-if="page === 'board'" class="simple-page board-page">
        <header><div><h1>会话</h1><p>管理本地任务、归档与已关闭会话</p></div><button class="outline-button" @click="refreshIndex(false)">刷新</button></header>
        <div class="session-board">
          <article v-for="task in liveSessions" :key="task.session_id" :class="{ pinned: task.pinned }"><button @click="chooseTask(task.session_id)"><b>{{ task.title || 'Untitled task' }}</b><span>{{ task.status }} · {{ task.updated_at }}</span></button><SessionActions :session="task" @changed="refreshIndex(false)" @closed="refreshIndex(false)" /></article>
          <h2 v-if="archivedSessions.length">已归档</h2>
          <article v-for="task in archivedSessions" :key="task.session_id" class="archived"><button @click="chooseTask(task.session_id)"><b>{{ task.title || 'Untitled task' }}</b><span>{{ task.updated_at }}</span></button><SessionActions :session="task" @changed="refreshIndex(false)" @closed="refreshIndex(false)" /></article>
          <div v-if="!sessions.length" class="empty-state"><LayoutDashboard :size="58" /><h2>暂无会话</h2></div>
        </div>
      </section>
      <section v-else-if="page === 'automations'" class="simple-page automation-page"><header><div><h1>定时任务</h1><p>让 SztuCode 按计划自动执行任务，并把结果定时送达</p></div><button class="create-button" disabled><Plus :size="17" />创建</button></header><div class="empty-state"><CalendarClock :size="64" /><h2>暂无定时任务</h2><p>定时任务协议尚未接入 daemon，因此创建功能目前不可用。</p></div></section>

      <section v-else-if="page === 'skills'" class="simple-page"><header><div><h1>插件</h1></div><button class="outline-button" @click="refreshIndex(false)">刷新</button></header><div v-if="providerStatus?.skills.length" class="skill-grid"><article v-for="skill in providerStatus.skills" :key="skill.name"><Wrench :size="18" /><div><h2>{{ skill.name }}</h2><p>{{ skill.description }}</p></div><span>可用</span></article></div><div v-else class="empty-state"><Puzzle :size="58" /><h2>没有已发现的技能</h2><p>{{ connected ? '当前没有可用技能。' : '连接本地服务后加载技能。' }}</p></div></section>

      <section v-else-if="page === 'webbridge'" class="simple-page"><header><div><h1>WebBridge</h1><p>连接浏览器扩展，让 Agent 在授权范围内协助网页操作</p></div></header><div class="bridge-card"><Globe2 :size="24" /><div><h2>浏览器连接</h2><p>当前未连接。此功能需要浏览器扩展和 daemon WebBridge 协议。</p></div><span class="status-pill">未连接</span></div></section>

      <section v-else class="settings-screen"><header class="settings-top"><button title="返回工作区" aria-label="返回工作区" @click="openPage('work')"><ArrowLeft :size="19" /></button><h1>设置</h1></header><div class="settings-layout"><aside><span>SztuCode</span><button class="active">SztuCode Work</button></aside><main><section><span class="settings-section-label">系统设置</span><div class="setting-group"><label><div><b>开机自启动</b><p>登录系统时自动启动 SztuCode。</p></div><input :checked="autostart" type="checkbox" :disabled="!nativeSettingsAvailable" @change="toggleAutostart" /></label><label><div><b>系统通知</b><p>允许 SztuCode 发送任务结果与重要提醒。</p></div><input v-model="notifications" type="checkbox" /></label><label><div><b>保持电脑唤醒</b><p>任务运行期间阻止电脑进入睡眠。</p></div><input :checked="stayAwake" type="checkbox" :disabled="!nativeSettingsAvailable" @change="toggleStayAwake" /></label><p v-if="nativeSettingsError" class="native-settings-error">{{ nativeSettingsError }}</p></div></section><section><span class="settings-section-label">模型与审批</span><div class="setting-group"><label class="stack"><b>Provider</b><select :value="runtimeSettings?.provider" @change="chooseProvider"><option value="anthropic">Anthropic</option><option value="openai">OpenAI</option></select></label><label class="stack"><b>模型</b><input :value="runtimeSettings?.model" placeholder="模型名称" @change="chooseModel" /></label><label class="stack"><b>权限模式</b><select :value="runtimeSettings?.permission_mode" @change="choosePermissionMode(($event.target as HTMLSelectElement).value as RuntimeSettings['permission_mode'])"><option value="normal">标准审批</option><option value="plan">计划模式</option><option value="accept_edits">允许编辑</option><option value="auto">全部允许</option></select></label></div></section><section><span class="settings-section-label">模型管理</span><div class="setting-group ccswitch-mgr"><div class="ccswitch-current-row"><div><b>当前模型</b><p>{{ runtimeSettings?.model || '未配置模型' }}<template v-if="runtimeSettings?.base_url"><br />{{ runtimeSettings.base_url }}</template></p></div><button type="button" class="ccswitch-import-btn" :disabled="ccswitchLoading" @click="ccswitchOpen ? (ccswitchOpen = false) : loadCcswitchProviders()">{{ ccswitchLoading ? '加载中…' : (ccswitchOpen ? '收起' : '从 cc-switch 导入') }}</button></div><div v-if="ccswitchOpen" class="ccswitch-list"><div v-for="item in ccswitchProviders" :key="item.id" class="ccswitch-card"><span class="ccswitch-card__dot" :class="{ has: item.has_api_key }" /><div class="ccswitch-card__info"><b>{{ item.name }}<em v-if="item.is_current">当前</em></b><span>{{ item.base_url }}</span><small>{{ item.model }}</small></div><button type="button" :disabled="ccswitchApplying === item.id" @click="useCcswitchProvider(item.id)">{{ ccswitchApplying === item.id ? '应用中…' : '使用此配置' }}</button></div><p v-if="!ccswitchProviders.length && !ccswitchLoading" class="ccswitch-empty">本机未发现可导入的 cc-switch 供应商，请确认已安装 CC Switch</p></div><p v-if="ccswitchError" class="native-settings-error">{{ ccswitchError }}</p></div></section><section><span class="settings-section-label">WebBridge</span><div class="setting-group"><label><div><b>允许网站所有操作</b><p>允许 Agent 在浏览器中执行已授权的网页动作。</p></div><input v-model="webBridgeAllowed" type="checkbox" disabled /></label><label><div><b>浏览器连接</b><p>显示 SztuCode 与本地浏览器扩展的连接状态。</p></div><em>未连接</em></label></div></section></main></div></section>
    </main>
  </div>
</template>
