import { X } from "lucide-react";
import { Fragment, useMemo } from "react";
import type { Change, DiffView, DiffRow } from "../../types";
import { splitDiff } from "../../types";

type DiffDrawerProps = {
  change: Change;
  diff: string;
  diffLoading: boolean;
  diffView: DiffView;
  revertConfirming: boolean;
  reverting: boolean;
  onChangeView: (view: DiffView) => void;
  onClose: () => void;
  onAskAgentToFix: (path: string) => void;
  onRevert: () => void;
  onConfirmRevert: () => void;
  onCancelRevert: () => void;
};

/** 代码变更审阅抽屉：对照/统一视图、撤销、让 Agent 修复 */
export function DiffDrawer({
  change,
  diff,
  diffLoading,
  diffView,
  revertConfirming,
  reverting,
  onChangeView,
  onClose,
  onAskAgentToFix,
  onRevert,
  onConfirmRevert,
  onCancelRevert,
}: DiffDrawerProps) {
  const diffRows = useMemo<DiffRow[]>(() => splitDiff(diff), [diff]);

  return (
    <section
      className="diff-drawer"
      role="dialog"
      aria-modal="true"
      aria-label={`${change.path} 的代码变更`}
    >
      {/* 头部 */}
      <header className="diff-head">
        <div>
          <span className="eyebrow">
            代码审阅{change.agent_owned ? " · 本轮 Agent 变更" : ""}
          </span>
          <h2>{change.path}</h2>
        </div>
        <div className="diff-controls">
          <button
            className={diffView === "split" ? "active" : ""}
            onClick={() => onChangeView("split")}
          >
            对照
          </button>
          <button
            className={diffView === "unified" ? "active" : ""}
            onClick={() => onChangeView("unified")}
          >
            统一
          </button>
          <button className="agent-fix" onClick={() => onAskAgentToFix(change.path)}>
            让 Agent 修复
          </button>
          {change.agent_owned && change.revertible && (
            <button className="revert-control" onClick={onRevert}>
              撤销本轮
            </button>
          )}
          <button className="diff-close" onClick={onClose} aria-label="关闭代码审阅">
            <X size={18} />
          </button>
        </div>
      </header>

      {/* 撤销确认 */}
      {revertConfirming && (
        <div className="revert-confirm">
          <div>
            <b>恢复到本轮 Agent 开始前</b>
            <span>仅恢复此文件；若文件后来被修改，系统会拒绝覆盖。</span>
          </div>
          <button onClick={onCancelRevert}>取消</button>
          <button className="danger" disabled={reverting} onClick={onConfirmRevert}>
            {reverting ? "正在恢复…" : "确认撤销"}
          </button>
        </div>
      )}

      {/* Diff 内容 */}
      {diffLoading ? (
        <div className="diff-empty">正在读取工作区差异…</div>
      ) : !diff ? (
        <div className="diff-empty">该文件没有可显示的未提交差异。</div>
      ) : diffView === "unified" ? (
        <pre className="diff-unified">
          {diff.split("\n").map((line, index) => (
            <code
              key={index}
              className={
                line.startsWith("+")
                  ? "added"
                  : line.startsWith("-")
                    ? "removed"
                    : line.startsWith("@@")
                      ? "hunk"
                      : ""
              }
            >
              {line || " "}
            </code>
          ))}
        </pre>
      ) : (
        <div className="diff-split">
          <div className="diff-pane-label">修改前</div>
          <div className="diff-pane-label">修改后</div>
          {diffRows.map((row, index) => (
            <Fragment key={index}>
              <code className={`diff-cell ${row.kind}`}>{row.old || " "}</code>
              <code className={`diff-cell ${row.kind}`}>{row.next || " "}</code>
            </Fragment>
          ))}
        </div>
      )}
    </section>
  );
}
