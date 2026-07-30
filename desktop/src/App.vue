<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  ArrowLeft, Bot, CalendarClock, ChevronDown, CirclePlus, CircleUserRound,
  Folder, Globe2, LayoutDashboard, MessageCircle, Minimize2, Monitor, PanelLeftClose, PanelLeftOpen, Plug, Plus, Puzzle,
  Settings, ShieldCheck, Square, Wrench, X,
} from "@lucide/vue";
import { getCurrentWindow } from "@tauri-apps/api/window";
import ExecutionTimeline from "./components/timeline/ExecutionTimeline.vue";
import type { TimelineStep, ToolCallEntry } from "./components/timeline/types";
import {
  connectRuntime, createSession, getProviderStatus, getRuntimeSettings, listSessions,
  listWorkspaces, onRuntimeEvent, respondPermission, sendPrompt, sessionHistory, setRuntimeSettings,
  type ProviderStatus, type RuntimeSettings, type Session, type Workspace,
} from "./services/sztu-runtime";

type Page = "work" | "chat" | "board" | "skills" | "automations" | "webbridge" | "settings";
type RuntimeEvent = Record<string, unknown>;
const page = ref<Page>("work");
const sidebarCollapsed = ref(false);
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
const providerStatus = ref<ProviderStatus | null>(null);
const runtimeSettings = ref<RuntimeSettings | null>(null);
const notifications = ref(true);
const stayAwake = ref(false);
const webBridgeAllowed = ref(false);
const currentStepByRun = new Map<string, number>();

const active = computed(() => sessions.value.find((item) => item.session_id === activeId.value) ?? null);
const activeWorkspace = computed(() => workspaces.value.find((item) => item.workspace_id === active.value?.workspace_id) ?? workspace.value);
const liveSessions = computed(() => sessions.value.filter((item) => !item.archived));
const recentSessions = computed(() => liveSessions.value.filter((item) => !item.workspace_id).slice(0, 6));
const projects = computed(() => workspaces.value.map((item) => ({ ...item, tasks: liveSessions.value.filter((task) => task.workspace_id === item.workspace_id).slice(0, 5) })));
const orderedTimeline = computed(() => [...timeline.value.values()].sort((left, right) => left.step - right.step));

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
function hydrateTimeline(messages: unknown[]) {
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
      next.set(step, { ...current, status: "done", toolCalls: completed });
      continue;
    }
    if (role === "user") {
      step += 1;
      next.set(step, { ...emptyStep(step), status: "done", userMessage: text });
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
      thinking: [current.thinking, thinking].filter(Boolean).join("\n\n") || undefined,
      finalText: [current.finalText, text].filter(Boolean).join("\n\n") || undefined,
      toolCalls: [...current.toolCalls, ...calls],
    });
  }
  timeline.value = next;
}function applyRuntimeEvent(event: RuntimeEvent) {
  const type = String(event.type ?? "");
  const runId = String(event.run_id ?? "");
  if (type === "session.created" || type === "session.closed" || type === "session.waiting_for_input") {
    void refreshIndex();
    return;
  }
  // 运行事件没有 session_id，只消费由当前会话发送消息返回的 run_id，避免串到其他任务。
  if (!runId || runId !== activeRunId.value) return;
  if (type === "step.started") {
    const step = Number(event.step);
    currentStepByRun.set(runId, step);
    setStep(step, (current) => ({ ...current, status: "thinking" }));
    return;
  }
  if (type === "llm.token") {
    const step = stepFor(event);
    setStep(step, (current) => ({ ...current, status: "thinking", tokens: [...current.tokens, String(event.token ?? "")] }));
    return;
  }
  if (type === "llm.thinking") {
    const step = stepFor(event);
    setStep(step, (current) => ({ ...current, thinking: `${current.thinking ?? ""}${String(event.thinking ?? "")}` }));
    return;
  }
  if (type === "llm.usage") {
    const step = stepFor(event);
    setStep(step, (current) => ({ ...current, usage: { inputTokens: Number(event.input_tokens ?? 0), outputTokens: Number(event.output_tokens ?? 0), contextPct: Number(event.context_pct ?? 0), model: String(event.model ?? "") } }));
    return;
  }
  if (type === "tool.call_started") {
    const step = stepFor(event);
    const call: ToolCallEntry = { id: String(event.tool_use_id), name: String(event.tool_name), params: (event.params as Record<string, unknown>) ?? {}, status: "running" };
    setStep(step, (current) => ({ ...current, status: "acting", toolCalls: [...current.toolCalls.filter((item) => item.id !== call.id), call] }));
    return;
  }
  if (type === "tool.call_finished" || type === "tool.call_failed") {
    const step = stepFor(event);
    const callId = String(event.tool_use_id);
    setStep(step, (current) => ({ ...current, status: "observing", toolCalls: current.toolCalls.map((call) => call.id !== callId ? call : { ...call, status: type === "tool.call_finished" ? "done" : "failed", output: type === "tool.call_finished" ? String(event.output ?? "") : undefined, error: type === "tool.call_failed" ? String(event.error_message ?? "工具调用失败") : undefined, elapsedMs: Number(event.elapsed_ms ?? 0) }) }));
    return;
  }
  if (type === "permission.requested") {
    const step = stepFor(event);
    const toolUseId = String(event.tool_use_id);
    setStep(step, (current) => ({ ...current, status: "acting", permission: { toolUseId, toolName: String(event.tool_name), preview: String(event.param_preview ?? "等待确认"), status: "pending" }, toolCalls: current.toolCalls.map((call) => call.id === toolUseId ? { ...call, status: "awaiting_permission" } : call) }));
    return;
  }
  if (type === "permission.granted" || type === "permission.denied") {
    const toolUseId = String(event.tool_use_id);
    for (const step of timeline.value.keys()) setStep(step, (current) => current.permission?.toolUseId === toolUseId ? { ...current, permission: { ...current.permission, status: type === "permission.granted" ? "granted" : "denied" } } : current);
    return;
  }
  if (type === "step.finished") {
    const step = Number(event.step ?? stepFor(event));
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
  if (loadHistory && activeId.value) hydrateTimeline(await sessionHistory(activeId.value));
  loading.value = false;
}
async function newTask(project = workspace.value, initialPrompt = prompt.value.trim()) {
  if (!connected.value || sending.value) return;
  sending.value = true;
  try {
    const sessionId = await createSession(project);
    activeId.value = sessionId; timeline.value = new Map(); activeRunId.value = null; page.value = "work";
    if (initialPrompt) { prompt.value = ""; addUserMessage(initialPrompt); activeRunId.value = await sendPrompt(sessionId, initialPrompt); }
    await refreshIndex(false);
  } finally { sending.value = false; }
}
async function chooseTask(id: string) { activeId.value = id; activeRunId.value = null; currentStepByRun.clear(); hydrateTimeline(await sessionHistory(id)); page.value = "work"; }
async function chooseWorkspace(item: Workspace) { workspace.value = item; projectMenuOpen.value = false; const matching = liveSessions.value.find((session) => session.workspace_id === item.workspace_id); if (matching) await chooseTask(matching.session_id); }
async function submit() { const content = prompt.value.trim(); if (!content || !activeId.value || sending.value) return; prompt.value = ""; addUserMessage(content); sending.value = true; try { activeRunId.value = await sendPrompt(activeId.value, content); } finally { sending.value = false; } }
async function decidePermission(toolUseId: string, decision: "allow_once" | "deny_once") { await respondPermission(toolUseId, decision); }
async function choosePermissionMode(value: RuntimeSettings["permission_mode"]) { const result = await setRuntimeSettings({ permission_mode: value }); if (result) runtimeSettings.value = result; }
async function chooseModel(event: Event) { const model = (event.target as HTMLInputElement).value.trim(); if (!model) return; const result = await setRuntimeSettings({ model }); if (result) runtimeSettings.value = result; }
async function chooseProvider(event: Event) { const provider = (event.target as HTMLSelectElement).value as RuntimeSettings["provider"]; const result = await setRuntimeSettings({ provider }); if (result) runtimeSettings.value = result; }
function openPage(next: Page) { page.value = next; projectMenuOpen.value = false; }
async function minimizeWindow() { await getCurrentWindow().minimize(); }
async function toggleMaximizeWindow() { await getCurrentWindow().toggleMaximize(); }
async function closeWindow() { await getCurrentWindow().close(); }
function toggleSidebar() { sidebarCollapsed.value = !sidebarCollapsed.value; }
function handleGlobalShortcut(event: KeyboardEvent) {
  if (event.ctrlKey && event.key.toLowerCase() === "b") { event.preventDefault(); toggleSidebar(); }
}
let stopEvents: (() => void) | undefined;
onMounted(() => {
  window.addEventListener("keydown", handleGlobalShortcut);
  void refreshIndex(true).then(() => { stopEvents = onRuntimeEvent(applyRuntimeEvent); });
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleGlobalShortcut);
  stopEvents?.();
});
watch(page, (next) => { if (next === "skills" || next === "settings") void refreshIndex(false); });
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

    <aside id="primary-navigation" class="kimi-sidebar">
      <div class="mode-switch" role="tablist" aria-label="工作模式">
        <button :class="{ active: page !== 'chat' }" @click="openPage('work')"><Monitor :size="15" />Work</button>
        <button :class="{ active: page === 'chat' }" @click="openPage('chat')"><MessageCircle :size="15" />Chat</button>
      </div>

      <nav class="primary-nav" aria-label="Primary navigation">
        <button :class="{ active: page === 'work' }" @click="newTask()"><CirclePlus :size="18" />新建任务 <kbd>Ctrl</kbd><kbd>K</kbd></button>
        <button :class="{ active: page === 'board' }" @click="openPage('board')"><LayoutDashboard :size="17" />看板</button>
        <button :class="{ active: page === 'skills' }" @click="openPage('skills')"><Plug :size="17" />插件</button>
        <button :class="{ active: page === 'automations' }" @click="openPage('automations')"><CalendarClock :size="17" />定时任务</button>
        <button :class="{ active: page === 'webbridge' }" @click="openPage('webbridge')"><Globe2 :size="17" />WebBridge</button>
      </nav>

      <section class="side-section project-tree">
        <span class="side-label">项目</span>
        <div v-for="item in projects" :key="item.workspace_id" class="project-group">
          <button class="project-row" :class="{ active: item.workspace_id === workspace?.workspace_id }" @click="chooseWorkspace(item)"><Folder :size="16" /><span>{{ item.name }}</span></button>
          <button v-for="task in item.tasks" :key="task.session_id" class="project-task" :class="{ active: task.session_id === activeId }" @click="chooseTask(task.session_id)">{{ task.title || 'Untitled task' }}</button>
        </div>
        <p v-if="!projects.length" class="side-empty">打开本地工作区后会显示在这里</p>
      </section>
      <section class="side-section conversations">
        <span class="side-label">对话</span>
        <button v-for="task in recentSessions" :key="task.session_id" class="conversation-row" :class="{ active: task.session_id === activeId }" @click="chooseTask(task.session_id)"><i :class="{ running: task.status === 'active' }" /><span>{{ task.title || 'Untitled task' }}</span></button>
        <p v-if="!recentSessions.length" class="side-empty">历史对话会显示在这里</p>
      </section>

      <footer class="sidebar-footer">
        <button class="account"><CircleUserRound :size="23" /><span><b>SztuCode</b><small>{{ connected ? 'Connected' : 'Offline' }}</small></span></button>
        <button class="settings-link" @click="openPage('settings')"><Settings :size="16" /></button>
      </footer>
    </aside>

    <main class="kimi-main">
      <template v-if="page === 'work'">
        <section v-if="active" class="work-page">
          <header class="work-header">
            <button class="workspace-trigger" @click="projectMenuOpen = !projectMenuOpen"><span>{{ activeWorkspace?.name || '未选择项目' }}</span><ChevronDown :size="14" /></button>
            <div v-if="projectMenuOpen" class="project-popover"><button v-for="item in workspaces" :key="item.workspace_id" @click="chooseWorkspace(item)">{{ item.name }}<small>{{ item.path }}</small></button></div>
            <div class="work-header__tools"><button title="File context"><Folder :size="18" /></button></div>
          </header>
          <div class="work-layout">
            <section class="task-canvas">
              <div class="task-stream">
                <div v-if="!orderedTimeline.length" class="task-intro"><span class="agent-orb"><Bot :size="20" /></span><p>任务已经创建。告诉 SztuCode 你希望完成什么，它会在这里展示计划、工具调用与最终结果。</p></div>
                <ExecutionTimeline :steps="orderedTimeline" @decide="decidePermission" />
              </div>
              <form class="kimi-composer" @submit.prevent="submit"><textarea v-model="prompt" placeholder="输入消息" rows="3" /><div class="composer-toolbar"><button type="button" class="round"><Plus :size="18" /></button><button type="button" class="permission" @click="choosePermissionMode(runtimeSettings?.permission_mode === 'auto' ? 'normal' : 'auto')"><ShieldCheck :size="15" />{{ runtimeSettings?.permission_mode === 'auto' ? '全部允许' : '标准审批' }}<ChevronDown :size="13" /></button><span class="model-label"><i :class="{ online: providerStatus?.ready_for_next_run }" />{{ runtimeSettings?.model || '未配置模型' }}</span><button class="send" type="submit" :disabled="!prompt.trim() || sending">↑</button></div></form>
            </section>
            <aside class="inspector-panel inspector-panel--blank" aria-hidden="true" />
          </div>
        </section>
        <section v-else class="landing-page"><div class="kimi-hero"><span class="mascot"><Bot :size="32" /></span><div><h1>让 SztuCode 帮你完成任务</h1><a>本地开发版</a></div></div><form class="kimi-composer landing-composer" @submit.prevent="newTask()"><textarea v-model="prompt" placeholder="输入消息" rows="3" /><div class="composer-toolbar"><button type="button" class="round"><Plus :size="18" /></button><button type="button" class="permission"><ShieldCheck :size="15" />标准审批<ChevronDown :size="13" /></button><span /><button class="send" type="submit" :disabled="!connected">↑</button></div><div class="composer-project"><Folder :size="15" />进入项目工作<ChevronDown :size="13" /></div></form></section>
      </template>

      <section v-else-if="page === 'chat'" class="landing-page chat-landing"><div class="kimi-hero"><span class="mascot"><MessageCircle :size="31" /></span><div><h1>与 SztuCode 对话</h1><p>发起不关联项目的本地 AI 对话</p></div></div><form class="kimi-composer landing-composer" @submit.prevent="newTask(null)"><textarea v-model="prompt" placeholder="输入消息" rows="3" /><div class="composer-toolbar"><button type="button" class="round"><Plus :size="18" /></button><button type="button" class="permission"><ShieldCheck :size="15" />标准审批<ChevronDown :size="13" /></button><span /><button class="send" type="submit" :disabled="!connected">↑</button></div></form></section>

      <section v-else-if="page === 'board'" class="simple-page board-page"><header><div><h1>看板</h1></div></header><div class="empty-state"><LayoutDashboard :size="58" /><h2>暂无看板任务</h2></div></section>
      <section v-else-if="page === 'automations'" class="simple-page automation-page"><header><div><h1>定时任务</h1><p>让 SztuCode 按计划自动执行任务，并把结果定时送达</p></div><button class="create-button" disabled><Plus :size="17" />创建</button></header><div class="empty-state"><CalendarClock :size="64" /><h2>暂无定时任务</h2><p>定时任务协议尚未接入 daemon，因此创建功能目前不可用。</p></div></section>

      <section v-else-if="page === 'skills'" class="simple-page"><header><div><h1>插件</h1></div><button class="outline-button" @click="refreshIndex(false)">刷新</button></header><div v-if="providerStatus?.skills.length" class="skill-grid"><article v-for="skill in providerStatus.skills" :key="skill.name"><Wrench :size="18" /><div><h2>{{ skill.name }}</h2><p>{{ skill.description }}</p></div><span>可用</span></article></div><div v-else class="empty-state"><Puzzle :size="58" /><h2>没有已发现的技能</h2><p>{{ connected ? '当前没有可用技能。' : '连接本地服务后加载技能。' }}</p></div></section>

      <section v-else-if="page === 'webbridge'" class="simple-page"><header><div><h1>WebBridge</h1><p>连接浏览器扩展，让 Agent 在授权范围内协助网页操作</p></div></header><div class="bridge-card"><Globe2 :size="24" /><div><h2>浏览器连接</h2><p>当前未连接。此功能需要浏览器扩展和 daemon WebBridge 协议。</p></div><span class="status-pill">未连接</span></div></section>

      <section v-else class="settings-screen"><header class="settings-top"><button title="返回工作区" aria-label="返回工作区" @click="openPage('work')"><ArrowLeft :size="19" /></button><h1>设置</h1></header><div class="settings-layout"><aside><span>SztuCode</span><button class="active">SztuCode Work</button></aside><main><section><span class="settings-section-label">系统设置</span><div class="setting-group"><label><div><b>开机自启动</b><p>登录系统时自动启动 SztuCode。</p></div><input type="checkbox" disabled /></label><label><div><b>系统通知</b><p>允许 SztuCode 发送任务结果与重要提醒。</p></div><input v-model="notifications" type="checkbox" /></label><label><div><b>保持电脑唤醒</b><p>任务运行期间阻止电脑进入睡眠。</p></div><input v-model="stayAwake" type="checkbox" /></label></div></section><section><span class="settings-section-label">模型与审批</span><div class="setting-group"><label class="stack"><b>Provider</b><select :value="runtimeSettings?.provider" @change="chooseProvider"><option value="anthropic">Anthropic</option><option value="openai">OpenAI</option></select></label><label class="stack"><b>模型</b><input :value="runtimeSettings?.model" placeholder="模型名称" @change="chooseModel" /></label><label class="stack"><b>权限模式</b><select :value="runtimeSettings?.permission_mode" @change="choosePermissionMode(($event.target as HTMLSelectElement).value as RuntimeSettings['permission_mode'])"><option value="normal">标准审批</option><option value="plan">计划模式</option><option value="accept_edits">允许编辑</option><option value="auto">全部允许</option></select></label></div></section><section><span class="settings-section-label">WebBridge</span><div class="setting-group"><label><div><b>允许网站所有操作</b><p>允许 Agent 在浏览器中执行已授权的网页动作。</p></div><input v-model="webBridgeAllowed" type="checkbox" disabled /></label><label><div><b>浏览器连接</b><p>显示 SztuCode 与本地浏览器扩展的连接状态。</p></div><em>未连接</em></label></div></section></main></div></section>
    </main>
  </div>
</template>
