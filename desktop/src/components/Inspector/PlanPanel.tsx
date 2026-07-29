import { ListChecks } from "lucide-react";
import type { PlanItem } from "../../types";

type PlanPanelProps = {
  items: PlanItem[];
};

const statusLabel: Record<string, string> = {
  completed: "已完成",
  in_progress: "进行中",
  pending: "待开始",
};

/** 执行计划面板：展示 Agent 的计划条目与状态 */
export function PlanPanel({ items }: PlanPanelProps) {
  if (!items.length) return null;

  return (
    <section className="plan-panel">
      <header>
        <ListChecks size={15} />
        <span>执行计划</span>
      </header>
      {items.map((item) => (
        <div className={`plan-row ${item.status}`} key={item.id}>
          <i />
          <div>
            <b>{item.subject}</b>
            <small>
              {statusLabel[item.status] ?? item.status}
              {item.blocked_by.length
                ? ` · 等待 #${item.blocked_by.join("、#")}`
                : ""}
            </small>
          </div>
        </div>
      ))}
    </section>
  );
}
