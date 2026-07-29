import { X } from "lucide-react";
import type { Diagnostics } from "../../types";

type DiagnosticsDialogProps = {
  open: boolean;
  loading: boolean;
  diagnostics: Diagnostics | null;
  onClose: () => void;
  onRetry: () => void;
};

/** 诊断对话框：Daemon 状态、版本、Git 信息 */
export function DiagnosticsDialog({
  open,
  loading,
  diagnostics,
  onClose,
  onRetry,
}: DiagnosticsDialogProps) {
  if (!open) return null;

  return (
    <section
      className="settings-drawer"
      role="dialog"
      aria-modal="true"
      aria-label="本地诊断"
    >
      <div className="settings-sheet diagnostics-sheet">
        <header>
          <div>
            <span className="eyebrow">本地运行状态</span>
            <h2>诊断</h2>
          </div>
          <button onClick={onClose} aria-label="关闭诊断">
            <X size={18} />
          </button>
        </header>

        {loading ? (
          <div className="diagnostics-empty">正在检查本地服务…</div>
        ) : diagnostics ? (
          <dl className="diagnostics-grid">
            <div>
              <dt>Daemon</dt>
              <dd><i /> 已连接</dd>
            </div>
            <div>
              <dt>版本</dt>
              <dd>{diagnostics.version}</dd>
            </div>
            <div>
              <dt>已运行</dt>
              <dd>{diagnostics.uptime}</dd>
            </div>
            <div>
              <dt>Git 分支</dt>
              <dd>{diagnostics.branch}</dd>
            </div>
            <div>
              <dt>仓库状态</dt>
              <dd>{diagnostics.repository ? "已识别" : "非 Git 仓库"}</dd>
            </div>
            <div>
              <dt>未提交变更</dt>
              <dd>{diagnostics.changes}</dd>
            </div>
          </dl>
        ) : (
          <div className="diagnostics-empty">
            无法连接本地服务。确认 daemon 已启动后重试。
          </div>
        )}

        <button className="diagnostics-retry" onClick={onRetry}>
          重新检查
        </button>
      </div>
    </section>
  );
}
