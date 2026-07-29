import {
  FolderOpen, ListChecks, Pin, Plus, Settings2, TerminalSquare,
} from "lucide-react";
import type { Session } from "../../types";
import { short, sessionState } from "../../types";

type SidebarProps = {
  sessions: Session[];
  sessionId: string | null;
  workspaceName: string | null;
  sidebarOpen: boolean;
  onClose: () => void;
  onNewTask: () => void;
  onChooseWorkspace: () => void;
  onSelectSession: (id: string) => void;
  onOpenTaskManager: () => void;
  onOpenSettings: () => void;
  onOpenDiagnostics: () => void;
};

/** 侧边栏：新建任务、工作区选择、固定/最近任务列表、底部操作 */
export function Sidebar({
  sessions,
  sessionId,
  workspaceName,
  sidebarOpen,
  onClose,
  onNewTask,
  onChooseWorkspace,
  onSelectSession,
  onOpenTaskManager,
  onOpenSettings,
  onOpenDiagnostics,
}: SidebarProps) {
  const visible = sessions.filter((item) => !item.archived);
  const pinned = visible.filter((item) => item.pinned);
  const recent = visible.filter((item) => !item.pinned);

  return (
    <>
      {sidebarOpen && (
        <button className="mobile-scrim" onClick={onClose} aria-label="关闭任务栏" />
      )}
      <aside className={`sidebar ${sidebarOpen ? "mobile-open" : ""}`}>
        <button className="new-task" onClick={onNewTask}>
          <Plus size={16} />
          新任务
          <kbd>Ctrl N</kbd>
        </button>

        <button className="workspace-picker" onClick={onChooseWorkspace}>
          <FolderOpen size={15} />
          {workspaceName ? "切换工作区" : "选择本地工作区"}
        </button>

        {pinned.length > 0 && (
          <>
            <div className="sidebar-label sidebar-label-pinned">
              固定<span>{pinned.length}</span>
            </div>
            <nav className="task-list pinned-task-list" aria-label="固定任务">
              {pinned.map((item) => (
                <button
                  key={item.session_id}
                  className={`task-row ${item.session_id === sessionId ? "selected" : ""}`}
                  onClick={() => {
                    onClose();
                    onSelectSession(item.session_id);
                  }}
                >
                  <i className={item.status === "active" ? "pulse" : "pinned"} />
                  <span className="task-copy">
                    <b>{short(item.title || "未命名任务")}</b>
                    <small>已固定 · {sessionState(item)}</small>
                  </span>
                  <Pin size={12} />
                </button>
              ))}
            </nav>
          </>
        )}

        <div className="sidebar-label">
          最近任务<span>{recent.length}</span>
        </div>
        <nav className="task-list" aria-label="任务历史">
          {recent.map((item) => (
            <button
              key={item.session_id}
              className={`task-row ${item.session_id === sessionId ? "selected" : ""}`}
              onClick={() => {
                onClose();
                onSelectSession(item.session_id);
              }}
            >
              <i className={item.status === "active" ? "pulse" : ""} />
              <span className="task-copy">
                <b>{short(item.title || "未命名任务")}</b>
                <small>{sessionState(item)}</small>
              </span>
            </button>
          ))}
          {!visible.length && (
            <p className="empty-list">任务会保存在本机，断开后仍可恢复。</p>
          )}
        </nav>

        <div className="sidebar-foot">
          <button onClick={onOpenTaskManager}>
            <ListChecks size={15} />任务
          </button>
          <button onClick={onOpenSettings}>
            <Settings2 size={15} />设置
          </button>
          <button onClick={onOpenDiagnostics}>
            <TerminalSquare size={15} />诊断
          </button>
        </div>
      </aside>
    </>
  );
}
