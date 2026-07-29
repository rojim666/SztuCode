import { Pin, X } from "lucide-react";
import type { Session } from "../../types";

type TaskManagerDialogProps = {
  open: boolean;
  session: Session | undefined;
  titleDraft: string;
  managing: boolean;
  onClose: () => void;
  onTitleChange: (value: string) => void;
  onRename: () => void;
  onTogglePin: () => void;
  onArchive: () => void;
};

/** 任务管理对话框：重命名、固定/取消固定、归档 */
export function TaskManagerDialog({
  open,
  session,
  titleDraft,
  managing,
  onClose,
  onTitleChange,
  onRename,
  onTogglePin,
  onArchive,
}: TaskManagerDialogProps) {
  if (!open) return null;

  const isPinned = session?.pinned ?? false;

  return (
    <section
      className="settings-drawer"
      role="dialog"
      aria-modal="true"
      aria-label="任务管理"
    >
      <div className="settings-sheet task-manager-sheet">
        <header>
          <div>
            <span className="eyebrow">当前任务</span>
            <h2>任务管理</h2>
          </div>
          <button onClick={onClose} aria-label="关闭任务管理">
            <X size={18} />
          </button>
        </header>

        <p>任务的消息、计划、变更记录与运行回放会继续保留在本机。</p>

        {/* 重命名 */}
        <label className="task-title-editor">
          <span>任务名称</span>
          <input
            value={titleDraft}
            onChange={(event) => onTitleChange(event.target.value)}
            placeholder="为这段工作命名"
          />
          <button
            disabled={managing || !titleDraft.trim()}
            onClick={onRename}
          >
            {managing ? "保存中…" : "保存名称"}
          </button>
        </label>

        {/* 固定 */}
        <div className="task-pin">
          <div>
            <b>{isPinned ? "已固定任务" : "固定任务"}</b>
            <span>
              {isPinned
                ? "它会显示在侧栏顶部，并优先于最近任务。"
                : "将这项工作保留在侧栏顶部，方便长期跟进。"}
            </span>
          </div>
          <button disabled={managing} onClick={onTogglePin}>
            <Pin size={13} />
            {isPinned ? "取消固定" : "固定"}
          </button>
        </div>

        {/* 归档 */}
        <div className="task-archive">
          <div>
            <b>归档任务</b>
            <span>从最近任务列表移除，不删除任何记录。</span>
          </div>
          <button disabled={managing} onClick={onArchive}>
            归档
          </button>
        </div>
      </div>
    </section>
  );
}
