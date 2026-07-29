import { ChevronRight, FolderOpen, GitBranch, Menu } from "lucide-react";
import type { ConnectionState, Workspace } from "../../types";

type TopBarProps = {
  connection: ConnectionState;
  workspace: Workspace | null;
  onOpenSidebar: () => void;
};

const connectionLabel: Record<ConnectionState, string> = {
  connecting: "连接中",
  ready: "已连接",
  offline: "离线",
};

/** 顶部导航栏：品牌、路径面包屑、连接状态、移动端菜单按钮 */
export function TopBar({ connection, workspace, onOpenSidebar }: TopBarProps) {
  return (
    <header className="topbar" data-tauri-drag-region>
      <div className="brand">
        <span className="brand-mark">S</span>
        <span>SztuCode</span>
        <span className="brand-sub">LOCAL AGENT WORKBENCH</span>
      </div>

      <div className="crumb">
        <FolderOpen size={14} />
        <span>{workspace?.name ?? "尚未选择工作区"}</span>
        {workspace && (
          <>
            <ChevronRight size={14} />
            <GitBranch size={14} />
            <span>本地工作区</span>
          </>
        )}
      </div>

      <div className={`connection ${connection}`}>
        <i />
        {connectionLabel[connection]}
      </div>

      <button
        className="mobile-nav"
        onClick={onOpenSidebar}
        aria-label="打开任务栏"
      >
        <Menu size={18} />
      </button>
    </header>
  );
}
