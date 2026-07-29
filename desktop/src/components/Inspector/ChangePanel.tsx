import { FileCode2 } from "lucide-react";
import type { Change } from "../../types";

type ChangePanelProps = {
  changes: Change[];
  onOpenDiff: (change: Change) => void;
  onRefresh: () => void;
};

/** 变更面板：展示未提交的变更列表 */
export function ChangePanel({ changes, onOpenDiff, onRefresh }: ChangePanelProps) {
  return (
    <section className="change-panel">
      <header>
        <FileCode2 size={15} />
        <span>变更</span>
        <button onClick={onRefresh}>刷新</button>
      </header>
      {changes.length ? (
        changes.map((change) => (
          <button
            className="change-row"
            key={change.path}
            onClick={() => onOpenDiff(change)}
          >
            <i className={change.worktree_status === "?" ? "add" : "modify"} />
            <span>{change.path}</span>
            <small>
              {change.index_status}
              {change.worktree_status}
            </small>
          </button>
        ))
      ) : (
        <p>工作区干净。完成任务后，文件改动会显示在这里。</p>
      )}
    </section>
  );
}
