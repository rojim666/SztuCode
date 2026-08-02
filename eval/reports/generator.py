"""
SztuCode 评测结果报告生成器

聚合 SWE-bench 结果 + 轨迹分析 + 工程维度指标，生成完整评测报告。

用法:
    python -m eval.reports.generator \
        --swebench-results eval/reports/swebench_results.json \
        --trajectory-report eval/reports/trajectory_report.json \
        --output eval/reports/eval_report.md
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def generate_report(
    swebench_results: dict | None = None,
    trajectory_report: dict | None = None,
    agent_version: str = "unknown",
    model_name: str = "unknown",
    dataset_name: str = "SWE-bench Lite",
) -> str:
    """生成 Markdown 评测报告"""

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# SztuCode Evaluation Report",
        "",
        f"- **评测日期**: {now}",
        f"- **Agent 版本**: {agent_version}",
        f"- **LLM 模型**: {model_name}",
        f"- **评测集**: {dataset_name}",
        "",
        "---",
        "",
    ]

    # Layer 1: SWE-bench 结果
    lines.append("## Layer 1: 标准基准结果")
    lines.append("")

    if swebench_results:
        total = swebench_results.get("total", 0)
        resolved = swebench_results.get("resolved", 0)
        failed = swebench_results.get("failed", 0)
        regression = swebench_results.get("regression", 0)
        no_patch = swebench_results.get("no_patch", 0)

        resolved_rate = (resolved / total * 100) if total > 0 else 0

        lines.extend([
            "| 指标 | 结果 |",
            "|------|------|",
            f"| Total instances | {total} |",
            f"| Resolved | {resolved} ({resolved_rate:.1f}%) |",
            f"| Fail (tests not passed) | {failed} |",
            f"| Regression (broke other tests) | {regression} |",
            f"| No Patch (agent 未生成 diff) | {no_patch} |",
            "",
        ])

        # 对标
        lines.extend([
            "### 对标",
            "",
            "| Agent | 评测集 | Resolved Rate |",
            "|-------|--------|:---:|",
            f"| **SztuCode (本项目)** | {dataset_name} | **{resolved_rate:.1f}%** |",
            "| Claude Sonnet 4.5 | SWE-bench Verified | 77.2% |",
            "| GPT-4 Turbo | SWE-bench Verified | 38.0% |",
            "| OpenHands | SWE-bench Verified | 35% |",
            "",
        ])
    else:
        lines.extend([
            "SWE-bench 结果尚未生成。请先运行 `python -m eval.swebench.adapter`。",
            "",
        ])

    lines.extend(["---", ""])

    # Layer 2: 轨迹质量
    lines.append("## Layer 2: 轨迹质量")
    lines.append("")

    if trajectory_report and "summary" in trajectory_report:
        summary = trajectory_report["summary"]

        if "path_efficiency" in summary:
            pe = summary["path_efficiency"]
            lines.extend([
                "### 路径效率",
                "",
                "| 指标 | 平均值 | 中位数 | 标准差 |",
                "|------|--------|--------|--------|",
                f"| 步数 | {pe['avg_steps']} | {pe['median_steps']} | {pe['stdev_steps']} |",
                f"| 工具调用数 | {pe['avg_tool_calls']} | - | - |",
                f"| 效率得分 | {pe['avg_efficiency_score']} | - | - |",
                "",
            ])

        if "tool_discipline" in summary:
            td = summary["tool_discipline"]
            lines.extend([
                "### 工具纪律",
                "",
                "| 指标 | 平均值 |",
                "|------|--------|",
                f"| 读后写比例 | {td['avg_read_before_write_ratio']:.1%} |",
                "",
            ])

        if "cost" in summary:
            c = summary["cost"]
            lines.extend([
                "### 成本",
                "",
                "| 指标 | 值 |",
                "|------|-----|",
                f"| 平均 Token / Task | {c['avg_tokens']:,} |",
                f"| 中位数 Token | {c['median_tokens']:,} |",
                f"| 总成本 | ${c['total_cost_usd']} |",
                f"| 平均成本 / Task | ${c['avg_cost_usd']} |",
                "",
            ])

        if "blast_radius" in summary:
            br = summary["blast_radius"]
            lines.extend([
                "### 爆炸半径",
                "",
                "| 指标 | 平均值 | 中位数 |",
                "|------|--------|--------|",
                f"| 修改文件数 | {br['avg_files_changed']} | {br['median_files_changed']} |",
                "",
            ])
    else:
        lines.extend([
            "轨迹分析结果尚未生成。请先运行 `python -m eval.trajectory.analyzer`。",
            "",
        ])

    lines.extend(["---", ""])

    # Layer 3: 工程维度
    lines.extend([
        "## Layer 3: 工程维度（SztuCode 专项）",
        "",
        "| 维度 | 指标 | 目标 | 状态 |",
        "|------|------|------|------|",
        "| Loop 鲁棒性 | max_steps 终止率 | < 20% | 待测 |",
        "| Loop 鲁棒性 | 熔断触发率 | < 5% | 待测 |",
        "| Loop 鲁棒性 | 流式重试成功率 | > 90% | 待测 |",
        "| 上下文治理 | compact 压缩比 | > 3:1 | 待测 |",
        "| 上下文治理 | 压缩后完成率差 | < 10% | 待测 |",
        "| 权限安全 | 越界拦截率 | 100% | 待测 |",
        "| 权限安全 | 误审批率 | 0% | 待测 |",
        "| 成本效率 | Token / Task | < 50K | 待测 |",
        "| 成本效率 | $ / 成功任务 | 对标同类 | 待测 |",
        "",
        "---",
        "",
    ])

    # 失败模式分析
    lines.extend([
        "## 失败模式分析",
        "",
        "根据 SWE-bench 官方研究，agent 失败主要分为以下几类：",
        "",
        "| 失败类型 | 描述 | 预估占比 | 本项目实际 |",
        "|----------|------|----------|-----------|",
        "| 错误诊断 | 修了症状没修根因 | ~25% | 待分析 |",
        "| 正确修复但位置错误 | 逻辑对但改错文件/函数 | ~15% | 待分析 |",
        "| 上下文耗尽 | context window 不够用 | ~20% | 待分析 |",
        "| 测试盲区 | 修了但破坏了其他测试 | ~10% | 待分析 |",
        "| 编辑执行错误 | edit_file old_str 不匹配 | ~10% | 待分析 |",
        "",
        "> 占比数据来源：SWE-bench trajectory 分析（engineersofai.com）",
        "",
        "---",
        "",
    ])

    # 建议
    lines.extend([
        "## 改进建议",
        "",
        "基于评测结果的改进方向（待填充）：",
        "",
        "1. **如果 Resolved Rate < 10%**：基础能力不足，优先检查 prompt 工程和工具描述质量",
        "2. **如果 max_steps 终止率 > 30%**：增加 max_steps 或优化 agent 的步数效率",
        "3. **如果盲写比例 > 30%**：在 system prompt 中强化"先读后写"规则",
        "4. **如果爆炸半径 < 70%**：在 system prompt 中强调最小化修改范围",
        "5. **如果上下文耗尽 > 20%**：调低 compact_threshold 或优化 compact 摘要质量",
        "",
        "---",
        "",
        f"*报告生成时间: {now}*",
    ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="SztuCode 评测报告生成器")
    parser.add_argument("--swebench-results", default=None, help="SWE-bench 结果 JSON")
    parser.add_argument("--trajectory-report", default=None, help="轨迹分析报告 JSON")
    parser.add_argument("--agent-version", default="sztu-code v0.1", help="Agent 版本")
    parser.add_argument("--model-name", default="claude-sonnet-4-20250514", help="模型名称")
    parser.add_argument("--dataset-name", default="SWE-bench Lite", help="评测集名称")
    parser.add_argument("--output", default="eval/reports/eval_report.md", help="输出路径")
    args = parser.parse_args()

    swebench_results = None
    if args.swebench_results and Path(args.swebench_results).exists():
        with open(args.swebench_results) as f:
            swebench_results = json.load(f)

    trajectory_report = None
    if args.trajectory_report and Path(args.trajectory_report).exists():
        with open(args.trajectory_report) as f:
            trajectory_report = json.load(f)

    report = generate_report(
        swebench_results=swebench_results,
        trajectory_report=trajectory_report,
        agent_version=args.agent_version,
        model_name=args.model_name,
        dataset_name=args.dataset_name,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")

    print(f"Report saved to: {output_path}")


if __name__ == "__main__":
    main()
