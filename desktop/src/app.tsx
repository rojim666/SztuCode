import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { TopBar } from "./components/Shell/TopBar";
import { Sidebar } from "./components/Shell/Sidebar";
import { ConversationView } from "./components/Chat/ConversationView";
import { InspectorPanel } from "./components/Inspector/InspectorPanel";
import { DiffDrawer } from "./components/Diff/DiffDrawer";
import { FileViewer } from "./components/Diff/FileViewer";
import { CommandPalette } from "./components/CommandPalette/CommandPalette";
import { PermissionBar } from "./components/Permissions/PermissionBar";
import { SettingsDialog } from "./components/Settings/SettingsDialog";
import { DiagnosticsDialog } from "./components/Settings/DiagnosticsDialog";
import { TaskManagerDialog } from "./components/TaskManager/TaskManagerDialog";
import { useDaemonConnection } from "./hooks/useDaemon";
import { useSessions } from "./hooks/useSessions";
import { useWorkspace } from "./hooks/useWorkspace";
import { useTimeline } from "./hooks/useTimeline";
import { usePermissions } from "./hooks/usePermissions";
import { useSettings } from "./hooks/useSettings";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import { getClient } from "./hooks/useDaemon";
import type { Change, DiffView, FileNode, PaletteCommand } from "./types";
// utility types used by child components

const client = getClient();

// ── App 根组件：编排 Hooks 与子组件 ────────────────────────

export function App() {
  // ── Refs（需在组件顶层声明）─────────────────────────────
  const composerRef = useRef<HTMLTextAreaElement>(null);

  // ── 状态 ─────────────────────────────────────────────────
  const [prompt, setPrompt] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [mobileInspectorOpen, setMobileInspectorOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteQuery, setPaletteQuery] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [taskManagerOpen, setTaskManagerOpen] = useState(false);
  const [taskTitleDraft, setTaskTitleDraft] = useState("");
  const [taskManaging, setTaskManaging] = useState(false);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [diagnostics, setDiagnostics] = useState<import("./types").Diagnostics | null>(null);
  const [diagnosticsLoading, setDiagnosticsLoading] = useState(false);

  // Diff 相关
  const [selectedChange, setSelectedChange] = useState<Change | null>(null);
  const [diff, setDiff] = useState("");
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffView, setDiffView] = useState<DiffView>("split");
  const [revertConfirming, setRevertConfirming] = useState(false);
  const [reverting, setReverting] = useState(false);

  // 文件查看相关
  const [selectedFile, setSelectedFile] = useState<FileNode | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [fileLoading, setFileLoading] = useState(false);

  // ── Hooks ────────────────────────────────────────────────
  const timeline = useTimeline();

  const daemon = useDaemonConnection((event) => {
    // 复合事件处理器：先由 timeline 处理
    const handled = timeline.handleEvent(event, {
      onRunStarted: () => daemon.setNotice("Agent 正在分析任务并准备执行。"),
      onRunFinished: (runId, status, reason) => {
        daemon.setNotice(
          status === "success"
            ? "本轮任务已完成，可查看变更与验证结果。"
            : `任务结束：${reason}`,
        );
        void workspace.refreshChanges(undefined, runId);
        void sessions.refreshSessions();
      },
      onSessionWaiting: () => void sessions.refreshSessions(),
    });

    if (!handled) return;

    // 权限请求
    if (String(handled.type ?? "") === "permission.requested") {
      permissions.setPermission({
        tool_use_id: String(handled.tool_use_id),
        tool_name: String(handled.tool_name),
        params: handled.params,
        run_id: String(handled.run_id ?? ""),
      });
    }

    // 权限模式变更
    if (String(handled.type ?? "") === "permission.mode_changed") {
      permissions.setMode(String(handled.new_mode ?? "normal"));
    }

    // 变更应用
    if (String(handled.type ?? "") === "change.applied") {
      const runId = String(handled.run_id ?? "");
      timeline.selectedRunRef.current = runId || timeline.selectedRunRef.current;
      const count = Array.isArray(handled.paths) ? handled.paths.length : 0;
      daemon.setNotice(`本轮 Agent 已记录 ${count} 个可审阅变更；确认后可安全撤销。`);
      void workspace.refreshChanges(undefined, runId);
    }
  });

  const sessions = useSessions(client);
  const workspace = useWorkspace(client);
  const permissions = usePermissions(client);
  const settings = useSettings(client);

  // 同步 timeline 的 sessionRef 与 sessions hook
  useEffect(() => {
    timeline.syncSessionId(sessions.sessionId);
  }, [timeline, sessions.sessionId]);

  // ── 派生数据 ─────────────────────────────────────────────
  const activeSession = useMemo(
    () => sessions.sessions.find((s) => s.session_id === sessions.sessionId),
    [sessions.sessions, sessions.sessionId],
  );

  // ── 连接就绪后引导选择工作区并恢复会话 ─────────────────
  useEffect(() => {
    if (daemon.connection !== "ready") return;
    let stopped = false;

    const init = async () => {
      // 加载工作区列表
      const opened = await client.request("workspace.list");
      const recent = (opened.workspaces as import("./types").Workspace[]) ?? [];
      workspace.setWorkspaces(recent);
      if (!workspace.workspaceRef.current && recent.length) {
        workspace.setWorkspace(recent[0]);
        await workspace.refreshTree(recent[0]);
      }
      await sessions.refreshSessions();

      // 恢复上次会话
      if (sessions.sessionRef.current) {
        const session = await sessions.selectSession(sessions.sessionRef.current, { announce: false });
        if (!stopped && session) {
          const history = await client.request("session.get_history", {
            session_id: session.session_id,
          });
          timeline.loadHistory((history.messages as unknown[]) ?? []);
          if (session.latest_run_id) {
            timeline.selectedRunRef.current = session.latest_run_id;
            const replay = await client.request("run.replay", {
              run_id: session.latest_run_id,
            });
            for (const evt of (replay.events as import("./lib/ipc").IpcEvent[]) ?? []) {
              if (evt.type !== "llm.token") timeline.handleEvent(evt);
            }
          }
          const linkedWorkspace = workspace.workspacesRef.current.find(
            (w) => w.workspace_id === session.workspace_id,
          );
          if (linkedWorkspace) {
            workspace.setWorkspace(linkedWorkspace);
            await workspace.refreshChanges(linkedWorkspace, session.latest_run_id);
            await workspace.refreshTree(linkedWorkspace);
          }
        }
      }

      // 恢复活跃运行
      if (timeline.activeRunRef.current) {
        const state = await client.request("run.get", {
          run_id: timeline.activeRunRef.current,
        });
        if (state.status !== "running") timeline.setActiveRunId(null);
      }
    };

    void init().catch(console.error);
    return () => { stopped = true; };
  }, [daemon.connection]);

  // ── 操作函数 ─────────────────────────────────────────────

  const chooseWorkspace = useCallback(() => {
    void workspace.chooseWorkspace(daemon.setNotice);
  }, [workspace, daemon.setNotice]);

  const newTask = useCallback(() => {
    void sessions.newTask(workspace.workspace, daemon.setNotice).then((id) => {
      if (id) {
        timeline.setTimeline([]);
        permissions.setPermission(null);
        timeline.setPlanItems([]);
        timeline.setTestResults([]);
      }
    });
  }, [sessions, workspace.workspace, daemon.setNotice, timeline, permissions]);

  const selectSession = useCallback(
    async (id: string) => {
      permissions.setPermission(null);
      timeline.setActiveRunId(null);
      timeline.setTimeline([]);
      timeline.setPlanItems([]);
      timeline.setTestResults([]);
      timeline.selectedRunRef.current = null;

      const result = await sessions.selectSessionWithHistory(id);
      if (!result.session) return;

      timeline.loadHistory(result.messages);

      if (result.session.latest_run_id) {
        timeline.selectedRunRef.current = result.session.latest_run_id;
        const replay = await client.request("run.replay", {
          run_id: result.session.latest_run_id,
        });
        for (const evt of (replay.events as import("./lib/ipc").IpcEvent[]) ?? []) {
          if (evt.type !== "llm.token") timeline.handleEvent(evt);
        }
      }

      const linkedWorkspace = workspace.workspacesRef.current.find(
        (w) => w.workspace_id === result.session?.workspace_id,
      );
      if (linkedWorkspace) {
        workspace.setWorkspace(linkedWorkspace);
        await workspace.refreshChanges(linkedWorkspace, result.session.latest_run_id);
        await workspace.refreshTree(linkedWorkspace);
      }

      daemon.setNotice(
        `已恢复"${result.session.title || "未命名任务"}"的上下文与消息记录。`,
      );
      await sessions.refreshSessions();
    },
    [sessions, workspace, timeline, daemon.setNotice],
  );

  const submit = useCallback(
    async (event: FormEvent) => {
      event.preventDefault();
      const content = prompt.trim();
      if (!content) return;

      timeline.addUserMessage(content);
      setPrompt("");
      daemon.setNotice("任务已提交，正在等待 Agent 的第一条可见状态。");

      const result = await sessions.sendMessage(content, workspace.workspace, daemon.setNotice);
      if (result) {
        timeline.selectedRunRef.current = result.runId;
        timeline.setActiveRunId(result.runId);
      }
    },
    [prompt, sessions, workspace.workspace, daemon.setNotice, timeline],
  );

  const toggleMode = useCallback(() => {
    const next = permissions.mode === "normal" ? "plan" : "normal";
    void permissions.setPermissionMode(next, daemon.setNotice);
  }, [permissions, daemon.setNotice]);

  const openDiagnostics = useCallback(async () => {
    setDiagnosticsOpen(true);
    setDiagnosticsLoading(true);
    const result = await settings.getDiagnostics(workspace.getWorkspaceStatus);
    setDiagnostics(result);
    setDiagnosticsLoading(false);
  }, [settings, workspace.getWorkspaceStatus]);

  const openDiff = useCallback(
    async (change: Change) => {
      setSelectedChange(change);
      setRevertConfirming(false);
      setDiff("");
      setDiffLoading(true);
      const content = await workspace.getDiff(change, daemon.setNotice);
      setDiff(content ?? "");
      setDiffLoading(false);
    },
    [workspace, daemon.setNotice],
  );

  const openFile = useCallback(
    async (node: FileNode) => {
      if (node.kind !== "file") return;
      setSelectedFile(node);
      setFileContent("");
      setFileLoading(true);
      const result = await workspace.openFile(node, daemon.setNotice);
      if (result) setFileContent(result.content);
      setFileLoading(false);
    },
    [workspace, daemon.setNotice],
  );

  const askAgentToFix = useCallback(
    (path: string) => {
      setPrompt(
        `请检查并修复 ${path} 中刚才审阅到的问题。先说明准备修改的内容，再实施修改并运行相关验证。`,
      );
      setSelectedChange(null);
      setSelectedFile(null);
      daemon.setNotice(
        `已将 ${path} 作为当前任务上下文；补充要求后即可发送给 Agent。`,
      );
      window.setTimeout(() => composerRef.current?.focus(), 0);
    },
    [daemon.setNotice],
  );

  const openTaskManager = useCallback(() => {
    if (!activeSession) {
      daemon.setNotice("先选择或创建一个任务，再进行重命名或归档。");
      return;
    }
    setTaskTitleDraft(activeSession.title);
    setTaskManagerOpen(true);
  }, [activeSession, daemon.setNotice]);

  const renameTask = useCallback(async () => {
    if (!sessions.sessionId || !taskTitleDraft.trim()) return;
    setTaskManaging(true);
    await sessions.renameTask(sessions.sessionId, taskTitleDraft.trim(), daemon.setNotice);
    setTaskManaging(false);
  }, [sessions, taskTitleDraft, daemon.setNotice]);

  const archiveTask = useCallback(async () => {
    if (!sessions.sessionId) return;
    setTaskManaging(true);
    await sessions.archiveTask(sessions.sessionId, daemon.setNotice);
    setTaskManaging(false);
    setTaskManagerOpen(false);
    timeline.setTimeline([]);
    timeline.setPlanItems([]);
    timeline.setTestResults([]);
  }, [sessions, daemon.setNotice, timeline]);

  const togglePin = useCallback(async () => {
    if (!activeSession || !sessions.sessionId) return;
    setTaskManaging(true);
    await sessions.togglePin(sessions.sessionId, !activeSession.pinned, daemon.setNotice);
    setTaskManaging(false);
  }, [sessions, activeSession, daemon.setNotice]);

  const revertChange = useCallback(async () => {
    if (!selectedChange) return;
    setReverting(true);
    await workspace.revertChange(selectedChange, daemon.setNotice);
    setReverting(false);
    setRevertConfirming(false);
    setSelectedChange(null);
  }, [workspace, selectedChange, daemon.setNotice]);

  const decide = useCallback(
    (decision: string) => {
      void permissions.decide(decision, daemon.setNotice);
    },
    [permissions, daemon.setNotice],
  );

  // ── 命令面板命令 ─────────────────────────────────────────
  const paletteCommands = useMemo<PaletteCommand[]>(
    () => [
      {
        id: "new", title: "新建任务", detail: "在当前工作区开始一个可恢复任务",
        key: "Ctrl N", action: newTask,
      },
      {
        id: "workspace", title: "切换工作区",
        detail: workspace.workspace?.name ?? "选择本地代码仓库", key: "",
        action: chooseWorkspace,
      },
      {
        id: "plan", title: "进入计划模式", detail: "先拆分与确认，再让 Agent 执行",
        key: "Ctrl ⇧ P", action: () => void permissions.setPermissionMode("plan", daemon.setNotice),
      },
      {
        id: "review", title: "查看变更审阅",
        detail: `${workspace.changes.length} 个未提交变更`, key: "",
        action: () => {
          if (workspace.changes[0]) openDiff(workspace.changes[0]);
        },
      },
      {
        id: "pin", title: activeSession?.pinned ? "取消固定当前任务" : "固定当前任务",
        detail: activeSession?.pinned
          ? "移回按最近活动排序的任务列表"
          : "将任务保留在侧栏顶部",
        key: "", disabled: !activeSession, action: togglePin,
      },
      {
        id: "stop", title: "停止当前运行",
        detail: timeline.activeRunId ? "请求安全停止当前 Agent" : "当前没有运行中的任务",
        key: "Esc", disabled: !timeline.activeRunId,
        action: () => void timeline.cancelRun(client, daemon.setNotice),
      },
      {
        id: "focus", title: "聚焦任务输入", detail: "继续描述或追问当前任务",
        key: "Ctrl 2", action: () => composerRef.current?.focus(),
      },
      {
        id: "settings", title: "打开权限设置", detail: "调整审批与执行策略",
        key: "", action: () => setSettingsOpen(true),
      },
      {
        id: "diagnostics", title: "查看本地诊断", detail: "检查 daemon、Git 与工作区状态",
        key: "", action: openDiagnostics,
      },
    ],
    [
      newTask, chooseWorkspace, workspace.workspace, workspace.changes,
      activeSession, timeline.activeRunId, permissions.setPermissionMode,
      daemon.setNotice, openDiff, togglePin, openDiagnostics,
    ],
  );

  // ── 键盘快捷键 ───────────────────────────────────────────
  useKeyboardShortcuts({
    onCommandPalette: () => setPaletteOpen(true),
    onNewTask: () => void newTask(),
    onPlanMode: () => void permissions.setPermissionMode("plan", daemon.setNotice),
    onFocusComposer: () => composerRef.current?.focus(),
    onEscape: () => {
      setPaletteOpen(false);
      setSelectedChange(null);
    },
  });

  // ── 设置面板打开时加载设置 ───────────────────────────────
  useEffect(() => {
    if (settingsOpen) void settings.loadSettings();
  }, [settingsOpen]);

  // ── 渲染 ─────────────────────────────────────────────────
  const timelineHasTools = timeline.timeline.some((item) => item.kind === "tool");

  return (
    <main className="app-shell">
      <TopBar
        connection={daemon.connection}
        workspace={workspace.workspace}
        onOpenSidebar={() => setSidebarOpen(true)}
      />

      <section className="workbench">
        <Sidebar
          sessions={sessions.sessions}
          sessionId={sessions.sessionId}
          workspaceName={workspace.workspace?.name ?? null}
          sidebarOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          onNewTask={newTask}
          onChooseWorkspace={chooseWorkspace}
          onSelectSession={(id) => { void selectSession(id); }}
          onOpenTaskManager={openTaskManager}
          onOpenSettings={() => setSettingsOpen(true)}
          onOpenDiagnostics={openDiagnostics}
        />

        <ConversationView
          activeSession={activeSession}
          connection={daemon.connection}
          daemonStarting={daemon.daemonStarting}
          notice={daemon.notice}
          timeline={timeline.timeline}
          prompt={prompt}
          workspace={workspace.workspace}
          mode={permissions.mode}
          composerRef={composerRef}
          onSuggestion={setPrompt}
          onPromptChange={setPrompt}
          onSubmit={(e) => void submit(e)}
          onToggleMode={toggleMode}
          onOpenSettings={() => setSettingsOpen(true)}
          onStartDaemon={daemon.startLocalService}
        />

        <InspectorPanel
          rightOpen={true}
          mobileInspectorOpen={mobileInspectorOpen}
          changes={workspace.changes}
          treeNodes={workspace.treeNodes}
          planItems={timeline.planItems}
          testResults={timeline.testResults}
          activeRunId={timeline.activeRunId}
          timelineHasTools={timelineHasTools}
          onClose={() => { /* right panel can't be closed in this layout */ }}
          onMobileClose={() => setMobileInspectorOpen(false)}
          onMobileOpen={() => setMobileInspectorOpen(true)}
          onOpenDiff={(change) => { void openDiff(change); }}
          onOpenFile={(node) => { void openFile(node); }}
          onRefreshChanges={() => { void workspace.refreshChanges(); }}
          onRefreshTree={() => { void workspace.refreshTree(); }}
          onCancelRun={() => { void timeline.cancelRun(client, daemon.setNotice); }}
        />
      </section>

      {/* 覆盖层 */}
      {selectedChange && (
        <DiffDrawer
          change={selectedChange}
          diff={diff}
          diffLoading={diffLoading}
          diffView={diffView}
          revertConfirming={revertConfirming}
          reverting={reverting}
          onChangeView={setDiffView}
          onClose={() => setSelectedChange(null)}
          onAskAgentToFix={askAgentToFix}
          onRevert={() => setRevertConfirming(true)}
          onConfirmRevert={() => void revertChange()}
          onCancelRevert={() => setRevertConfirming(false)}
        />
      )}

      {selectedFile && (
        <FileViewer
          file={selectedFile}
          content={fileContent}
          loading={fileLoading}
          onClose={() => setSelectedFile(null)}
          onAskAgentToFix={askAgentToFix}
        />
      )}

      <CommandPalette
        open={paletteOpen}
        query={paletteQuery}
        commands={paletteCommands}
        onQueryChange={setPaletteQuery}
        onClose={() => { setPaletteOpen(false); setPaletteQuery(""); }}
      />

      {permissions.permission && (
        <PermissionBar
          permission={permissions.permission}
          onDenyOnce={() => decide("deny_once")}
          onAllowOnce={() => decide("allow_once")}
          onAlwaysAllow={() => decide("always_allow")}
        />
      )}

      <SettingsDialog
        open={settingsOpen}
        loading={settings.settingsLoading}
        runtimeSettings={settings.runtimeSettings}
        providerStatus={settings.providerStatus}
        mode={permissions.mode}
        modelDraft={settings.modelDraft}
        onClose={() => setSettingsOpen(false)}
        onModelDraftChange={(v) => settings.setModelDraft(v)}
        onModelDraftBlur={() => {
          if (settings.modelDraft && settings.modelDraft !== settings.runtimeSettings?.model) {
            void settings.updateRuntimeSettings({ model: settings.modelDraft }, daemon.setNotice);
          }
        }}
        onProviderChange={(v) => {
          void settings.updateRuntimeSettings({ provider: v }, daemon.setNotice);
        }}
        onPermissionModeChange={(m) => {
          void permissions.setPermissionMode(m, daemon.setNotice);
        }}
      />

      <DiagnosticsDialog
        open={diagnosticsOpen}
        loading={diagnosticsLoading}
        diagnostics={diagnostics}
        onClose={() => setDiagnosticsOpen(false)}
        onRetry={() => { void openDiagnostics(); }}
      />

      <TaskManagerDialog
        open={taskManagerOpen}
        session={activeSession}
        titleDraft={taskTitleDraft}
        managing={taskManaging}
        onClose={() => setTaskManagerOpen(false)}
        onTitleChange={setTaskTitleDraft}
        onRename={() => void renameTask()}
        onTogglePin={() => void togglePin()}
        onArchive={() => void archiveTask()}
      />
    </main>
  );
}
