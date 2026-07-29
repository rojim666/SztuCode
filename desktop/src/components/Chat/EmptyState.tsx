import { ListChecks, Search } from "lucide-react";

type EmptyStateProps = {
  onSuggestion: (prompt: string) => void;
};

/** 空状态占位：引导用户发起第一个任务 */
export function EmptyState({ onSuggestion }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <div className="crosshair" />
      <h2>让 Agent 接管一段清晰的工作</h2>
      <p>
        从修复一个 Bug、审阅一组改动或实现一个小功能开始。
        每次调用、审批与变更都会留在任务时间线中。
      </p>
      <div className="starter">
        <button
          onClick={() =>
            onSuggestion("检查当前仓库，找出最值得先修复的问题并给出计划。")
          }
        >
          <Search size={14} />
          检查仓库
        </button>
        <button
          onClick={() =>
            onSuggestion("为当前项目补充缺失的测试，并说明验证方式。")
          }
        >
          <ListChecks size={14} />
          补充测试
        </button>
      </div>
    </div>
  );
}
