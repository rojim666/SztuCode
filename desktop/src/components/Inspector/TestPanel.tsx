import { ListChecks } from "lucide-react";
import type { TestResult } from "../../types";

type TestPanelProps = {
  results: TestResult[];
};

/** 验证结果面板：展示测试通过/失败状态 */
export function TestPanel({ results }: TestPanelProps) {
  if (!results.length) return null;

  const passed = results.filter((r) => r.status === "passed").length;

  return (
    <section className="test-panel">
      <header>
        <ListChecks size={15} />
        <span>验证结果</span>
        <small>{passed} 通过</small>
      </header>
      {results.map((result) => (
        <div className={`test-row ${result.status}`} key={result.tool_use_id}>
          <i />
          {result.summary}
        </div>
      ))}
    </section>
  );
}
