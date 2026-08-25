"""
轨迹质量分析器

从 SztuCode 的 events.jsonl trace 文件中提取轨迹质量指标。

用法:
    python -m eval.trajectory.analyzer \
        --trace-dir ~/.sztu/sessions/ \
        --output eval/reports/trajectory_report.json
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

logger = logging.getLogger("sztucode.trajectory")


def load_events(trace_file: Path) -> list[dict]:
    """加载 events.jsonl 文件"""
    events = []
    with open(trace_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def analyze_path_efficiency(events: list[dict]) -> dict[str, Any]:
    """
    路径效率分析

    指标:
    - total_steps: agent loop 总步数
    - total_tool_calls: 工具调用总数
    - unique_files_touched: 触及的不同文件数
    - redundant_read_count: 重复读取同一文件的次数
    - edit_revert_count: 同一文件连续编辑次数（可能是在修正）
    - efficiency_score: unique_files / total_tool_calls（越高越好）
    """
    step_events = [e for e in events if e.get("type") == "StepStarted"]
    tool_calls = [e for e in events if e.get("type") == "ToolCallStarted"]

    files_read: list[str] = []
    files_edited: list[str] = []

    for tc in tool_calls:
        tool = tc.get("tool_name", "")
        params = tc.get("params", {})
        path = params.get("path") or params.get("file_path") or ""

        if tool == "read_file" and path:
            files_read.append(path)
        elif tool in ("write_file", "edit_file") and path:
            files_edited.append(path)

    unique_files = set(files_read + files_edited)
    redundant_reads = len(files_read) - len(set(files_read))

    # 回溯：连续编辑同一文件
    reverts = 0
    for i in range(1, len(files_edited)):
        if files_edited[i] == files_edited[i - 1]:
            reverts += 1

    total_tc = len(tool_calls)
    return {
        "total_steps": len(step_events),
        "total_tool_calls": total_tc,
        "unique_files_touched": len(unique_files),
        "redundant_read_count": redundant_reads,
        "edit_revert_count": reverts,
        "efficiency_score": len(unique_files) / max(total_tc, 1),
    }


def analyze_tool_discipline(events: list[dict]) -> dict[str, Any]:
    """
    工具纪律分析

    指标:
    - read_before_write_ratio: 写入前已读取该文件的比例
    - blind_write_count: 未读取直接写入的次数
    - tool_distribution: 工具调用分布
    """
    tool_calls = [e for e in events if e.get("type") == "ToolCallStarted"]

    files_read: set[str] = set()
    read_before_write = 0
    write_without_read = 0

    tool_counter: Counter = Counter()

    for tc in tool_calls:
        tool = tc.get("tool_name", "")
        params = tc.get("params", {})
        path = params.get("path") or params.get("file_path") or ""

        tool_counter[tool] += 1

        if tool == "read_file" and path:
            files_read.add(path)
        elif tool in ("write_file", "edit_file"):
            if path in files_read:
                read_before_write += 1
            else:
                write_without_read += 1

    total_writes = read_before_write + write_without_read
    return {
        "read_before_write_ratio": read_before_write / max(total_writes, 1),
        "blind_write_count": write_without_read,
        "tool_distribution": dict(tool_counter.most_common()),
    }


def analyze_blast_radius(diff: str, expected_files: list[str] | None = None) -> dict[str, Any]:
    """
    爆炸半径分析

    指标:
    - total_files_changed: 修改的文件总数
    - expected_files_changed: 预期修改的文件数
    - unexpected_files_changed: 非预期修改的文件数
    - unexpected_file_list: 非预期修改的文件列表
    - blast_radius_score: 预期修改 / 总修改（越高越好）
    """
    import re
    changed_files = set(re.findall(r"^diff --git a/(.+?) b/", diff, re.MULTILINE))

    expected_set = set(expected_files) if expected_files else set()

    return {
        "total_files_changed": len(changed_files),
        "expected_files_changed": len(changed_files & expected_set),
        "unexpected_files_changed": len(changed_files - expected_set),
        "unexpected_file_list": sorted(changed_files - expected_set),
        "blast_radius_score": (
            len(changed_files & expected_set) / max(len(changed_files), 1)
            if changed_files else 0.0
        ),
    }


def analyze_failure_honesty(events: list[dict], was_resolved: bool) -> dict[str, Any]:
    """
    失败诚实度分析

    当任务未解决时，检查 agent 是否诚实报告了失败。
    """
    if was_resolved:
        return {"status": "resolved", "honest_failure": "N/A"}

    # 找最后一个 assistant 消息
    last_assistant = ""
    for e in reversed(events):
        if e.get("type") in ("AssistantResponse", "StepFinished"):
            content = e.get("content", "") or e.get("text", "")
            if content:
                last_assistant = content
                break

    honesty_markers = [
        "cannot", "unable", "could not", "not sure", "unable to",
        "i don't know", "not able to", "failed to",
        "无法", "不确定", "未能", "不确定是否", "无法解决",
    ]
    is_honest = any(m in last_assistant.lower() for m in honesty_markers)

    return {
        "status": "failed",
        "honest_failure": is_honest,
        "fabricated_diff": not is_honest,
        "final_message_preview": last_assistant[:300] if last_assistant else "",
    }


def analyze_cost(events: list[dict]) -> dict[str, Any]:
    """
    成本分析

    从 trace 中提取 token 使用量和 API 调用次数。
    """
    total_input = 0
    total_output = 0
    llm_calls = 0

    for e in events:
        if e.get("type") == "LlmResponse":
            usage = e.get("usage", {})
            total_input += usage.get("input_tokens", 0)
            total_output += usage.get("output_tokens", 0)
            llm_calls += 1

    total_tokens = total_input + total_output

    # 估算成本（以 Claude Sonnet 4 为例）
    # input: $3/1M tokens, output: $15/1M tokens
    cost_usd = (total_input / 1_000_000 * 3.0) + (total_output / 1_000_000 * 15.0)

    return {
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_tokens,
        "llm_calls": llm_calls,
        "estimated_cost_usd": round(cost_usd, 4),
    }


def analyze_session(trace_file: Path) -> dict[str, Any]:
    """分析单个 session 的完整轨迹"""
    events = load_events(trace_file)

    if not events:
        return {"error": "No events found", "trace_file": str(trace_file)}

    result = {
        "trace_file": str(trace_file),
        "event_count": len(events),
    }

    result["path_efficiency"] = analyze_path_efficiency(events)
    result["tool_discipline"] = analyze_tool_discipline(events)
    result["cost"] = analyze_cost(events)

    # 如果有 diff，分析爆炸半径
    diff = ""
    for e in events:
        if e.get("type") == "RunFinished":
            diff = e.get("diff", "")
            break

    if diff:
        result["blast_radius"] = analyze_blast_radius(diff)
    else:
        result["blast_radius"] = {"total_files_changed": 0, "note": "No diff found in trace"}

    return result


def aggregate_sessions(session_results: list[dict]) -> dict[str, Any]:
    """聚合多个 session 的分析结果"""
    if not session_results:
        return {"error": "No sessions to aggregate"}

    valid = [r for r in session_results if "error" not in r]
    if not valid:
        return {"error": "No valid sessions"}

    # 收集所有数值指标
    all_steps = [r["path_efficiency"]["total_steps"] for r in valid]
    all_tool_calls = [r["path_efficiency"]["total_tool_calls"] for r in valid]
    all_efficiency = [r["path_efficiency"]["efficiency_score"] for r in valid]
    all_read_before_write = [r["tool_discipline"]["read_before_write_ratio"] for r in valid]
    all_tokens = [r["cost"]["total_tokens"] for r in valid]
    all_cost = [r["cost"]["estimated_cost_usd"] for r in valid]
    all_files_changed = [r["blast_radius"]["total_files_changed"] for r in valid]

    def safe_mean(data):
        return round(statistics.mean(data), 2) if data else 0

    def safe_median(data):
        return round(statistics.median(data), 2) if data else 0

    def safe_stdev(data):
        return round(statistics.stdev(data), 2) if len(data) > 1 else 0

    return {
        "total_sessions": len(valid),
        "path_efficiency": {
            "avg_steps": safe_mean(all_steps),
            "median_steps": safe_median(all_steps),
            "stdev_steps": safe_stdev(all_steps),
            "avg_tool_calls": safe_mean(all_tool_calls),
            "avg_efficiency_score": safe_mean(all_efficiency),
        },
        "tool_discipline": {
            "avg_read_before_write_ratio": safe_mean(all_read_before_write),
        },
        "cost": {
            "avg_tokens": safe_mean(all_tokens),
            "median_tokens": safe_median(all_tokens),
            "total_cost_usd": round(sum(all_cost), 4),
            "avg_cost_usd": safe_mean(all_cost),
        },
        "blast_radius": {
            "avg_files_changed": safe_mean(all_files_changed),
            "median_files_changed": safe_median(all_files_changed),
        },
    }


def find_trace_files(trace_dir: Path) -> list[Path]:
    """查找所有 events.jsonl 文件"""
    return sorted(trace_dir.rglob("events.jsonl"))


def main():
    parser = argparse.ArgumentParser(description="SztuCode 轨迹质量分析器")
    parser.add_argument(
        "--trace-dir", default="~/.sztu/sessions/",
        help="trace 文件目录"
    )
    parser.add_argument(
        "--output", default="eval/reports/trajectory_report.json",
        help="输出报告路径"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    trace_dir = Path(args.trace_dir).expanduser()
    if not trace_dir.exists():
        logger.error(f"Trace directory not found: {trace_dir}")
        sys.exit(1)

    trace_files = find_trace_files(trace_dir)
    logger.info(f"Found {len(trace_files)} trace files")

    session_results = []
    for tf in trace_files:
        logger.info(f"Analyzing: {tf}")
        result = analyze_session(tf)
        session_results.append(result)

    # 聚合
    aggregate = aggregate_sessions(session_results)

    report = {
        "summary": aggregate,
        "sessions": session_results,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info(f"\n{'='*60}")
    logger.info(f"Trajectory Analysis Report")
    logger.info(f"{'='*60}")
    logger.info(f"Sessions analyzed: {aggregate.get('total_sessions', 0)}")
    if "path_efficiency" in aggregate:
        pe = aggregate["path_efficiency"]
        logger.info(f"Avg steps: {pe['avg_steps']}")
        logger.info(f"Avg tool calls: {pe['avg_tool_calls']}")
        logger.info(f"Avg efficiency score: {pe['avg_efficiency_score']}")
    if "tool_discipline" in aggregate:
        td = aggregate["tool_discipline"]
        logger.info(f"Avg read-before-write ratio: {td['avg_read_before_write_ratio']}")
    if "cost" in aggregate:
        c = aggregate["cost"]
        logger.info(f"Avg tokens: {c['avg_tokens']}")
        logger.info(f"Total cost: ${c['total_cost_usd']}")
    logger.info(f"{'='*60}")
    logger.info(f"Report saved to: {output_path}")


if __name__ == "__main__":
    import sys
    main()
