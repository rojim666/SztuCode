import { Activity, ChevronRight, CircleStop, PanelRightClose } from "lucide-react";
import type { Change, FileNode, PlanItem, TestResult } from "../../types";
import { ChangePanel } from "./ChangePanel";
import { FilePanel } from "./FilePanel";
import { PlanPanel } from "./PlanPanel";
import { TestPanel } from "./TestPanel";

type InspectorPanelProps = {
  rightOpen: boolean;
  mobileInspectorOpen: boolean;
  changes: Change[];
  treeNodes: FileNode[];
  planItems: PlanItem[];
  testResults: TestResult[];
  activeRunId: string | null;
  timelineHasTools: boolean;
  onClose: () => void;
  onMobileClose: () => void;
  onMobileOpen: () => void;
  onOpenDiff: (change: Change) => void;
  onOpenFile: (node: FileNode) => void;
  onRefreshChanges: () => void;
  onRefreshTree: () => void;
  onCancelRun: () => void;
};

/** 右侧检查器面板：变更、计划、测试、文件树、运行状态 */
export function InspectorPanel({
  rightOpen,
  mobileInspectorOpen,
  changes,
  treeNodes,
  planItems,
  testResults,
  activeRunId,
  timelineHasTools,
  onClose,
  onMobileClose,
  onMobileOpen,
  onOpenDiff,
  onOpenFile,
  onRefreshChanges,
  onRefreshTree,
  onCancelRun,
}: InspectorPanelProps) {
  const completed = planItems.filter((i) => i.status === "completed").length;

  if (!rightOpen) {
    return (
      <button
        className="open-inspector"
        onClick={onClose}
      >
        变更 <ChevronRight size={15} />
      </button>
    );
  }

  return (
    <>
      <aside className={`inspector ${mobileInspectorOpen ? "mobile-visible" : ""}`}>
        {/* 头部 */}
        <div className="inspector-head">
          <div>
            <span className="eyebrow">工作区状态</span>
            <h2>变更与验证</h2>
          </div>
          <button onClick={onMobileClose} aria-label="收起检查器">
            <PanelRightClose size={17} />
          </button>
        </div>

        {/* 统计 */}
        <section className="stat-row">
          <div>
            <span>未提交变更</span>
            <b>{changes.length}</b>
          </div>
          <div>
            <span>计划进度</span>
            <b>
              {completed}/{planItems.length || "—"}
            </b>
          </div>
        </section>

        {/* 文件树 */}
        <FilePanel nodes={treeNodes} onOpenFile={onOpenFile} onRefresh={onRefreshTree} />

        {/* 执行计划 */}
        <PlanPanel items={planItems} />

        {/* 测试结果 */}
        <TestPanel results={testResults} />

        {/* 变更列表 */}
        <ChangePanel changes={changes} onOpenDiff={onOpenDiff} onRefresh={onRefreshChanges} />

        {/* 运行卡片 */}
        <button
          className={`run-card ${activeRunId ? "can-stop" : ""}`}
          onClick={onCancelRun}
          disabled={!activeRunId}
        >
          <Activity size={16} />
          <div>
            <b>{activeRunId ? "正在运行" : "运行记录"}</b>
            <span>
              {activeRunId
                ? "点击停止当前运行"
                : timelineHasTools
                  ? "工具活动已记录在时间线"
                  : "等待任务开始"}
            </span>
          </div>
          <CircleStop size={16} />
        </button>
      </aside>

      {/* 移动端触发按钮 */}
      {!mobileInspectorOpen && (
        <button className="mobile-inspector-trigger" onClick={onMobileOpen}>
          变更 <ChevronRight size={15} />
        </button>
      )}
    </>
  );
}
