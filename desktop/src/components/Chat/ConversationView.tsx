import { ShieldCheck, WandSparkles } from "lucide-react";
import type { FormEvent } from "react";
import type { ConnectionState, Session, TimelineItem, Workspace } from "../../types";
import { modeLabel } from "../../types";
import { Composer } from "./Composer";
import { Timeline } from "./Timeline";

type ConversationViewProps = {
  activeSession: Session | undefined;
  connection: ConnectionState;
  daemonStarting: boolean;
  notice: string;
  timeline: TimelineItem[];
  prompt: string;
  workspace: Workspace | null;
  mode: string;
  composerRef: React.RefObject<HTMLTextAreaElement>;
  onSuggestion: (prompt: string) => void;
  onPromptChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onToggleMode: () => void;
  onOpenSettings: () => void;
  onStartDaemon: () => void;
};

/** 对话主区域：头部、通知栏、时间线、输入框 */
export function ConversationView({
  activeSession,
  connection,
  daemonStarting,
  notice,
  timeline,
  prompt,
  workspace,
  mode,
  composerRef,
  onSuggestion,
  onPromptChange,
  onSubmit,
  onToggleMode,
  onOpenSettings,
  onStartDaemon,
}: ConversationViewProps) {
  return (
    <section className="conversation">
      {/* 头部 */}
      <div className="conversation-head">
        <div>
          <span className="eyebrow">
            {activeSession ? "当前任务" : "开始工作"}
          </span>
          <h1>
            {activeSession?.title || "选择工作区，发起第一个任务"}
          </h1>
        </div>
        <button className="mode" onClick={onOpenSettings}>
          <ShieldCheck size={15} />
          {modeLabel(mode)}
        </button>
      </div>

      {/* 通知栏 */}
      <div className="notice">
        <WandSparkles size={16} />
        <span>{notice}</span>
        {connection === "offline" && (
          <button
            className="start-daemon"
            disabled={daemonStarting}
            onClick={onStartDaemon}
          >
            {daemonStarting ? "启动中…" : "启动本地服务"}
          </button>
        )}
      </div>

      {/* 时间线 */}
      <Timeline items={timeline} onSuggestion={onSuggestion} />

      {/* 输入框 */}
      <Composer
        prompt={prompt}
        workspace={workspace}
        mode={mode}
        composerRef={composerRef}
        onChange={onPromptChange}
        onSubmit={onSubmit}
        onToggleMode={onToggleMode}
      />
    </section>
  );
}
