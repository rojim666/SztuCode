from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from sztu_code.core.config import SztuConfig
from sztu_code.core.context import ExecutionContext
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.openai_provider import OpenAIProvider
from sztu_code.core.loop import AgentLoop
from sztu_code.core.permissions.manager import PermissionManager
from sztu_code.core.permissions.policy import PermissionMode
from sztu_code.core.subagent.registry import BackgroundTaskRegistry
from sztu_code.core.subagent.tool import SpawnAgentTool
from sztu_code.core.tools.builtin.bash import BashTool
from sztu_code.core.tools.builtin.edit_file import EditFileTool
from sztu_code.core.tools.builtin.glob_search import GlobSearchTool
from sztu_code.core.tools.builtin.grep_search import GrepSearchTool
from sztu_code.core.tools.builtin.list_dir import ListDirTool
from sztu_code.core.tools.builtin.read_file import ReadFileTool
from sztu_code.core.tools.builtin.write_file import WriteFileTool
from sztu_code.core.tools.registry import ToolRegistry
from sztu_code.core.workflow.model import WorkflowResult
from sztu_code.core.workflow.scope import ScopeAuditLog
from sztu_code.core.workflow.tool import WorkflowRunTool

ROOT = Path(__file__).parents[1]
REPORT_PATH = Path(
    os.environ.get(
        "SZTU_EVAL_REPORT",
        str(Path(tempfile.gettempdir()) / "sztucode-workflow-live-report.json"),
    )
)


# 加载离线门禁使用的同一组场景与工作区辅助函数
def _load_support() -> Any:
    path = ROOT / "tests" / "integration" / "test_multi_agent_workflow_e2e.py"
    spec = importlib.util.spec_from_file_location("issue18_eval_support", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load evaluation support: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# 对任何动态审批请求自动拒绝，确保在线模型不能扩大固定场景范围
def _permission_manager(bus: EventBus) -> PermissionManager:
    manager = PermissionManager(mode=PermissionMode.ACCEPT_EDITS)

    # 收到 ASK 事件立即拒绝；范围内编辑和只读测试仍按策略自动放行
    async def deny_request(event: BaseModel) -> None:
        if event.model_dump().get("type") == "permission.requested":
            manager.respond(str(event.model_dump().get("tool_use_id")), "deny_once")

    bus.subscribe(deny_request)
    return manager


# 构建允许读、定向写和测试的单 Agent 工具集
def _single_registry(
    root: Path,
    paths: list[str],
    audit: ScopeAuditLog,
) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in (
        ReadFileTool(root),
        WriteFileTool(root, paths, audit),
        EditFileTool(root, paths, audit),
        ListDirTool(root),
        GrepSearchTool(root),
        GlobSearchTool(root),
        BashTool(root),
    ):
        registry.register(tool)
    return registry


# 使用真实 DeepSeek provider 运行同任务的单 Agent 基线
async def _run_single(
    support: Any,
    provider: OpenAIProvider,
    root: Path,
    scenario: Any,
    trace_path: Path,
) -> dict[str, Any]:
    before = support._module_snapshot(root, scenario)
    capture = support._TraceCapture(trace_path)
    await capture.start()
    paths = support._changed_paths(scenario)
    audit = ScopeAuditLog()
    manager = _permission_manager(capture.bus)
    context = ExecutionContext(
        run_id=f"live-single-{scenario.id}",
        goal=(
            f"Implement this task: {scenario.goal}\n"
            f"Only modify these assigned files: {json.dumps(paths, ensure_ascii=False)}\n"
            f"Read tests in {scenario.test_path}, use read/edit/write file tools, and run "
            f"exactly `{scenario.test_command}` until it passes. Do not modify tests or other files."
        ),
        max_steps=20,
        max_tokens=200_000,
        max_wall_clock_s=300,
    )
    loop = AgentLoop(
        provider,
        _single_registry(root, paths, audit),
        capture.bus,
        permission_manager=manager,
        wrap_up_on_max_steps=False,
        grace_step_on_max_steps=True,
    )
    try:
        await loop.run(context)
    finally:
        await capture.stop()
    final_test = await support._run_scenario_test(root, scenario)
    files = support._module_snapshot(root, scenario)
    expected = {change.path: change.after for change in scenario.changes}
    changed_paths = sorted(path for path in files if files[path] != before[path])
    return {
        "status": context.status,
        "reason": str(context.reason or ""),
        "tests_passed": not final_test.is_error,
        "changed_paths": changed_paths,
        "modules_match_expected": files == expected,
        "scope_escalations": audit.paths,
        "tokens": context.total_tokens(),
        "elapsed_s": round(context.elapsed_s(), 3),
        "trace_events": len(support._event_payloads(capture.records())),
    }


# 使用生产 WorkflowRunTool 运行真实 Planner→Coder→Tester→Reviewer 链
async def _run_workflow(
    support: Any,
    provider: OpenAIProvider,
    root: Path,
    scenario: Any,
    trace_path: Path,
) -> dict[str, Any]:
    before = support._module_snapshot(root, scenario)
    capture = support._TraceCapture(trace_path)
    await capture.start()
    manager = _permission_manager(capture.bus)
    config = SztuConfig()
    config.workflow.max_retries = 1
    config.budget.max_tokens = 500_000
    config.budget.max_wall_clock_s = 600
    spawn_tool = SpawnAgentTool(
        provider=provider,
        parent_bus=capture.bus,
        parent_run_id=f"live-parent-{scenario.id}",
        permission_manager=manager,
        max_steps=20,
        task_registry=BackgroundTaskRegistry(),
        runs_dir=root / ".runs",
        session_id=f"live-eval-{scenario.id}",
        workspace_root=root,
        budget=config.budget,
        wrap_up_on_max_steps=False,
        grace_step_on_max_steps=True,
        max_depth=config.workflow.max_depth,
    )
    tool = WorkflowRunTool(
        spawn_tool,
        capture.bus,
        f"live-parent-{scenario.id}",
        root,
        config,
    )
    try:
        raw = await tool.invoke(
            {
                "goal": (
                    f"{scenario.goal}. Read {scenario.test_path}; Coder may only modify the "
                    f"two assigned files. Tester and Reviewer must run exactly "
                    f"`{scenario.test_command}`."
                ),
                "allowed_paths": support._changed_paths(scenario),
                "completion_criteria": [
                    "两个分配模块达到测试定义的目标状态",
                    f"独立 Tester 执行 {scenario.test_command} 并通过",
                    "Reviewer 基于实际文件、测试和范围审计接受交付",
                ],
            }
        )
    finally:
        await capture.stop()
    result = None
    try:
        result = WorkflowResult.model_validate_json(raw.content)
    except ValueError:
        pass
    final_test = await support._run_scenario_test(root, scenario)
    files = support._module_snapshot(root, scenario)
    expected = {change.path: change.after for change in scenario.changes}
    changed_paths = sorted(path for path in files if files[path] != before[path])
    events = support._event_payloads(capture.records())
    artifacts = [
        state.artifact
        for state in result.tasks
        if result is not None and state.artifact is not None
    ] if result is not None else []
    tester = next((item for item in artifacts if item.role == "tester"), None)
    reviewer = next((item for item in artifacts if item.role == "reviewer"), None)
    return {
        "status": result.status if result is not None else "invalid_result",
        "reason": result.reason if result is not None else raw.content[:500],
        "tests_passed": not final_test.is_error,
        "changed_paths": changed_paths,
        "modules_match_expected": files == expected,
        "independent_tester": bool(
            tester and tester.commands and tester.output and tester.conclusion
        ),
        "reviewer_accepted": bool(reviewer and reviewer.review_decision == "accept"),
        "trace_handoffs": sum(
            event.get("type") == "workflow.handoff" for event in events
        ),
        "trace_reviews": sum(
            event.get("type") == "workflow.reviewed" for event in events
        ),
        "tokens": result.total_tokens if result is not None else 0,
        "elapsed_s": round(result.elapsed_s, 3) if result is not None else 0.0,
        "tool_error": raw.is_error,
        "tasks": (
            [
                {
                    "id": state.task.id,
                    "owner": state.task.owner,
                    "status": state.status,
                    "error": state.error,
                    "dependencies": state.task.dependencies,
                }
                for state in result.tasks
            ]
            if result is not None
            else []
        ),
    }


# 顺序执行五个在线场景并写出不含密钥和原始提示的汇总报告
async def main() -> None:
    support = _load_support()
    scenarios = support._scenarios()
    selected = os.environ.get("SZTU_EVAL_SCENARIO", "").strip()
    if selected:
        selected_ids = {item.strip() for item in selected.split(",") if item.strip()}
        scenarios = [scenario for scenario in scenarios if scenario.id in selected_ids]
        if not scenarios:
            raise ValueError(f"unknown scenario: {selected}")
    provider = OpenAIProvider("deepseek-v4-flash", context_window=1_000_000)
    report: dict[str, Any] = {
        "model": "deepseek-v4-flash",
        "base_url": "https://api.deepseek.com",
        "run_at": datetime.now(UTC).isoformat(),
        "scenarios": [],
    }
    with tempfile.TemporaryDirectory(prefix="sztucode-workflow-live-") as raw:
        temp_root = Path(raw)
        for index, scenario in enumerate(scenarios, 1):
            print(f"[{index}/{len(scenarios)}] {scenario.id}: single Agent", flush=True)
            single_root = temp_root / scenario.id / "single"
            support._seed_workspace(single_root, scenario)
            single_red = await support._run_scenario_test(single_root, scenario)
            single = await _run_single(
                support,
                provider,
                single_root,
                scenario,
                temp_root / scenario.id / "single-trace.jsonl",
            )
            print(f"[{index}/{len(scenarios)}] {scenario.id}: workflow", flush=True)
            workflow_root = temp_root / scenario.id / "workflow"
            support._seed_workspace(workflow_root, scenario)
            workflow_red = await support._run_scenario_test(workflow_root, scenario)
            workflow = await _run_workflow(
                support,
                provider,
                workflow_root,
                scenario,
                temp_root / scenario.id / "workflow-trace.jsonl",
            )
            report["scenarios"].append(
                {
                    "id": scenario.id,
                    "initial_tests_failed": single_red.is_error and workflow_red.is_error,
                    "single_agent": single,
                    "multi_agent": workflow,
                }
            )
            REPORT_PATH.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    print(f"report={REPORT_PATH}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
