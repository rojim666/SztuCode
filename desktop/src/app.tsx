import { open } from "@tauri-apps/plugin-dialog";
import { invoke } from "@tauri-apps/api/core";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  Activity, ArrowUp, ChevronRight, CircleStop, FileCode2, FolderOpen,
  GitBranch, ListChecks, PanelRightClose, Plus, Search, Settings2, ShieldCheck,
  Command, Menu, Pin, TerminalSquare, WandSparkles, X,
} from "lucide-react";
import { FormEvent, Fragment, useEffect, useMemo, useRef, useState } from "react";
import { IpcClient, type IpcEvent } from "./lib/ipc";

type Session = { session_id: string; title: string; status: string; updated_at: string; archived: boolean; pinned?: boolean; workspace_id?: string | null; latest_run_id?: string | null };
type Workspace = { workspace_id: string; path: string; name: string };
type Change = { path: string; index_status: string; worktree_status: string; run_id?: string | null; agent_owned?: boolean; revertible?: boolean };
type TimelineItem = { id: string; kind: "user" | "agent" | "tool" | "system"; title?: string; body: string; state?: string };
type Permission = { tool_use_id: string; tool_name: string; params: unknown; run_id?: string };
type DiffView = "unified" | "split";
type DiffRow = { old: string; next: string; kind: "context" | "added" | "removed" | "meta" };
type PlanItem = { id: number; subject: string; status: "pending" | "in_progress" | "completed"; blocked_by: number[] };
type TestResult = { tool_use_id: string; status: "passed" | "failed"; summary: string };
type PaletteCommand = { id: string; title: string; detail: string; key: string; disabled?: boolean; action: () => void };
type Diagnostics = { version: string; uptime: string; branch: string; changes: number; repository: boolean };
type FileNode = { path: string; name: string; kind: "file" | "directory"; children?: FileNode[] };
type RuntimeSettings = { provider: "anthropic" | "openai"; model: string; router: string; permission_mode: string; applies_at: "next_run"; persistent: boolean };
type ProviderStatus = { provider: "anthropic" | "openai"; model: string; api_key_configured: boolean; custom_endpoint_configured: boolean; ready_for_next_run: boolean; mcp_servers: { name: string; transport: string; status: "connected" | "unavailable"; tool_count: number }[]; skills: { name: string; description: string }[] };
type DaemonStartResult = { status: "started" | "starting" | "already_running"; detail: string };

const client = new IpcClient();
const topics = ["session.*", "run.*", "step.*", "tool.*", "llm.*", "permission.*", "context.*", "subagent.*", "change.*", "log.*"];

function short(value: string, length = 44) { return value.length > length ? `${value.slice(0, length - 1)}…` : value; }
function sessionState(session: Session) { return session.status === "active" ? "运行中" : "就绪"; }
function errorText(error: unknown) { return error instanceof Error ? error.message : String(error); }
function modeLabel(mode: string) { return ({ normal: "标准审批", plan: "计划模式", accept_edits: "允许编辑", auto: "自动执行" } as Record<string, string>)[mode] ?? mode; }
function modeDescription(mode: string) { return ({ normal: "每项有影响的操作都由你确认。", plan: "默认只允许只读分析与计划拆分。", accept_edits: "允许工作区文件编辑，其余操作仍审批。", auto: "低风险步骤自动执行，高风险动作仍可见。" } as Record<string, string>)[mode] ?? "使用本地安全策略执行。"; }

function messageText(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content.map((block) => {
    if (!block || typeof block !== "object") return "";
    const value = block as Record<string, unknown>;
    if (value.type === "text") return String(value.text ?? "");
    if (value.type === "tool_use") return `调用工具：${String(value.name ?? "unknown")}`;
    if (value.type === "tool_result") return String(value.content ?? "工具已完成");
    return "";
  }).filter(Boolean).join("\n\n");
}

function historyToTimeline(messages: unknown[]): TimelineItem[] {
  return messages.flatMap((message, index) => {
    if (!message || typeof message !== "object") return [];
    const value = message as Record<string, unknown>;
    const body = messageText(value.content);
    if (!body) return [];
    return [{ id: `history-${index}`, kind: value.role === "user" ? "user" : "agent", body }];
  });
}

function splitDiff(diff: string): DiffRow[] {
  const rows: DiffRow[] = [];
  for (const line of diff.split("\n")) {
    if (line.startsWith("+++ ") || line.startsWith("--- ") || line.startsWith("@@") || line.startsWith("diff --git") || line.startsWith("index ")) {
      rows.push({ old: line, next: line, kind: "meta" });
    } else if (line.startsWith("-")) {
      rows.push({ old: line.slice(1), next: "", kind: "removed" });
    } else if (line.startsWith("+")) {
      rows.push({ old: "", next: line.slice(1), kind: "added" });
    } else {
      const value = line.startsWith(" ") ? line.slice(1) : line;
      rows.push({ old: value, next: value, kind: "context" });
    }
  }
  return rows;
}

export function App() {
  const [connection, setConnection] = useState<"connecting" | "ready" | "offline">("connecting");
  const [daemonStarting, setDaemonStarting] = useState(false);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [changes, setChanges] = useState<Change[]>([]);
  const [treeNodes, setTreeNodes] = useState<FileNode[]>([]);
  const [selectedFile, setSelectedFile] = useState<FileNode | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [fileLoading, setFileLoading] = useState(false);
  const [planItems, setPlanItems] = useState<PlanItem[]>([]);
  const [testResults, setTestResults] = useState<TestResult[]>([]);
  const [permission, setPermission] = useState<Permission | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState("normal");
  const [rightOpen, setRightOpen] = useState(true);
  const [notice, setNotice] = useState("选择一个本地仓库，开始可审阅的编码任务。");
  const [selectedChange, setSelectedChange] = useState<Change | null>(null);
  const [diff, setDiff] = useState("");
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffView, setDiffView] = useState<DiffView>("split");
  const [revertConfirming, setRevertConfirming] = useState(false);
  const [reverting, setReverting] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteQuery, setPaletteQuery] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [taskManagerOpen, setTaskManagerOpen] = useState(false);
  const [taskTitleDraft, setTaskTitleDraft] = useState("");
  const [taskManaging, setTaskManaging] = useState(false);
  const [runtimeSettings, setRuntimeSettings] = useState<RuntimeSettings | null>(null);
  const [providerStatus, setProviderStatus] = useState<ProviderStatus | null>(null);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [modelDraft, setModelDraft] = useState("");
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [diagnostics, setDiagnostics] = useState<Diagnostics | null>(null);
  const [diagnosticsLoading, setDiagnosticsLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [mobileInspectorOpen, setMobileInspectorOpen] = useState(false);
  const streamId = useRef<string | null>(null);
  const sessionRef = useRef<string | null>(null);
  const workspaceRef = useRef<Workspace | null>(null);
  const workspacesRef = useRef<Workspace[]>([]);
  const activeRunRef = useRef<string | null>(null);
  const selectedRunRef = useRef<string | null>(null);
  const selectionRef = useRef(0);
  const paletteInputRef = useRef<HTMLInputElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const timelineParentRef = useRef<HTMLDivElement | null>(null);

  sessionRef.current = sessionId;
  workspaceRef.current = workspace;
  workspacesRef.current = workspaces;
  activeRunRef.current = activeRunId;
  const activeSession = useMemo(() => sessions.find((item) => item.session_id === sessionId), [sessions, sessionId]);
  const visibleSessions = useMemo(() => sessions.filter((item) => !item.archived), [sessions]);
  const pinnedSessions = useMemo(() => visibleSessions.filter((item) => item.pinned), [visibleSessions]);
  const recentSessions = useMemo(() => visibleSessions.filter((item) => !item.pinned), [visibleSessions]);
  const timelineVirtualizer = useVirtualizer({
    count: timeline.length,
    getScrollElement: () => timelineParentRef.current,
    estimateSize: () => 108,
    overscan: 10,
  });

  async function refreshSessions() {
    const result = await client.request("session.list", { limit: 50 });
    setSessions((result.sessions as Session[]) ?? []);
  }

  async function startLocalService() {
    setDaemonStarting(true);
    setNotice("正在启动本地 Agent 服务…");
    try {
      const result = await invoke<DaemonStartResult>("daemon_start");
      setNotice(`${result.detail}，工作台将在连接就绪后自动恢复。`);
    } catch (error) { setNotice(`启动失败：${errorText(error)}`); }
    finally { setDaemonStarting(false); }
  }

  async function refreshChanges(selected = workspaceRef.current, runId = selectedRunRef.current) {
    if (!selected) return;
    const result = await client.request("change.list", { workspace_id: selected.workspace_id, ...(runId ? { run_id: runId } : {}) });
    setChanges((result.changes as Change[]) ?? []);
  }

  async function refreshTree(selected = workspaceRef.current) {
    if (!selected) return;
    const result = await client.request("workspace.tree", { workspace_id: selected.workspace_id, max_depth: 2, max_entries: 180 });
    setTreeNodes((result.nodes as FileNode[]) ?? []);
  }

  async function selectSession(id: string, { announce = true } = {}) {
    const selection = ++selectionRef.current;
    setSessionId(id);
    sessionRef.current = id;
    setPermission(null);
    setActiveRunId(null);
    activeRunRef.current = null;
    setTimeline([]);
    setPlanItems([]);
    setTestResults([]);
    selectedRunRef.current = null;
    try {
      const [resumed, history] = await Promise.all([
        client.request("session.resume", { session_id: id }),
        client.request("session.get_history", { session_id: id }),
      ]);
      if (selection !== selectionRef.current) return;
      setTimeline(historyToTimeline((history.messages as unknown[]) ?? []));
      const session = resumed.session as Session | undefined;
      if (session?.latest_run_id) {
        selectedRunRef.current = session.latest_run_id;
        const replay = await client.request("run.replay", { run_id: session.latest_run_id });
        for (const event of (replay.events as IpcEvent[]) ?? []) {
          if (event.type !== "llm.token") handleEvent(event);
        }
      }
      const linkedWorkspace = workspacesRef.current.find(
        (item) => item.workspace_id === session?.workspace_id,
      );
      if (linkedWorkspace) {
        setWorkspace(linkedWorkspace);
        await refreshChanges(linkedWorkspace, session?.latest_run_id);
        await refreshTree(linkedWorkspace);
      }
      if (announce) setNotice(`已恢复“${session?.title || "未命名任务"}”的上下文与消息记录。`);
      await refreshSessions();
    } catch (error) {
      if (selection === selectionRef.current) setNotice(`恢复任务失败：${errorText(error)}`);
    }
  }

  function handleEvent(event: IpcEvent) {
    const type = String(event.type ?? "");
    if (event.session_id && event.session_id !== sessionRef.current) return;
    const expectedRun = activeRunRef.current ?? selectedRunRef.current;
    if (event.run_id && expectedRun && event.run_id !== expectedRun) return;
    if (type === "llm.token") {
      const token = String(event.token ?? "");
      if (!token) return;
      const id = streamId.current ?? crypto.randomUUID();
      streamId.current = id;
      setTimeline((items) => {
        const last = items.at(-1);
        if (last?.id === id) return [...items.slice(0, -1), { ...last, body: last.body + token }];
        return [...items, { id, kind: "agent", body: token }];
      });
      return;
    }
    streamId.current = null;
    if (type === "run.started") setNotice("Agent 正在分析任务并准备执行。");
    if (type === "run.finished") {
      setActiveRunId(null);
      setNotice(event.status === "success" ? "本轮任务已完成，可查看变更与验证结果。" : `任务结束：${String(event.reason ?? "未成功完成")}`);
      void refreshChanges(undefined, String(event.run_id ?? selectedRunRef.current ?? ""));
      void refreshSessions();
    }
    if (type === "tool.call_started") {
      setTimeline((items) => [...items, { id: String(event.tool_use_id), kind: "tool", title: String(event.tool_name), body: JSON.stringify(event.params ?? {}, null, 2), state: "运行中" }]);
    }
    if (type === "tool.call_finished" || type === "tool.call_failed") {
      const id = String(event.tool_use_id);
      setTimeline((items) => items.map((item) => item.id === id ? { ...item, body: String(event.output ?? event.error_message ?? item.body), state: type.endsWith("failed") ? "失败" : "完成" } : item));
    }
    if (type === "permission.requested") setPermission({ tool_use_id: String(event.tool_use_id), tool_name: String(event.tool_name), params: event.params, run_id: String(event.run_id ?? "") });
    if (type === "plan.updated") setPlanItems((event.items as PlanItem[]) ?? []);
    if (type === "test.result") {
      const result = event as unknown as TestResult;
      setTestResults((items) => [...items.filter((item) => item.tool_use_id !== result.tool_use_id), result]);
    }
    if (type === "permission.mode_changed") setMode(String(event.new_mode ?? "normal"));
    if (type === "change.applied") {
      const runId = String(event.run_id ?? "");
      selectedRunRef.current = runId || selectedRunRef.current;
      setNotice(`本轮 Agent 已记录 ${Array.isArray(event.paths) ? event.paths.length : 0} 个可审阅变更；确认后可安全撤销。`);
      void refreshChanges(undefined, runId);
    }
    if (type === "session.waiting_for_input") void refreshSessions();
  }

  useEffect(() => {
    let stopped = false;
    let retryTimer: number | undefined;
    const reconnect = async () => {
      if (stopped) return;
      setConnection("connecting");
      try {
        await client.connect("127.0.0.1", 7437);
        await client.request("event.subscribe", { topics, scope: "global" });
        const opened = await client.request("workspace.list");
        const recent = (opened.workspaces as Workspace[]) ?? [];
        workspacesRef.current = recent;
        setWorkspaces(recent);
        if (!workspaceRef.current && recent.length) setWorkspace(recent[0]);
        if (!workspaceRef.current && recent.length) await refreshTree(recent[0]);
        await refreshSessions();
        if (sessionRef.current) await selectSession(sessionRef.current, { announce: false });
        if (activeRunRef.current) {
          const state = await client.request("run.get", { run_id: activeRunRef.current });
          if (state.status !== "running") setActiveRunId(null);
        }
        setConnection("ready");
      } catch (error) {
        setConnection("offline");
        setNotice(`本地服务暂不可用：${errorText(error)}。正在自动重试。`);
        retryTimer = window.setTimeout(() => void reconnect(), 2_000);
      }
    };
    const stopEvents = client.onEvent(handleEvent);
    const stopDisconnect = client.onDisconnect((reason) => {
      if (stopped) return;
      setConnection("offline");
      setNotice(`连接已断开：${reason}。正在恢复工作台。`);
      window.clearTimeout(retryTimer);
      retryTimer = window.setTimeout(() => void reconnect(), 1_200);
    });
    void reconnect();
    return () => {
      stopped = true;
      window.clearTimeout(retryTimer);
      stopEvents();
      stopDisconnect();
      client.dispose();
    };
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(true);
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "n") {
        event.preventDefault();
        void newTask();
      }
      if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === "p") {
        event.preventDefault();
        void setPermissionMode("plan");
      }
      if ((event.ctrlKey || event.metaKey) && event.key === "2") {
        event.preventDefault();
        composerRef.current?.focus();
      }
      if (event.key === "Escape") {
        setPaletteOpen(false);
        setSelectedChange(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

  useEffect(() => {
    if (paletteOpen) window.setTimeout(() => paletteInputRef.current?.focus(), 0);
  }, [paletteOpen]);

  async function chooseWorkspace() {
    const selected = await open({ directory: true, multiple: false, title: "选择代码仓库" });
    if (!selected || Array.isArray(selected)) return;
    try {
      const result = await client.request("workspace.open", { path: selected });
      const next = result.workspace as Workspace;
      setWorkspace(next);
      setWorkspaces((items) => [next, ...items.filter((item) => item.workspace_id !== next.workspace_id)]);
      setNotice(`已打开 ${next.name}。接下来可以从任务、文件和变更三个视角推进工作。`);
      await refreshChanges(next);
      await refreshTree(next);
    } catch (error) { setNotice(`打开工作区失败：${errorText(error)}`); }
  }

  async function newTask() {
    if (!workspace) { setNotice("请先选择工作区，再创建任务。这样执行上下文、文件和变更才会保持一致。"); return; }
    try {
      const result = await client.request("session.create", { mode: "chat", title: "", workspace_id: workspace.workspace_id });
      ++selectionRef.current;
      const nextSessionId = String(result.session_id);
      setSessionId(nextSessionId);
      sessionRef.current = nextSessionId;
      setTimeline([]);
      setPermission(null);
      setPlanItems([]);
      setTestResults([]);
      await refreshSessions();
      setNotice("新任务已创建。描述希望 Agent 在工作区完成的目标。");
    } catch (error) { setNotice(`创建任务失败：${errorText(error)}`); }
  }

  function openTaskManager() {
    if (!activeSession) { setNotice("先选择或创建一个任务，再进行重命名或归档。"); return; }
    setTaskTitleDraft(activeSession.title);
    setTaskManagerOpen(true);
  }

  async function renameCurrentTask() {
    if (!sessionId || !taskTitleDraft.trim()) return;
    setTaskManaging(true);
    try {
      await client.request("session.rename", { session_id: sessionId, title: taskTitleDraft.trim() });
      await refreshSessions();
      setNotice("任务名称已更新。");
    } catch (error) { setNotice(`重命名失败：${errorText(error)}`); }
    finally { setTaskManaging(false); }
  }

  async function archiveCurrentTask() {
    if (!sessionId) return;
    setTaskManaging(true);
    try {
      await client.request("session.archive", { session_id: sessionId });
      ++selectionRef.current;
      setTaskManagerOpen(false);
      setSessionId(null);
      sessionRef.current = null;
      setTimeline([]);
      setPlanItems([]);
      setTestResults([]);
      await refreshSessions();
      setNotice("任务已归档；历史记录和运行回放仍会保留在本机。");
    } catch (error) { setNotice(`归档失败：${errorText(error)}`); }
    finally { setTaskManaging(false); }
  }

  async function setCurrentTaskPinned(pinned: boolean) {
    if (!sessionId) return;
    setTaskManaging(true);
    try {
      await client.request("session.pin", { session_id: sessionId, pinned });
      await refreshSessions();
      setNotice(pinned ? "任务已固定在侧栏顶部。" : "任务已从固定区移回最近任务。");
    } catch (error) { setNotice(`更新固定状态失败：${errorText(error)}`); }
    finally { setTaskManaging(false); }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const content = prompt.trim();
    if (!content) return;
    if (!workspace) { setNotice("请先选择工作区，这样任务、文件和变更才会归属同一个仓库。"); return; }
    let target = sessionId;
    if (!target) {
      const created = await client.request("session.create", { mode: "chat", title: content.slice(0, 40), workspace_id: workspace.workspace_id });
      target = String(created.session_id);
      setSessionId(target);
      await refreshSessions();
    }
    setTimeline((items) => [...items, { id: crypto.randomUUID(), kind: "user", body: content }]);
    setPrompt("");
    setNotice("任务已提交，正在等待 Agent 的第一条可见状态。");
    try {
      const result = await client.request("session.send_message", { session_id: target, content });
      const runId = String(result.run_id);
      selectedRunRef.current = runId;
      setActiveRunId(runId);
    } catch (error) { setNotice(`发送失败：${errorText(error)}`); }
  }

  async function cancelRun() {
    if (!activeRunId) return;
    try {
      const result = await client.request("run.cancel", { run_id: activeRunId });
      setNotice(result.status === "cancelling" ? "已请求停止当前运行。" : "当前没有可停止的运行。");
    } catch (error) { setNotice(`停止运行失败：${errorText(error)}`); }
  }

  async function decide(decision: string) {
    if (!permission) return;
    try {
      await client.request("permission.respond", { tool_use_id: permission.tool_use_id, decision });
      setPermission(null);
    } catch (error) { setNotice(`审批未送达：${errorText(error)}`); }
  }

  async function setPermissionMode(nextMode: string) {
    try {
      const result = await client.request("permission.set_mode", { mode: nextMode });
      if (!result.ok) throw new Error(String(result.error ?? "权限策略未更新"));
      setMode(String(result.mode ?? nextMode));
      setNotice(`已切换为${modeLabel(String(result.mode ?? nextMode))}。`);
      setSettingsOpen(false);
    } catch (error) { setNotice(`更新权限策略失败：${errorText(error)}`); }
  }

  async function loadSettings() {
    setSettingsLoading(true);
    try {
      const [settingsResult, providerResult] = await Promise.all([
        client.request("settings.get"), client.request("provider.status"),
      ]);
      const settings = settingsResult.settings as RuntimeSettings;
      setRuntimeSettings(settings);
      setModelDraft(settings.model);
      setMode(settings.permission_mode);
      setProviderStatus(providerResult as unknown as ProviderStatus);
    } catch (error) { setNotice(`读取设置失败：${errorText(error)}`); }
    finally { setSettingsLoading(false); }
  }

  async function updateRuntimeSettings(update: Record<string, string>) {
    try {
      const result = await client.request("settings.update", update);
      const settings = result.settings as RuntimeSettings;
      setRuntimeSettings(settings);
      setMode(settings.permission_mode);
      setModelDraft(settings.model);
      setNotice("设置已保存，将在下一轮 Agent 任务生效。");
      await loadSettings();
    } catch (error) { setNotice(`更新设置失败：${errorText(error)}`); }
  }

  useEffect(() => { if (settingsOpen) void loadSettings(); }, [settingsOpen]);

  async function openDiagnostics() {
    setDiagnosticsOpen(true);
    setDiagnosticsLoading(true);
    try {
      const ping = await client.request("core.ping", { client: "sztucode-desktop" });
      const status = workspace
        ? await client.request("workspace.status", { workspace_id: workspace.workspace_id })
        : null;
      setDiagnostics({
        version: String(ping.server_version ?? "unknown"),
        uptime: `${Math.max(0, Math.round(Number(ping.uptime_ms ?? 0) / 1000))} s`,
        branch: String(status?.branch ?? "—"),
        changes: Number(status?.changed_file_count ?? 0),
        repository: Boolean(status?.is_git_repository),
      });
    } catch (error) {
      setDiagnostics(null);
      setNotice(`诊断请求失败：${errorText(error)}`);
    } finally { setDiagnosticsLoading(false); }
  }

  async function openDiff(change: Change) {
    if (!workspace) return;
    setSelectedChange(change);
    setRevertConfirming(false);
    setDiff("");
    setDiffLoading(true);
    try {
      const result = await client.request("change.diff", { workspace_id: workspace.workspace_id, path: change.path });
      setDiff(String(result.diff ?? ""));
    } catch (error) { setDiff(`无法读取 Diff：${errorText(error)}`); }
    finally { setDiffLoading(false); }
  }

  async function revertSelectedChange() {
    if (!workspace || !selectedChange?.agent_owned || !selectedChange.run_id) return;
    setReverting(true);
    try {
      const result = await client.request("change.revert", {
        workspace_id: workspace.workspace_id,
        run_id: selectedChange.run_id,
        paths: [selectedChange.path],
        confirm: "revert",
      });
      const reverted = (result.reverted_paths as string[]) ?? [];
      const blocked = result.blocked_paths as Record<string, string> | undefined;
      if (reverted.length) setNotice(`已恢复 ${reverted.join("、")} 到本轮 Agent 运行前的内容。`);
      else setNotice(`未执行覆盖：${Object.values(blocked ?? {})[0] ?? "文件不再满足安全回退条件"}`);
      await refreshChanges(workspace, selectedChange.run_id);
      setRevertConfirming(false);
      setSelectedChange(null);
    } catch (error) { setNotice(`撤销失败：${errorText(error)}`); }
    finally { setReverting(false); }
  }

  async function openFile(node: FileNode) {
    if (!workspace || node.kind !== "file") return;
    setSelectedFile(node);
    setFileContent("");
    setFileLoading(true);
    try {
      const result = await client.request("file.read", { workspace_id: workspace.workspace_id, path: node.path });
      setFileContent(String(result.content ?? ""));
    } catch (error) { setFileContent(`无法读取文件：${errorText(error)}`); }
    finally { setFileLoading(false); }
  }

  function askAgentToFix(path: string) {
    setPrompt(`请检查并修复 ${path} 中刚才审阅到的问题。先说明准备修改的内容，再实施修改并运行相关验证。`);
    setSelectedChange(null);
    setSelectedFile(null);
    setNotice(`已将 ${path} 作为当前任务上下文；补充要求后即可发送给 Agent。`);
    window.setTimeout(() => composerRef.current?.focus(), 0);
  }

  const diffRows = useMemo(() => splitDiff(diff), [diff]);
  const paletteCommands: PaletteCommand[] = useMemo(() => [
    { id: "new", title: "新建任务", detail: "在当前工作区开始一个可恢复任务", key: "Ctrl N", action: () => { void newTask(); } },
    { id: "workspace", title: "切换工作区", detail: workspace?.name ?? "选择本地代码仓库", key: "", action: () => { void chooseWorkspace(); } },
    { id: "plan", title: "进入计划模式", detail: "先拆分与确认，再让 Agent 执行", key: "Ctrl ⇧ P", action: () => { void setPermissionMode("plan"); } },
    { id: "review", title: "查看变更审阅", detail: `${changes.length} 个未提交变更`, key: "", action: () => { setRightOpen(true); if (changes[0]) void openDiff(changes[0]); } },
    { id: "pin", title: activeSession?.pinned ? "取消固定当前任务" : "固定当前任务", detail: activeSession?.pinned ? "移回按最近活动排序的任务列表" : "将任务保留在侧栏顶部", key: "", disabled: !activeSession, action: () => { void setCurrentTaskPinned(!activeSession?.pinned); } },
    { id: "stop", title: "停止当前运行", detail: activeRunId ? "请求安全停止当前 Agent" : "当前没有运行中的任务", key: "Esc", disabled: !activeRunId, action: () => { void cancelRun(); } },
    { id: "focus", title: "聚焦任务输入", detail: "继续描述或追问当前任务", key: "Ctrl 2", action: () => composerRef.current?.focus() },
    { id: "settings", title: "打开权限设置", detail: "调整审批与执行策略", key: "", action: () => setSettingsOpen(true) },
    { id: "diagnostics", title: "查看本地诊断", detail: "检查 daemon、Git 与工作区状态", key: "", action: () => { void openDiagnostics(); } },
  ], [activeRunId, activeSession, changes, workspace]);
  const matchingCommands = paletteCommands.filter((command) => `${command.title} ${command.detail}`.toLowerCase().includes(paletteQuery.toLowerCase()));
  function runPaletteCommand(command: PaletteCommand) {
    if (command.disabled) return;
    command.action();
    setPaletteOpen(false);
    setPaletteQuery("");
  }
  function renderTree(nodes: FileNode[], depth = 0): React.ReactNode {
    return nodes.map((node) => node.kind === "directory"
      ? <div className="tree-directory" key={node.path} style={{ paddingLeft: depth * 10 }}><span><FolderOpen size={13}/>{node.name}</span>{node.children && renderTree(node.children, depth + 1)}</div>
      : <button className="tree-file" key={node.path} style={{ paddingLeft: depth * 10 + 4 }} onClick={() => void openFile(node)}><FileCode2 size={13}/>{node.name}</button>);
  }
  return <main className="app-shell">
    <header className="topbar">
      <div className="brand"><span className="brand-mark">S</span><span>SztuCode</span><span className="brand-sub">LOCAL AGENT WORKBENCH</span></div>
      <div className="crumb"><FolderOpen size={14}/><span>{workspace?.name ?? "尚未选择工作区"}</span>{workspace && <><ChevronRight size={14}/><GitBranch size={14}/><span>本地工作区</span></>}</div>
      <div className={`connection ${connection}`}><i />{connection === "ready" ? "已连接" : connection === "connecting" ? "连接中" : "离线"}</div>
      <button className="mobile-nav" onClick={() => setSidebarOpen(true)} aria-label="打开任务栏"><Menu size={18}/></button>
    </header>
    <section className="workbench">
      {sidebarOpen && <button className="mobile-scrim" onClick={() => setSidebarOpen(false)} aria-label="关闭任务栏"/>}
      <aside className={`sidebar ${sidebarOpen ? "mobile-open" : ""}`}>
        <button className="new-task" onClick={() => void newTask()}><Plus size={16}/>新任务<kbd>Ctrl N</kbd></button>
        <button className="workspace-picker" onClick={() => void chooseWorkspace()}><FolderOpen size={15}/>{workspace ? "切换工作区" : "选择本地工作区"}</button>
        {pinnedSessions.length > 0 && <><div className="sidebar-label sidebar-label-pinned">固定<span>{pinnedSessions.length}</span></div><nav className="task-list pinned-task-list" aria-label="固定任务">{pinnedSessions.map((item) => <button key={item.session_id} className={`task-row ${item.session_id === sessionId ? "selected" : ""}`} onClick={() => { setSidebarOpen(false); void selectSession(item.session_id); }}><i className={item.status === "active" ? "pulse" : "pinned"}/><span className="task-copy"><b>{short(item.title || "未命名任务")}</b><small>已固定 · {sessionState(item)}</small></span><Pin size={12}/></button>)}</nav></>}
        <div className="sidebar-label">最近任务<span>{recentSessions.length}</span></div>
        <nav className="task-list" aria-label="任务历史">
          {recentSessions.map((item) => <button key={item.session_id} className={`task-row ${item.session_id === sessionId ? "selected" : ""}`} onClick={() => { setSidebarOpen(false); void selectSession(item.session_id); }}>
            <i className={item.status === "active" ? "pulse" : ""}/><span className="task-copy"><b>{short(item.title || "未命名任务")}</b><small>{sessionState(item)}</small></span>
          </button>)}
          {!visibleSessions.length && <p className="empty-list">任务会保存在本机，断开后仍可恢复。</p>}
        </nav>
        <div className="sidebar-foot"><button onClick={openTaskManager}><ListChecks size={15}/>任务</button><button onClick={() => setSettingsOpen(true)}><Settings2 size={15}/>设置</button><button onClick={() => void openDiagnostics()}><TerminalSquare size={15}/>诊断</button></div>
      </aside>
      <section className="conversation">
        <div className="conversation-head"><div><span className="eyebrow">{activeSession ? "当前任务" : "开始工作"}</span><h1>{activeSession?.title || "选择工作区，发起第一个任务"}</h1></div><button className="mode" onClick={() => setSettingsOpen(true)}><ShieldCheck size={15}/>{modeLabel(mode)}</button></div>
        <div className="notice"><WandSparkles size={16}/><span>{notice}</span>{connection === "offline" && <button className="start-daemon" disabled={daemonStarting} onClick={() => void startLocalService()}>{daemonStarting ? "启动中…" : "启动本地服务"}</button>}</div>
        <div className="timeline" ref={timelineParentRef}>
          {!timeline.length && <div className="empty-state"><div className="crosshair"/><h2>让 Agent 接管一段清晰的工作</h2><p>从修复一个 Bug、审阅一组改动或实现一个小功能开始。每次调用、审批与变更都会留在任务时间线中。</p><div className="starter"><button onClick={() => setPrompt("检查当前仓库，找出最值得先修复的问题并给出计划。")}><Search size={14}/>检查仓库</button><button onClick={() => setPrompt("为当前项目补充缺失的测试，并说明验证方式。")}><ListChecks size={14}/>补充测试</button></div></div>}
          {!!timeline.length && <div className="timeline-virtual" style={{ height: timelineVirtualizer.getTotalSize() }}>{timelineVirtualizer.getVirtualItems().map((virtualItem) => { const item = timeline[virtualItem.index]; return <article className={`timeline-item ${item.kind}`} data-index={virtualItem.index} key={item.id} ref={timelineVirtualizer.measureElement} style={{ transform: `translateY(${virtualItem.start}px)` }}><div className="item-rail"><i /></div><div className="item-content">{item.title && <header><span>{item.kind === "tool" ? "工具调用" : item.kind}</span><b>{item.title}</b><em>{item.state}</em></header>}<pre className={item.kind === "agent" ? "prose" : "code"}>{item.body}</pre></div></article>; })}</div>}
        </div>
        <form className="composer" onSubmit={(event) => void submit(event)}><textarea ref={composerRef} value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder={workspace ? "描述要在这个工作区完成的任务…" : "先选择一个本地工作区…"} rows={3}/><div className="composer-bar"><span><kbd>Ctrl ↵</kbd> 发送<span className="dot">·</span><kbd>/</kbd> 命令</span><button type="button" className="mode-select" onClick={() => void setPermissionMode(mode === "normal" ? "plan" : "normal")}>{modeLabel(mode)}</button><button className="send" type="submit" aria-label="发送任务"><ArrowUp size={17}/></button></div></form>
        </section>
      {rightOpen && <aside className={`inspector ${mobileInspectorOpen ? "mobile-visible" : ""}`}><div className="inspector-head"><div><span className="eyebrow">工作区状态</span><h2>变更与验证</h2></div><button onClick={() => { setRightOpen(false); setMobileInspectorOpen(false); }} aria-label="收起检查器"><PanelRightClose size={17}/></button></div><section className="stat-row"><div><span>未提交变更</span><b>{changes.length}</b></div><div><span>计划进度</span><b>{planItems.filter((item) => item.status === "completed").length}/{planItems.length || "—"}</b></div></section>{treeNodes.length > 0 && <section className="file-panel"><header><FolderOpen size={15}/><span>文件</span><button onClick={() => void refreshTree()}>刷新</button></header><div className="file-tree">{renderTree(treeNodes)}</div></section>}{planItems.length > 0 && <section className="plan-panel"><header><ListChecks size={15}/><span>执行计划</span></header>{planItems.map((item) => <div className={`plan-row ${item.status}`} key={item.id}><i/><div><b>{item.subject}</b><small>{item.status === "completed" ? "已完成" : item.status === "in_progress" ? "进行中" : item.blocked_by.length ? `等待 #${item.blocked_by.join("、#")}` : "待开始"}</small></div></div>)}</section>}{testResults.length > 0 && <section className="test-panel"><header><ListChecks size={15}/><span>验证结果</span><small>{testResults.filter((item) => item.status === "passed").length} 通过</small></header>{testResults.map((result) => <div className={`test-row ${result.status}`} key={result.tool_use_id}><i/>{result.summary}</div>)}</section>}<section className="change-panel"><header><FileCode2 size={15}/><span>变更</span><button onClick={() => void refreshChanges()}>刷新</button></header>{changes.length ? changes.map((change) => <button className="change-row" key={change.path} onClick={() => void openDiff(change)}><i className={change.worktree_status === "?" ? "add" : "modify"}/><span>{change.path}</span><small>{change.index_status}{change.worktree_status}</small></button>) : <p>工作区干净。完成任务后，文件改动会显示在这里。</p>}</section><button className={`run-card ${activeRunId ? "can-stop" : ""}`} onClick={() => void cancelRun()} disabled={!activeRunId}><Activity size={16}/><div><b>{activeRunId ? "正在运行" : "运行记录"}</b><span>{activeRunId ? "点击停止当前运行" : timeline.some((item) => item.kind === "tool") ? "工具活动已记录在时间线" : "等待任务开始"}</span></div><CircleStop size={16}/></button></aside>}
      {!rightOpen && <button className="open-inspector" onClick={() => { setRightOpen(true); setMobileInspectorOpen(true); }}>变更 <ChevronRight size={15}/></button>}
      {rightOpen && <button className="mobile-inspector-trigger" onClick={() => setMobileInspectorOpen(true)}>变更 <ChevronRight size={15}/></button>}
    </section>
    {selectedChange && <section className="diff-drawer" role="dialog" aria-modal="true" aria-label={`${selectedChange.path} 的代码变更`}><header className="diff-head"><div><span className="eyebrow">代码审阅{selectedChange.agent_owned ? " · 本轮 Agent 变更" : ""}</span><h2>{selectedChange.path}</h2></div><div className="diff-controls"><button className={diffView === "split" ? "active" : ""} onClick={() => setDiffView("split")}>对照</button><button className={diffView === "unified" ? "active" : ""} onClick={() => setDiffView("unified")}>统一</button><button className="agent-fix" onClick={() => askAgentToFix(selectedChange.path)}>让 Agent 修复</button>{selectedChange.agent_owned && selectedChange.revertible && <button className="revert-control" onClick={() => setRevertConfirming(true)}>撤销本轮</button>}<button className="diff-close" onClick={() => setSelectedChange(null)} aria-label="关闭代码审阅"><X size={18}/></button></div></header>{revertConfirming && <div className="revert-confirm"><div><b>恢复到本轮 Agent 开始前</b><span>仅恢复此文件；若文件后来被修改，系统会拒绝覆盖。</span></div><button onClick={() => setRevertConfirming(false)}>取消</button><button className="danger" disabled={reverting} onClick={() => void revertSelectedChange()}>{reverting ? "正在恢复…" : "确认撤销"}</button></div>}{diffLoading ? <div className="diff-empty">正在读取工作区差异…</div> : !diff ? <div className="diff-empty">该文件没有可显示的未提交差异。</div> : diffView === "unified" ? <pre className="diff-unified">{diff.split("\n").map((line, index) => <code key={index} className={line.startsWith("+") ? "added" : line.startsWith("-") ? "removed" : line.startsWith("@@") ? "hunk" : ""}>{line || " "}</code>)}</pre> : <div className="diff-split"><div className="diff-pane-label">修改前</div><div className="diff-pane-label">修改后</div>{diffRows.map((row, index) => <Fragment key={index}><code className={`diff-cell ${row.kind}`}>{row.old || " "}</code><code className={`diff-cell ${row.kind}`}>{row.next || " "}</code></Fragment>)}</div>}</section>}
    {selectedFile && <section className="file-drawer" role="dialog" aria-modal="true" aria-label={`${selectedFile.path} 的文件内容`}><header className="diff-head"><div><span className="eyebrow">文件查看</span><h2>{selectedFile.path}</h2></div><div className="diff-controls"><button className="agent-fix" onClick={() => askAgentToFix(selectedFile.path)}>让 Agent 修复</button><button className="diff-close" onClick={() => setSelectedFile(null)} aria-label="关闭文件查看"><X size={18}/></button></div></header>{fileLoading ? <div className="diff-empty">正在读取文件…</div> : <pre className="file-content">{fileContent}</pre>}</section>}
    {paletteOpen && <section className="command-palette" role="dialog" aria-modal="true" aria-label="命令面板" onMouseDown={(event) => { if (event.target === event.currentTarget) setPaletteOpen(false); }}><div className="palette-sheet"><header><Command size={17}/><input ref={paletteInputRef} value={paletteQuery} onChange={(event) => setPaletteQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && matchingCommands[0]) runPaletteCommand(matchingCommands[0]); }} placeholder="搜索命令、工作区或任务操作…"/><kbd>Esc</kbd></header><div className="palette-list">{matchingCommands.map((command) => <button key={command.id} disabled={command.disabled} onClick={() => runPaletteCommand(command)}><div><b>{command.title}</b><span>{command.detail}</span></div>{command.key && <kbd>{command.key}</kbd>}</button>)}{!matchingCommands.length && <p>没有匹配的命令。</p>}</div></div></section>}
    {taskManagerOpen && <section className="settings-drawer" role="dialog" aria-modal="true" aria-label="任务管理"><div className="settings-sheet task-manager-sheet"><header><div><span className="eyebrow">当前任务</span><h2>任务管理</h2></div><button onClick={() => setTaskManagerOpen(false)} aria-label="关闭任务管理"><X size={18}/></button></header><p>任务的消息、计划、变更记录与运行回放会继续保留在本机。</p><label className="task-title-editor"><span>任务名称</span><input value={taskTitleDraft} onChange={(event) => setTaskTitleDraft(event.target.value)} placeholder="为这段工作命名"/><button disabled={taskManaging || !taskTitleDraft.trim()} onClick={() => void renameCurrentTask()}>{taskManaging ? "保存中…" : "保存名称"}</button></label><div className="task-pin"><div><b>{activeSession?.pinned ? "已固定任务" : "固定任务"}</b><span>{activeSession?.pinned ? "它会显示在侧栏顶部，并优先于最近任务。" : "将这项工作保留在侧栏顶部，方便长期跟进。"}</span></div><button disabled={taskManaging} onClick={() => void setCurrentTaskPinned(!activeSession?.pinned)}><Pin size={13}/>{activeSession?.pinned ? "取消固定" : "固定"}</button></div><div className="task-archive"><div><b>归档任务</b><span>从最近任务列表移除，不删除任何记录。</span></div><button disabled={taskManaging} onClick={() => void archiveCurrentTask()}>归档</button></div></div></section>}
    {settingsOpen && <section className="settings-drawer" role="dialog" aria-modal="true" aria-label="运行设置"><div className="settings-sheet settings-sheet-wide"><header><div><span className="eyebrow">本地运行配置</span><h2>设置与连接</h2></div><button onClick={() => setSettingsOpen(false)} aria-label="关闭设置"><X size={18}/></button></header>{settingsLoading ? <div className="diagnostics-empty">正在读取运行时配置…</div> : <div className="settings-sections"><section className="settings-section"><header><span>模型 Provider</span><i className={providerStatus?.ready_for_next_run ? "ok" : "warn"}/></header><div className="setting-grid"><label>服务<select value={runtimeSettings?.provider ?? "anthropic"} onChange={(event) => void updateRuntimeSettings({ provider: event.target.value })}><option value="anthropic">Anthropic</option><option value="openai">OpenAI 兼容</option></select></label><label>模型<input value={modelDraft} onChange={(event) => setModelDraft(event.target.value)} onBlur={() => { if (modelDraft && modelDraft !== runtimeSettings?.model) void updateRuntimeSettings({ model: modelDraft }); }}/></label></div><p>{providerStatus?.api_key_configured ? "凭据已配置；修改将在下一轮任务生效。" : "未发现当前 Provider 的 API Key；可查看本地环境变量后重试。"}{providerStatus?.custom_endpoint_configured ? " 使用自定义端点。" : ""}</p></section><section className="settings-section"><header><span>执行策略</span><small>高风险操作仍会明确审批</small></header><div className="policy-list">{(["normal", "plan", "accept_edits", "auto"] as const).map((item) => <button className={mode === item ? "selected" : ""} key={item} onClick={() => void updateRuntimeSettings({ permission_mode: item })}><i/><div><b>{modeLabel(item)}</b><span>{modeDescription(item)}</span></div></button>)}</div></section><section className="settings-section integration-section"><header><span>MCP 与 Skills</span><small>{providerStatus?.skills.length ?? 0} 个 Skills</small></header>{providerStatus?.mcp_servers.length ? <div className="integration-list">{providerStatus.mcp_servers.map((server) => <div key={server.name}><i className={server.status === "connected" ? "ok" : "warn"}/><b>{server.name}</b><span>{server.status === "connected" ? `${server.tool_count} 个工具可用` : "当前不可用"}</span><em>{server.transport}</em></div>)}</div> : <p>没有配置 MCP 服务。Skills 与 Provider 状态来自本地 daemon，不会上传凭据。</p>}<div className="skill-strip">{providerStatus?.skills.slice(0, 6).map((skill) => <span key={skill.name} title={skill.description}>#{skill.name}</span>)}</div></section></div>}</div></section>}
    {diagnosticsOpen && <section className="settings-drawer" role="dialog" aria-modal="true" aria-label="本地诊断"><div className="settings-sheet diagnostics-sheet"><header><div><span className="eyebrow">本地运行状态</span><h2>诊断</h2></div><button onClick={() => setDiagnosticsOpen(false)} aria-label="关闭诊断"><X size={18}/></button></header>{diagnosticsLoading ? <div className="diagnostics-empty">正在检查本地服务…</div> : diagnostics ? <dl className="diagnostics-grid"><div><dt>Daemon</dt><dd><i/> 已连接</dd></div><div><dt>版本</dt><dd>{diagnostics.version}</dd></div><div><dt>已运行</dt><dd>{diagnostics.uptime}</dd></div><div><dt>Git 分支</dt><dd>{diagnostics.branch}</dd></div><div><dt>仓库状态</dt><dd>{diagnostics.repository ? "已识别" : "非 Git 仓库"}</dd></div><div><dt>未提交变更</dt><dd>{diagnostics.changes}</dd></div></dl> : <div className="diagnostics-empty">无法连接本地服务。确认 daemon 已启动后重试。</div>}<button className="diagnostics-retry" onClick={() => void openDiagnostics()}>重新检查</button></div></section>}
    {permission && <section className="permission-bar"><div className="permission-copy"><ShieldCheck size={18}/><div><b>需要你的确认：{permission.tool_name}</b><span>{JSON.stringify(permission.params)}</span></div></div><div className="permission-actions"><button onClick={() => void decide("deny_once")}>拒绝</button><button onClick={() => void decide("allow_once")}>允许一次</button><button className="always" onClick={() => void decide("always_allow")}>始终允许</button></div></section>}
  </main>;
}
