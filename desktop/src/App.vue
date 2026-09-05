<script setup lang="ts">
import { computed, KeepAlive, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import AppIcon from "./components/icons/AppIcon.vue";
import { confirm, message, open as openDialog, invoke, listen, getCurrentWindow, getCurrentWebview, IS_TAURI } from "./lib/tauri-shim";
import ProjectInspector from "./components/Inspector/ProjectInspector.vue";
import ModelConfigMenu from "./components/ModelConfig/ModelConfigMenu.vue";
import SessionActions from "./components/session/SessionActions.vue";
import ChatPortal, { type ChatView } from "./components/Chat/ChatPortal.vue";
// 暂时隐藏“修改了 N 个文件”提示，保留组件以便后续恢复。
// import ChangeSummaryRail from "./components/Diff/ChangeSummaryRail.vue";
import ExecutionTimeline from "./components/timeline/ExecutionTimeline.vue";
import AgentLogo from "./components/timeline/AgentLogo.vue";
import SessionStatsLine from "./components/timeline/SessionStatsLine.vue";
import SlashCommandMenu from "./components/CommandPalette/SlashCommandMenu.vue";
import SkillCenter from "./components/Skills/SkillCenter.vue";
import SettingsDialog from "./components/Settings/SettingsDialog.vue";
import QueueDock from "./components/Composer/QueueDock.vue";
import UserQuestionComposer from "./components/UserQuestions/UserQuestionComposer.vue";
import SourceControlPanel from "./components/SourceControl/SourceControlPanel.vue";
import { slashMenuItems } from "./components/CommandPalette/slash-menu";
import type { ContextInjectionEntry, PermissionDecision, PermissionState, PlanItem, TimelineEvent, TimelineStep, ToolCallEntry, WorkflowTaskEntry } from "./components/timeline/types";
import { isMacOSPlatform } from "./lib/platform";
import { appendThinkingBatch, appendTokenBatch, createTokenFrameBatcher } from "./utils/timelineStream";
import { deriveSessionStats } from "./utils/sessionStats";
import { resolveComposerSubmitMode, type ComposerSubmitGesture, type QueueDockItem } from "./utils/composerSubmission";
import { loadComposerDraft, saveComposerDraft } from "./utils/composerDraft";
import { friendlyError } from "./utils/errorNotice";
import { loadAppearanceSettings, type AppearanceSettings } from "./services/appearance";
import {
  archiveSession, cancelRun, connectRuntime, createSession, deleteWorkspace, getProviderStatus, getRuntimeConnectionError, getRuntimeSettings, listChanges, listPendingUserQuestions, listSessions,
  listWorkspaces, moveSession, onRuntimeDisconnect, onRuntimeEvent, openWorkspace, pinWorkspace, readAttachments, renameWorkspace, respondPermission, respondUserQuestion, resumeWorkspace,
  revertChanges, sendPrompt, sessionHistory, setRuntimeSettings, steerPrompt, workspaceStatus,
  type Attachment, type ImageBlock, type PendingUserQuestion, type ProviderStatus, type RuntimeSettings, type Session, type UserQuestionAnswer, type Workspace,
} from "./services/sztu-runtime";

const { t } = useI18n({ useScope: "global" });

type Page = "work" | "chat" | "board" | "skills" | "automations" | "webbridge" | "source-control";
type WorkMode = "code" | "chat";
type AppMenu = "file" | "edit" | "view" | "help";
type RuntimeEvent = Record<string, unknown>;
type ProjectDialogTone = "neutral" | "success" | "danger";
type ProjectDialogState = {
  title: string;
  message: string;
  tone: ProjectDialogTone;
  confirmLabel: string;
  cancelLabel?: string;
};
type QueuedSubmission = {
  id: string;
  text: string;
  contentSuffix: string;
  images: ImageBlock[];
  attachmentCount: number;
  // 原样保留入列时的附件，编辑时需要把内容完整退回输入框重来
  attachments: PendingAttachment[];
};
const FULL_SIDEBAR_MIN_WIDTH = 952;
const FULL_SIDEBAR_MIN_HEIGHT = 640;
const SIDEBAR_MIN_WIDTH = 224;
const SIDEBAR_MAX_WIDTH = 360;
const SIDEBAR_COLLAPSE_PULL = 48;
// 会话区保留的最小宽度，用于钳制右侧功能栏宽度，避免窗口变窄时被挤没
const CONVERSATION_MIN_WIDTH = 320;
// 窗口窄于该宽度时自动收起右侧功能栏
const INSPECTOR_AUTO_COLLAPSE_WIDTH = 1000;
const page = ref<Page>("work");
const workMode = ref<WorkMode>("code");
const modeMenuOpen = ref(false);
const chatView = ref<ChatView>("home");
// 正式界面暂时隐藏入口；视觉测试可用开发态查询参数覆盖，避免整套 ChatPortal 回归被跳过。
const chatEntryVisible = import.meta.env.DEV
  && new URLSearchParams(window.location.search).get("visual-chat") === "1";
const sidebarCollapsed = ref(window.innerWidth < FULL_SIDEBAR_MIN_WIDTH || window.innerHeight < FULL_SIDEBAR_MIN_HEIGHT);
let sidebarAutoCollapsed = sidebarCollapsed.value;
const storedSidebarWidth = Number(localStorage.getItem("sztu.sidebarWidth"));
const sidebarWidth = ref(Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, storedSidebarWidth || 268)));
const sidebarResizing = ref(false);
const sidebarAnimating = ref(false);
const sidebarCollapseArmed = ref(false);
const sidebarPull = ref(0);
const windowResizing = ref(false);
let stopSidebarDragListeners: (() => void) | undefined;
let sidebarAnimTimer: number | undefined;
let windowResizeEndTimer: number | undefined;
const connected = ref(false);
const runtimeConnectionError = ref("");
const loading = ref(true);
const workspaces = ref<Workspace[]>([]);
const workspace = ref<Workspace | null>(null);
const sessions = ref<Session[]>([]);
const activeId = ref<string | null>(null);
type SessionViewState = {
  timeline: Map<number, TimelineStep>;
  activeRunId: string | null;
  runActive: boolean;
  loaded: boolean;
  loading: boolean;
  queue: QueuedSubmission[];
  queueDispatching: boolean;
  queueBusyId: string | null;
};
const sessionViews = reactive(new Map<string, SessionViewState>());
const launcherTimeline = ref<Map<number, TimelineStep>>(new Map());
function ensureSessionView(sessionId: string): SessionViewState {
  let view = sessionViews.get(sessionId);
  if (!view) {
    view = reactive({
      timeline: new Map(), activeRunId: null, runActive: false, loaded: false, loading: false,
      queue: [], queueDispatching: false, queueBusyId: null,
    });
    sessionViews.set(sessionId, view);
  }
  return view;
}
const activeView = computed(() => activeId.value ? ensureSessionView(activeId.value) : null);
// 保留 timeline/activeRunId/runActive 兼容入口，实际状态按 session_id 隔离。
const timeline = computed<Map<number, TimelineStep>>({
  get: () => activeView.value?.timeline ?? launcherTimeline.value,
  set: (value) => {
    if (activeView.value) {
      activeView.value.timeline = value;
      activeView.value.loaded = true;
    }
    else launcherTimeline.value = value;
  },
});
const activeRunId = computed<string | null>({
  get: () => activeView.value?.activeRunId ?? null,
  set: (value) => {
    if (!activeView.value) return;
    activeView.value.activeRunId = value;
    if (value && activeId.value) runToSession.set(value, activeId.value);
  },
});
const runActive = computed<boolean>({
  get: () => activeView.value?.runActive ?? false,
  set: (value) => { if (activeView.value) activeView.value.runActive = value; },
});
const activeQueueItems = computed<QueueDockItem[]>(() => (activeView.value?.queue ?? []).map((item) => ({
  id: item.id,
  text: item.text,
  attachmentCount: item.attachmentCount,
})));
const runToSession = new Map<string, string>();
const finishedRunIds = new Set<string>();
// 发送请求尚未返回 run_id 时记录停止意图，拿到 run_id 后立即补发取消。
const stopRequestedSessions = new Set<string>();
const deferredRuntimeEvents = new Map<string, RuntimeEvent[]>();
const historyLoadVersionBySession = new Map<string, number>();
const sessionLoadingTimers = new Map<string, ReturnType<typeof setTimeout>>();
const historyLoadPromises = new Map<string, Promise<void>>();
let runtimeTargetSessionId: string | null = null;
const tokenBatcher = createTokenFrameBatcher(
  ({ runId, step, tokens }) => {
    const sessionId = runToSession.get(runId);
    if (sessionId) setSessionStep(step, (current) => appendTokenBatch({ ...current, runId }, tokens), sessionId);
  },
  (callback) => window.requestAnimationFrame(callback),
  (handle) => window.cancelAnimationFrame(handle),
);
const prompt = ref("");
const activePrompt = ref<HTMLTextAreaElement | null>(null);
// 会话流"回到底部"悬浮按钮：离开底部时显示，点击回到底部
const taskStreamEl = ref<HTMLElement | null>(null);
const streamScrolledUp = ref(false);
let userScrollPaused = false; // 用户主动滚动时暂停自动跟随
let programmaticScroll = false; // 标记程序触发的滚动，避免误判用户操作
let lastScrollTop = 0;

function isAtBottom(el: HTMLElement, threshold = 4) {
  // 精确检测是否在最底部，阈值很小确保真的到底才恢复
  return el.scrollHeight - el.scrollTop - el.clientHeight <= threshold;
}

function handleTaskStreamScroll() {
  const el = taskStreamEl.value;
  if (!el) return;
  const st = el.scrollTop;

  // 跳过程序触发的滚动事件
  if (programmaticScroll) {
    lastScrollTop = st;
    return;
  }

  if (userScrollPaused) {
    // 只有当用户真正滚动到最底部时才恢复自动跟随
    if (isAtBottom(el, 4)) {
      userScrollPaused = false;
      streamScrolledUp.value = false;
    }
  } else {
    // 检测用户是否主动向上滚动：scrollTop 减小，即使很小的幅度也算
    // 只要离开底部或者向上滚动，立即暂停，不抢占用户控制权
    if (st < lastScrollTop - 1 || !isAtBottom(el, 8)) {
      userScrollPaused = true;
      streamScrolledUp.value = true;
    }
  }

  lastScrollTop = st;
}

// 用户通过 wheel/touch/键盘 主动滚动时立即暂停自动跟随
function markUserScrolling() {
  const el = taskStreamEl.value;
  if (!el || programmaticScroll) return;
  // 只要用户主动交互且不在最底部，立即暂停
  if (!isAtBottom(el, 8)) {
    userScrollPaused = true;
    streamScrolledUp.value = true;
  }
}

function scrollTaskStreamToBottom() {
  const el = taskStreamEl.value;
  if (!el) return;
  programmaticScroll = true;
  el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  // 平滑滚动完成后重置标志
  window.setTimeout(() => {
    programmaticScroll = false;
    if (el && isAtBottom(el, 8)) {
      userScrollPaused = false;
      streamScrolledUp.value = false;
      lastScrollTop = el.scrollTop;
    }
  }, 400);
}

let autoScrollFrame: number | undefined;
function keepTaskStreamAtBottom() {
  if (userScrollPaused || autoScrollFrame !== undefined) return;
  autoScrollFrame = window.requestAnimationFrame(() => {
    autoScrollFrame = undefined;
    const el = taskStreamEl.value;
    if (!el || userScrollPaused) return;
    // 只有在底部时才自动跟随，用户离开底部后完全不干预
    if (!isAtBottom(el, 20)) {
      streamScrolledUp.value = true;
      return;
    }
    programmaticScroll = true;
    el.scrollTop = el.scrollHeight;
    lastScrollTop = el.scrollHeight;
    // 下一帧重置程序滚动标志
    window.requestAnimationFrame(() => {
      programmaticScroll = false;
    });
  });
}

// 会话轮次圆点导航（Trae Work风格）
const TURN_DOT_VISIBLE = 11; // 固定可见圆点数量（奇数，中间为active）
const TURN_DOT_SIZE = 8;     // 圆点直径
const TURN_DOT_GAP = 8;      // 圆点间距
const TURN_DOT_PAD = 16;     // rail 上下 padding
const TURN_DOT_STEP = TURN_DOT_SIZE + TURN_DOT_GAP; // 每个圆点占用高度

const turnDotActive = ref(-1);
const turnDotCount = ref(0);
const turnDotRailEl = ref<HTMLElement | null>(null);
const turnDotWrapEl = ref<HTMLElement | null>(null);
const turnDotHoverIdx = ref(-1);
const turnDotBubbleTop = ref(0);
// 轮次摘要标签依赖时间线数据与语言包，用 computed 保证切换语言后即时更新
const turnLabels = computed<string[]>(() => extractTurnLabels(orderedTimeline.value));
let turnObserver: IntersectionObserver | undefined;
let turnElements: HTMLElement[] = [];
let isScrollingToTurn = false;
let scrollToTurnTimer: number | undefined;
let turnScrollRaf: number | undefined;

function extractTurnLabels(steps: TimelineStep[]): string[] {
  const labels: string[] = [];
  for (const step of steps) {
    const msg = (step.userMessage ?? "").trim();
    if (!msg) continue;
    // 取第一行，去除markdown，截断为简短摘要
    const firstLine = msg.split(/\r?\n/)[0]?.replace(/[#*`_~\[\]]/g, "").trim() ?? "";
    labels.push(firstLine.length > 60 ? firstLine.slice(0, 57) + "…" : firstLine || t("app.turnFallback", { n: labels.length + 1 }));
  }
  return labels;
}

function scrollRailToActive() {
  const rail = turnDotRailEl.value;
  if (!rail) return;
  const idx = turnDotActive.value;
  if (idx < 0) return;
  // 让 active 圆点位于 rail 垂直居中位置：dotCenter - (railHeight/2 - dotRadius)
  const dotCenter = TURN_DOT_PAD + idx * TURN_DOT_STEP + TURN_DOT_SIZE / 2;
  const targetScroll = dotCenter - rail.clientHeight / 2;
  if (turnScrollRaf) cancelAnimationFrame(turnScrollRaf);
  turnScrollRaf = requestAnimationFrame(() => {
    rail.scrollTo({ top: Math.max(0, targetScroll), behavior: "smooth" });
  });
}

function refreshTurnObserver() {
  turnObserver?.disconnect();
  const el = taskStreamEl.value;
  if (!el) return;
  const steps = el.querySelectorAll<HTMLElement>(".execution-timeline > .timeline-step");
  turnElements = Array.from(steps);
  turnDotCount.value = turnElements.length;
  if (!turnElements.length) { turnDotActive.value = -1; return; }

  turnObserver = new IntersectionObserver((entries) => {
    if (isScrollingToTurn) return;
    let bestIdx = -1;
    let bestTop = Infinity;
    for (const entry of entries) {
      if (entry.isIntersecting) {
        const idx = turnElements.indexOf(entry.target as HTMLElement);
        const rect = entry.boundingClientRect;
        const containerTop = el.getBoundingClientRect().top;
        const distance = Math.abs(rect.top - containerTop - 60);
        if (distance < bestTop) {
          bestTop = distance;
          bestIdx = idx;
        }
      }
    }
    if (bestIdx === -1) {
      for (let i = 0; i < turnElements.length; i++) {
        const rect = turnElements[i].getBoundingClientRect();
        const containerRect = el.getBoundingClientRect();
        if (rect.bottom > containerRect.top + 20 && rect.top < containerRect.bottom - 20) {
          bestIdx = i;
          break;
        }
      }
    }
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - 30) {
      bestIdx = turnElements.length - 1;
    }
    if (el.scrollTop < 30 && turnElements.length) {
      bestIdx = 0;
    }
    if (bestIdx >= 0) {
      const changed = turnDotActive.value !== bestIdx;
      turnDotActive.value = bestIdx;
      if (changed) nextTick(scrollRailToActive);
    }
  }, {
    root: el,
    threshold: [0, 0.1, 0.3, 0.5, 0.9, 1],
    rootMargin: "-10% 0px -40% 0px",
  });
  for (const step of turnElements) turnObserver.observe(step);
  nextTick(scrollRailToActive);
}

function scrollToTurn(idx: number) {
  const el = taskStreamEl.value;
  if (!el || !turnElements[idx]) return;
  isScrollingToTurn = true;
  const prev = turnDotActive.value;
  turnDotActive.value = idx;
  if (prev !== idx) nextTick(scrollRailToActive);
  const target = turnElements[idx];
  const containerTop = el.getBoundingClientRect().top;
  const targetTop = target.getBoundingClientRect().top;
  el.scrollBy({ top: targetTop - containerTop - 24, behavior: "smooth" });
  window.clearTimeout(scrollToTurnTimer);
  scrollToTurnTimer = window.setTimeout(() => { isScrollingToTurn = false; }, 700);
}

function handleDotHover(idx: number, event: FocusEvent | MouseEvent) {
  turnDotHoverIdx.value = idx;
  // 用相对于wrap的位置定位气泡（垂直居中于圆点）
  nextTick(() => {
    const wrap = turnDotWrapEl.value;
    const dot = event.currentTarget as HTMLElement | null;
    if (!wrap || !dot) return;
    const wrapRect = wrap.getBoundingClientRect();
    const dotRect = dot.getBoundingClientRect();
    // 气泡top值 = 圆点中心 - 气泡高度一半。先用圆点中心 - 14px（约为单行文本半高）
    turnDotBubbleTop.value = dotRect.top - wrapRect.top + dotRect.height / 2 - 14;
  });
}

// 监听 orderedTimeline 和 DOM 变化，刷新观察器（在 orderedTimeline 定义后注册，见下方）
const launcherPrompt = ref<HTMLTextAreaElement | null>(null);
const slashMenuActiveIndex = ref(0);
const slashMenuDismissed = ref(false);
const sending = ref(false);
const projectMenuOpen = ref(false);
const launcherProjectMenuOpen = ref(false);
const launcherProjectQuery = ref("");
const launcherPermissionMenuOpen = ref(false);
const permissionConfirmOpen = ref(false);
const permissionSaving = ref(false);
const permissionSettingsError = ref("");
// 防止连续按键在 steer 请求尚未返回时重复追加同一条消息。
const steering = ref(false);
const projectActionsOpen = ref<string | null>(null);
const projectPreviewId = ref<string | null>(null);
const projectPreviewStyle = ref<Record<string, string>>({});
let projectPreviewCloseTimer: number | undefined;
const projectEditingId = ref<string | null>(null);
const projectEditName = ref("");
const projectEditError = ref("");
const projectActionBusy = ref(false);
const projectDialog = ref<ProjectDialogState | null>(null);
let projectDialogResolve: ((accepted: boolean) => void) | null = null;
const taskQuery = ref("");
const taskSearchOpen = ref(false);
const taskSearchInput = ref<HTMLInputElement | null>(null);
const inspectorOpen = ref(false);
const inspectorRendered = ref(false);
// 输出链接「在右侧浏览器栏打开」的组件句柄（TokenStream 派发全局事件后由 App 转发）
const inspectorRef = ref<InstanceType<typeof ProjectInspector> | null>(null);
const inspectorWidth = ref(Math.min(720, Math.max(340, Number(localStorage.getItem("sztu.inspectorWidth")) || 390)));
const inspectorResizing = ref(false);
// 响应式窗口宽度 + 窄窗自动收起右侧功能栏的追踪标志
const windowWidth = ref(window.innerWidth);
let inspectorAutoCollapsed = false;
// 「查看项目文件」请求：通知右侧功能栏切到文件标签页并浏览指定项目
const filesRequest = ref<{ workspaceId: string; seq: number } | null>(null);
let filesRequestSeq = 0;
// 可视化产物自动预览：AI 生成报告 / HTML / 图片等文件后自动打开右侧功能栏查看
const VISUAL_ARTIFACT_RE = /\.(?:html?|xhtml|png|jpe?g|gif|webp|svg|md|markdown)$/i;
const autoPreviewedArtifacts = new Map<string, Set<string>>(); // sessionId → 已自动预览过的路径
const pendingVisualWrites = new Map<string, string>(); // toolUseId → 写入中的可视化产物路径
let inspectorCloseTimer: ReturnType<typeof setTimeout> | undefined;
let inspectorOpenFrame: number | undefined;
let trayListeners: Array<() => void> = [];
// 待发送附件：图片走 base64 内容块，文本把内容注入消息
type PendingAttachment = {
  path: string; name: string; size: number;
  kind: "image" | "text";
  mime?: string;
  textContent?: string;
  dataBase64?: string;
};
const attachedFiles = ref<PendingAttachment[]>([]);
const providerStatus = ref<ProviderStatus | null>(null);
const runtimeSettings = ref<RuntimeSettings | null>(null);
const settingsOpen = ref(false);
const settingsInitialSection = ref<"appearance" | "agent">("appearance");
const activeAppMenu = ref<AppMenu | null>(null);
const statusBarVisible = ref(localStorage.getItem("sztu.statusBarVisible") !== "false");
const webviewZoom = ref(Number(localStorage.getItem("sztu.webviewZoom")) || 1);
let lastEditableElement: HTMLInputElement | HTMLTextAreaElement | HTMLElement | null = null;
const settingsButton = ref<HTMLButtonElement | null>(null);
const appearanceSettings = ref<AppearanceSettings>(loadAppearanceSettings());
const currentStepByRun = new Map<string, number>();
const runStepBase = new Map<string, number>(); // 每个 run 的 step 起点偏移，避免跨 run 步号冲突
const liveRunUsage = new Map<string, { inputTokens: number; outputTokens: number; cacheReadInputTokens: number }>();
// 首 token 延迟追踪（借鉴 dsh assistant-timing）：run 起点 → 首个 token 的时间差
const runStartedAtByRun = new Map<string, number>();
const firstTokenByRun = new Map<string, number>();
// 切换会话加载动画：超过 260ms 未返回时显示终端图标动效，避免快加载闪屏
const sessionLoading = computed(() => activeView.value?.loading ?? false);
// 后台会话（非当前展示）正在等待审批的权限，切走后仍可审批，避免任务停滞
const pendingPermissions = ref<Array<{ toolUseId: string; toolName: string; preview: string; runId: string; sessionId: string }>>([]);
const permissionContexts = new Map<string, { runId: string; sessionId: string }>();
const pendingUserQuestions = ref<PendingUserQuestion[]>([]);
const questionSubmittingId = ref<string | null>(null);
const questionErrors = reactive(new Map<string, string>());
const resolvedQuestionIds = new Set<string>();
let questionEventVersion = 0;

// 未发送的启动器输入按项目持久化；切走或重启应用后再次点击项目仍可继续编辑。
watch(prompt, (value) => {
  if (!activeId.value) saveComposerDraft(workspace.value?.workspace_id ?? null, value);
});

const active = computed(() => sessions.value.find((item) => item.session_id === activeId.value) ?? null);
const activeUserQuestion = computed(() => pendingUserQuestions.value.find((item) => item.session_id === activeId.value) ?? null);
const backgroundUserQuestions = computed(() => pendingUserQuestions.value.filter((item) => item.session_id !== activeId.value));
// 发送请求中或正在执行 run 时，把发送按钮切换为停止按钮
const isRunActive = computed(() => sending.value || runActive.value);
// 追加模式只代表当前会话已有一个实际运行中的 run；发送请求的短暂窗口仍使用普通发送状态。
const isAppending = computed(() => Boolean(activeId.value && activeView.value?.runActive));
const activeWorkspace = computed(() => workspaces.value.find((item) => item.workspace_id === active.value?.workspace_id) ?? workspace.value);
// IDE 操作必须跟随当前会话绑定的工作区，不能回退到新建任务启动器残留的项目。
const activeSessionWorkspace = computed(() => {
  const workspaceId = active.value?.workspace_id;
  return workspaceId ? workspaces.value.find((item) => item.workspace_id === workspaceId) ?? null : null;
});
const activeWorkspaces = computed(() => workspaces.value.filter((item) => !item.archived));
const archivedProjects = computed(() => workspaces.value.filter((item) => item.archived));
const liveSessions = computed(() => sessions.value.filter((item) => !item.archived));
const archivedSessions = computed(() => sessions.value.filter((item) => item.archived));
const recentSessions = computed(() => liveSessions.value.filter((item) => !item.workspace_id).slice(0, 6));
const normalizedTaskQuery = computed(() => taskQuery.value.trim().toLocaleLowerCase());
// 历史会话的标题可能为空（例如旧版本创建的临时会话）；搜索弹窗首次打开时
// 会立即计算结果，因此这里必须把空标题按空字符串处理，避免点击搜索直接抛异常。
const matchesTaskQuery = (item: Session) => !normalizedTaskQuery.value || String(item.title ?? "").toLocaleLowerCase().includes(normalizedTaskQuery.value);
const visibleSessions = computed(() => liveSessions.value.filter(matchesTaskQuery));
const temporaryTasks = computed(() => visibleSessions.value.filter((item) => !item.workspace_id).slice(0, 5));
const allProjects = computed(() => activeWorkspaces.value
  .map((item) => {
    const projectMatches = item.name.toLocaleLowerCase().includes(normalizedTaskQuery.value);
    const candidates = normalizedTaskQuery.value && !projectMatches ? visibleSessions.value : liveSessions.value;
    return { ...item, tasks: candidates.filter((task) => task.workspace_id === item.workspace_id && (item.pinned || !task.pinned)).slice(0, 6), projectMatches };
  })
  .filter((item) => !normalizedTaskQuery.value || item.projectMatches || item.tasks.length));
const previewProject = computed(() => allProjects.value.find((item) => item.workspace_id === projectPreviewId.value) ?? null);

function showProjectPreview(item: Workspace, event: MouseEvent | FocusEvent) {
  window.clearTimeout(projectPreviewCloseTimer);
  const eventTarget = event.target as HTMLElement | null;
  if (eventTarget?.closest(".project-action-menu")) {
    keepProjectPreviewOpen();
    return;
  }
  sessionPreview.value = null;
  projectActionsOpen.value = null;
  const anchor = event.currentTarget as HTMLElement | null;
  if (!anchor) return;
  const rect = anchor.getBoundingClientRect();
  const width = 254;
  projectPreviewStyle.value = {
    left: `${Math.min(rect.right, window.innerWidth - width - 8)}px`,
    top: `${Math.max(8, Math.min(rect.top, window.innerHeight - 150))}px`,
  };
  projectPreviewId.value = item.workspace_id;
}
function scheduleProjectPreviewClose() {
  window.clearTimeout(projectPreviewCloseTimer);
  const closingId = projectPreviewId.value;
  if (!closingId) return;
  projectPreviewCloseTimer = window.setTimeout(() => {
    if (projectPreviewId.value === closingId) projectPreviewId.value = null;
  }, 700);
}
function keepProjectPreviewOpen() {
  window.clearTimeout(projectPreviewCloseTimer);
  projectPreviewCloseTimer = undefined;
}
function handleProjectPreviewFocusOut(event: FocusEvent) {
  const next = event.relatedTarget as HTMLElement | null;
  if (next?.closest(".project-preview-card")) {
    keepProjectPreviewOpen();
    return;
  }
  scheduleProjectPreviewClose();
}
function openProjectActions(item: Workspace) {
  keepProjectPreviewOpen();
  projectPreviewId.value = null;
  sessionPreview.value = null;
  projectActionsOpen.value = item.workspace_id;
}
function handleProjectRowPointerDown(item: Workspace, event: PointerEvent) {
  if (event.button !== 0) return;
  const target = event.target as HTMLElement | null;
  if (target?.closest(".project-action-menu")) return;
  beginTask(item);
}
const pinnedProjects = computed(() => allProjects.value.filter((item) => item.pinned));
const projectBeingEdited = computed(() => workspaces.value.find((item) => item.workspace_id === projectEditingId.value) ?? null);
const projects = computed(() => allProjects.value.filter((item) => !item.pinned));
const pinnedTemporaryTasks = computed(() => visibleSessions.value.filter((item) => item.pinned && (!item.workspace_id || !pinnedProjects.value.some((project) => project.workspace_id === item.workspace_id))));
const ordinaryTemporaryTasks = computed(() => temporaryTasks.value.filter((item) => !item.pinned));
const filteredLauncherWorkspaces = computed(() => {
  const query = launcherProjectQuery.value.trim().toLocaleLowerCase();
  if (!query) return activeWorkspaces.value.slice(0, 6);
  return activeWorkspaces.value.filter((item) => `${item.name} ${item.path}`.toLocaleLowerCase().includes(query)).slice(0, 8);
});
const orderedTimeline = computed(() => [...timeline.value.values()].sort((left, right) => left.step - right.step));
// 流式输出和思考动画不断改变内容高度；用户未主动上滑时持续跟随最新输出。
// Timeline updates are replaced by the microtask batcher; a shallow watch
// avoids recursively traversing every streamed token and nested tool entry.
watch(() => timeline.value, keepTaskStreamAtBottom);
// 轮次变化时刷新圆点导航观察器
// Turn navigation only depends on the number of steps, not streamed content.
watch([activeId, () => timeline.value.size], () => { nextTick(refreshTurnObserver); });
// 全局会话统计（借鉴 dsh sessionStats 投影）：按 runId 去重的会话级 token/用时/轮步数，
// 由底部统计栏展示；数据源与时间线同源，翻页与压缩不改变数字
const sessionStats = computed(() => deriveSessionStats(orderedTimeline.value));
// 从当前会话 Agent trace 聚合 AI 修改过的文件路径，按路径去重。
// 暂时停用文件修改汇总，保留实现以便恢复右侧提示。
// const changeSummaryPaths = computed(() => {
//   const paths = new Set<string>();
//   for (const item of orderedTimeline.value) {
//     for (const entry of item.changes ?? []) {
//       for (const path of entry.paths) if (path) paths.add(path);
//     }
//   }
//   return [...paths];
// });
const permissionModeLabel = computed(() => ({
  normal: t("app.permissionMode.normal"),
  plan: t("app.permissionMode.plan"),
  accept_edits: t("app.permissionMode.acceptEdits"),
  auto: t("app.permissionMode.auto"),
}[runtimeSettings.value?.permission_mode ?? "normal"]));
// 状态语义与后端一致：active=会话进行中（含新建未跑完一轮）、waiting_for_input=等待用户输入、closed=已完成
const taskStatusLabel = (item: Session) => item.status === "active" ? t("app.taskStatus.active") : item.status === "waiting_for_input" ? t("app.taskStatus.waitingInput") : t("app.taskStatus.done");
function formatSessionUsage(item: Session): string {
  const tokens = Number(item.total_input_tokens ?? 0) + Number(item.total_output_tokens ?? 0);
  const seconds = Number(item.total_elapsed_s ?? 0);
  const tokenText = tokens >= 1000 ? `${(tokens / 1000).toFixed(tokens >= 10000 ? 0 : 1)}k tokens` : `${tokens} tokens`;
  const durationText = seconds < 60 ? t("app.durationSeconds", { s: Math.round(seconds) }) : t("app.durationMinutes", { m: Math.floor(seconds / 60), s: Math.round(seconds % 60) });
  return item.status === "active" && !tokens ? t("app.timing") : `${durationText} · ${tokenText}`;
}

// 对话条目悬停预览：展示计时、分支、项目目录与累计 token
const sessionPreview = ref<{ task: Session; top: number; left: number } | null>(null);
const branchCache = ref(new Map<string, string | null>());
type TaskTitleScrollState = { frame: number; direction: 1 | -1; lastAt: number; pauseUntil: number };
const taskTitleScrollStates = new WeakMap<HTMLElement, TaskTitleScrollState>();

function stopTaskTitleElementScroll(title: HTMLElement, reset = true) {
  const state = taskTitleScrollStates.get(title);
  if (state) cancelAnimationFrame(state.frame);
  taskTitleScrollStates.delete(title);
  if (reset) title.scrollLeft = 0;
}

function startTaskTitleScroll(event: FocusEvent) {
  const button = event.currentTarget as HTMLElement;
  const title = button.querySelector<HTMLElement>("[data-auto-scroll-title]");
  if (!title) return;
  stopTaskTitleElementScroll(title);
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  const maxScroll = title.scrollWidth - title.clientWidth;
  if (maxScroll <= 1) return;
  const state: TaskTitleScrollState = {
    frame: 0,
    direction: 1,
    lastAt: performance.now(),
    pauseUntil: performance.now() + 650,
  };
  const tick = (now: number) => {
    if (!title.isConnected || document.activeElement !== button) {
      stopTaskTitleElementScroll(title);
      return;
    }
    const elapsed = Math.min(50, now - state.lastAt);
    state.lastAt = now;
    if (now >= state.pauseUntil) {
      title.scrollLeft += state.direction * elapsed * 0.035;
      if (title.scrollLeft >= maxScroll - 0.5) {
        title.scrollLeft = maxScroll;
        state.direction = -1;
        state.pauseUntil = now + 750;
      } else if (title.scrollLeft <= 0.5) {
        title.scrollLeft = 0;
        state.direction = 1;
        state.pauseUntil = now + 750;
      }
    }
    state.frame = requestAnimationFrame(tick);
  };
  taskTitleScrollStates.set(title, state);
  state.frame = requestAnimationFrame(tick);
}

function stopTaskTitleScroll(event: FocusEvent) {
  const title = (event.currentTarget as HTMLElement).querySelector<HTMLElement>("[data-auto-scroll-title]");
  if (title) stopTaskTitleElementScroll(title);
}

function showSessionPreview(task: Session, event: MouseEvent) {
  keepProjectPreviewOpen();
  projectPreviewId.value = null;
  projectActionsOpen.value = null;
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
  sessionPreview.value = { task, top: Math.max(8, Math.min(rect.top, window.innerHeight - 150)), left: Math.min(rect.right, window.innerWidth - 262) };
  if (task.workspace_id && !branchCache.value.has(task.workspace_id)) void loadBranch(task.workspace_id);
}
function hideSessionPreview() { sessionPreview.value = null; }
// 分支信息按工作区缓存，避免每次悬停都触发 git 查询
async function loadBranch(workspaceId: string) {
  let branch: string | null = null;
  try { branch = (await workspaceStatus(workspaceId)).branch; } catch { branch = null; }
  const next = new Map(branchCache.value);
  next.set(workspaceId, branch);
  branchCache.value = next;
}
function previewBranch(task: Session): string {
  if (!task.workspace_id) return "—";
  const cached = branchCache.value.get(task.workspace_id);
  if (cached === undefined) return "…";
  return cached ?? "—";
}
function previewDirectory(task: Session): string {
  if (!task.workspace_id) return t("app.temporaryTask");
  const found = workspaces.value.find((item) => item.workspace_id === task.workspace_id);
  return found ? found.path : "—";
}
function previewElapsed(task: Session): string {
  const seconds = Number(task.total_elapsed_s ?? 0);
  if (seconds < 60) return t("app.elapsedSeconds", { s: Math.round(seconds) });
  return t("app.elapsedMinutes", { m: Math.floor(seconds / 60), s: Math.round(seconds % 60) });
}
function previewTokens(task: Session): string {
  const tokens = Number(task.total_input_tokens ?? 0) + Number(task.total_output_tokens ?? 0);
  return tokens >= 1000 ? `${(tokens / 1000).toFixed(tokens >= 10000 ? 0 : 1)}k` : String(tokens);
}
// 工作区布局：仅传 CSS 变量，grid 列由样式表定义，
// 这样媒体查询能按窗口宽度覆盖列结构（内联 grid-template-columns 会锁死响应式，窗口变窄不重排）。
// 同时按当前窗口宽度钳制 inspector 宽度，保证会话区始终有 CONVERSATION_MIN_WIDTH 可用。
const workLayoutStyle = computed(() => {
  if (!inspectorOpen.value || !activeWorkspace.value) return { "--inspector-width": "0px" };
  const sidebarW = sidebarCollapsed.value ? 0 : sidebarWidth.value;
  const available = windowWidth.value - sidebarW - 6 - CONVERSATION_MIN_WIDTH;
  const clamped = Math.min(inspectorWidth.value, Math.max(280, available));
  return { "--inspector-width": `${clamped}px` };
});

async function toggleTaskSearch() {
  taskSearchOpen.value = !taskSearchOpen.value;
  if (taskSearchOpen.value) {
    await nextTick();
    taskSearchInput.value?.focus();
  }
}

function clearTaskSearch() {
  taskQuery.value = "";
  taskSearchOpen.value = false;
}
// 延迟卸载工作区面板，保证关闭动画完整播放
function setInspectorOpen(next: boolean) {
  if (inspectorCloseTimer) clearTimeout(inspectorCloseTimer);
  if (inspectorOpenFrame !== undefined) cancelAnimationFrame(inspectorOpenFrame);
  if (next) {
    inspectorRendered.value = true;
    inspectorOpenFrame = requestAnimationFrame(() => {
      inspectorOpen.value = true;
      inspectorOpenFrame = undefined;
    });
    return;
  }
  inspectorOpenFrame = undefined;
  inspectorOpen.value = false;
  inspectorCloseTimer = setTimeout(() => {
    inspectorRendered.value = false;
    inspectorCloseTimer = undefined;
  }, 240);
}
function toggleInspector() { setInspectorOpen(!inspectorOpen.value); }
// 拖拽分割线调整左右面板宽度比，并限制最小/最大宽度
function startDividerDrag(event: PointerEvent) {
  if (event.button !== 0) return;
  event.preventDefault();
  const startX = event.clientX;
  const startWidth = inspectorWidth.value;
  const target = event.currentTarget as HTMLElement;
  const container = target.parentElement;
  const maxWidth = Math.max(340, (container?.clientWidth ?? 1200) - CONVERSATION_MIN_WIDTH);
  const minWidth = 340;
  let rafId = 0;
  let pendingWidth = startWidth;
  inspectorResizing.value = true;
  document.body.style.cursor = "col-resize";
  document.body.style.userSelect = "none";
  target.setPointerCapture?.(event.pointerId);
  const flush = () => {
    rafId = 0;
    inspectorWidth.value = Math.min(maxWidth, Math.max(minWidth, pendingWidth));
  };
  function onMove(ev: PointerEvent) {
    pendingWidth = startWidth + (startX - ev.clientX);
    if (!rafId) rafId = requestAnimationFrame(flush);
  }
  function finish() {
    if (rafId) { cancelAnimationFrame(rafId); flush(); }
    inspectorResizing.value = false;
    localStorage.setItem("sztu.inspectorWidth", String(Math.round(inspectorWidth.value)));
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    target.releasePointerCapture?.(event.pointerId);
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerup", finish);
    document.removeEventListener("pointercancel", finish);
  }
  document.addEventListener("pointermove", onMove);
  document.addEventListener("pointerup", finish, { once: true });
  document.addEventListener("pointercancel", finish, { once: true });
}
const slashQuery = computed(() => {
  const match = prompt.value.match(/^\/([^\s]*)$/);
  return match ? match[1] : null;
});
const slashMenuOpen = computed(() => slashQuery.value !== null && !slashMenuDismissed.value);
const slashItems = computed(() => slashQuery.value === null ? [] : slashMenuItems(slashQuery.value, providerStatus.value?.skills ?? []));

type HistoryBlock = Record<string, unknown>;

function entryRole(entry: unknown) { return String((entry as { role?: unknown })?.role ?? "").toLowerCase(); }
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
function isHiddenHistoryBlock(block: HistoryBlock): boolean {
  const type = String(block.type ?? block.role ?? "").toLowerCase();
  return type === "system" || type === "developer" || type === "system_prompt" || type === "developer_prompt";
}
// 识别内部上下文注入消息并归类为可折叠上下文行。
// 会话压缩作为「模型实际收到的注入」展示；任务进度画布不进入会话区。
function contextInjectionOf(blocks: HistoryBlock[]): ContextInjectionEntry | null {
  const text = blocks.filter((block) => String(block.type) === "text").map(blockText).join("\n").trim();
  if (/^This session is being continued from a previous conversation that ran out of context\.[\s\S]*\n\nSummary:\n/i.test(text)) {
    const summary = text.replace(/^This session is being continued from a previous conversation that ran out of context\.[\s\S]*?\n\nSummary:\n/i, "").trim();
    return {
      id: `ctx-compaction-${crypto.randomUUID()}`,
      source: "compaction",
      label: t("app.contextCompaction"),
      chars: text.length,
      preview: summary.slice(0, 90),
      text: summary,
    };
  }
  if (/^Understood, I'll continue from this summary\.$/i.test(text)) return null;  // 摘要确认无信息量
  return null;
}
function isTaskProgressInjection(blocks: HistoryBlock[]): boolean {
  const text = blocks.filter((block) => String(block.type) === "text").map(blockText).join("\n").trim();
  return /^\[Task progress\]\s+step_\d+/i.test(text);
}
function extractTextFromContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((item) => {
        if (typeof item === "string") return item;
        if (isRecord(item)) {
          // 标准 content block 格式：{ type: "text", text: "..." }
          if (typeof item.text === "string") return item.text;
          // 图片块不提取文本
          if (String(item.type) === "image") return "";
          // 其他块尝试JSON序列化
          return JSON.stringify(item);
        }
        return String(item ?? "");
      })
      .filter(Boolean)
      .join("\n");
  }
  if (isRecord(content)) {
    if (typeof content.text === "string") return content.text;
    return JSON.stringify(content);
  }
  return content != null ? String(content) : "";
}

function extractImagesFromContent(content: unknown): Array<{ data: string; mimeType: string }> {
  const images: Array<{ data: string; mimeType: string }> = [];
  if (!Array.isArray(content)) return images;
  for (const item of content) {
    if (!isRecord(item)) continue;
    const type = String(item.type ?? "");
    if (type !== "image" && !/image/i.test(type)) continue;
    // 提取 base64 图片数据：支持 { source: { data, media_type } } 或直接 { data, mimeType } 格式
    let data = "";
    let mimeType = "image/png";
    if (typeof item.data === "string") {
      data = item.data;
      if (typeof item.mimeType === "string") mimeType = item.mimeType;
      else if (typeof item.media_type === "string") mimeType = item.media_type;
    } else if (isRecord(item.source)) {
      if (typeof item.source.data === "string") {
        data = item.source.data;
        if (typeof item.source.media_type === "string") mimeType = item.source.media_type;
        else if (typeof item.source.mimeType === "string") mimeType = item.source.mimeType;
      }
    }
    if (data) images.push({ data, mimeType });
  }
  return images;
}

function blockOutput(block: HistoryBlock): string {
  // 优先从标准 content 块递归提取文本，正确处理 Anthropic/AI SDK 格式
  return extractTextFromContent(block.content);
}
function emptyStep(step: number): TimelineStep { return { step, status: "thinking", tokens: [], toolCalls: [] }; }
function appendTimelineEvent(step: TimelineStep, event: TimelineEvent): TimelineStep {
  const events = [...(step.events ?? [])];
  const existing = events.findIndex((item) => item.id === event.id);
  if (existing >= 0) events[existing] = { ...events[existing], ...event };
  else events.push(event);
  return { ...step, events };
}
// 结构事件微任务批处理（借鉴 dsh web GUI Notifier.markDirty）：同一 tick 内的多个事件
// （如 run.finished 收尾的 N 步）合并为一次快照替换；流式 token 仍走 RAF 帧级批处理
const pendingTimelineBySession = new Map<string, Map<number, TimelineStep>>();
let timelineFlushScheduled = false;
function scheduleTimelineFlush() {
  if (timelineFlushScheduled) return;
  timelineFlushScheduled = true;
  queueMicrotask(() => {
    timelineFlushScheduled = false;
    for (const [sessionId, pending] of pendingTimelineBySession) {
      if (!pending.size) continue;
      const view = ensureSessionView(sessionId);
      const next = new Map(view.timeline);
      for (const [step, item] of pending) next.set(step, item);
      view.timeline = next;
    }
    pendingTimelineBySession.clear();
  });
}
function discardPendingTimeline(sessionId: string | null = activeId.value) {
  if (sessionId) pendingTimelineBySession.delete(sessionId);
}
function discardAllPendingTimeline() {
  pendingTimelineBySession.clear();
}
function pendingTimelineFor(sessionId: string) {
  let pending = pendingTimelineBySession.get(sessionId);
  if (!pending) {
    pending = new Map();
    pendingTimelineBySession.set(sessionId, pending);
  }
  return pending;
}
function maxTimelineStep(sessionId: string): number {
  // Avoid spreading an ever-growing timeline into Math.max (which allocates
  // an argument array and can hit the engine's argument limit).
  let max = 0;
  for (const step of ensureSessionView(sessionId).timeline.keys()) {
    if (step > max) max = step;
  }
  for (const step of pendingTimelineBySession.get(sessionId)?.keys() ?? []) {
    if (step > max) max = step;
  }
  return max;
}
function setSessionStep(step: number, updater: (current: TimelineStep) => TimelineStep, sessionId: string | null = activeId.value) {
  if (!sessionId) return;
  const pending = pendingTimelineFor(sessionId);
  const base = pending.get(step) ?? ensureSessionView(sessionId).timeline.get(step) ?? emptyStep(step);
  pending.set(step, updater(base));
  scheduleTimelineFlush();
}
function stepForSession(event: RuntimeEvent, sessionId: string): number {
  const runId = String(event.run_id ?? ensureSessionView(sessionId).activeRunId ?? "");
  const existing = currentStepByRun.get(runId);
  if (existing !== undefined) return existing;
  const base = runStepBase.get(runId) ?? maxTimelineStep(sessionId);
  const fallback = base + 1;
  currentStepByRun.set(runId, fallback);
  return fallback;
}
function addUserMessage(content: string, sessionId: string) {
  const view = ensureSessionView(sessionId);
  view.loaded = true;
  const step = maxTimelineStep(sessionId) + 1;
  const startedAt = new Date().toISOString();
  setSessionStep(step, (current) => ({ ...current, status: "thinking", userMessage: content, userMessageTime: startedAt, runStartedAt: startedAt }), sessionId);
  return step;
}
function hydrateTimeline(
  messages: unknown[],
  runStats: Record<string, { input_tokens: number; output_tokens: number; cache_read_input_tokens: number; elapsed_s: number; context_pct: number }> = {},
  contextInjections: Array<Record<string, unknown>> = [],
  sessionId: string | null = activeId.value,
) {
  if (!sessionId) return;
  const view = ensureSessionView(sessionId);
  discardPendingTimeline(sessionId);
  const next = new Map<number, TimelineStep>();
  const stepByRunId = new Map<string, number>();
  for (const runId of Object.keys(runStats)) runToSession.set(runId, sessionId);
  let step = 0;
  for (const message of messages) {
    const role = entryRole(message);
    const messageRecord = isRecord(message) ? message : {};
    const messageRunId = String((messageRecord as { run_id?: unknown }).run_id ?? "") || undefined;
    const messageTime = String((messageRecord as { ts?: unknown; timestamp?: unknown }).ts ?? (messageRecord as { timestamp?: unknown }).timestamp ?? "");

    // System/developer prompts are runtime context, never conversation output.
    if (role === "system" || role === "developer") continue;

    // --- 1. 处理 role: "tool" 消息（标准AI SDK格式：工具执行结果）---
    if (role === "tool") {
      if (!step) step = 1;
      const current = next.get(step) ?? { ...emptyStep(step), status: "done" };
      const toolCallId = String(messageRecord.tool_call_id ?? messageRecord.tool_use_id ?? "");
      const isError = Boolean(messageRecord.is_error);
      const outputText = extractTextFromContent(messageRecord.content);
      const images = extractImagesFromContent(messageRecord.content);

      const updatedCalls = current.toolCalls.map((call) => {
        if (call.id !== toolCallId) return call;
        return {
          ...call,
          status: isError ? "failed" as const : "done" as const,
          output: outputText || call.output,
          error: isError ? outputText : undefined,
          images: images.length > 0 ? [...(call.images ?? []), ...images] : call.images,
        };
      });
      next.set(step, { ...current, toolCalls: updatedCalls, status: "done" });
      continue;
    }

    // --- 兼容旧格式块（content是数组，包含tool_result块在user消息里）---
    const blocks = historyBlocks(message);
    const visibleBlocks = blocks.filter((block) => !isHiddenHistoryBlock(block));

    // 任务进度是内部画布信息，不在会话区展示。
    if (isTaskProgressInjection(blocks)) continue;
    // 其余内部上下文注入折叠为上下文行挂到当前 turn，不占对话位。
    const injected = contextInjectionOf(blocks);
    if (injected) {
      if (!step) step = 1;
      const current = next.get(step) ?? { ...emptyStep(step), status: "done" };
      next.set(step, { ...current, contextInjections: [...(current.contextInjections ?? []), injected] });
      continue;
    }

    if (role !== "user" && role !== "assistant") continue;
    if (!visibleBlocks.length && role !== "assistant") continue;

    // 模型对压缩摘要的确认消息无信息量，整条丢弃，避免污染该轮总结文本。
    const plainText = blocks.filter((block) => String(block.type) === "text").map(blockText).filter(Boolean).join("\n").trim();
    if (role === "assistant" && /^Understood, I'll continue from this summary\.$/i.test(plainText)) continue;

    // --- 从块中提取文本/思考/工具结果（旧格式） ---
    let text = visibleBlocks.filter((block) => String(block.type) === "text").map(blockText).filter(Boolean).join("\n");
    let thinkingFromBlocks = visibleBlocks.filter((block) => String(block.type) === "thinking").map((block) => typeof block.thinking === "string" ? block.thinking : "").filter(Boolean).join("\n\n");
    const toolResultsFromBlocks = visibleBlocks.filter((block) => String(block.type) === "tool_result");

    // --- 2. 处理 user 消息 ---
    if (role === "user") {
      // 特殊情况：旧格式中user消息只包含tool_result块（没有文本），属于上一轮assistant工具调用的结果
      if (toolResultsFromBlocks.length && !text) {
        if (!step) step = 1;
        const current = next.get(step) ?? { ...emptyStep(step), status: "done" };
        const completed = current.toolCalls.map((call) => {
          const result = toolResultsFromBlocks.find((item) => String(item.tool_use_id) === call.id);
          if (!result) return call;
          const outputText = blockOutput(result);
          const images = extractImagesFromContent(result.content);
          return {
            ...call,
            status: result.is_error ? "failed" as const : "done" as const,
            output: outputText,
            error: result.is_error ? outputText : undefined,
            images: images.length > 0 ? [...(call.images ?? []), ...images] : call.images,
          };
        });
        next.set(step, { ...current, status: "done", runId: messageRunId ?? current.runId, toolCalls: completed });
        continue;
      }

      // 正常用户消息：开始新一步
      step += 1;
      if (messageRunId) {
        stepByRunId.set(messageRunId, step);
        runToSession.set(messageRunId, sessionId);
        currentStepByRun.set(messageRunId, step);
      }
      next.set(step, {
        ...emptyStep(step),
        status: "done",
        runId: messageRunId,
        runStats: messageRunId && runStats[messageRunId] ? {
          inputTokens: Number(runStats[messageRunId].input_tokens ?? 0),
          outputTokens: Number(runStats[messageRunId].output_tokens ?? 0),
          cacheReadInputTokens: Number(runStats[messageRunId].cache_read_input_tokens ?? 0),
          elapsedSeconds: Number(runStats[messageRunId].elapsed_s ?? 0),
          contextPct: Number(runStats[messageRunId].context_pct ?? 0),
        } : undefined,
        userMessage: text,
        userMessageTime: messageTime,
        runStartedAt: messageRunId && messageTime ? messageTime : undefined,
      });
      continue;
    }

    // --- 3. 处理 assistant 消息 ---
    if (!step) step = 1;
    if (messageRunId) {
      stepByRunId.set(messageRunId, step);
      runToSession.set(messageRunId, sessionId);
      currentStepByRun.set(messageRunId, step);
    }
    const current = next.get(step) ?? { ...emptyStep(step), status: "done" };

    // 支持标准AI SDK格式：从顶层字段提取
    // - reasoning_content: 思考过程
    const reasoningContent = typeof messageRecord.reasoning_content === "string" ? messageRecord.reasoning_content : "";
    const thinking = [current.thinking, thinkingFromBlocks, reasoningContent].filter(Boolean).join("\n\n") || undefined;

    // - tool_calls: 工具调用（标准格式 [{id, name, input: {}}]）
    const toolCallsFromTop = Array.isArray(messageRecord.tool_calls) ? messageRecord.tool_calls as Record<string, unknown>[] : [];
    const callsFromTop: ToolCallEntry[] = toolCallsFromTop.map((tc) => ({
      id: String(tc.id ?? crypto.randomUUID()),
      name: String(tc.name ?? t("app.toolCall")),
      params: isRecord(tc.input) ? tc.input : isRecord(tc.arguments) ? tc.arguments : {},
      status: "running", // 初始running，等后续role:tool消息匹配后改为done/failed
    }));

    // 旧格式块中的tool_use
    const callsFromBlocks: ToolCallEntry[] = visibleBlocks.filter((block) => String(block.type) === "tool_use").map((block) => ({
      id: String(block.id ?? block.tool_use_id ?? crypto.randomUUID()),
      name: String(block.name ?? t("app.toolCall")),
      params: isRecord(block.input) ? block.input : isRecord(block.params) ? block.params : {},
      status: "done",
    }));

    const calls = [...callsFromTop, ...callsFromBlocks];

    // 如果没有文本内容，尝试从顶层text字段提取（标准SDK格式）
    if (!text && typeof messageRecord.content === "string") {
      text = messageRecord.content;
    }

    const events: TimelineEvent[] = [
      ...visibleBlocks.flatMap((block, index) => {
        if (String(block.type) === "text" && blockText(block)) return [{ id: `text-${step}-${index}`, kind: "text" as const, text: blockText(block) }];
        if (String(block.type) === "thinking" && typeof block.thinking === "string" && block.thinking) return [{ id: `thinking-${step}-${index}`, kind: "thinking" as const, text: block.thinking }];
        if (String(block.type) === "tool_use") return [{ id: `tool-${String(block.id ?? block.tool_use_id ?? index)}`, kind: "tool" as const, toolCallId: String(block.id ?? block.tool_use_id ?? index) }];
        return [];
      }),
      // 顶层文本作为text事件
      ...(text && !visibleBlocks.some(b => String(b.type) === "text" && blockText(b)) ? [{ id: `text-${step}-top`, kind: "text" as const, text }] : []),
      // 顶层reasoning_content作为thinking事件
      ...(reasoningContent && !thinkingFromBlocks ? [{ id: `thinking-${step}-top`, kind: "thinking" as const, text: reasoningContent }] : []),
      // 顶层tool_calls作为tool事件
      ...callsFromTop.map((tc) => ({ id: `tool-${tc.id}`, kind: "tool" as const, toolCallId: tc.id })),
    ];

    next.set(step, {
      ...current,
      status: "done",
      runId: messageRunId ?? current.runId,
      runStats: messageRunId && runStats[messageRunId] ? {
        inputTokens: Number(runStats[messageRunId].input_tokens ?? 0),
        outputTokens: Number(runStats[messageRunId].output_tokens ?? 0),
        cacheReadInputTokens: Number(runStats[messageRunId].cache_read_input_tokens ?? 0),
        elapsedSeconds: Number(runStats[messageRunId].elapsed_s ?? 0),
        contextPct: Number(runStats[messageRunId].context_pct ?? 0),
      } : current.runStats,
      thinking,
      finalText: [current.finalText, text].filter(Boolean).join("\n\n") || undefined,
      toolCalls: [...current.toolCalls, ...calls],
      events: [...(current.events ?? []), ...events],
    });
  }
  for (const injection of contextInjections) {
    const runId = String(injection.run_id ?? "");
    const injectionStep = stepByRunId.get(runId);
    if (!injectionStep) continue;
    const current = next.get(injectionStep) ?? { ...emptyStep(injectionStep), status: "done" };
    const text = String(injection.text ?? injection.preview ?? "");
    const entry: ContextInjectionEntry = {
      id: `ctx-history-${runId}-${current.contextInjections?.length ?? 0}`,
      source: "system",
      label: String(injection.label ?? t("app.contextInjection")),
      chars: Number(injection.chars ?? text.length),
      preview: String(injection.preview ?? ""),
      text,
      files: Array.isArray(injection.files) ? injection.files.filter((file): file is string => typeof file === "string") : undefined,
    };
    next.set(injectionStep, {
      ...current,
      contextInjections: [...(current.contextInjections ?? []), entry],
    });
  }
  // 历史会话中所有工具调用都应该是完成状态，把没匹配到结果的running工具调用标记为done
  for (const [stepNum, stepData] of next) {
    let needsUpdate = false;
    const updatedCalls = stepData.toolCalls.map((call) => {
      if (call.status === "running") {
        needsUpdate = true;
        return { ...call, status: "done" as const, output: call.output || "" };
      }
      return call;
    });
    if (needsUpdate) {
      next.set(stepNum, { ...stepData, toolCalls: updatedCalls });
    }
  }

  if (view.runActive && view.activeRunId) {
    const runningStep = [...next.entries()].reverse().find(([, item]) => item.runId === view.activeRunId);
    if (runningStep) {
      const [runningStepNumber, item] = runningStep;
      next.set(runningStepNumber, {
        ...item,
        status: item.status === "failed" ? "failed" : "thinking",
        runStartedAt: item.runStartedAt || item.userMessageTime || new Date().toISOString(),
      });
    }
  }
  view.timeline = next;
  view.loaded = true;
}
function runtimeSessionIdFor(event: RuntimeEvent): string | null {
  const runId = String(event.run_id ?? "");
  const relatedRunId = String(event.parent_run_id ?? runId);
  const explicitSessionId = String(event.session_id ?? "");
  if (explicitSessionId) return explicitSessionId;
  const mapped = runToSession.get(relatedRunId) ?? runToSession.get(runId);
  if (mapped) return mapped;
  for (const [sessionId, view] of sessionViews) {
    if (view.activeRunId === relatedRunId || view.activeRunId === runId) return sessionId;
  }
  if (String(event.type ?? "") === "run.started") return runtimeTargetSessionId ?? (sending.value ? activeId.value : null);
  return null;
}
function deferRuntimeEvent(sessionId: string, event: RuntimeEvent) {
  deferredRuntimeEvents.set(sessionId, [...(deferredRuntimeEvents.get(sessionId) ?? []), event]);
}
function applyRuntimeEvent(event: RuntimeEvent) {
  const type = String(event.type ?? "");
  const runId = String(event.run_id ?? "");
  const relatedRunId = String(event.parent_run_id ?? runId);
  if (type === "session.created" || type === "session.closed" || type === "session.waiting_for_input") {
    void refreshIndex();
    return;
  }
  const sessionId = runtimeSessionIdFor(event);
  if (!sessionId) return;
  const view = ensureSessionView(sessionId);
  if (runId) runToSession.set(runId, sessionId);
  if (relatedRunId) runToSession.set(relatedRunId, sessionId);
  if (type === "run.started") {
    finishedRunIds.delete(runId);
    view.activeRunId = runId;
    view.runActive = true;
  } else if (type === "run.finished") {
    finishedRunIds.add(runId);
    if (view.activeRunId === runId) {
      view.activeRunId = null;
      view.runActive = false;
    }
  }
  if (type === "permission.requested" && sessionId !== activeId.value) {
    const toolUseId = String(event.tool_use_id);
    permissionContexts.set(toolUseId, { runId: relatedRunId, sessionId });
    if (!pendingPermissions.value.some((permission) => permission.toolUseId === toolUseId)) {
      pendingPermissions.value = [...pendingPermissions.value, {
        toolUseId,
        toolName: String(event.tool_name),
        preview: String(event.param_preview ?? t("app.awaitingConfirmation")),
        runId: relatedRunId,
        sessionId,
      }];
    }
  } else if (type === "permission.granted" || type === "permission.denied") {
    const toolUseId = String(event.tool_use_id);
    permissionContexts.delete(toolUseId);
    pendingPermissions.value = pendingPermissions.value.filter((permission) => permission.toolUseId !== toolUseId);
  }
  if (type === "question.requested") {
    const rpcId = String(event.rpc_id ?? "");
    if (!rpcId) return;
    questionEventVersion += 1;
    resolvedQuestionIds.delete(rpcId);
    const pending = {
      rpc_id: rpcId,
      session_id: sessionId,
      run_id: runId,
      questions: Array.isArray(event.questions) ? event.questions : [],
    } as PendingUserQuestion;
    pendingUserQuestions.value = [
      ...pendingUserQuestions.value.filter((item) => item.rpc_id !== rpcId),
      pending,
    ];
    return;
  }
  if (type === "question.resolved") {
    const rpcId = String(event.rpc_id ?? "");
    questionEventVersion += 1;
    resolvedQuestionIds.add(rpcId);
    pendingUserQuestions.value = pendingUserQuestions.value.filter((item) => item.rpc_id !== rpcId);
    questionErrors.delete(rpcId);
    if (questionSubmittingId.value === rpcId) questionSubmittingId.value = null;
    return;
  }
  if (!view.loaded || historyLoadPromises.has(sessionId)) {
    deferRuntimeEvent(sessionId, event);
    return;
  }
  applyRuntimeEventToSession(event, sessionId);
}
function applyRuntimeEventToSession(event: RuntimeEvent, sessionId: string) {
  const view = ensureSessionView(sessionId);
  const timeline = { get value() { return view.timeline; } };
  const activeRunId = {
    get value() { return view.activeRunId; },
    set value(value: string | null) { view.activeRunId = value; },
  };
  const runActive = {
    get value() { return view.runActive; },
    set value(value: boolean) { view.runActive = value; },
  };
  const setStep = (step: number, updater: (current: TimelineStep) => TimelineStep) => setSessionStep(step, updater, sessionId);
  const stepFor = (runtimeEvent: RuntimeEvent) => stepForSession(runtimeEvent, sessionId);
  const type = String(event.type ?? "");
  const runId = String(event.run_id ?? "");
  const relatedRunId = String(event.parent_run_id ?? runId);
  const timelineEvent = event.parent_run_id ? { ...event, run_id: relatedRunId } : event;
  if (type !== "llm.token" && relatedRunId) tokenBatcher.flushRun(relatedRunId);
  if (type === "run.finished" && event.parent_run_id) return;
  // run 开始后刷新会话列表，让侧栏中的会话及时从"等待输入"移入"运行中"
  if (type === "run.started") void refreshIndex(false);
  // 权限审批是全局的：即使切到其他会话，后台任务的权限也要能审批，避免任务停滞
  if (type === "permission.requested") {
    const toolUseId = String(event.tool_use_id);
    permissionContexts.set(toolUseId, { runId: relatedRunId, sessionId });
    const perm: PermissionState = { toolUseId, toolName: String(event.tool_name), preview: String(event.param_preview ?? t("app.awaitingConfirmation")), status: "pending" };
    const step = stepFor(timelineEvent);
    setStep(step, (current) => ({ ...current, status: "acting", permission: perm, toolCalls: current.toolCalls.map((call) => call.id === toolUseId ? { ...call, status: "awaiting_permission" } : call) }));
    return;
  }
  if (type === "permission.granted" || type === "permission.denied") {
    const toolUseId = String(event.tool_use_id);
    permissionContexts.delete(toolUseId);
    pendingPermissions.value = pendingPermissions.value.filter((p) => p.toolUseId !== toolUseId);
    for (const step of timeline.value.keys()) setStep(step, (current) => current.permission?.toolUseId === toolUseId ? { ...current, permission: { ...current.permission, status: type === "permission.granted" ? "granted" : "denied" } } : current);
    return;
  }
  if (!relatedRunId) return;
  if (type === "run.started") {
    const messageStep = maxTimelineStep(sessionId);
    setStep(messageStep || 1, (current) => ({ ...current, status: "thinking", runId, runStartedAt: String(event.ts ?? new Date().toISOString()) }));
    liveRunUsage.set(runId, { inputTokens: 0, outputTokens: 0, cacheReadInputTokens: 0 });
    runStartedAtByRun.set(runId, Date.now());
    firstTokenByRun.delete(runId);
    return;
  }
  // 上下文注入：模型实际收到的完整 system 内容 → 可折叠上下文行
  if (type === "context.injected") {
    if (String(event.source ?? "system") === "canvas") return;
    const step = stepFor(timelineEvent);
    const entry: ContextInjectionEntry = {
      id: `ctx-${runId}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      source: String(event.source ?? "system") as ContextInjectionEntry["source"],
      label: String(event.label ?? t("app.contextInjection")),
      chars: Number(event.chars ?? 0),
      preview: String(event.preview ?? ""),
      text: String(event.text ?? event.preview ?? ""),
      files: Array.isArray(event.files) ? event.files.filter((file): file is string => typeof file === "string") : undefined,
    };
    setStep(step, (current) => ({ ...current, contextInjections: [...(current.contextInjections ?? []), entry] }));
    return;
  }
  // 策略干预（权限熔断/卡死干预）：把注入给 LLM 的干预消息展示为上下文行
  if (type === "denial.intervention" || type === "stuck.loop") {
    const step = stepFor(timelineEvent);
    const entry: ContextInjectionEntry = {
      id: `ctx-${type}-${runId}-${Date.now()}`,
      source: "intervention",
      label: type === "denial.intervention" ? t("app.denialIntervention") : t("app.stuckIntervention"),
      chars: String(event.message ?? "").length,
      preview: String(event.message ?? "").slice(0, 90),
      text: String(event.message ?? ""),
    };
    setStep(step, (current) => ({ ...current, contextInjections: [...(current.contextInjections ?? []), entry] }));
    return;
  }
  if (type === "session.message_steered") {
    const content = String(event.content ?? "").trim();
    if (!content) return;
    const step = stepFor(timelineEvent);
    const entry: ContextInjectionEntry = {
      id: `ctx-steering-${runId}-${Date.now()}`,
      source: "steering",
      label: t("app.steeringDirective"),
      chars: content.length,
      preview: content.slice(0, 100),
      text: content,
    };
    setStep(step, (current) => ({ ...current, contextInjections: [...(current.contextInjections ?? []), entry] }));
    return;
  }
  if (type === "step.started") {
    // 每个 run 的 step 从 1 编号，这里按 run 做偏移，保证跨 run 步号不冲突
    if (!runStepBase.has(runId)) runStepBase.set(runId, maxTimelineStep(sessionId));
    const step = (runStepBase.get(runId) ?? 0) + Number(event.step);
    currentStepByRun.set(runId, step);
    setStep(step, (current) => ({ ...current, status: "thinking", runId }));
    return;
  }
  if (type === "phase.changed") {
    // daemon 已明确下发阶段，直接采信；前端推断只在收不到该事件时兜底
    const step = stepFor(timelineEvent);
    const phase = String(event.phase ?? "");
    if (phase) setStep(step, (current) => ({ ...current, daemonPhase: phase as TimelineStep["daemonPhase"] }));
    return;
  }
  if (type === "llm.token") {
    // 首个 token 打时间戳（TTFT），只记录一次
    if (!firstTokenByRun.has(relatedRunId)) firstTokenByRun.set(relatedRunId, Date.now());
    const step = stepFor(timelineEvent);
    tokenBatcher.enqueue(relatedRunId, step, String(event.token ?? ""));
    return;
  }
  if (type === "llm.thinking") {
    const step = stepFor(timelineEvent);
    const thinking = String(event.thinking ?? "");
    if (thinking) setStep(step, (current) => appendThinkingBatch({ ...current, runId: relatedRunId }, [thinking]));
    return;
  }
  if (type === "llm.usage") {
    const step = stepFor(timelineEvent);
    const inputTokens = Number(event.input_tokens ?? 0);
    const outputTokens = Number(event.output_tokens ?? 0);
    const cacheReadInputTokens = Number(event.cache_read_input_tokens ?? 0);
    const previous = liveRunUsage.get(relatedRunId) ?? { inputTokens: 0, outputTokens: 0, cacheReadInputTokens: 0 };
    const cumulative = {
      inputTokens: previous.inputTokens + inputTokens,
      outputTokens: previous.outputTokens + outputTokens,
      cacheReadInputTokens: previous.cacheReadInputTokens + cacheReadInputTokens,
    };
    liveRunUsage.set(relatedRunId, cumulative);
    // 首 token 延迟：首个 llm.token 与 run.started 的时间差（借鉴 dsh assistant-timing）
    const startedAt = runStartedAtByRun.get(relatedRunId);
    const firstTokenAt = firstTokenByRun.get(relatedRunId);
    const ttftMs = startedAt !== undefined && firstTokenAt !== undefined
      ? Math.max(0, firstTokenAt - startedAt)
      : undefined;
    setStep(step, (current) => ({
      ...current,
      runId: relatedRunId,
      usage: {
        inputTokens, outputTokens, contextPct: Number(event.context_pct ?? 0), model: String(event.model ?? ""),
        contextWindow: Number(event.context_window ?? 0), availableTokens: Number(event.available_tokens ?? 0),
        reservedOutputTokens: Number(event.reserved_output_tokens ?? 0), systemTokens: Number(event.system_tokens ?? 0),
        summaryTokens: Number(event.summary_tokens ?? 0), conversationTokens: Number(event.conversation_tokens ?? 0),
        toolTokens: Number(event.tool_tokens ?? 0),
      },
      runStats: { ...cumulative, elapsedSeconds: 0, ttftMs },
    }));
    return;
  }
  if (type === "context.compacting" || type === "context.compacted") {
    const step = stepFor(timelineEvent);
    setStep(step, (current) => current.usage ? ({
      ...current,
      usage: {
        ...current.usage,
        compacting: type === "context.compacting",
        compactedTokens: type === "context.compacted"
          ? Math.max(0, Number(event.original_tokens ?? 0) - Number(event.summary_tokens ?? 0))
          : current.usage.compactedTokens,
      },
    }) : current);
    return;
  }
  if (type === "tool.call_started") {
    const step = stepFor(timelineEvent);
    const call: ToolCallEntry = { id: String(event.tool_use_id), name: String(event.tool_name), params: (event.params as Record<string, unknown>) ?? {}, status: "running", startedAt: String(event.started_at ?? "") };
    // 写文件工具落盘可视化产物时登记，待写入完成后自动预览
    if ((call.name === "write_file" || call.name === "edit_file") && typeof call.params.path === "string" && VISUAL_ARTIFACT_RE.test(call.params.path)) {
      pendingVisualWrites.set(call.id, call.params.path);
    }
    setStep(step, (current) => appendTimelineEvent({ ...current, status: "acting", toolCalls: [...current.toolCalls.filter((item) => item.id !== call.id), call] }, { id: `tool-${call.id}`, kind: "tool", toolCallId: call.id }));
    return;
  }
  if (type === "tool.call_finished" || type === "tool.call_failed") {
    const step = stepFor(timelineEvent);
    const callId = String(event.tool_use_id);
    setStep(step, (current) => ({ ...current, status: "observing", toolCalls: current.toolCalls.map((call) => call.id !== callId ? call : { ...call, status: type === "tool.call_finished" ? "done" : "failed", output: type === "tool.call_finished" ? String(event.output ?? "") : undefined, error: type === "tool.call_failed" ? String(event.error_message ?? t("app.toolCallFailed")) : undefined, elapsedMs: Number(event.elapsed_ms ?? 0), images: type === "tool.call_finished" && Array.isArray(event.images) ? (event.images as { mimeType: string; data: string }[]) : undefined }) }));
    const visualPath = pendingVisualWrites.get(callId);
    pendingVisualWrites.delete(callId);
    if (visualPath && type === "tool.call_finished") autoPreviewVisualArtifacts(sessionId, [visualPath]);
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
    const changedPaths = (event.paths as string[] | undefined) ?? [];
    setStep(step, (current) => ({ ...current, changes: [...(current.changes ?? []), { paths: changedPaths, workspacePath: String(event.workspace_path ?? "") }] }));
    autoPreviewVisualArtifacts(sessionId, changedPaths);
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
  if (type === "workflow.started") {
    const step = stepFor(timelineEvent);
    const tasks = ((event.tasks as Record<string, unknown>[] | undefined) ?? []).map((task) => ({
      id: String(task.id ?? ""),
      title: String(task.title ?? ""),
      owner: String(task.owner ?? "coder") as WorkflowTaskEntry["owner"],
      status: String(task.status ?? "pending") as WorkflowTaskEntry["status"],
      dependencies: (task.dependencies as string[] | undefined) ?? [],
      completionCriteria: (task.completion_criteria as string[] | undefined) ?? [],
      allowedPaths: (task.allowed_paths as string[] | undefined) ?? [],
      attempt: Number(task.attempt ?? 0),
      error: String(task.error ?? "") || undefined,
    }));
    setStep(step, (current) => ({ ...current, workflowTasks: tasks }));
    return;
  }
  if (type === "workflow.task_updated") {
    const step = stepFor(timelineEvent);
    const task = (event.task as Record<string, unknown> | undefined) ?? {};
    const entry = {
      id: String(task.id ?? ""),
      title: String(task.title ?? ""),
      owner: String(task.owner ?? "coder") as WorkflowTaskEntry["owner"],
      status: String(task.status ?? "pending") as WorkflowTaskEntry["status"],
      dependencies: (task.dependencies as string[] | undefined) ?? [],
      completionCriteria: (task.completion_criteria as string[] | undefined) ?? [],
      allowedPaths: (task.allowed_paths as string[] | undefined) ?? [],
      attempt: Number(task.attempt ?? 0),
      error: String(task.error ?? "") || undefined,
    };
    setStep(step, (current) => ({ ...current, workflowTasks: [...(current.workflowTasks ?? []).filter((item) => item.id !== entry.id), entry] }));
    return;
  }
  if (type === "workflow.handoff") {
    const step = stepFor(timelineEvent);
    const artifact = (event.artifact as Record<string, unknown> | undefined) ?? {};
    setStep(step, (current) => ({ ...current, workflowHandoffs: [...(current.workflowHandoffs ?? []), {
      taskId: String(artifact.task_id ?? ""),
      role: String(artifact.role ?? "coder") as "planner" | "coder" | "tester" | "reviewer",
      status: String(artifact.status) === "failed" ? "failed" : "succeeded",
      summary: String(artifact.summary ?? ""),
      changedPaths: (artifact.changed_paths as string[] | undefined) ?? [],
      scopeEscalations: (artifact.scope_escalations as string[] | undefined) ?? [],
      commands: (artifact.commands as string[] | undefined) ?? [],
      output: String(artifact.output ?? ""),
      conclusion: String(artifact.conclusion ?? ""),
      childRunId: String(artifact.child_run_id ?? ""),
    }] }));
    return;
  }
  if (type === "workflow.reviewed") {
    const step = stepFor(timelineEvent);
    setStep(step, (current) => ({ ...current, workflowReviews: [...(current.workflowReviews ?? []), {
      taskId: String(event.task_id ?? ""),
      decision: String(event.decision) === "accept" ? "accept" : "return",
      diffSummary: String(event.diff_summary ?? ""),
      testSummary: String(event.test_summary ?? ""),
      securitySummary: String(event.security_summary ?? ""),
      conclusion: String(event.conclusion ?? ""),
    }] }));
    return;
  }
  if (type === "workflow.finished") {
    const step = stepFor(timelineEvent);
    setStep(step, (current) => ({ ...current, workflowOutcome: {
      status: String(event.status) as "succeeded" | "failed" | "cancelled" | "timed_out",
      reason: String(event.reason ?? ""),
      totalTokens: Number(event.total_tokens ?? 0),
      elapsedS: Number(event.elapsed_s ?? 0),
    } }));
    return;
  }
  if (type === "skill.invoked") {
    const step = stepFor(timelineEvent);
    setStep(step, (current) => ({ ...current, skills: [...(current.skills ?? []), { name: String(event.skill_name ?? ""), arguments: String(event.arguments ?? "") }] }));
    return;
  }
  if (type === "step.finished") {
    const step = Number(event.step ?? stepFor(timelineEvent));
    setStep(step, (current) => ({ ...current, status: current.status === "acting" ? "observing" : "done", finalText: current.finalText || current.streamText || current.tokens.join("") }));
    return;
  }
  if (type === "run.finished") {
    const runStatus = String(event.status);
    for (const step of timeline.value.keys()) {
      setStep(step, (current) => current.runId === relatedRunId ? {
        ...current,
        status: runStatus === "success" ? "done" : "failed",
        finalText: current.finalText || current.streamText || current.tokens.join(""),
        outcome: {
          status: runStatus === "interrupted" ? "interrupted" : (runStatus === "success" ? "success" : "failed"),
          reason: String(event.reason ?? "") || undefined,
        },
        runStats: {
          inputTokens: Number(event.total_input_tokens ?? 0),
          outputTokens: Number(event.total_output_tokens ?? 0),
          cacheReadInputTokens: Number(event.cache_read_input_tokens ?? 0),
          elapsedSeconds: Number(event.elapsed_s ?? 0),
          contextPct: Number(event.context_pct ?? 0),
          ttftMs: current.runStats?.ttftMs,
        },
      } : current);
    }
    if (runId === activeRunId.value) {
      activeRunId.value = null;
      runActive.value = false;
    }
    liveRunUsage.delete(relatedRunId);
    runStartedAtByRun.delete(relatedRunId);
    firstTokenByRun.delete(relatedRunId);
    void refreshIndex(false);
    void drainSessionQueue(sessionId);
    return;
  }
}

async function loadSessionHistory(sessionId: string) {
  const view = ensureSessionView(sessionId);
  if (view.loaded) return;
  const existing = historyLoadPromises.get(sessionId);
  if (existing) return existing;
  const version = (historyLoadVersionBySession.get(sessionId) ?? 0) + 1;
  historyLoadVersionBySession.set(sessionId, version);
  const previousTimer = sessionLoadingTimers.get(sessionId);
  if (previousTimer) window.clearTimeout(previousTimer);
  const timer = window.setTimeout(() => { view.loading = true; }, 260);
  sessionLoadingTimers.set(sessionId, timer);
  const request = (async () => {
    let hydrated = false;
    try {
      const history = await sessionHistory(sessionId);
      if (historyLoadVersionBySession.get(sessionId) !== version) return;
      hydrateTimeline(history.messages, history.run_stats, history.context_injections, sessionId);
      hydrated = true;
    } catch (error) {
      console.warn("Failed to load session history", error);
    } finally {
      window.clearTimeout(timer);
      if (sessionLoadingTimers.get(sessionId) === timer) sessionLoadingTimers.delete(sessionId);
      view.loading = false;
      historyLoadPromises.delete(sessionId);
    }
    if (!hydrated) return;
    // 恢复每个run的文件变更列表（changes不存储在消息历史中，需要单独拉取）
    const runIds = new Set<string>();
    for (const step of view.timeline.values()) {
      if (step.runId) runIds.add(step.runId);
    }
    for (const rid of runIds) {
      try {
        const changes = await listChanges(wsId.value, rid);
        if (historyLoadVersionBySession.get(sessionId) !== version) return;
        const stepEntry = [...view.timeline.entries()].find(([, s]) => s.runId === rid);
        if (!stepEntry || !changes.length) continue;
        const [stepNum, step] = stepEntry;
        const existing = step.changes ?? [];
        const existingPaths = new Set(existing.map((c) => c.path.toLowerCase()));
        const merged: ChangeEntry[] = [...existing];
        for (const ch of changes) {
          if (!existingPaths.has(ch.path.toLowerCase())) merged.push(ch);
        }
        view.timeline.set(stepNum, { ...step, changes: merged });
      } catch { /* ignore list changes errors for historical runs */ }
    }
    const deferred = deferredRuntimeEvents.get(sessionId) ?? [];
    deferredRuntimeEvents.delete(sessionId);
    for (const event of deferred) applyRuntimeEvent(event);
  })();
  historyLoadPromises.set(sessionId, request);
  return request;
}

async function refreshIndex(loadHistory = false) {
  connected.value = await connectRuntime();
  runtimeConnectionError.value = getRuntimeConnectionError();
  if (!connected.value) { loading.value = false;
    if ("__TAURI_INTERNALS__" in window) {
      // splash 已改为轮询探测 daemon 就绪，不再依赖 app:ready 事件
    }
 return; }
  const questionVersion = questionEventVersion;
  const [nextWorkspaces, nextSessions, nextSettings, nextProvider, questionSnapshot] = await Promise.all([
    listWorkspaces(), listSessions(), getRuntimeSettings(), getProviderStatus(), listPendingUserQuestions(),
  ]);
  workspaces.value = nextWorkspaces; sessions.value = nextSessions; runtimeSettings.value = nextSettings; providerStatus.value = nextProvider;
  const snapshot = questionSnapshot.filter((item) => !resolvedQuestionIds.has(item.rpc_id));
  if (questionVersion === questionEventVersion) {
    pendingUserQuestions.value = snapshot;
  } else {
    const merged = new Map(snapshot.map((item) => [item.rpc_id, item]));
    for (const item of pendingUserQuestions.value) {
      if (!resolvedQuestionIds.has(item.rpc_id)) merged.set(item.rpc_id, item);
    }
    pendingUserQuestions.value = [...merged.values()];
  }
  for (const session of nextSessions) {
    const view = ensureSessionView(session.session_id);
    const latestRunId = session.latest_run_id ?? null;
    if (latestRunId) {
      runToSession.set(latestRunId, session.session_id);
      if (session.status === "active" && !finishedRunIds.has(latestRunId)) {
        view.activeRunId = latestRunId;
        view.runActive = true;
      }
    } else if (session.status !== "active") {
      view.activeRunId = null;
      view.runActive = false;
    }
  }
  workspace.value ??= nextWorkspaces[0] ?? null;
  activeId.value ??= nextSessions.find((item) => !item.archived)?.session_id ?? null;
  if (loadHistory && activeId.value) await loadSessionHistory(activeId.value);
  loading.value = false;
    if ("__TAURI_INTERNALS__" in window) {
      // splash 已改为轮询探测 daemon 就绪，不再依赖 app:ready 事件
    }

}

// 提交当前问题的完整回答批次；后端成功后 question.resolved 会释放 composer
async function submitUserQuestion(pending: PendingUserQuestion, answers: UserQuestionAnswer[]) {
  questionSubmittingId.value = pending.rpc_id;
  questionErrors.delete(pending.rpc_id);
  try {
    await respondUserQuestion(pending, answers);
    pendingUserQuestions.value = pendingUserQuestions.value.filter((item) => item.rpc_id !== pending.rpc_id);
  } catch (error) {
    questionErrors.set(pending.rpc_id, error instanceof Error ? error.message : String(error));
  } finally {
    if (questionSubmittingId.value === pending.rpc_id) questionSubmittingId.value = null;
  }
}

function beginTask(project: Workspace | null = workspace.value) {
  if (!activeId.value) saveComposerDraft(workspace.value?.workspace_id ?? null, prompt.value);
  window.clearTimeout(projectPreviewCloseTimer);
  projectPreviewId.value = null;
  sessionPreview.value = null;
  projectActionsOpen.value = null;
  closeLauncherMenus();
  workspace.value = project;
  activeId.value = null;
  launcherTimeline.value = new Map();
  attachedFiles.value = [];
  page.value = "work";
  prompt.value = loadComposerDraft(project?.workspace_id ?? null);
  void nextTick(() => launcherPrompt.value?.focus());
}
function insertProvisionalSession(sessionId: string, title: string, project: Workspace | null) {
  const now = new Date().toISOString();
  const provisional: Session = {
    session_id: sessionId,
    title: title.slice(0, 40),
    status: "waiting_for_input",
    updated_at: now,
    archived: false,
    pinned: false,
    workspace_id: project?.workspace_id ?? null,
    latest_run_id: null,
    total_input_tokens: 0,
    total_output_tokens: 0,
    total_elapsed_s: 0,
  };
  sessions.value = [provisional, ...sessions.value.filter((item) => item.session_id !== sessionId)];
}
async function startSessionRun(sessionId: string, content: string, images: ImageBlock[] = [], clearDraft = false): Promise<boolean> {
  const trimmed = content.trim();
  if (!trimmed || !connected.value || sending.value) return false;
  const session = sessions.value.find((item) => item.session_id === sessionId);
  if (session?.archived || session?.status === "closed") return false;
  const clientMessageId = crypto.randomUUID();
  const view = ensureSessionView(sessionId);
  const messageStep = addUserMessage(trimmed, sessionId);
  sending.value = true;
  if (clearDraft && activeId.value === sessionId) prompt.value = "";
  try {
    runtimeTargetSessionId = sessionId;
    const runId = await sendPrompt(sessionId, trimmed, images, clientMessageId);
    runToSession.set(runId, sessionId);
    const stopRequested = stopRequestedSessions.delete(sessionId);
    // run.finished 可能在 session.send_message 响应前到达，不能把已结束的 run 重新标成运行中。
    if (!finishedRunIds.has(runId)) {
      view.activeRunId = runId;
      view.runActive = true;
    }
    setSessionStep(messageStep, (current) => ({ ...current, runId }), sessionId);
    if (stopRequested && !finishedRunIds.has(runId)) {
      try {
        await cancelRun(runId);
      } catch (error) {
        // 取消请求失败不应把已经成功提交的任务误标为发送失败。
        console.warn("Failed to cancel run requested before run_id was available", error);
      }
    }
    return true;
  } catch (error) {
    stopRequestedSessions.delete(sessionId);
    setSessionStep(messageStep, (current) => ({
      ...current,
      status: "failed",
      outcome: { status: "failed", reason: error instanceof Error ? error.message : String(error) },
    }), sessionId);
    return false;
  } finally {
    runtimeTargetSessionId = null;
    sending.value = false;
  }
}
async function submitTask(content: string, project: Workspace | null = workspace.value, images: ImageBlock[] = []): Promise<boolean> {
  const trimmed = content.trim();
  if (!trimmed || !connected.value || sending.value) return false;
  if (activeId.value) return await startSessionRun(activeId.value, trimmed, images, true);

  sending.value = true;
  try {
    const sessionId = await createSession(project);
    // 先把新会话放入本地索引，避免等待下一次 session.list 才能渲染会话区。
    insertProvisionalSession(sessionId, trimmed, project);
    const view = ensureSessionView(sessionId);
    view.timeline = new Map();
    view.activeRunId = null;
    view.runActive = false;
    view.loaded = true;
    activeId.value = sessionId;
    page.value = "work";
    saveComposerDraft(project?.workspace_id ?? null, "");
    prompt.value = "";
    sending.value = false;
    const sent = await startSessionRun(sessionId, trimmed, images);
    if (sent) void refreshIndex(false);
    return sent;
  } finally {
    runtimeTargetSessionId = null;
    sending.value = false;
  }
}
function enqueueSubmission(sessionId: string, text: string, payload: string, images: ImageBlock[], attachmentCount: number) {
  const view = ensureSessionView(sessionId);
  view.queue = [...view.queue, {
    id: crypto.randomUUID(),
    text,
    contentSuffix: payload.startsWith(text) ? payload.slice(text.length) : "",
    images: images.map((image) => ({ ...image })),
    attachmentCount,
    attachments: attachedFiles.value.map((file) => ({ ...file })),
  }];
}
// 编辑待处理任务 = 把它原样退回输入框：文本回到 prompt，附件回到 attachedFiles，
// 再从队列里移除。这样复用输入框的全部编辑能力，也不会丢掉已附加的文件。
function editQueuedSubmission(id: string) {
  const view = activeView.value;
  const item = view?.queue.find((entry) => entry.id === id);
  if (!view || !item || view.queueBusyId === id) return;
  prompt.value = prompt.value.trim() ? `${prompt.value.trim()}\n\n${item.text}` : item.text;
  const known = new Set(attachedFiles.value.map((file) => file.path));
  attachedFiles.value = [
    ...attachedFiles.value,
    ...item.attachments.filter((file) => !known.has(file.path)).map((file) => ({ ...file })),
  ];
  view.queue = view.queue.filter((entry) => entry.id !== id);
  slashMenuDismissed.value = false;
  void nextTick(() => (activeId.value ? activePrompt.value : launcherPrompt.value)?.focus());
}
function removeQueuedSubmission(id: string) {
  const view = activeView.value;
  if (!view || view.queueBusyId === id) return;
  view.queue = view.queue.filter((item) => item.id !== id);
}
async function steerQueuedSubmission(id: string) {
  const sessionId = activeId.value;
  const view = activeView.value;
  const item = view?.queue.find((entry) => entry.id === id);
  if (!sessionId || !view?.runActive || !item || view.queueBusyId) return;
  view.queueBusyId = id;
  try {
    await steerPrompt(sessionId, item.text + item.contentSuffix, item.images);
    view.queue = view.queue.filter((entry) => entry.id !== id);
  } catch (error) {
    void showProjectNotice(t("app.steerFailed"), friendlyError(error).message, "danger");
  } finally {
    view.queueBusyId = null;
  }
}
async function drainSessionQueue(sessionId: string) {
  const view = ensureSessionView(sessionId);
  if (view.runActive || view.queueDispatching || !view.queue.length) return;
  if (sending.value) {
    window.setTimeout(() => { void drainSessionQueue(sessionId); }, 180);
    return;
  }
  const item = view.queue[0];
  view.queueDispatching = true;
  view.queueBusyId = item.id;
  try {
    const sent = await startSessionRun(sessionId, item.text + item.contentSuffix, item.images);
    if (sent) view.queue = view.queue.filter((entry) => entry.id !== item.id);
  } finally {
    view.queueBusyId = null;
    view.queueDispatching = false;
  }
}
// 停止当前正在执行的 run；后端取消后通过 run.finished 事件更新界面状态
async function stopActiveRun() {
  const runId = activeRunId.value;
  if (!runId) {
    // 发送 RPC 仍在等待 run_id；保留停止意图，避免按钮点击被吞掉。
    if (sending.value && activeId.value) stopRequestedSessions.add(activeId.value);
    return;
  }
  try {
    await cancelRun(runId);
  } catch (error) {
    // 保持运行态与停止入口，用户可以再次发起取消；最终状态只由 run.finished 收尾。
    console.warn(t("app.stopRequestTimeout"), error);
  }
}
async function chooseTask(id: string) {
  taskSearchOpen.value = false;
  try {
    const stored = JSON.parse(localStorage.getItem("sztu.unreadSessions") ?? "[]");
    if (Array.isArray(stored) && stored.includes(id)) {
      localStorage.setItem("sztu.unreadSessions", JSON.stringify(stored.filter((item) => item !== id)));
    }
  } catch {
    // Ignore unavailable localStorage in embedded/private webviews.
  }
  document.dispatchEvent(new CustomEvent("sztu:session-unread-change", {
    detail: { sessionId: id, unread: false },
  }));
  const session = sessions.value.find((item) => item.session_id === id);
  const view = ensureSessionView(id);
  const latestRunId = session?.latest_run_id ?? null;
  if (latestRunId) {
    runToSession.set(latestRunId, id);
    if (session?.status === "active" && !view.activeRunId) {
      view.activeRunId = latestRunId;
      view.runActive = true;
    }
  }
  activeId.value = id;
  page.value = "work";
  await loadSessionHistory(id);
}
async function chooseWorkspace(item: Workspace) { workspace.value = item; projectMenuOpen.value = false; const matching = liveSessions.value.find((session) => session.workspace_id === item.workspace_id); if (matching) await chooseTask(matching.session_id); }
// 解析 URL hash (#session=<id>) 并激活对应会话：支撑"在新窗口打开"与"复制会话链接"，
// 链接失效或会话已删除时静默回退到默认启动页。
function consumeSessionHash() {
  const match = /#session=([^&]+)/.exec(window.location.hash ?? "");
  if (!match) return;
  const sessionId = decodeURIComponent(match[1]);
  history.replaceState(null, "", window.location.pathname + window.location.search);
  const tryActivate = (attempt: number) => {
    const session = sessions.value.find((item) => item.session_id === sessionId);
    if (session) {
      const owner = workspaces.value.find((item) => item.workspace_id === session.workspace_id);
      if (owner) workspace.value = owner;
      void chooseTask(sessionId);
      return;
    }
    // 会话索引尚未加载完成时重试；期间用户已手动选择会话则放弃
    if (attempt < 10 && !activeId.value) window.setTimeout(() => tryActivate(attempt + 1), 600);
  };
  tryActivate(0);
}
async function createProjectTask(item: Workspace) {
  projectActionsOpen.value = null;
  beginTask(item);
}
async function showProjectFiles(item: Workspace) {
  projectActionsOpen.value = null;
  // 跳转到右侧功能栏的「文件」标签页并浏览该项目（seq 递增保证重复点击也能触发）
  filesRequest.value = { workspaceId: item.workspace_id, seq: ++filesRequestSeq };
  workspace.value = item;
  setInspectorOpen(true);
  const matching = liveSessions.value.find((session) => session.workspace_id === item.workspace_id);
  if (matching) {
    await chooseTask(matching.session_id);
  } else if (!activeId.value) {
    // 无活动会话：为该工作区建一个会话，保证会话区 UI 不空白、可恢复
    const sessionId = await createSession(item);
    const view = ensureSessionView(sessionId);
    view.timeline = new Map();
    view.loaded = true;
    activeId.value = sessionId;
    page.value = "work";
    await refreshIndex(false);
  }
}
async function deleteProject(item: Workspace) {
  projectActionsOpen.value = null;
  const ok = await confirm(t("app.deleteProjectConfirm", { name: item.name }), { title: t("app.deleteProjectTitle"), kind: "warning" });
  if (!ok) return;
  try {
    await deleteWorkspace(item.workspace_id);
  } catch (error) {
    // 删除失败（如命中安全护栏）时保留列表并提示
    void showProjectNotice(t("app.deleteProjectFailed"), friendlyError(error).message, "danger");
    return;
  }
  workspaces.value = workspaces.value.filter((entry) => entry.workspace_id !== item.workspace_id);
  if (workspace.value?.workspace_id === item.workspace_id) {
    workspace.value = workspaces.value[0] ?? null;
    activeId.value = null;
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
async function submit(gesture: ComposerSubmitGesture = "enter") {
  const content = prompt.value.trim();
  if (!content || steering.value || (sending.value && !isAppending.value)) return;
  if (activeId.value && (active.value?.archived || active.value?.status === "closed")) return;
  const mode = ({ "/plan": "plan", "/edits": "accept_edits", "/auto": "auto" } as const)[content as "/plan" | "/edits" | "/auto"];
  if (mode) {
    await choosePermissionMode(mode);
    prompt.value = "";
    slashMenuDismissed.value = false;
    void nextTick(() => (activeId.value ? activePrompt.value : launcherPrompt.value)?.focus());
    return;
  }
  const { content: payload, images } = buildMessagePayload(content);
  const attachmentCount = attachedFiles.value.length;
  const sessionId = activeId.value;
  if (sessionId && isAppending.value) {
    const submitMode = resolveComposerSubmitMode(true, gesture, true);
    if (submitMode === "queue") {
      enqueueSubmission(sessionId, content, payload, images, attachmentCount);
      prompt.value = "";
      attachedFiles.value = [];
    } else {
      steering.value = true;
      try {
        await steerPrompt(sessionId, payload, images);
        prompt.value = "";
        attachedFiles.value = [];
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        // run 刚好结束时 steer 会被服务拒绝，此时转入队列；其它错误不能静默吞掉草稿。
        const runStillActive = sessionId ? ensureSessionView(sessionId).runActive : false;
        if (!runStillActive && sessionId) {
          // 追加提交与 run.finished 同时到达时，直接启动一个新的 run，
          // 避免输入框一直停留在追加模式且任务没有进入运行态。
          const sent = await startSessionRun(sessionId, payload, images);
          if (sent) {
            prompt.value = "";
            attachedFiles.value = [];
          }
        } else if (/busy|steer unavailable|session busy|运行中|繁忙/i.test(message)) {
          enqueueSubmission(sessionId, content, payload, images, attachmentCount);
          prompt.value = "";
          attachedFiles.value = [];
        } else {
          void showProjectNotice(t("app.sendFailed"), friendlyError(error).message, "danger");
        }
      } finally {
        steering.value = false;
      }
    }
    slashMenuDismissed.value = false;
    void nextTick(() => activePrompt.value?.focus());
    return;
  }
  const sent = await submitTask(payload, workspace.value, images);
  if (sent) attachedFiles.value = [];
}
// Shift+Enter 换行；运行中 Enter 排队，Ctrl/Cmd+Enter 转入当前轮，并忽略输入法候选确认
function onComposerKeydown(event: KeyboardEvent) {
  if (slashMenuOpen.value && !event.isComposing) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const count = slashItems.value.length;
      if (count) slashMenuActiveIndex.value = (slashMenuActiveIndex.value + (event.key === "ArrowDown" ? 1 : -1) + count) % count;
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      // 阻止冒泡到全局快捷键，避免"关闭斜杠菜单"被误当作"停止任务"
      event.stopPropagation();
      slashMenuDismissed.value = true;
      return;
    }
    if (event.key === "Enter" && !event.shiftKey && !event.ctrlKey && !event.metaKey && !event.altKey && slashItems.value.length) {
      event.preventDefault();
      chooseSkill(slashItems.value[Math.min(slashMenuActiveIndex.value, slashItems.value.length - 1)].name);
      return;
    }
  }
  if (event.key !== "Enter" || event.shiftKey) return;
  if (event.isComposing || event.keyCode === 229 || event.repeat || event.altKey) return;
  event.preventDefault();
  void submit(event.ctrlKey || event.metaKey ? "accelerated" : "enter");
}
async function decidePermission(toolUseId: string, decision: PermissionDecision) {
  const context = permissionContexts.get(toolUseId);
  if (!context) throw new Error("Permission request is no longer active");
  await respondPermission(toolUseId, decision, context.runId, context.sessionId);
}
function beginProjectEdit(item: Workspace) {
  window.clearTimeout(projectPreviewCloseTimer);
  projectPreviewId.value = null;
  projectEditingId.value = item.workspace_id;
  projectEditName.value = item.name;
  projectEditError.value = "";
  projectActionsOpen.value = null;
}
function closeProjectEdit() {
  if (projectActionBusy.value) return;
  projectEditingId.value = null;
  projectEditError.value = "";
}
function settleProjectDialog(accepted: boolean) {
  const resolve = projectDialogResolve;
  projectDialogResolve = null;
  projectDialog.value = null;
  resolve?.(accepted);
}
function openProjectDialog(dialog: ProjectDialogState): Promise<boolean> {
  projectDialogResolve?.(false);
  projectDialog.value = dialog;
  return new Promise((resolve) => { projectDialogResolve = resolve; });
}
async function showProjectNotice(title: string, dialogMessage: string, tone: ProjectDialogTone = "neutral") {
  await openProjectDialog({ title, message: dialogMessage, tone, confirmLabel: t("app.gotIt") });
}
async function confirmProjectAction(title: string, dialogMessage: string, confirmLabel: string) {
  return await openProjectDialog({ title, message: dialogMessage, tone: "danger", confirmLabel, cancelLabel: t("app.cancel") });
}
async function saveProjectEdit() {
  const item = projectBeingEdited.value;
  if (!item) return;
  if (!projectEditName.value.trim() || projectActionBusy.value) return;
  projectActionBusy.value = true;
  projectEditError.value = "";
  try {
    const updated = await renameWorkspace(item.workspace_id, projectEditName.value);
    workspaces.value = workspaces.value.map((entry) => entry.workspace_id === updated.workspace_id ? updated : entry);
    projectEditingId.value = null;
    projectActionsOpen.value = null;
  } catch (error) { projectEditError.value = error instanceof Error ? error.message : String(error); }
  finally { projectActionBusy.value = false; }
}
async function toggleProjectPinned(item: Workspace) {
  if (projectActionBusy.value) return;
  projectActionBusy.value = true;
  try {
    const updated = await pinWorkspace(item.workspace_id, !item.pinned);
    workspaces.value = workspaces.value.map((entry) => entry.workspace_id === updated.workspace_id ? updated : entry);
    projectActionsOpen.value = null;
  } catch (error) { await showProjectNotice(t("app.actionFailed"), error instanceof Error ? error.message : String(error), "danger"); }
  finally { projectActionBusy.value = false; }
}
async function openProjectExplorer(item: Workspace) {
  projectActionsOpen.value = null;
  try {
    await invoke("open_path_with_app", { path: item.path, appId: "explorer" });
  } catch (error) {
    await showProjectNotice(t("app.openExplorerFailed"), error instanceof Error ? error.message : String(error), "danger");
  }
}
async function createProjectWorktree(item: Workspace) {
  if (projectActionBusy.value) return;
  projectActionBusy.value = true;
  projectActionsOpen.value = null;
  try {
    const status = await workspaceStatus(item.workspace_id);
    if (!status.is_git_repository) {
      await showProjectNotice(t("app.worktreeCreateFailed"), t("app.worktreeNotGitRepo"));
      return;
    }
    const result = await invoke<{ path: string }>("create_persistent_worktree", { workspacePath: item.path, worktreeId: item.workspace_id, label: "project" });
    await showProjectNotice(t("app.worktreeCreated"), result.path, "success");
  } catch (error) {
    await showProjectNotice(t("app.worktreeCreateFailed"), error instanceof Error ? error.message : String(error), "danger");
  }
  finally { projectActionBusy.value = false; }
}
async function archiveProjectChats(item: Workspace) {
  if (projectActionBusy.value) return;
  const chats = sessions.value.filter((session) => session.workspace_id === item.workspace_id && !session.archived);
  projectActionsOpen.value = null;
  if (!chats.length) {
    await showProjectNotice(t("app.archiveChats"), t("app.archiveNoChats"));
    return;
  }
  projectActionBusy.value = true;
  try {
    await Promise.all(chats.map((session) => archiveSession(session.session_id)));
    await refreshIndex(false);
    await showProjectNotice(t("app.archiveDone"), t("app.archiveCount", { n: chats.length }), "success");
  } catch (error) {
    await showProjectNotice(t("app.archiveFailed"), error instanceof Error ? error.message : String(error), "danger");
  }
  finally { projectActionBusy.value = false; }
}
async function removeProject(item: Workspace) {
  if (projectActionBusy.value) return;
  const chats = sessions.value.filter((session) => session.workspace_id === item.workspace_id);
  projectActionsOpen.value = null;
  const chatSummary = chats.length
    ? t("app.removeProjectChatSummary", { n: chats.length })
    : t("app.removeProjectNoChats");
  const accepted = await confirmProjectAction(t("app.removeProject"), t("app.removeProjectConfirm", { name: item.name, chatSummary }), t("app.removeProjectConfirmLabel"));
  if (!accepted) return;
  projectActionBusy.value = true;
  try {
    await Promise.all(chats.map((session) => moveSession(session.session_id, null)));
    await deleteWorkspace(item.workspace_id);
    workspaces.value = workspaces.value.filter((workspaceItem) => workspaceItem.workspace_id !== item.workspace_id);
    const wasCurrentWorkspace = workspace.value?.workspace_id === item.workspace_id;
    await refreshIndex(false);
    if (wasCurrentWorkspace) workspace.value = null;
    await showProjectNotice(t("app.removeDone"), chats.length ? t("app.removeChatsMoved", { n: chats.length }) : t("app.removeProjectDone"), "success");
  } catch (error) {
    await refreshIndex(false);
    await showProjectNotice(t("app.removeFailed"), error instanceof Error ? error.message : String(error), "danger");
  }
  finally { projectActionBusy.value = false; }
}
// 撤销后清除该 run 的全部改动，使变更卡片随之消失
function handleReverted(runId: string) {
  discardPendingTimeline();
  const next = new Map(timeline.value);
  for (const [step, item] of next) {
    if (item.runId === runId) next.set(step, { ...item, changes: [] });
  }
  timeline.value = next;
  void refreshIndex(false);
}
// 重试：回退该 run 的所有文件改动，删除旧输出，从用户消息下方重新开始
async function handleRetry(runId: string, userMessage: string) {
  const wsId = activeWorkspace.value?.workspace_id;
  if (!wsId) return;
  try {
    // 1. 回退文件改动
    const changes = await listChanges(wsId, runId);
    const paths = changes.map((c) => c.path);
    if (paths.length) {
      await revertChanges(wsId, runId, paths);
    }

    // 2. 删除该runId的所有旧输出，保留用户消息
    discardPendingTimeline();
    const next = new Map<number, TimelineStep>();

    for (const [stepNum, item] of timeline.value) {
      if (item.runId === runId) {
        // 属于该run的step：如果包含用户消息，保留消息清空输出；否则跳过（删除）
        if (item.userMessage) {
          const resetStep: TimelineStep = {
            ...emptyStep(stepNum),
            userMessage: item.userMessage,
            userMessageTime: item.userMessageTime,
            permissionMode: item.permissionMode,
          };
          next.set(stepNum, resetStep);
        }
        // 没有userMessage的assistant输出step直接删除，不加入next
      } else {
        // 不属于该run的step完整保留
        next.set(stepNum, item);
      }
    }

    timeline.value = next;
    void refreshIndex(false);

    // 3. 滚动到底部，等待UI更新后重新提交任务
    nextTick(() => {
      keepTaskStreamAtBottom();
    });
    await submitTask(userMessage, null);
  } catch (error) {
    void showProjectNotice(t("app.retryFailed"), friendlyError(error).message, "danger");
  }
}
// 中断任务的"继续执行"：向当前会话补发一条续跑消息，复用交接摘要作为上下文
function handleContinue() {
  void submitTask("继续", null);
}
// 所有变更审阅统一进入右上角 Git 源代码管理页
function handleReview() {
  if (activeWorkspace.value) openPage("source-control");
}
async function openLocalProject() {
  closeLauncherMenus();
  const selected = await openDialog({ directory: true, multiple: false, title: t("app.openLocalProjectTitle") });
  if (typeof selected !== "string") return;
  workspace.value = await openWorkspace(selected);
  await refreshIndex(false);
  beginTask(workspace.value);
}
function closeLauncherMenus() {
  launcherProjectMenuOpen.value = false;
  launcherPermissionMenuOpen.value = false;
}
function toggleLauncherProjectMenu() {
  launcherProjectMenuOpen.value = !launcherProjectMenuOpen.value;
  launcherPermissionMenuOpen.value = false;
  if (!launcherProjectMenuOpen.value) launcherProjectQuery.value = "";
}
function toggleLauncherPermissionMenu() {
  launcherPermissionMenuOpen.value = !launcherPermissionMenuOpen.value;
  launcherProjectMenuOpen.value = false;
  permissionSettingsError.value = "";
}
function chooseLauncherWorkspace(item: Workspace) {
  workspace.value = item;
  closeLauncherMenus();
  launcherProjectQuery.value = "";
}
function clearLauncherWorkspace() {
  workspace.value = null;
  closeLauncherMenus();
  launcherProjectQuery.value = "";
}
async function createLocalWorkspace() {
  closeLauncherMenus();
  const selected = await openDialog({ directory: true, multiple: false, title: t("app.newWorkspaceDialogTitle") });
  if (typeof selected !== "string") return;
  workspace.value = await openWorkspace(selected);
  await refreshIndex(false);
  beginTask(workspace.value);
}
// 按 1KB/1MB 格式化附件大小
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
function removeAttachment(index: number) { attachedFiles.value = attachedFiles.value.filter((_, i) => i !== index); }
// 从当前附件构造发送载荷：文本附件拼进 content，图片附件收集成 images 内容块
function buildMessagePayload(baseText: string): { content: string; images: ImageBlock[] } {
  const images: ImageBlock[] = [];
  const sections: string[] = [];
  for (const att of attachedFiles.value) {
    if (att.kind === "image" && att.dataBase64) {
      images.push({ media_type: att.mime ?? "image/png", data: att.dataBase64 });
    } else if (att.kind === "text" && att.textContent) {
      sections.push(`[附件: ${att.name}]\n\`\`\`\n${att.textContent}\n\`\`\``);
    }
  }
  return { content: [baseText, ...sections].filter(Boolean).join("\n\n"), images };
}
// 被跳过的附件统一汇总为一次提示，避免多文件时连续弹窗
function notifySkippedAttachments(skipped: string[]) {
  if (!skipped.length) return;
  const shown = skipped.slice(0, 4).join(t("app.attachmentSkipSeparator"));
  const more = skipped.length > 4 ? t("app.attachmentsMoreSkipped", { n: skipped.length - 4 }) : "";
  void showProjectNotice(t("app.attachmentsPartiallySkipped"), shown + more, "danger");
}
// 处理「添加附件」读取结果：图片/文本归档，超限或二进制在 error 中提示并跳过
function addReadAttachments(results: Attachment[]) {
  const added: PendingAttachment[] = [];
  const skipped: string[] = [];
  for (const item of results) {
    if (item.error) { skipped.push(`${item.name}：${friendlyError(item.error).message}`); continue; }
    if (item.mime_type?.startsWith("image/") && item.data_base64) {
      added.push({ path: item.path, name: item.name, size: item.size, kind: "image", mime: item.mime_type, dataBase64: item.data_base64 });
    } else if (item.is_text && item.text_content != null) {
      added.push({ path: item.path, name: item.name, size: item.size, kind: "text", textContent: item.text_content });
    } else {
      skipped.push(t("app.attachmentUnsupported", { name: item.name }));
    }
  }
  if (added.length) attachedFiles.value = [...attachedFiles.value, ...added];
  notifySkippedAttachments(skipped);
}
async function selectAttachments() {
  if ("__TAURI_INTERNALS__" in window) {
    const selected = await openDialog({ directory: false, multiple: true, title: t("app.addAttachment") });
    const paths = typeof selected === "string" ? [selected] : selected ?? [];
    if (!paths.length) return;
    addReadAttachments(await readAttachments(paths));
  } else {
    // 浏览器（非 Tauri）回退：用 file input 读取本地文件
    const input = document.createElement("input");
    input.type = "file";
    input.multiple = true;
    input.style.display = "none";
    input.addEventListener("change", () => {
      const files = Array.from(input.files ?? []);
      void (async () => {
        const skipped: string[] = [];
        for (const file of files) {
          const reason = await addBrowserFile(file);
          if (reason) skipped.push(reason);
        }
        notifySkippedAttachments(skipped);
      })();
      input.remove();
    });
    document.body.appendChild(input);
    input.click();
  }
}
// 浏览器回退：把 File 读成图片 base64 或文本内容，附带同样的限制；返回跳过原因（null 表示已添加）
async function addBrowserFile(file: File): Promise<string | null> {
  const isImage = file.type.startsWith("image/");
  const limit = isImage ? 5 * 1024 * 1024 : 1024 * 1024;
  if (file.size > limit) return t("app.attachmentTooLarge", { name: file.name, limit: isImage ? "5MB" : "1MB" });
  if (isImage) {
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result ?? ""));
      reader.onerror = () => reject(new Error(t("app.attachmentReadImageFailed")));
      reader.readAsDataURL(file);
    }).catch(() => "");
    const comma = dataUrl.indexOf(",");
    const dataBase64 = comma >= 0 ? dataUrl.slice(comma + 1) : "";
    if (dataBase64) attachedFiles.value = [...attachedFiles.value, { path: file.name, name: file.name, size: file.size, kind: "image", mime: file.type, dataBase64 }];
    return dataBase64 ? null : t("app.attachmentReadFailed", { name: file.name });
  }
  const textLike = !file.type || file.type.startsWith("text/") || ["application/json", "application/xml"].includes(file.type);
  if (!textLike) return t("app.attachmentUnsupported", { name: file.name });
  const text = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(new Error(t("app.attachmentReadFileFailed")));
    reader.readAsText(file);
  }).catch(() => "");
  attachedFiles.value = [...attachedFiles.value, { path: file.name, name: file.name, size: file.size, kind: "text", mime: file.type || undefined, textContent: text.slice(0, 32 * 1024) }];
  return null;
}
// 处理输入框粘贴：剪贴板含图片时读取为附件并阻止默认行为，纯文本粘贴正常放行
function onPasteImage(event: ClipboardEvent) {
  const items = event.clipboardData?.items;
  if (!items) return;
  for (const item of Array.from(items)) {
    if (item.kind === "file" && item.type.startsWith("image/")) {
      const file = item.getAsFile();
      if (file) {
        event.preventDefault();
        void addBrowserFile(file);
      }
      break;
    }
  }
}
function chooseSkill(name: string) {
  prompt.value = "/" + name + " ";
  slashMenuDismissed.value = false;
  void nextTick(() => (activeId.value ? activePrompt.value : launcherPrompt.value)?.focus());
}
function handlePromptInput() {
  slashMenuDismissed.value = false;
  slashMenuActiveIndex.value = 0;
}
function closeActiveSession() { activeId.value = null; launcherTimeline.value = new Map(); void refreshIndex(false); }
async function applyPermissionMode(value: RuntimeSettings["permission_mode"]) {
  permissionSaving.value = true;
  permissionSettingsError.value = "";
  try {
    const result = await setRuntimeSettings({ permission_mode: value });
    if (result) runtimeSettings.value = result;
    launcherPermissionMenuOpen.value = false;
  } catch (error) {
    permissionSettingsError.value = friendlyError(error).message;
  } finally {
    permissionSaving.value = false;
  }
}
async function choosePermissionMode(value: RuntimeSettings["permission_mode"]) {
  if (value === "auto" && runtimeSettings.value?.permission_mode !== "auto") {
    launcherPermissionMenuOpen.value = false;
    permissionConfirmOpen.value = true;
    return;
  }
  await applyPermissionMode(value);
}
async function confirmFullAccess() {
  await applyPermissionMode("auto");
  if (!permissionSettingsError.value) permissionConfirmOpen.value = false;
}
function handleModelConfigUpdated(settings: RuntimeSettings, status: ProviderStatus | null) {
  runtimeSettings.value = settings;
  providerStatus.value = status;
}
function openModelManager() { settingsInitialSection.value = "agent"; settingsOpen.value = true; }
function openSettings() {
  settingsInitialSection.value = "appearance";
  settingsOpen.value = true;
  projectMenuOpen.value = false;
  closeLauncherMenus();
}
function closeAppMenu() { activeAppMenu.value = null; }
function toggleAppMenu(menu: AppMenu) {
  const focused = document.activeElement;
  if (focused instanceof HTMLInputElement || focused instanceof HTMLTextAreaElement || focused instanceof HTMLElement && focused.isContentEditable) lastEditableElement = focused;
  activeAppMenu.value = activeAppMenu.value === menu ? null : menu;
}
function runAppMenuAction(action: () => void | Promise<void>) { closeAppMenu(); void action(); }
function currentComposer() { return activeId.value ? activePrompt.value : launcherPrompt.value; }
function editCurrentField(command: "undo" | "redo" | "cut" | "copy" | "paste" | "selectAll") {
  const target = lastEditableElement ?? currentComposer();
  closeAppMenu();
  void nextTick(() => {
    target?.focus();
    if (command === "selectAll" && (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement)) target.select();
    else document.execCommand(command);
  });
}
function openInspectorTool(tool: "files" | "browser" | "terminal") {
  if (!activeWorkspace.value) return;
  setInspectorOpen(true);
  void nextTick(() => inspectorRef.value?.[tool === "files" ? "openFiles" : tool === "browser" ? "openBrowser" : "openTerminal"]?.());
}
function openCommandPalette() {
  prompt.value = "/";
  slashMenuDismissed.value = false;
  slashMenuActiveIndex.value = 0;
  void nextTick(() => currentComposer()?.focus());
}
function toggleStatusBar() {
  statusBarVisible.value = !statusBarVisible.value;
  localStorage.setItem("sztu.statusBarVisible", String(statusBarVisible.value));
}
async function applyZoom(next: number) {
  const zoom = Math.min(2, Math.max(.6, Math.round(next * 10) / 10));
  webviewZoom.value = zoom;
  localStorage.setItem("sztu.webviewZoom", String(zoom));
  try { await getCurrentWebview().setZoom(zoom); }
  catch { document.documentElement.style.zoom = String(zoom); }
}
async function openWorkspaceInIde() {
  const target = activeSessionWorkspace.value;
  if (!target) return;
  try { await invoke("open_workspace_in_ide", { workspaceId: target.workspace_id, workspacePath: target.path }); }
  catch (error) { void showProjectNotice(t("app.openIdeFailed"), friendlyError(error).message, "danger"); }
}
async function openProjectHomepage() {
  const { openUrl } = await import("@tauri-apps/plugin-opener");
  await openUrl("https://github.com/rojim666/SztuCode");
}
async function openLicense() {
  const { openUrl } = await import("@tauri-apps/plugin-opener");
  await openUrl("https://github.com/rojim666/SztuCode/blob/main/LICENSE");
}
async function showKeyboardShortcuts() {
  const mod = isMacOS ? "⌘" : "Ctrl";
  await message(t("app.keyboardShortcutsBody", { mod }), { title: t("app.keyboardShortcuts"), kind: "info" });
}
async function showAbout() {
  await message(t("app.aboutBody"), { title: t("app.about"), kind: "info" });
}
function closeSettings() {
  settingsOpen.value = false;
  void nextTick(() => settingsButton.value?.focus());
}
function handleAppearanceChange(settings: AppearanceSettings) {
  appearanceSettings.value = settings;
}
function openPage(next: Page) { page.value = next; projectMenuOpen.value = false; modeMenuOpen.value = false; closeLauncherMenus(); if (next === "chat") chatView.value = "home"; }
function switchWorkMode(mode: WorkMode) { workMode.value = mode; modeMenuOpen.value = false; }
async function submitChat(content: string) {
  const { content: payload, images } = buildMessagePayload(content);
  await submitTask(payload, null, images);
  attachedFiles.value = [];
  page.value = "chat";
  chatView.value = "home";
}
const isMacOS = isMacOSPlatform();
async function minimizeWindow() { await getCurrentWindow().minimize(); }
// macOS：Rust 无动画 work-area fill，避开 NSWindow.zoom 与主面板不同步
async function toggleMaximizeWindow() {
  if (isMacOS) {
    await invoke("macos_toggle_work_area");
    return;
  }
  await getCurrentWindow().toggleMaximize();
}
async function closeWindow() { await getCurrentWindow().close(); }
let stopMacTitlebandDragArm: (() => void) | undefined;
// 顶栏空白区：移动超过阈值再拖窗，避免吞掉单击/双击；双击用 dblclick 最大化
function onMacTitlebandPointerDown(event: PointerEvent) {
  if (event.button !== 0) return;
  const target = event.target as HTMLElement | null;
  if (target?.closest(".nav-toggle-wrap, button, a, input, textarea, select, [role='button']")) return;
  if (event.detail >= 2) {
    event.preventDefault();
    return;
  }
  stopMacTitlebandDragArm?.();
  const startX = event.clientX;
  const startY = event.clientY;
  const onMove = (moveEvent: PointerEvent) => {
    if (Math.hypot(moveEvent.clientX - startX, moveEvent.clientY - startY) < 4) return;
    stopMacTitlebandDragArm?.();
    void getCurrentWindow().startDragging().catch(() => undefined);
  };
  const onUp = () => { stopMacTitlebandDragArm?.(); };
  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onUp, { once: true });
  window.addEventListener("pointercancel", onUp, { once: true });
  stopMacTitlebandDragArm = () => {
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    window.removeEventListener("pointercancel", onUp);
    stopMacTitlebandDragArm = undefined;
  };
}
async function onMacTitlebandDblClick(event: MouseEvent) {
  const target = event.target as HTMLElement | null;
  if (target?.closest(".nav-toggle-wrap, button, a, input, textarea, select, [role='button']")) return;
  event.preventDefault();
  stopMacTitlebandDragArm?.();
  try {
    await toggleMaximizeWindow();
  } catch (error) {
    console.error("toggleMaximizeWindow failed", error);
  }
}
function animateSidebarCollapsed(next: boolean) {
  sidebarAnimating.value = true;
  sidebarCollapsed.value = next;
  window.clearTimeout(sidebarAnimTimer);
  sidebarAnimTimer = window.setTimeout(() => { sidebarAnimating.value = false; }, 220);
}
function toggleSidebar() {
  animateSidebarCollapsed(!sidebarCollapsed.value);
  sidebarAutoCollapsed = false;
}
// 拖动边界调整导航宽度，越过最小宽度后的折叠阈值才收起导航
function startSidebarDrag(event: PointerEvent) {
  if (sidebarCollapsed.value || event.button !== 0) return;
  event.preventDefault();
  stopSidebarDragListeners?.();
  const target = event.currentTarget as HTMLElement;
  target.setPointerCapture?.(event.pointerId);
  const startX = event.clientX;
  const startWidth = sidebarWidth.value;
  sidebarResizing.value = true;
  sidebarAutoCollapsed = false;
  document.body.style.cursor = "col-resize";
  document.body.style.userSelect = "none";
  let rafId = 0;
  let pendingWidth = startWidth;
  let pendingOverPull = 0;
  let pendingArmed = false;
  const flush = () => {
    rafId = 0;
    sidebarWidth.value = Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, pendingWidth));
    sidebarPull.value = -Math.min(14, pendingOverPull * .28);
    sidebarCollapseArmed.value = pendingArmed;
  };
  const onMove = (moveEvent: PointerEvent) => {
    pendingWidth = startWidth + moveEvent.clientX - startX;
    pendingOverPull = Math.max(0, SIDEBAR_MIN_WIDTH - pendingWidth);
    pendingArmed = pendingOverPull >= SIDEBAR_COLLAPSE_PULL;
    if (!rafId) rafId = requestAnimationFrame(flush);
  };
  const finish = () => {
    if (rafId) { cancelAnimationFrame(rafId); flush(); }
    stopSidebarDragListeners?.();
    sidebarResizing.value = false;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    target.releasePointerCapture?.(event.pointerId);
    if (sidebarCollapseArmed.value) sidebarCollapsed.value = true;
    else localStorage.setItem("sztu.sidebarWidth", String(Math.round(sidebarWidth.value)));
    sidebarCollapseArmed.value = false;
    sidebarPull.value = 0;
  };
  document.addEventListener("pointermove", onMove);
  document.addEventListener("pointerup", finish, { once: true });
  document.addEventListener("pointercancel", finish, { once: true });
  stopSidebarDragListeners = () => {
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerup", finish);
    document.removeEventListener("pointercancel", finish);
    stopSidebarDragListeners = undefined;
  };
}
// 支持键盘在限定范围内调整导航宽度
function resizeSidebarWithKeyboard(event: KeyboardEvent) {
  let nextWidth = sidebarWidth.value;
  if (event.key === "ArrowLeft") nextWidth -= 16;
  else if (event.key === "ArrowRight") nextWidth += 16;
  else if (event.key === "Home") nextWidth = SIDEBAR_MIN_WIDTH;
  else if (event.key === "End") nextWidth = SIDEBAR_MAX_WIDTH;
  else return;
  event.preventDefault();
  sidebarWidth.value = Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, nextWidth));
  localStorage.setItem("sztu.sidebarWidth", String(sidebarWidth.value));
}
function applySidebarAutoCollapse() {
  const belowFullSidebarSize = window.innerWidth < FULL_SIDEBAR_MIN_WIDTH || window.innerHeight < FULL_SIDEBAR_MIN_HEIGHT;
  if (belowFullSidebarSize) {
    if (!sidebarCollapsed.value) {
      animateSidebarCollapsed(true);
      sidebarAutoCollapsed = true;
    }
    return;
  }
  if (sidebarAutoCollapsed) {
    animateSidebarCollapsed(false);
    sidebarAutoCollapsed = false;
  }
}
function applyInspectorAutoCollapse() {
  // 窄窗口自动收起右侧功能栏，避免会话区被挤没
  if (window.innerWidth < INSPECTOR_AUTO_COLLAPSE_WIDTH) {
    if (inspectorOpen.value) {
      setInspectorOpen(false);
      inspectorAutoCollapsed = true;
    }
  } else if (inspectorAutoCollapsed) {
    inspectorAutoCollapsed = false;
    setInspectorOpen(true);
  }
}
function handleWindowResize() {
  windowWidth.value = window.innerWidth;
  windowResizing.value = true;
  window.clearTimeout(windowResizeEndTimer);
  windowResizeEndTimer = window.setTimeout(() => {
    windowResizing.value = false;
    // 先卸掉 window-resizing（transition:none），再播侧栏列宽动画
    void nextTick(() => {
      applySidebarAutoCollapse();
      applyInspectorAutoCollapse();
    });
  }, 120);
}
function handleGlobalShortcut(event: KeyboardEvent) {
  const mod = event.ctrlKey || event.metaKey;
  // Ctrl/Cmd+Escape 是运行中的紧急停止快捷键，不受输入框焦点影响。
  if (mod && event.key === "Escape" && isRunActive.value) {
    event.preventDefault();
    void stopActiveRun();
    return;
  }
  if (mod && event.key.toLowerCase() === "n") { event.preventDefault(); beginTask(); }
  if (mod && event.key.toLowerCase() === "o") { event.preventDefault(); void openLocalProject(); }
  if (mod && event.key.toLowerCase() === "e") { event.preventDefault(); openPage("source-control"); }
  if (mod && event.key.toLowerCase() === "j") { event.preventDefault(); openInspectorTool("terminal"); }
  if (mod && event.key.toLowerCase() === "g") { event.preventDefault(); openInspectorTool("files"); }
  if (mod && event.shiftKey && event.key.toLowerCase() === "b") { event.preventDefault(); openInspectorTool("browser"); }
  if (mod && event.shiftKey && event.key === "/") { event.preventDefault(); void showKeyboardShortcuts(); }
  if (mod && event.key === "=") { event.preventDefault(); void applyZoom(webviewZoom.value + .1); }
  if (mod && event.key === "-") { event.preventDefault(); void applyZoom(webviewZoom.value - .1); }
  if (mod && event.key === "0") { event.preventDefault(); void applyZoom(1); }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "b") { event.preventDefault(); toggleSidebar(); }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); openCommandPalette(); }
  if (event.key === "Escape") {
    if (activeAppMenu.value) closeAppMenu();
    else if (permissionConfirmOpen.value) permissionConfirmOpen.value = false;
    else if (slashMenuOpen.value) slashMenuDismissed.value = true;
    else if (isRunActive.value) void stopActiveRun();
    else closeLauncherMenus();
  }
}
function handleDocumentPointerDown(event: PointerEvent) {
  const target = event.target as HTMLElement | null;
  if (!target?.closest(".app-menu-bar")) closeAppMenu();
  if (!target?.closest(".task-search-popover, .task-search-toggle")) clearTaskSearch();
  if (!target?.closest(".project-row-shell")) projectActionsOpen.value = null;
  if (!target?.closest(".launcher-project-control")) launcherProjectMenuOpen.value = false;
  if (!target?.closest(".launcher-permission-control")) launcherPermissionMenuOpen.value = false;
  if (!target?.closest(".mode-switch-wrap")) modeMenuOpen.value = false;
}
let stopEvents: (() => void) | undefined;
let stopDisconnect: (() => void) | undefined;
let runtimeReconnectTimer: number | undefined;
let runtimeReconnectAttempt = 0;
let runtimeRefreshPromise: Promise<void> | null = null;

function scheduleRuntimeReconnect() {
  if (runtimeReconnectTimer !== undefined || connected.value) return;
  const delay = Math.min(500 * (2 ** runtimeReconnectAttempt), 5_000);
  runtimeReconnectAttempt += 1;
  runtimeReconnectTimer = window.setTimeout(() => {
    runtimeReconnectTimer = undefined;
    void refreshRuntime(false);
  }, delay);
}

async function refreshRuntime(loadHistory: boolean) {
  if (runtimeRefreshPromise) return runtimeRefreshPromise;
  runtimeRefreshPromise = refreshIndex(loadHistory)
    .then(() => {
      if (connected.value) runtimeReconnectAttempt = 0;
      else scheduleRuntimeReconnect();
    })
    .catch((error) => {
      connected.value = false;
      console.warn("Failed to reconnect to local service", error);
      scheduleRuntimeReconnect();
    })
    .finally(() => { runtimeRefreshPromise = null; });
  return runtimeRefreshPromise;
}

// 输出链接 → 右侧浏览器栏：打开 Inspector 并导航到目标 URL；
// 无挂载的工作区面板（ref 为空）时回退系统默认浏览器
function onOpenInAppBrowser(event: Event) {
  const url = (event as CustomEvent<{ url: string }>).detail?.url;
  if (!url) return;
  const inspector = inspectorRef.value;
  if (inspector?.openUrlInAppBrowser) {
    setInspectorOpen(true);
    inspector.openUrlInAppBrowser(url);
  } else {
    void import("@tauri-apps/plugin-opener").then(({ openUrl }) => openUrl(url));
  }
}

// AI 输出中的文件链接 → 在右侧功能栏「文件」标签页中预览
async function onOpenFileLink(event: Event) {
  const rawPath = (event as CustomEvent<{ path: string }>).detail?.path;
  if (!rawPath) return;
  const ws = activeWorkspace.value;
  if (!ws?.path) return;
  // 确保右侧功能栏是打开的，并切到文件标签页
  setInspectorOpen(true);
  // 标准化路径：去掉行号后缀、统一分隔符为 /、去掉开头的 ./ 前缀（../ 交由 FileTree 解析）
  let targetPath = rawPath.trim();
  targetPath = targetPath.replace(/:\d+(?:-\d+)?$/, "");
  targetPath = targetPath.replace(/\\/g, "/").replace(/^\.\//, "");
  // 等待 inspector 渲染后调用 previewFile（传递相对路径，FileTree 内部会处理解析）
  await nextTick();
  inspectorRef.value?.previewFile(targetPath);
}

// 文件变更徽章 → 打开对应文件的diff预览
async function onOpenFileFromTimeline(rawPath: string) {
  setInspectorOpen(true);
  await nextTick();
  inspectorRef.value?.openChangeDiff(rawPath);
}

// AI 生成可视化产物（报告 / HTML / 图片）后自动打开右侧功能栏预览最新一个
function autoPreviewVisualArtifacts(sessionId: string, paths: string[]) {
  if (!sessionId || sessionId !== activeId.value) return;
  const target = [...paths].reverse().find((p) => VISUAL_ARTIFACT_RE.test(p));
  if (!target) return;
  const key = target.replace(/\\/g, "/").toLowerCase();
  const seen = autoPreviewedArtifacts.get(sessionId) ?? new Set<string>();
  autoPreviewedArtifacts.set(sessionId, seen);
  // 同一文件已预览过且面板被用户关闭 → 不重复打扰
  if (seen.has(key) && !inspectorOpen.value) return;
  seen.add(key);
  setInspectorOpen(true);
  void nextTick(() => inspectorRef.value?.previewFile(target));
}

// 打开所有变更面板
async function onOpenChangesFromTimeline(_runId: string) {
  setInspectorOpen(true);
  await nextTick();
  inspectorRef.value?.openChangesPanel();
}

// 内置浏览器元素选择器 → 把选中的元素信息追加到对话输入框
function onInjectElement(event: Event) {
  const text = (event as CustomEvent<{ text: string }>).detail?.text;
  if (!text?.trim()) return;
  prompt.value = prompt.value.trim() ? `${prompt.value.trim()}\n\n${text}` : text;
  void nextTick(() => currentComposer()?.focus());
}

onMounted(() => {
  window.addEventListener("keydown", handleGlobalShortcut);
  window.addEventListener("resize", handleWindowResize);
  handleWindowResize(); // 初始化窗口宽度与窄窗自动收起状态
  window.addEventListener("sztu:open-in-app-browser", onOpenInAppBrowser);
  window.addEventListener("sztu:open-file", onOpenFileLink);
  window.addEventListener("sztu:inject-element", onInjectElement);
  document.addEventListener("pointerdown", handleDocumentPointerDown);
  stopDisconnect = onRuntimeDisconnect(() => {
    connected.value = false;
    scheduleRuntimeReconnect();
  });
  stopEvents = onRuntimeEvent(applyRuntimeEvent);
  if ("__TAURI_INTERNALS__" in window) {
    void Promise.all([
      listen("tray://new_chat", () => beginTask()),
      listen("tray://workspaces", () => { page.value = "work"; }),
      listen("tray://settings", () => { settingsOpen.value = true; }),
    ]).then((unlisteners) => { trayListeners = unlisteners; });
  }
  void refreshRuntime(true);
  consumeSessionHash();
  window.addEventListener("hashchange", consumeSessionHash);
  nextTick(refreshTurnObserver);
});
onBeforeUnmount(() => {
  window.clearTimeout(projectPreviewCloseTimer);
  if (autoScrollFrame !== undefined) window.cancelAnimationFrame(autoScrollFrame);
  tokenBatcher.clear();
  discardAllPendingTimeline();
  for (const timer of sessionLoadingTimers.values()) window.clearTimeout(timer);
  sessionLoadingTimers.clear();
  stopSidebarDragListeners?.();
  stopMacTitlebandDragArm?.();
  window.clearTimeout(sidebarAnimTimer);
  window.clearTimeout(windowResizeEndTimer);
  window.clearTimeout(runtimeReconnectTimer);
  window.clearTimeout(scrollToTurnTimer);
  if (turnScrollRaf) cancelAnimationFrame(turnScrollRaf);
  turnObserver?.disconnect();
  document.body.style.cursor = "";
  document.body.style.userSelect = "";
  if (inspectorCloseTimer) clearTimeout(inspectorCloseTimer);
  if (inspectorOpenFrame !== undefined) cancelAnimationFrame(inspectorOpenFrame);
  window.removeEventListener("keydown", handleGlobalShortcut);
  trayListeners.forEach((stop) => stop());
  trayListeners = [];
  window.removeEventListener("resize", handleWindowResize);
  window.removeEventListener("sztu:open-in-app-browser", onOpenInAppBrowser);
  window.removeEventListener("sztu:open-file", onOpenFileLink);
  window.removeEventListener("sztu:inject-element", onInjectElement);
  window.removeEventListener("hashchange", consumeSessionHash);
  document.removeEventListener("pointerdown", handleDocumentPointerDown);
  stopEvents?.();
  stopDisconnect?.();
});
watch(page, (next) => { if (next === "skills") void refreshIndex(false); });
// 切换/新建会话后会话流从头渲染，回到底部按钮状态随之复位
watch(activeId, () => { streamScrolledUp.value = false; });
</script>

<template>
  <div
    class="kimi-shell"
    :class="{ 'is-macos': isMacOS, 'sidebar-collapsed': sidebarCollapsed, 'sidebar-resizing': sidebarResizing, 'sidebar-animating': sidebarAnimating, 'sidebar-collapse-armed': sidebarCollapseArmed, 'window-resizing': windowResizing }"
    :style="{ '--sidebar-width': `${sidebarWidth}px`, '--sidebar-pull': `${sidebarPull}px` }"
  >
    <!-- macOS: fixed toolbar — toggle never moves between titlebar / sidebar. -->
    <header v-if="isMacOS" class="sidebar-macos-toolbar" @pointerdown="onMacTitlebandPointerDown" @dblclick="onMacTitlebandDblClick">
      <div class="nav-toggle-wrap" @pointerdown.stop @dblclick.stop>
        <button class="nav-toggle" type="button" aria-controls="primary-navigation" :aria-expanded="!sidebarCollapsed" :aria-label="sidebarCollapsed ? t('app.expandNav') : t('app.collapseNav')" @click="toggleSidebar">
          <AppIcon v-if="sidebarCollapsed" name="PanelLeftOpen" :size="16" />
          <AppIcon v-else name="PanelLeftClose" :size="16" />
        </button>
        <div class="nav-toggle-tooltip" role="tooltip"><span>{{ sidebarCollapsed ? t('app.expandNav') : t('app.collapseNav') }}</span><kbd>⌘</kbd><kbd>B</kbd></div>
      </div>
    </header>
    <header class="kimi-titlebar" :class="{ 'is-macos': isMacOS }">
      <div v-if="!isMacOS" class="nav-toggle-wrap">
        <button class="nav-toggle" type="button" aria-controls="primary-navigation" :aria-expanded="!sidebarCollapsed" :aria-label="sidebarCollapsed ? t('app.expandNav') : t('app.collapseNav')" @click="toggleSidebar">
          <AppIcon v-if="sidebarCollapsed" name="PanelLeftOpen" :size="16" />
          <AppIcon v-else name="PanelLeftClose" :size="16" />
        </button>
        <div class="nav-toggle-tooltip" role="tooltip"><span>{{ sidebarCollapsed ? t('app.expandNav') : t('app.collapseNav') }}</span><kbd>Ctrl</kbd><kbd>B</kbd></div>
      </div>
      <nav class="app-menu-bar" :aria-label="t('app.appMenuAria')" @pointerdown.stop @dblclick.stop>
        <div class="app-menu-item">
          <button type="button" aria-haspopup="menu" :aria-expanded="activeAppMenu === 'file'" @click="toggleAppMenu('file')">{{ t('app.file') }}</button>
          <div v-if="activeAppMenu === 'file'" class="app-menu-popover" role="menu" :aria-label="t('app.fileMenuAria')">
            <button type="button" role="menuitem" @click="runAppMenuAction(() => beginTask())"><span>{{ t('app.newTask') }}</span><kbd>{{ isMacOS ? '⌘' : 'Ctrl' }} N</kbd></button>
            <button type="button" role="menuitem" @click="runAppMenuAction(openLocalProject)"><span>{{ t('app.openFolder') }}</span><kbd>{{ isMacOS ? '⌘' : 'Ctrl' }} O</kbd></button>
            <div class="app-menu-separator" role="separator" />
            <button type="button" role="menuitem" :disabled="!activeWorkspace" @click="runAppMenuAction(() => openInspectorTool('terminal'))"><span>{{ t('app.newTerminal') }}</span><kbd>{{ isMacOS ? '⌘' : 'Ctrl' }} J</kbd></button>
            <button type="button" role="menuitem" :disabled="!activeWorkspace" @click="runAppMenuAction(() => openInspectorTool('browser'))"><span>{{ t('app.newBrowser') }}</span><kbd>{{ isMacOS ? '⌘' : 'Ctrl' }} ⇧ B</kbd></button>
            <div class="app-menu-separator" role="separator" />
            <button type="button" role="menuitem" :disabled="!activeSessionWorkspace" @click="runAppMenuAction(openWorkspaceInIde)"><span>{{ t('app.openInIde') }}</span></button>
            <div class="app-menu-separator" role="separator" />
            <button type="button" role="menuitem" @click="runAppMenuAction(closeWindow)"><span>{{ t('app.quit') }}</span></button>
          </div>
        </div>
        <div class="app-menu-item">
          <button type="button" aria-haspopup="menu" :aria-expanded="activeAppMenu === 'edit'" @click="toggleAppMenu('edit')">{{ t('app.edit') }}</button>
          <div v-if="activeAppMenu === 'edit'" class="app-menu-popover" role="menu" :aria-label="t('app.editMenuAria')">
            <button type="button" role="menuitem" @click="editCurrentField('undo')"><span>{{ t('app.undo') }}</span><kbd>{{ isMacOS ? '⌘' : 'Ctrl' }} Z</kbd></button>
            <button type="button" role="menuitem" @click="editCurrentField('redo')"><span>{{ t('app.redo') }}</span><kbd>{{ isMacOS ? '⌘' : 'Ctrl' }} Y</kbd></button>
            <div class="app-menu-separator" role="separator" />
            <button type="button" role="menuitem" @click="editCurrentField('cut')"><span>{{ t('app.cut') }}</span><kbd>{{ isMacOS ? '⌘' : 'Ctrl' }} X</kbd></button>
            <button type="button" role="menuitem" @click="editCurrentField('copy')"><span>{{ t('app.copy') }}</span><kbd>{{ isMacOS ? '⌘' : 'Ctrl' }} C</kbd></button>
            <button type="button" role="menuitem" @click="editCurrentField('paste')"><span>{{ t('app.paste') }}</span><kbd>{{ isMacOS ? '⌘' : 'Ctrl' }} V</kbd></button>
            <div class="app-menu-separator" role="separator" />
            <button type="button" role="menuitem" @click="editCurrentField('selectAll')"><span>{{ t('app.selectAll') }}</span><kbd>{{ isMacOS ? '⌘' : 'Ctrl' }} A</kbd></button>
          </div>
        </div>
        <div class="app-menu-item">
          <button type="button" aria-haspopup="menu" :aria-expanded="activeAppMenu === 'view'" @click="toggleAppMenu('view')">{{ t('app.view') }}</button>
          <div v-if="activeAppMenu === 'view'" class="app-menu-popover" role="menu" :aria-label="t('app.viewMenuAria')">
            <button type="button" role="menuitem" @click="runAppMenuAction(() => openPage('source-control'))"><span>{{ t('app.changes') }}</span><kbd>{{ isMacOS ? '⌘' : 'Ctrl' }} E</kbd></button>
            <button type="button" role="menuitem" :disabled="!activeWorkspace" @click="runAppMenuAction(() => openInspectorTool('browser'))"><span>{{ t('app.browser') }}</span><kbd>{{ isMacOS ? '⌘' : 'Ctrl' }} ⇧ B</kbd></button>
            <button type="button" role="menuitem" :disabled="!activeWorkspace" @click="runAppMenuAction(() => openInspectorTool('files'))"><span>{{ t('app.file') }}</span><kbd>{{ isMacOS ? '⌘' : 'Ctrl' }} G</kbd></button>
            <button type="button" role="menuitem" :disabled="!activeWorkspace" @click="runAppMenuAction(() => openInspectorTool('terminal'))"><span>{{ t('app.terminal') }}</span><kbd>{{ isMacOS ? '⌘' : 'Ctrl' }} J</kbd></button>
            <div class="app-menu-separator" role="separator" />
            <button type="button" role="menuitemcheckbox" :aria-checked="statusBarVisible" @click="runAppMenuAction(toggleStatusBar)"><span><i class="app-menu-check">{{ statusBarVisible ? '✓' : '' }}</i>{{ t('app.statusBar') }}</span></button>
            <div class="app-menu-separator" role="separator" />
            <button type="button" role="menuitem" @click="runAppMenuAction(() => applyZoom(webviewZoom + .1))"><span>{{ t('app.zoomIn') }}</span><kbd>{{ isMacOS ? '⌘' : 'Ctrl' }} =</kbd></button>
            <button type="button" role="menuitem" @click="runAppMenuAction(() => applyZoom(webviewZoom - .1))"><span>{{ t('app.zoomOut') }}</span><kbd>{{ isMacOS ? '⌘' : 'Ctrl' }} -</kbd></button>
            <button type="button" role="menuitem" @click="runAppMenuAction(() => applyZoom(1))"><span>{{ t('app.resetZoom') }}</span><kbd>{{ isMacOS ? '⌘' : 'Ctrl' }} 0</kbd></button>
            <div class="app-menu-separator" role="separator" />
            <button type="button" role="menuitem" @click="runAppMenuAction(openSettings)"><span>{{ t('app.settings') }}</span></button>
          </div>
        </div>
        <div class="app-menu-item">
          <button type="button" aria-haspopup="menu" :aria-expanded="activeAppMenu === 'help'" @click="toggleAppMenu('help')">{{ t('app.help') }}</button>
          <div v-if="activeAppMenu === 'help'" class="app-menu-popover app-menu-popover--help" role="menu" :aria-label="t('app.helpMenuAria')">
            <button type="button" role="menuitem" @click="runAppMenuAction(openCommandPalette)"><span>{{ t('app.commandPalette') }}</span><kbd>{{ isMacOS ? '⌘' : 'Ctrl' }} K</kbd></button>
            <button type="button" role="menuitem" @click="runAppMenuAction(showKeyboardShortcuts)"><span>{{ t('app.keyboardShortcuts') }}</span><kbd>{{ isMacOS ? '⌘' : 'Ctrl' }} ⇧ /</kbd></button>
            <div class="app-menu-separator" role="separator" />
            <button type="button" role="menuitem" @click="runAppMenuAction(openLicense)"><span>{{ t('app.viewLicense') }}</span></button>
            <button type="button" role="menuitem" @click="runAppMenuAction(openProjectHomepage)"><span>{{ t('app.projectHomepage') }}</span></button>
            <button type="button" role="menuitem" @click="runAppMenuAction(showAbout)"><span>{{ t('app.about') }}</span></button>
          </div>
        </div>
      </nav>
      <div v-if="isMacOS" class="titlebar-drag-region" @pointerdown="onMacTitlebandPointerDown" @dblclick="onMacTitlebandDblClick" />
      <div v-else class="titlebar-drag-region" data-tauri-drag-region @dblclick="toggleMaximizeWindow" />
      <div v-if="!isMacOS" class="window-actions" aria-label="Window controls">
        <button class="window-action" type="button" title="Minimize" aria-label="Minimize window" @click="minimizeWindow"><AppIcon name="Minus" :size="15" /></button>
        <button class="window-action" type="button" title="Maximize or restore" aria-label="Maximize or restore window" @click="toggleMaximizeWindow"><AppIcon name="SquareShape" :size="13" /></button>
        <button class="window-action window-action--close" type="button" title="Close" aria-label="Close window" @click="closeWindow"><AppIcon name="X" :size="17" /></button>
      </div>
    </header>

    <div class="sidebar-viewport">
      <aside id="primary-navigation" class="kimi-sidebar agent-sidebar">
      <header class="sidebar-brand">
        <div class="mode-switch-wrap">
          <button class="brand-mode-trigger" :aria-expanded="modeMenuOpen" aria-haspopup="menu" :aria-label="t('app.switchWorkMode')" @click="modeMenuOpen = !modeMenuOpen">
            <h1>{{ workMode === 'code' ? 'SztuCode' : 'SztuChat' }}</h1>
            <AppIcon name="ChevronDown" :size="14" />
          </button>
          <div v-if="modeMenuOpen" class="brand-mode-popover" role="menu" :aria-label="t('app.workMode')">
            <button type="button" role="menuitemradio" :aria-checked="workMode === 'code'" @click="switchWorkMode('code')">
              <span><b>SztuCode</b><small>{{ t('app.codeMode') }}</small></span>
              <AppIcon v-if="workMode === 'code'" name="Check" :size="15" />
            </button>
            <button type="button" role="menuitemradio" :aria-checked="workMode === 'chat'" @click="switchWorkMode('chat')">
              <span><b>SztuChat</b><small>{{ t('app.chatMode') }}</small></span>
              <AppIcon v-if="workMode === 'chat'" name="Check" :size="15" />
            </button>
          </div>
        </div>
        <button class="task-search-toggle" type="button" :title="t('app.searchTasks')" :aria-label="t('app.searchTasks')" :aria-expanded="taskSearchOpen" aria-controls="task-search-popover" @click="toggleTaskSearch">
          <AppIcon name="Search" :size="16" aria-hidden="true" />
        </button>
      </header>

      <Teleport to="body">
        <div v-if="taskSearchOpen" id="task-search-popover" class="task-search-popover" role="dialog" :aria-label="t('app.searchTasks')" @pointerdown.stop>
          <div class="task-search-popover__input"><AppIcon name="Search" :size="17" aria-hidden="true" /><input ref="taskSearchInput" v-model="taskQuery" type="search" :placeholder="t('app.searchTasks')" :aria-label="t('app.searchTasks')" @keydown.esc="clearTaskSearch" /><button v-if="taskQuery" type="button" :title="t('app.clearSearch')" :aria-label="t('app.clearSearch')" @click="taskQuery = ''"><AppIcon name="X" :size="15" /></button><kbd>Esc</kbd></div>
          <p class="task-search-popover__hint">{{ taskQuery ? t('app.searchResultsCount', { n: visibleSessions.length }) : t('app.recentSessions') }}</p>
          <div class="task-search-popover__results">
            <button v-for="task in (taskQuery ? visibleSessions : liveSessions.slice(0, 8))" :key="`popup-${task.session_id}`" type="button" @click="chooseTask(task.session_id)"><AppIcon name="Search" :size="14" /><span>{{ task.title || t('app.unnamedTask') }}</span><small>{{ taskStatusLabel(task) }}</small></button>
            <p v-if="taskQuery && !visibleSessions.length">{{ t('app.noMatchingSessions') }}</p>
          </div>
        </div>
      </Teleport>

      <div class="sidebar-command">
        <button class="new-task-button" @click="beginTask()"><AppIcon name="Compose" :size="16" />{{ t('app.newTask') }}</button>
      </div>

      <nav class="sidebar-tools" :aria-label="t('app.workbenchTools')">
        <button :class="{ active: page === 'board' }" @click="openPage('board')"><AppIcon name="LayoutDashboard" :size="16" :filled="page === 'board'" /><span>{{ t('app.allTasks') }}</span></button>
        <button :class="{ active: page === 'automations' }" @click="openPage('automations')"><AppIcon name="CalendarClock" :size="16" :filled="page === 'automations'" /><span>{{ t('app.automations') }}</span></button>
        <button :class="{ active: page === 'skills' }" @click="openPage('skills')"><AppIcon name="Puzzle" :size="16" :filled="page === 'skills'" /><span>{{ t('app.skills') }}</span></button>
        <button :class="{ active: page === 'webbridge' }" @click="openPage('webbridge')"><AppIcon name="Globe2" :size="16" :filled="page === 'webbridge'" /><span>{{ t('app.webbridge') }}</span></button>
        <button v-if="chatEntryVisible" :class="{ active: page === 'chat' }" @click="openPage('chat')"><AppIcon name="MessageCircle" :size="16" :filled="page === 'chat'" /><span>{{ t('app.generalChat') }}</span></button>
      </nav>

      <div class="sidebar-workspace">
        <section v-if="normalizedTaskQuery && !taskSearchOpen" class="side-section search-results">
          <span class="side-label">{{ t('app.searchResults') }} <small>{{ visibleSessions.length }}</small></span>
          <div v-for="task in visibleSessions" :key="`search-${task.session_id}`" class="sidebar-session status-session" @mouseenter="showSessionPreview(task, $event)" @mouseleave="hideSessionPreview">
            <button class="status-task-row" :class="{ active: task.session_id === activeId }" @focus="startTaskTitleScroll" @blur="stopTaskTitleScroll" @click="chooseTask(task.session_id)">
              <i :class="task.status" /><span><b data-auto-scroll-title>{{ task.title || t('app.unnamedTask') }}</b><small>{{ taskStatusLabel(task) }} · {{ formatSessionUsage(task) }}</small></span>
            </button>
            <SessionActions :session="task" :active="task.session_id === activeId" @changed="refreshIndex(false)" @closed="handleSessionClosed(task.session_id)" />
          </div>
          <p v-if="!visibleSessions.length" class="side-empty">{{ t('app.noMatchingTasks') }}</p>
        </section>

        <section class="side-section project-tree" :class="{ 'has-pinned-section': !normalizedTaskQuery && (pinnedProjects.length || pinnedTemporaryTasks.length) }">
          <span v-if="!normalizedTaskQuery && (pinnedProjects.length || pinnedTemporaryTasks.length)" class="side-label pinned-tree-label">{{ t('app.pinned') }}</span>
          <div v-if="pinnedTemporaryTasks.length && !normalizedTaskQuery" class="pinned-temporary-list">
            <div v-for="task in pinnedTemporaryTasks" :key="`pinned-temporary-${task.session_id}`" class="sidebar-session conversation-session"><button class="conversation-row" :class="{ active: task.session_id === activeId }" @click="chooseTask(task.session_id)"><span>{{ task.title || t('app.unnamedTask') }}</span></button><SessionActions :session="task" :active="task.session_id === activeId" @changed="refreshIndex(false)" @closed="handleSessionClosed(task.session_id)" /></div>
          </div>
          <span class="side-label side-label--action project-tree-label"><span>{{ t('app.projects') }}</span><button :title="t('app.openLocalDir')" :aria-label="t('app.openLocalDir')" @click="openLocalProject"><AppIcon name="FolderOpen" :size="16" /></button></span>
          <div v-for="item in allProjects" :key="item.workspace_id" class="project-group" :class="{ 'project-group--pinned': item.pinned }">
            <div class="project-row-shell" @pointerdown="handleProjectRowPointerDown(item, $event)" @mouseenter="showProjectPreview(item, $event)" @mouseleave="scheduleProjectPreviewClose" @focusin="showProjectPreview(item, $event)" @focusout="handleProjectPreviewFocusOut" @contextmenu.prevent.stop="openProjectActions(item)">
              <button class="project-row-toggle" :title="t('app.newTempSessionInProject')" @click.stop.prevent>
                <AppIcon name="FolderOpen" :size="16" />
                <span>{{ item.name }}</span>
              </button>
              <div v-if="projectActionsOpen === item.workspace_id" class="project-action-menu" role="menu" :aria-label="t('app.projectActionsAria', { name: item.name })">
                <button role="menuitem" :disabled="projectActionBusy" @click="toggleProjectPinned(item)"><AppIcon v-if="item.pinned" name="PinOff" :size="16" /><AppIcon v-else name="Pin" :size="16" />{{ item.pinned ? t('app.unpin') : t('app.pin') }}</button>
                <button role="menuitem" @click="beginProjectEdit(item)"><AppIcon name="Pencil" :size="16" />{{ t('app.edit') }}</button>
                <div class="project-action-menu__separator" />
                <button role="menuitem" @click="openProjectExplorer(item)"><AppIcon name="FolderOpen" :size="16" />{{ t('app.openInExplorer') }}</button>
                <button role="menuitem" :disabled="projectActionBusy" @click="createProjectWorktree(item)"><AppIcon name="GitBranch" :size="16" />{{ t('app.createWorktree') }}</button>
                <div class="project-action-menu__separator" />
                <button role="menuitem" :disabled="projectActionBusy" @click="archiveProjectChats(item)"><AppIcon name="Archive" :size="16" />{{ t('app.archiveChats') }}</button>
                <button role="menuitem" :disabled="projectActionBusy" @click="removeProject(item)"><AppIcon name="Unlink" :size="16" />{{ t('app.removeProject') }}</button>
              </div>
            </div>
            <div class="project-task-list">
              <div class="project-task-list__inner">
                <div v-for="task in item.tasks" :key="task.session_id" class="sidebar-session project-session" @mouseenter="showSessionPreview(task, $event)" @mouseleave="hideSessionPreview">
                  <button class="project-task" :class="{ active: task.session_id === activeId }" @focus="startTaskTitleScroll" @blur="stopTaskTitleScroll" @click="chooseTask(task.session_id)">
                    <span data-auto-scroll-title>{{ task.title || t('app.unnamedTask') }}</span>
                  </button>
                  <SessionActions :session="task" :active="task.session_id === activeId" @changed="refreshIndex(false)" @closed="handleSessionClosed(task.session_id)" />
                </div>
                <p v-if="!item.tasks.length" class="project-empty">{{ t('app.noChats') }}</p>
              </div>
            </div>
          </div>
          <p v-if="!allProjects.length && !normalizedTaskQuery" class="side-empty">{{ t('app.openLocalDirHint') }}</p>
        </section>

        <section v-if="ordinaryTemporaryTasks.length && !normalizedTaskQuery" class="side-section temporary-tasks">
          <span class="side-label">{{ t('app.temporaryTasks') }}</span>
          <div v-for="task in ordinaryTemporaryTasks" :key="task.session_id" class="sidebar-session conversation-session" @mouseenter="showSessionPreview(task, $event)" @mouseleave="hideSessionPreview">
            <button class="conversation-row" :class="{ active: task.session_id === activeId }" @focus="startTaskTitleScroll" @blur="stopTaskTitleScroll" @click="chooseTask(task.session_id)"><span data-auto-scroll-title>{{ task.title || t('app.unnamedTask') }}</span></button>
            <SessionActions :session="task" :active="task.session_id === activeId" @changed="refreshIndex(false)" @closed="handleSessionClosed(task.session_id)" />
          </div>
        </section>

        <details v-if="archivedProjects.length && !normalizedTaskQuery" class="archived-projects">
          <summary><AppIcon name="Archive" :size="16" />{{ t('app.archivedProjects') }} <small>{{ archivedProjects.length }}</small></summary>
          <div v-for="item in archivedProjects" :key="item.workspace_id" class="project-row-shell">
            <button class="project-row archived-project-row" :title="t('app.restoreProject')" @click="resumeProject(item)"><AppIcon name="RotateCcw" :size="16" /><span>{{ item.name }}</span></button>
          </div>
        </details>
      </div>

      <footer v-if="statusBarVisible" class="sidebar-footer">
        <div class="service-status" :title="runtimeConnectionError"><i :class="{ online: connected }" /><span><b>{{ t('app.localService') }}</b><small>{{ connected ? t('app.connected') : runtimeConnectionError ? t('app.reconnecting') : t('app.disconnected') }}</small></span></div>
        <button ref="settingsButton" class="settings-link" :title="t('app.settings')" :aria-label="t('app.settings')" :aria-expanded="settingsOpen" @click="openSettings"><AppIcon name="Settings" :size="16" /></button>
      </footer>
      </aside>
      <Teleport to="body">
        <div v-if="previewProject" class="project-preview-card project-preview-card--floating" :style="projectPreviewStyle" role="tooltip" @pointerenter="keepProjectPreviewOpen" @pointerdown="keepProjectPreviewOpen" @focusin="keepProjectPreviewOpen" @focusout="handleProjectPreviewFocusOut" @mouseleave="scheduleProjectPreviewClose">
          <header><AppIcon name="FolderOpen" :size="20" /><b>{{ previewProject.name }}</b><button type="button" :title="previewProject.pinned ? t('app.unpin') : t('app.pinProject')" :aria-label="previewProject.pinned ? t('app.unpin') : t('app.pinProject')" :disabled="projectActionBusy" @pointerdown.stop @click.stop="toggleProjectPinned(previewProject)"><AppIcon v-if="previewProject.pinned" name="PinOff" :size="16" /><AppIcon v-else name="Pin" :size="16" /></button></header>
          <div class="project-preview-card__meta"><span><AppIcon name="MessageCircle" :size="16" />{{ t('app.tasksCount', { n: previewProject.tasks.length }) }}</span></div>
          <div class="project-preview-card__path"><AppIcon name="FolderOpen" :size="16" /><span>{{ previewProject.path }}</span></div>
          <button type="button" class="project-preview-card__edit" @click.stop="beginProjectEdit(previewProject)"><AppIcon name="Pencil" :size="16" />{{ t('app.editProject') }}</button>
        </div>
      </Teleport>
    </div>
    <div
      class="sidebar-resizer"
      role="separator"
      :aria-label="t('app.resizeNavWidth')"
      aria-controls="primary-navigation"
      aria-orientation="vertical"
      :aria-valuemin="SIDEBAR_MIN_WIDTH"
      :aria-valuemax="SIDEBAR_MAX_WIDTH"
      :aria-valuenow="Math.round(sidebarWidth)"
      tabindex="0"
      :title="t('app.dragResizeNavWidth')"
      @pointerdown="startSidebarDrag"
      @keydown="resizeSidebarWithKeyboard"
    ></div>

    <div v-if="sessionPreview" class="session-preview" :style="{ top: `${sessionPreview.top}px`, left: `${sessionPreview.left}px` }" role="tooltip">
      <b class="session-preview__title">{{ sessionPreview.task.title || t('app.unnamedTask') }}</b>
      <div class="session-preview__row"><AppIcon name="Clock" :size="16" /><span>{{ t('app.timingLabel') }}</span><em>{{ previewElapsed(sessionPreview.task) }}</em></div>
      <div class="session-preview__row"><AppIcon name="GitBranch" :size="16" /><span>{{ t('app.branch') }}</span><em>{{ previewBranch(sessionPreview.task) }}</em></div>
      <div class="session-preview__row"><AppIcon name="Folder" :size="16" /><span>{{ t('app.projectDirectory') }}</span><em>{{ previewDirectory(sessionPreview.task) }}</em></div>
      <div class="session-preview__row"><AppIcon name="Coins" :size="16" /><span>{{ t('app.totalTokens') }}</span><em>{{ previewTokens(sessionPreview.task) }}</em></div>
    </div>

    <main class="kimi-main" :class="{ 'chat-main': page === 'chat', 'work-active': page === 'work' }">
      <div v-show="page === 'work'" class="work-page-host">
        <section v-if="active" class="work-page">
          <div class="work-layout" :class="{ 'no-inspector': !inspectorOpen || !activeWorkspace, 'inspector-resizing': inspectorResizing }" :style="workLayoutStyle">
            <section class="task-canvas">
              <div v-if="sessionLoading" class="session-loading" role="status" :aria-label="t('app.loadingSession')">
                <AppIcon name="Terminal" :size="40" />
                <span>{{ t('app.loadingSessionDots') }}</span>
              </div>
              <header class="work-header">
                <button class="workspace-trigger" @click="projectMenuOpen = !projectMenuOpen"><span>{{ activeWorkspace?.name || t('app.noProjectSelected') }}</span><AppIcon name="ChevronDown" :size="14" /></button>
                <div v-if="projectMenuOpen" class="project-popover"><button v-for="item in activeWorkspaces" :key="item.workspace_id" @click="chooseWorkspace(item)">{{ item.name }}<small>{{ item.path }}</small></button></div>
                <div class="work-header__tools">
                  <SessionActions :session="active" :active="true" @changed="refreshIndex(false)" @closed="closeActiveSession" />
                  <button class="source-control-toggle" :title="t('app.sourceControl')" :aria-label="t('app.sourceControl')" :disabled="!activeWorkspace" @click="openPage('source-control')"><AppIcon name="GitBranch" :size="18" /></button>
                  <button class="workspace-panel-toggle" :title="t('app.workspace')" :aria-label="t('app.workspace')" :aria-expanded="inspectorOpen" :class="{ active: inspectorOpen }" @click="toggleInspector"><AppIcon name="Folder" :size="18" :filled="inspectorOpen" /></button>
                </div>
              </header>
              <div v-if="pendingPermissions.length" class="global-permission-banner" aria-live="polite">
                <div v-for="perm in pendingPermissions" :key="perm.toolUseId" class="global-permission-item">
                  <AppIcon name="ShieldCheck" :size="15" /><b>{{ t('app.bgTaskPermission') }}</b><span>{{ perm.toolName }} · {{ perm.preview }}</span>
                  <button type="button" @click="decidePermission(perm.toolUseId, 'deny_once')">{{ t('app.deny') }}</button>
                  <button type="button" class="allow" @click="decidePermission(perm.toolUseId, 'allow_once')">{{ t('app.allowOnce') }}</button>
                </div>
              </div>
              <div v-if="backgroundUserQuestions.length" class="global-permission-banner global-question-banner" aria-live="polite">
                <div v-for="pending in backgroundUserQuestions" :key="pending.rpc_id" class="global-permission-item global-question-item">
                  <AppIcon name="MessageCircle" :size="15" /><b>{{ t('app.bgTaskQuestion') }}</b><span>{{ pending.questions[0]?.question || t('app.agentNeedsChoice') }}</span>
                  <button type="button" class="open" @click="chooseTask(pending.session_id)">{{ t('app.openTask') }}</button>
                </div>
              </div>
              <div class="task-conversation" :class="{ 'task-conversation--empty': !orderedTimeline.length, 'task-conversation--running': runActive || sending }">
                <div class="task-stream" ref="taskStreamEl" @scroll="handleTaskStreamScroll" @wheel.passive="markUserScrolling" @touchstart.passive="markUserScrolling">
                  <div v-if="!orderedTimeline.length" class="task-intro"><span class="task-intro-icon"><AppIcon name="Terminal" :size="36" /></span><b>{{ t('app.taskIntro', { name: activeWorkspace?.name || t('app.currentProject') }) }}</b></div>
                  <KeepAlive>
                    <ExecutionTimeline :key="active.session_id" :steps="orderedTimeline" :workspace-id="activeWorkspace?.workspace_id ?? undefined" :workspace-path="activeWorkspace?.path" @decide="decidePermission" @reverted="handleReverted" @retry="handleRetry" @review="handleReview" @continue="handleContinue" @open-file="onOpenFileFromTimeline" @open-changes="onOpenChangesFromTimeline" />
                  </KeepAlive>
                </div>
                <!-- Trae Work 风格：会话轮次圆点导航（固定可视数量，居中active，hover气泡） -->
                <div v-if="turnDotCount > 1" ref="turnDotWrapEl" class="turn-dot-wrap" :aria-label="t('app.turnNavAria')">
                  <nav class="turn-dot-rail" role="tablist" @mouseleave="turnDotHoverIdx = -1">
                    <div ref="turnDotRailEl" class="turn-dot-scroll">
                      <button
                        v-for="(label, idx) in turnLabels"
                        :key="idx"
                        :data-idx="idx"
                        type="button"
                        role="tab"
                        class="turn-dot"
                        :class="{ active: turnDotActive === idx }"
                        :aria-selected="turnDotActive === idx"
                        :aria-label="t('app.turnAria', { n: idx + 1, label })"
                        @click="scrollToTurn(idx)"
                        @mouseenter="handleDotHover(idx, $event)"
                        @focus="handleDotHover(idx, $event)"
                        @blur="turnDotHoverIdx = -1"
                      />
                    </div>
                  </nav>
                  <!-- 上下渐变遮罩 -->
                  <div class="turn-dot-fade turn-dot-fade--top" />
                  <div class="turn-dot-fade turn-dot-fade--bottom" />
                  <!-- 悬浮气泡（rail兄弟节点，不受任何overflow裁剪） -->
                  <span
                    v-if="turnDotHoverIdx >= 0 && turnLabels[turnDotHoverIdx]"
                    class="turn-dot-bubble"
                    :style="{ top: turnDotBubbleTop + 'px' }"
                  >
                    <span class="turn-dot-bubble-inner">{{ turnLabels[turnDotHoverIdx] }}</span>
                  </span>
                </div>
                <button v-if="streamScrolledUp" type="button" class="task-stream-to-bottom" :title="t('app.backToBottom')" :aria-label="t('app.backToBottom')" @click="scrollTaskStreamToBottom"><AppIcon name="ChevronDown" :size="16" /></button>
                <!-- 底部统计栏（借鉴 dsh StatsLine）：composer 上方一行全局会话统计 -->
                <SessionStatsLine v-if="sessionStats.steps" :stats="sessionStats" />
                <!-- 暂时隐藏“修改了 N 个文件”提示。
                <ChangeSummaryRail
                  v-if="active"
                  :paths="changeSummaryPaths"
                /> -->
                <QueueDock
                  :items="activeQueueItems"
                  :running="isRunActive"
                  :busy-id="activeView?.queueBusyId"
                  @edit="editQueuedSubmission"
                  @remove="removeQueuedSubmission"
                  @steer="steerQueuedSubmission"
                >
                  <UserQuestionComposer
                    v-if="activeUserQuestion"
                    :pending="activeUserQuestion"
                    :busy="questionSubmittingId === activeUserQuestion.rpc_id"
                    :error="questionErrors.get(activeUserQuestion.rpc_id)"
                    @submit="submitUserQuestion(activeUserQuestion, $event)"
                    @stop="stopActiveRun"
                  />
                    <form v-else class="kimi-composer active-composer" :class="{ 'append-mode': isAppending }" @submit.prevent="submit">
                      <SlashCommandMenu v-if="slashMenuOpen" :query="slashQuery ?? ''" :skills="providerStatus?.skills ?? []" :connected="connected" :active-index="slashMenuActiveIndex" @activate="slashMenuActiveIndex = $event" @select="chooseSkill" />
                      <div v-if="attachedFiles.length" class="attachment-strip"><span v-for="(file, index) in attachedFiles" :key="file.path" class="attachment-chip" :class="'attachment-chip--' + file.kind"><img v-if="file.kind === 'image' && file.dataBase64" :src="'data:' + (file.mime || 'image/png') + ';base64,' + file.dataBase64" :alt="file.name" /><template v-else><b>{{ file.name }}</b><small>{{ formatSize(file.size) }}</small></template><button type="button" :aria-label="t('app.removeAttachment')" @click="removeAttachment(index)"><AppIcon name="X" :size="12" /></button></span></div>
                      <textarea ref="activePrompt" v-model="prompt" :aria-label="t('app.taskInput')" :disabled="active.archived || active.status === 'closed'" :placeholder="active.archived || active.status === 'closed' ? t('app.resumeTaskHint') : (isAppending ? t('app.composerPlaceholder') : (sending ? t('app.sending') : t('app.composerPlaceholder')))" rows="3" @input="handlePromptInput" @keydown="onComposerKeydown" @paste="onPasteImage" />
                      <div class="composer-toolbar"><button type="button" class="round" :title="t('app.addContext')" :aria-label="t('app.addContext')" @click="selectAttachments"><AppIcon name="Plus" :size="18" /></button><button type="button" class="permission" :class="runtimeSettings?.permission_mode === 'auto' ? 'permission--full-access' : 'permission--per-item'" @click="choosePermissionMode(runtimeSettings?.permission_mode === 'auto' ? 'normal' : 'auto')"><AppIcon name="ShieldCheck" :size="15" />{{ runtimeSettings?.permission_mode === 'auto' ? t('app.allowAll') : t('app.perItemApproval') }}<AppIcon name="ChevronDown" :size="13" /></button><span /><ModelConfigMenu :settings="runtimeSettings" :status="providerStatus" @updated="handleModelConfigUpdated" @manage="openModelManager" /><button v-if="isRunActive" class="send stop" type="button" :title="t('app.stopTaskNow')" :aria-label="t('app.stopTask')" @click="stopActiveRun"><AppIcon name="Square" :size="14" /></button><button v-if="!isRunActive || prompt.trim()" class="send" type="submit" :title="isRunActive ? t('app.sendAppend') : t('app.sendTask')" :aria-label="isRunActive ? t('app.sendAppend') : t('app.sendTask')" :disabled="!prompt.trim() || active.archived || active.status === 'closed' || (sending && !isAppending) || steering"><AppIcon name="ArrowUp" :size="15" /></button></div>
                    </form>
                </QueueDock>
              </div>
            </section>
            <template v-if="inspectorRendered && activeWorkspace">
              <div class="layout-divider" role="separator" aria-orientation="vertical" :title="t('app.dragResizePanel')" style="touch-action: none;" @pointerdown="startDividerDrag" />
              <ProjectInspector
                ref="inspectorRef"
                :workspace-id="activeWorkspace.workspace_id"
                :run-id="active?.latest_run_id"
                :steps="orderedTimeline"
                :attachments="attachedFiles.map((item) => item.path)"
                :workspace-name="activeWorkspace.name"
                :workspace-path="activeWorkspace.path"
                :obscured="permissionConfirmOpen"
                :files-request="filesRequest"
                @close="setInspectorOpen(false)"
              />
            </template>
          </div>
        </section>
        <section v-else class="landing-page task-launcher" :class="{ 'slash-open': slashMenuOpen }">
          <div class="launcher-content">
            <header class="launcher-heading">
              <AgentLogo class="launcher-mark" size="large" />
              <div class="launcher-heading__copy">
                <h1 aria-label="Think it. Build it."><span aria-hidden="true">Think it. Build it.</span></h1>
              </div>
            </header>

            <form class="kimi-composer landing-composer" @submit.prevent="submit()">
              <SlashCommandMenu v-if="slashMenuOpen" :query="slashQuery ?? ''" :skills="providerStatus?.skills ?? []" :connected="connected" :active-index="slashMenuActiveIndex" @activate="slashMenuActiveIndex = $event" @select="chooseSkill" />
              <div class="composer-input-shell">
                <div v-if="attachedFiles.length" class="attachment-strip"><span v-for="(file, index) in attachedFiles" :key="file.path" class="attachment-chip" :class="'attachment-chip--' + file.kind"><img v-if="file.kind === 'image' && file.dataBase64" :src="'data:' + (file.mime || 'image/png') + ';base64,' + file.dataBase64" :alt="file.name" /><template v-else><b>{{ file.name }}</b><small>{{ formatSize(file.size) }}</small></template><button type="button" :aria-label="t('app.removeAttachment')" @click="removeAttachment(index)"><AppIcon name="X" :size="12" /></button></span></div>
                <textarea ref="launcherPrompt" v-model="prompt" :aria-label="t('app.taskInput')" :placeholder="t('app.composerPlaceholder')" rows="4" @input="handlePromptInput" @keydown="onComposerKeydown" @paste="onPasteImage" />
                <div class="composer-toolbar launcher-toolbar">
                  <button type="button" class="round launcher-attachment-trigger" :title="t('app.addAttachment')" :aria-label="t('app.addAttachment')" @click="selectAttachments"><AppIcon name="Plus" :size="18" /></button>
                  <div class="launcher-permission-control">
                    <button type="button" class="permission" :class="runtimeSettings?.permission_mode === 'auto' ? 'permission--full-access' : 'permission--per-item'" aria-haspopup="menu" :aria-expanded="launcherPermissionMenuOpen" @click.stop="toggleLauncherPermissionMenu"><AppIcon name="ShieldCheck" :size="15" />{{ permissionModeLabel }}<AppIcon name="ChevronDown" :size="13" /></button>
                    <div v-if="launcherPermissionMenuOpen" class="launcher-popover permission-popover" role="menu" :aria-label="t('app.permissionModeAria')">
                      <button type="button" class="full-access-row" role="menuitemcheckbox" :aria-checked="runtimeSettings?.permission_mode === 'auto'" @click="choosePermissionMode(runtimeSettings?.permission_mode === 'auto' ? 'normal' : 'auto')"><span><b>{{ t('app.allowAllPermissions') }}</b><small>{{ t('app.skipConfirmations') }}</small></span><i :class="{ active: runtimeSettings?.permission_mode === 'auto' }"><em /></i></button>
                      <p v-if="permissionSettingsError" class="launcher-menu-error">{{ permissionSettingsError }}</p>
                    </div>
                  </div>
                  <span />
                  <ModelConfigMenu :settings="runtimeSettings" :status="providerStatus" @updated="handleModelConfigUpdated" @manage="openModelManager" />
                  <button v-if="isRunActive" class="send stop" type="button" :title="t('app.stopTask')" :aria-label="t('app.stopTask')" @click="stopActiveRun"><AppIcon name="Square" :size="14" /></button><button v-else class="send" type="submit" :aria-label="t('app.sendTask')" :disabled="!connected || !prompt.trim()"><AppIcon name="ArrowUp" :size="15" /></button>
                </div>
              </div>
              <div class="launcher-project-control">
                <button type="button" class="composer-project" aria-haspopup="menu" :aria-expanded="launcherProjectMenuOpen" @click.stop="toggleLauncherProjectMenu"><AppIcon name="FolderOpen" :size="15" /><span>{{ workspace?.name || t('app.selectLocalProject') }}</span><AppIcon name="ChevronDown" :size="13" /></button>
                <div v-if="launcherProjectMenuOpen" class="launcher-popover project-picker-popover" role="menu" :aria-label="t('app.selectProject')">
                  <label class="project-picker-search"><AppIcon name="Search" :size="15" /><input v-model="launcherProjectQuery" type="search" :placeholder="t('app.searchWorkspace')" :aria-label="t('app.searchWorkspace')" /></label>
                  <div v-if="filteredLauncherWorkspaces.length" class="project-picker-list">
                    <button v-for="item in filteredLauncherWorkspaces" :key="item.workspace_id" type="button" role="menuitemradio" :aria-checked="workspace?.workspace_id === item.workspace_id" @click="chooseLauncherWorkspace(item)"><AppIcon name="Folder" :size="16" /><span><b>{{ item.name }}</b><small>{{ item.path }}</small></span><AppIcon v-if="workspace?.workspace_id === item.workspace_id" name="Check" :size="15" /></button>
                  </div>
                  <p v-else class="project-picker-empty">{{ t('app.noMatchingWorkspaces') }}</p>
                  <div class="project-picker-actions">
                    <button v-if="workspace" type="button" role="menuitem" @click="clearLauncherWorkspace"><AppIcon name="CirclePlus" :size="16" /><span>{{ t('app.temporaryTasks') }}</span></button>
                    <button type="button" role="menuitem" @click="createLocalWorkspace"><AppIcon name="FolderPlus" :size="16" /><span>{{ t('app.newWorkspace') }}</span></button>
                    <button type="button" role="menuitem" @click="openLocalProject"><AppIcon name="FolderOpen" :size="16" /><span>{{ t('app.openLocalFolder') }}</span></button>
                  </div>
                </div>
              </div>
            </form>

          </div>
        </section>
      </div>

      <section v-if="page === 'chat'"><ChatPortal :view="chatView" :connected="connected" @submit="submitChat" @navigate="chatView = $event" @open-project="openLocalProject" /></section>

      <section v-else-if="page === 'source-control'" class="source-control-host"><SourceControlPanel v-if="activeWorkspace" :workspace-id="activeWorkspace.workspace_id" :workspace-name="activeWorkspace.name" :workspace-path="activeWorkspace.path" @close="openPage('work')" @changed="refreshIndex(false)" /><div v-else class="source-control-no-workspace"><AppIcon name="GitBranch" :size="30" /><h1>{{ t('app.noWorkspaceAvailable') }}</h1><p>{{ t('app.openProjectForScm') }}</p><button type="button" @click="openPage('work')">{{ t('app.backToWorkspace') }}</button></div></section>

      <section v-else-if="page === 'board'" class="simple-page board-page">
        <header><div><h1>{{ t('app.allTasks') }}</h1><p>{{ t('app.boardSubtitle') }}</p></div><button class="outline-button" @click="refreshIndex(false)">{{ t('app.refresh') }}</button></header>
        <div class="session-board">
          <article v-for="task in liveSessions" :key="task.session_id" :class="{ pinned: task.pinned }"><button @click="chooseTask(task.session_id)"><b>{{ task.title || 'Untitled task' }}</b><span>{{ task.status }} · {{ task.updated_at }}</span></button><SessionActions :session="task" @changed="refreshIndex(false)" @closed="refreshIndex(false)" /></article>
          <h2 v-if="archivedSessions.length">{{ t('app.archived') }}</h2>
          <article v-for="task in archivedSessions" :key="task.session_id" class="archived"><button @click="chooseTask(task.session_id)"><b>{{ task.title || 'Untitled task' }}</b><span>{{ task.updated_at }}</span></button><SessionActions :session="task" @changed="refreshIndex(false)" @closed="refreshIndex(false)" /></article>
          <div v-if="!sessions.length" class="empty-state"><AppIcon name="LayoutDashboard" :size="58" /><h2>{{ t('app.noSessions') }}</h2></div>
        </div>
      </section>
      <section v-else-if="page === 'automations'" class="chat-main"><ChatPortal view="automations" :connected="connected" @submit="submitChat" @navigate="(view) => { page = 'chat'; chatView = view }" @open-project="openLocalProject" /></section>

      <section v-else-if="page === 'skills'" class="chat-main"><SkillCenter :connected="connected" :workspace-id="activeWorkspace?.workspace_id ?? null" :workspace-name="activeWorkspace?.name ?? null" /></section>

      <section v-else-if="page === 'webbridge'" class="simple-page"><header><div><h1>{{ t('app.webbridge') }}</h1><p>{{ t('app.webbridgeSubtitle') }}</p></div></header><div class="bridge-card"><AppIcon name="Globe2" :size="24" /><div><h2>{{ t('app.connectionStatus') }}</h2><p>{{ t('app.webbridgeHint') }}</p></div><span class="status-pill">{{ t('app.disconnected') }}</span></div></section>
    </main>

    <Teleport to="body">
      <SettingsDialog
        v-if="settingsOpen"
        :appearance="appearanceSettings"
        :runtime-settings="runtimeSettings"
        :permission-error="permissionSettingsError"
        :initial-section="settingsInitialSection"
        @close="closeSettings"
        @appearance-change="handleAppearanceChange"
        @permission-change="choosePermissionMode"
        @manage-model="openModelManager"
        @runtime-updated="runtimeSettings = $event"
      />

      <div v-if="projectBeingEdited" class="project-edit-backdrop" role="presentation" @mousedown.self="closeProjectEdit">
        <form class="project-edit-dialog" role="dialog" aria-modal="true" aria-labelledby="project-edit-title" @submit.prevent="saveProjectEdit" @keydown.esc.prevent="closeProjectEdit">
          <header>
            <div><h2 id="project-edit-title">{{ t('app.editProject') }}</h2><p>{{ t('app.editProjectDesc') }}</p></div>
            <button type="button" :aria-label="t('app.closeEditWindow')" :disabled="projectActionBusy" @click="closeProjectEdit"><AppIcon name="X" :size="18" /></button>
          </header>
          <div class="project-edit-dialog__body">
            <label><span>{{ t('app.projectName') }}</span><input v-model="projectEditName" maxlength="120" autocomplete="off" autofocus :placeholder="t('app.projectNamePlaceholder')" /></label>
            <label><span>{{ t('app.projectLocation') }}</span><input :value="projectBeingEdited.path" readonly tabindex="-1" /></label>
            <p v-if="projectEditError" class="project-edit-dialog__error" role="alert">{{ projectEditError }}</p>
          </div>
          <footer><button type="button" :disabled="projectActionBusy" @click="closeProjectEdit">{{ t('app.cancel') }}</button><button type="submit" class="primary" :disabled="projectActionBusy || !projectEditName.trim()">{{ projectActionBusy ? t('app.saving') : t('app.save') }}</button></footer>
        </form>
      </div>

      <div v-if="projectDialog" class="project-dialog-backdrop" role="presentation" @mousedown.self="settleProjectDialog(false)">
        <section class="project-dialog" :class="`project-dialog--${projectDialog.tone}`" :role="projectDialog.cancelLabel ? 'alertdialog' : 'dialog'" aria-modal="true" aria-labelledby="project-dialog-title" aria-describedby="project-dialog-message" @keydown.esc.stop.prevent="settleProjectDialog(false)">
          <div class="project-dialog__icon" aria-hidden="true">
            <AppIcon v-if="projectDialog.tone === 'success'" name="Check" :size="18" />
            <AppIcon v-else-if="projectDialog.tone === 'danger'" name="AlertTriangle" :size="18" />
            <AppIcon v-else name="Info" :size="18" />
          </div>
          <div class="project-dialog__content">
            <h2 id="project-dialog-title">{{ projectDialog.title }}</h2>
            <p id="project-dialog-message">{{ projectDialog.message }}</p>
          </div>
          <footer>
            <button v-if="projectDialog.cancelLabel" type="button" autofocus @click="settleProjectDialog(false)">{{ projectDialog.cancelLabel }}</button>
            <button type="button" class="primary" :class="{ danger: projectDialog.tone === 'danger' }" :autofocus="!projectDialog.cancelLabel" @click="settleProjectDialog(true)">{{ projectDialog.confirmLabel }}</button>
          </footer>
        </section>
      </div>

      <div v-if="permissionConfirmOpen" class="permission-confirm-backdrop" role="presentation" @mousedown.self="permissionConfirmOpen = false">
        <section class="permission-confirm" role="alertdialog" aria-modal="true" aria-labelledby="permission-confirm-title" aria-describedby="permission-confirm-description">
          <header><span><AppIcon name="AlertTriangle" :size="19" /></span><div><h2 id="permission-confirm-title">{{ t('app.highRiskPermission') }}</h2><p id="permission-confirm-description">{{ t('app.fullAccessWarning') }}</p></div></header>
          <div class="permission-confirm__body">
            <b>{{ t('app.possibleConsequences') }}</b>
            <ul><li>{{ t('app.consequenceFiles') }}</li><li>{{ t('app.consequenceConfig') }}</li><li>{{ t('app.consequenceIrreversible') }}</li></ul>
            <p><AppIcon name="AlertTriangle" :size="16" />{{ t('app.fullAccessCaution') }}</p>
          </div>
          <footer><button type="button" @click="permissionConfirmOpen = false">{{ t('app.cancel') }}</button><button type="button" class="danger" :disabled="permissionSaving" @click="confirmFullAccess">{{ permissionSaving ? t('app.enabling') : t('app.allowAllPermissions') }}</button></footer>
        </section>
      </div>
    </Teleport>
  </div>
</template>
