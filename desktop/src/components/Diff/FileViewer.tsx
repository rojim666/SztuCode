import { X } from "lucide-react";
import type { FileNode } from "../../types";

type FileViewerProps = {
  file: FileNode;
  content: string;
  loading: boolean;
  onClose: () => void;
  onAskAgentToFix: (path: string) => void;
};

/** 文件查看抽屉：显示文件内容 + 让 Agent 修复按钮 */
export function FileViewer({ file, content, loading, onClose, onAskAgentToFix }: FileViewerProps) {
  return (
    <section
      className="file-drawer"
      role="dialog"
      aria-modal="true"
      aria-label={`${file.path} 的文件内容`}
    >
      <header className="diff-head">
        <div>
          <span className="eyebrow">文件查看</span>
          <h2>{file.path}</h2>
        </div>
        <div className="diff-controls">
          <button className="agent-fix" onClick={() => onAskAgentToFix(file.path)}>
            让 Agent 修复
          </button>
          <button className="diff-close" onClick={onClose} aria-label="关闭文件查看">
            <X size={18} />
          </button>
        </div>
      </header>
      {loading ? (
        <div className="diff-empty">正在读取文件…</div>
      ) : (
        <pre className="file-content">{content}</pre>
      )}
    </section>
  );
}
