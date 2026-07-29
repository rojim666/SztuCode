import { ArrowUp, ShieldCheck } from "lucide-react";
import type { FormEvent, RefObject } from "react";
import type { Workspace } from "../../types";
import { modeLabel } from "../../types";

type ComposerProps = {
  prompt: string;
  workspace: Workspace | null;
  mode: string;
  composerRef: React.RefObject<HTMLTextAreaElement>;
  onChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onToggleMode: () => void;
};

/** 任务输入框（Composer）：文本区 + 模式切换 + 发送按钮 */
export function Composer({
  prompt,
  workspace,
  mode,
  composerRef,
  onChange,
  onSubmit,
  onToggleMode,
}: ComposerProps) {
  return (
    <form className="composer" onSubmit={onSubmit}>
      <textarea
        ref={composerRef}
        value={prompt}
        onChange={(event) => onChange(event.target.value)}
        placeholder={
          workspace
            ? "描述要在这个工作区完成的任务…"
            : "先选择一个本地工作区…"
        }
        rows={3}
      />
      <div className="composer-bar">
        <span>
          <kbd>Ctrl ↵</kbd> 发送<span className="dot">·</span>
          <kbd>/</kbd> 命令
        </span>
        <button type="button" className="mode-select" onClick={onToggleMode}>
          {modeLabel(mode)}
        </button>
        <button className="send" type="submit" aria-label="发送任务">
          <ArrowUp size={17} />
        </button>
      </div>
    </form>
  );
}
