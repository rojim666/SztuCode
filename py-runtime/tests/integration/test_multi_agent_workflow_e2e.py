from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field

from sztu_code.core.config import SztuConfig
from sztu_code.core.context import ExecutionContext
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import LlmResponse, ToolCallBlock
from sztu_code.core.loop import AgentLoop
from sztu_code.core.permissions.manager import PermissionManager
from sztu_code.core.permissions.policy import PermissionMode
from sztu_code.core.subagent.registry import BackgroundTaskRegistry
from sztu_code.core.subagent.tool import SpawnAgentTool
from sztu_code.core.tools.base import ToolResult
from sztu_code.core.tools.builtin.bash import BashTool
from sztu_code.core.tools.builtin.edit_file import EditFileTool
from sztu_code.core.tools.builtin.read_file import ReadFileTool
from sztu_code.core.tools.registry import ToolRegistry
from sztu_code.core.trace.record import TraceRecord
from sztu_code.core.trace.writer import TraceWriter
from sztu_code.core.workflow.evaluation import compare_with_single_agent
from sztu_code.core.workflow.model import SingleAgentBaseline, WorkflowResult
from sztu_code.core.workflow.scope import ScopeAuditLog
from sztu_code.core.workflow.tool import WorkflowRunTool

_SCENARIO_PATH = Path(__file__).parents[2] / "eval" / "workflow" / "scenarios.json"


class _ScenarioChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    before: str
    after: str


class _Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    goal: str
    changes: list[_ScenarioChange] = Field(min_length=2, max_length=2)
    test_path: str
    test_content: str
    test_command: str


@dataclass(frozen=True)
class _ObservedToolResult:
    content: str
    is_error: bool


@dataclass
class _SingleAgentEvidence:
    baseline: SingleAgentBaseline
    status: str
    files: dict[str, str]
    trace: list[dict[str, Any]]
    scope_escalations: list[str]


class _TraceCapture:
    # 初始化与生产环境相同的 EventBus → TraceWriter 事件落盘链
    def __init__(self, path: Path) -> None:
        self.bus = EventBus()
        self._path = path
        self._writer = TraceWriter(path)
        self.bus.subscribe(self._handle)

    # 启动异步 JSONL Trace 写入器
    async def start(self) -> None:
        await self._writer.start()

    # 把总线事件包装为统一 TraceRecord，保持与 CoreApp 的处理方式一致
    async def _handle(self, event: BaseModel) -> None:
        data = event.model_dump()
        self._writer.emit(
            TraceRecord(
                ts=datetime.now(UTC).isoformat(),
                direction="CORE",
                layer="event",
                kind="event",
                run_id=data.get("run_id"),
                data=data,
            )
        )

    # 等待所有事件刷盘并关闭后台写入任务
    async def stop(self) -> None:
        await self._writer.stop()

    # 解析已落盘的 JSONL，供端到端断言检查真实 Trace
    def records(self) -> list[dict[str, Any]]:
        return [
            json.loads(line)
            for line in self._path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


# 加载并严格校验五个固定跨模块任务定义
def _scenarios() -> list[_Scenario]:
    value = json.loads(_SCENARIO_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, list)
    scenarios = [_Scenario.model_validate(item) for item in value]
    assert len(scenarios) >= 5
    return scenarios


# 返回场景中由 Agent 负责修改的两个模块路径
def _changed_paths(scenario: _Scenario) -> list[str]:
    return [change.path for change in scenario.changes]


# 从 Agent 上下文中提取首次用户目标，作为确定性 provider 的角色路由依据
def _initial_goal(messages: list[dict[str, object]]) -> str:
    for message in messages:
        content = message.get("content")
        if message.get("role") == "user" and isinstance(content, str):
            return content
    return ""


# 收集真实工具调用返回给 Agent 的结果，保留失败标志供角色独立判断
def _tool_results(
    messages: list[dict[str, object]],
) -> dict[str, _ObservedToolResult]:
    results: dict[str, _ObservedToolResult] = {}
    for message in messages:
        content = message.get("content")
        if message.get("role") != "user" or not isinstance(content, list):
            continue
        for raw_block in content:
            if not isinstance(raw_block, dict) or raw_block.get("type") != "tool_result":
                continue
            tool_use_id = str(raw_block.get("tool_use_id", ""))
            results[tool_use_id] = _ObservedToolResult(
                content=str(raw_block.get("content", "")),
                is_error=bool(raw_block.get("is_error", False)),
            )
    return results


# 解析工作流角色提示中的结构化任务与依赖证据
def _delegation_context(goal: str) -> dict[str, Any]:
    marker = "Context: "
    if marker not in goal or "\nRole rule:" not in goal:
        return {}
    raw = goal.split(marker, 1)[1].split("\nRole rule:", 1)[0]
    value = json.loads(raw)
    return value if isinstance(value, dict) else {}


class _DeterministicEvaluationProvider:
    """Offline provider that drives real AgentLoop/tool paths without API credentials."""

    # 绑定单个固定任务；所有结论均从工具返回和场景目标计算
    def __init__(self, scenario: _Scenario) -> None:
        self._scenario = scenario

    # 根据冷启动角色提示生成工具调用，随后基于真实工具结果生成交接 JSON
    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> LlmResponse:
        del tool_schemas, bus, run_id, step, system
        goal = _initial_goal(messages)
        results = _tool_results(messages)
        if goal.startswith("Create a structured Planner handoff"):
            return self._planner_response()
        if "Role rule: Only modify files under allowed_paths" in goal:
            return self._coder_response(results)
        if "Role rule: Run the checks yourself" in goal:
            return self._tester_response(results)
        if "Role rule: Inspect the actual diff" in goal:
            return self._reviewer_response(goal, results)
        return self._single_agent_response(results)

    # 输出含依赖、负责人、完成条件与写入范围的真实 Planner 图
    def _planner_response(self) -> LlmResponse:
        coder_criteria = [
            f"{change.path} matches the requested implementation"
            for change in self._scenario.changes
        ]
        payload = {
            "planner_summary": "先完成两个模块，再由独立 Tester 验证和 Reviewer 仲裁",
            "tasks": [
                {
                    "id": "code",
                    "title": "实现跨模块变更",
                    "description": self._scenario.goal,
                    "owner": "coder",
                    "dependencies": [],
                    "completion_criteria": coder_criteria,
                    "allowed_paths": _changed_paths(self._scenario),
                    "depth": 0,
                    "token_budget": 0,
                    "time_budget_s": 30,
                    "max_retries": 0,
                },
                {
                    "id": "test",
                    "title": "独立运行场景测试",
                    "description": "执行固定 pytest 命令并保留原始输出",
                    "owner": "tester",
                    "dependencies": ["code"],
                    "completion_criteria": ["场景测试由 Tester 独立执行并通过"],
                    "allowed_paths": [],
                    "depth": 0,
                    "token_budget": 0,
                    "time_budget_s": 30,
                    "max_retries": 0,
                },
                {
                    "id": "review",
                    "title": "独立审查和仲裁",
                    "description": "核对实际文件、测试证据和范围审计",
                    "owner": "reviewer",
                    "dependencies": ["code", "test"],
                    "completion_criteria": ["Diff、测试和安全范围证据均被接受"],
                    "allowed_paths": [],
                    "depth": 0,
                    "token_budget": 0,
                    "time_budget_s": 30,
                    "max_retries": 0,
                },
            ],
        }
        return LlmResponse(
            stop_reason="end_turn",
            text=json.dumps(payload, ensure_ascii=False),
        )

    # 首轮调用真实 edit_file，次轮依据工具结果提交 Coder 交接
    def _coder_response(
        self, results: dict[str, _ObservedToolResult]
    ) -> LlmResponse:
        if not results:
            calls = [
                ToolCallBlock(
                    id=f"coder-edit-{index}",
                    name="edit_file",
                    input={
                        "path": change.path,
                        "old_string": change.before,
                        "new_string": change.after,
                    },
                )
                for index, change in enumerate(self._scenario.changes)
            ]
            return LlmResponse(stop_reason="tool_use", tool_calls=calls)
        succeeded = all(
            (item := results.get(f"coder-edit-{index}")) is not None
            and not item.is_error
            for index in range(len(self._scenario.changes))
        )
        payload = {
            "status": "succeeded" if succeeded else "failed",
            "summary": "两个目标模块均由 edit_file 实际更新",
            "conclusion": (
                "全部分配路径完成修改" if succeeded else "至少一个真实编辑调用失败"
            ),
        }
        return LlmResponse(
            stop_reason="end_turn",
            text=json.dumps(payload, ensure_ascii=False),
        )

    # 首轮调用真实 pytest，次轮把该工具的原始输出写入 Tester 交接
    def _tester_response(
        self, results: dict[str, _ObservedToolResult]
    ) -> LlmResponse:
        if "tester-pytest" not in results:
            return LlmResponse(
                stop_reason="tool_use",
                tool_calls=[
                    ToolCallBlock(
                        id="tester-pytest",
                        name="bash",
                        input={"command": self._scenario.test_command, "timeout": 30},
                    )
                ],
            )
        observed = results["tester-pytest"]
        passed = not observed.is_error and "passed" in observed.content.lower()
        payload = {
            "status": "succeeded" if passed else "failed",
            "summary": "独立执行场景 pytest",
            "commands": [self._scenario.test_command],
            "output": observed.content,
            "conclusion": "测试通过" if passed else "测试失败",
            "test_summary": observed.content.strip(),
        }
        return LlmResponse(
            stop_reason="end_turn",
            text=json.dumps(payload, ensure_ascii=False),
        )

    # 读取两个真实文件并重跑 pytest，再结合依赖交接完成独立仲裁
    def _reviewer_response(
        self,
        goal: str,
        results: dict[str, _ObservedToolResult],
    ) -> LlmResponse:
        expected_ids = {
            *(f"review-read-{index}" for index in range(len(self._scenario.changes))),
            "review-pytest",
        }
        if not expected_ids.issubset(results):
            calls = [
                ToolCallBlock(
                    id=f"review-read-{index}",
                    name="read_file",
                    input={"path": change.path},
                )
                for index, change in enumerate(self._scenario.changes)
            ]
            calls.append(
                ToolCallBlock(
                    id="review-pytest",
                    name="bash",
                    input={"command": self._scenario.test_command, "timeout": 30},
                )
            )
            return LlmResponse(stop_reason="tool_use", tool_calls=calls)

        context = _delegation_context(goal)
        dependencies = context.get("dependency_evidence", [])
        coder_evidence = next(
            (
                item
                for item in dependencies
                if isinstance(item, dict) and item.get("role") == "coder"
            ),
            {},
        )
        tester_evidence = next(
            (
                item
                for item in dependencies
                if isinstance(item, dict) and item.get("role") == "tester"
            ),
            {},
        )
        file_matches = all(
            not results[f"review-read-{index}"].is_error
            and results[f"review-read-{index}"].content == change.after
            for index, change in enumerate(self._scenario.changes)
        )
        pytest_result = results["review-pytest"]
        test_passed = not pytest_result.is_error and "passed" in pytest_result.content.lower()
        scope_ok = (
            sorted(coder_evidence.get("changed_paths", []))
            == sorted(_changed_paths(self._scenario))
            and not coder_evidence.get("scope_escalations", [])
        )
        tester_ok = (
            tester_evidence.get("status") == "succeeded"
            and tester_evidence.get("commands") == [self._scenario.test_command]
        )
        accepted = file_matches and test_passed and scope_ok and tester_ok
        diff_lines = sum(
            len(
                list(
                    difflib.unified_diff(
                        change.before.splitlines(),
                        results[f"review-read-{index}"].content.splitlines(),
                    )
                )
            )
            for index, change in enumerate(self._scenario.changes)
        )
        payload = {
            "status": "succeeded",
            "summary": "独立读取产物、复跑测试并检查范围审计",
            "diff_summary": (
                f"检查 2 个实际模块和 {diff_lines} 行 unified diff；"
                f"目标内容匹配={file_matches}"
            ),
            "test_summary": pytest_result.content.strip(),
            "security_summary": (
                "范围审计通过：2/2 改动均在分配路径内，0 次越界升级"
                if scope_ok
                else "范围审计失败：改动路径或升级记录不匹配"
            ),
            "review_decision": "accept" if accepted else "return",
            "conclusion": "接受交付" if accepted else "退回交付",
        }
        return LlmResponse(
            stop_reason="end_turn",
            text=json.dumps(payload, ensure_ascii=False),
        )

    # 单 Agent 在同一上下文中依次完成编辑和测试，形成可复现基线
    def _single_agent_response(
        self, results: dict[str, _ObservedToolResult]
    ) -> LlmResponse:
        edit_ids = [f"single-edit-{index}" for index in range(len(self._scenario.changes))]
        if not set(edit_ids).issubset(results):
            calls = [
                ToolCallBlock(
                    id=edit_ids[index],
                    name="edit_file",
                    input={
                        "path": change.path,
                        "old_string": change.before,
                        "new_string": change.after,
                    },
                )
                for index, change in enumerate(self._scenario.changes)
            ]
            return LlmResponse(stop_reason="tool_use", tool_calls=calls)
        if "single-pytest" not in results:
            return LlmResponse(
                stop_reason="tool_use",
                tool_calls=[
                    ToolCallBlock(
                        id="single-pytest",
                        name="bash",
                        input={"command": self._scenario.test_command, "timeout": 30},
                    )
                ],
            )
        observed = results["single-pytest"]
        passed = (
            all(not results[tool_id].is_error for tool_id in edit_ids)
            and not observed.is_error
            and "passed" in observed.content.lower()
        )
        return LlmResponse(
            stop_reason="end_turn",
            text="single Agent completed and tested the task" if passed else "baseline failed",
        )


# 写入相同的失败初始状态和场景测试，供两条执行路径隔离使用
def _seed_workspace(root: Path, scenario: _Scenario) -> None:
    for change in scenario.changes:
        path = root / change.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(change.before, encoding="utf-8")
    test_path = root / scenario.test_path
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text(scenario.test_content, encoding="utf-8")


# 读取两个目标模块的完整内容，避免以 Agent 自述代替产物检查
def _module_snapshot(root: Path, scenario: _Scenario) -> dict[str, str]:
    return {
        change.path: (root / change.path).read_text(encoding="utf-8")
        for change in scenario.changes
    }


# 通过产品 BashTool 运行场景 pytest，用于验证初始红灯和最终绿灯
async def _run_scenario_test(root: Path, scenario: _Scenario) -> ToolResult:
    return await BashTool(root).invoke({"command": scenario.test_command, "timeout": 30})


# 返回 Trace 中所有 EventBus 事件的数据载荷
def _event_payloads(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        data
        for record in records
        if record.get("layer") == "event"
        and isinstance((data := record.get("data")), dict)
    ]


# 在隔离目录中运行真实单 Agent 循环、编辑工具、pytest 和 Trace
async def _run_single_agent(
    root: Path,
    scenario: _Scenario,
    trace_path: Path,
) -> _SingleAgentEvidence:
    capture = _TraceCapture(trace_path)
    await capture.start()
    scope_audit = ScopeAuditLog()
    registry = ToolRegistry()
    registry.register(ReadFileTool(root))
    registry.register(EditFileTool(root, _changed_paths(scenario), scope_audit))
    registry.register(BashTool(root))
    context = ExecutionContext(
        run_id=f"single-{scenario.id}",
        goal=scenario.goal,
        max_steps=3,
    )
    loop = AgentLoop(
        _DeterministicEvaluationProvider(scenario),
        registry,
        capture.bus,
        permission_manager=PermissionManager(mode=PermissionMode.AUTO),
        wrap_up_on_max_steps=False,
        grace_step_on_max_steps=False,
    )
    try:
        await loop.run(context)
    finally:
        await capture.stop()
    records = capture.records()
    events = _event_payloads(records)
    test_passed = any(
        event.get("type") == "test.result" and event.get("status") == "passed"
        for event in events
    )
    files = _module_snapshot(root, scenario)
    completion_checks = sum(
        files[change.path] == change.after for change in scenario.changes
    ) + int(test_passed)
    baseline = SingleAgentBaseline(
        scenario_id=scenario.id,
        completion_checks=completion_checks,
        independent_test_evidence=False,
        independent_review_evidence=False,
        trace_handoffs=sum(
            event.get("type") == "workflow.handoff" for event in events
        ),
        tokens=context.total_tokens(),
        elapsed_s=context.elapsed_s(),
    )
    return _SingleAgentEvidence(
        baseline=baseline,
        status=context.status,
        files=files,
        trace=records,
        scope_escalations=scope_audit.paths,
    )


# 通过生产 WorkflowRunTool 跑 Planner→Coder→Tester→Reviewer 全链路
async def _run_multi_agent(
    root: Path,
    scenario: _Scenario,
    trace_path: Path,
) -> tuple[WorkflowResult, dict[str, str], list[dict[str, Any]]]:
    capture = _TraceCapture(trace_path)
    await capture.start()
    provider = _DeterministicEvaluationProvider(scenario)
    permission_manager = PermissionManager(mode=PermissionMode.AUTO)
    spawn_tool = SpawnAgentTool(
        provider=provider,
        parent_bus=capture.bus,
        parent_run_id=f"parent-{scenario.id}",
        permission_manager=permission_manager,
        max_steps=8,
        task_registry=BackgroundTaskRegistry(),
        runs_dir=root / ".runs",
        session_id=f"eval-{scenario.id}",
        workspace_root=root,
        wrap_up_on_max_steps=False,
        grace_step_on_max_steps=False,
    )
    config = SztuConfig()
    config.workflow.max_retries = 0
    tool = WorkflowRunTool(
        spawn_tool,
        capture.bus,
        f"parent-{scenario.id}",
        root,
        config,
    )
    try:
        tool_result = await tool.invoke(
            {
                "goal": scenario.goal,
                "allowed_paths": _changed_paths(scenario),
                "completion_criteria": [
                    "两个模块达到目标状态",
                    "场景 pytest 通过",
                    "Reviewer 接受 Diff、测试和范围审计",
                ],
            }
        )
    finally:
        await capture.stop()
    assert not tool_result.is_error, tool_result.content
    return (
        WorkflowResult.model_validate_json(tool_result.content),
        _module_snapshot(root, scenario),
        capture.records(),
    )


@pytest.mark.parametrize("scenario", _scenarios(), ids=lambda item: item.id)
# 功能：真实完成至少五个跨模块任务，并与同快照单 Agent 基线逐项比较
# 设计：先证实初始红灯，再运行两条真实 AgentLoop/工具/pytest/Trace 路径并核对等价产物与独立证据
async def test_cross_module_workflow_against_single_agent_baseline(
    tmp_path: Path,
    scenario: _Scenario,
) -> None:
    single_root = tmp_path / scenario.id / "single"
    workflow_root = tmp_path / scenario.id / "workflow"
    _seed_workspace(single_root, scenario)
    _seed_workspace(workflow_root, scenario)

    single_red = await _run_scenario_test(single_root, scenario)
    workflow_red = await _run_scenario_test(workflow_root, scenario)
    assert single_red.is_error
    assert workflow_red.is_error

    single = await _run_single_agent(
        single_root,
        scenario,
        tmp_path / scenario.id / "single-trace.jsonl",
    )
    workflow, workflow_files, workflow_trace = await _run_multi_agent(
        workflow_root,
        scenario,
        tmp_path / scenario.id / "workflow-trace.jsonl",
    )
    single_green = await _run_scenario_test(single_root, scenario)
    workflow_green = await _run_scenario_test(workflow_root, scenario)

    expected_files = {change.path: change.after for change in scenario.changes}
    assert single.status == "success"
    assert workflow.status == "succeeded"
    assert not single_green.is_error
    assert not workflow_green.is_error
    assert single.files == expected_files
    assert workflow_files == expected_files
    assert workflow_files == single.files
    assert not single.scope_escalations

    comparison = compare_with_single_agent(workflow, single.baseline)
    assert comparison.baseline_completion_checks == 3
    assert comparison.workflow_completion_checks >= comparison.baseline_completion_checks
    assert comparison.workflow_has_independent_test
    assert not comparison.baseline_has_independent_test
    assert comparison.workflow_has_independent_review
    assert not comparison.baseline_has_independent_review
    assert comparison.baseline_trace_handoffs == 0
    assert comparison.workflow_tokens == 0
    assert comparison.baseline_tokens == 0
    assert comparison.workflow_elapsed_s > 0
    assert comparison.baseline_elapsed_s > 0

    task_artifacts = {
        state.task.owner: state.artifact
        for state in workflow.tasks
        if state.artifact is not None
    }
    assert task_artifacts["coder"].changed_paths == sorted(_changed_paths(scenario))
    assert not task_artifacts["coder"].scope_escalations
    assert task_artifacts["tester"].commands == [scenario.test_command]
    assert "passed" in task_artifacts["tester"].output.lower()
    assert task_artifacts["reviewer"].review_decision == "accept"
    assert "0 次越界升级" in task_artifacts["reviewer"].security_summary
    child_run_ids = {artifact.child_run_id for artifact in task_artifacts.values()}
    assert len(child_run_ids) == 3
    assert "" not in child_run_ids

    workflow_events = _event_payloads(workflow_trace)
    workflow_types = [event.get("type") for event in workflow_events]
    assert workflow_types.count("workflow.started") == 1
    assert workflow_types.count("workflow.handoff") == 3
    assert workflow_types.count("workflow.reviewed") == 1
    assert workflow_types.count("workflow.finished") == 1
    assert workflow_types.count("subagent.started") == 4
    assert sum(
        event.get("type") == "test.result" and event.get("status") == "passed"
        for event in workflow_events
    ) == 2
    started = next(
        event for event in workflow_events if event.get("type") == "workflow.started"
    )
    planner_tasks = started["tasks"]
    assert [task["owner"] for task in planner_tasks] == ["coder", "tester", "reviewer"]
    assert planner_tasks[1]["dependencies"] == ["code"]
    assert planner_tasks[2]["dependencies"] == ["code", "test"]
    assert all(task["completion_criteria"] for task in planner_tasks)
    assert planner_tasks[0]["allowed_paths"] == _changed_paths(scenario)
    assert sum(
        event.get("type") == "tool.call_started"
        and event.get("tool_name") == "edit_file"
        for event in workflow_events
    ) == 2
    assert sum(
        event.get("type") == "tool.call_started" and event.get("tool_name") == "bash"
        for event in workflow_events
    ) == 2
    baseline_events = _event_payloads(single.trace)
    baseline_types = [event.get("type") for event in baseline_events]
    assert "workflow.handoff" not in baseline_types
    assert baseline_types.count("test.result") == 1
    assert sum(
        event.get("type") == "tool.call_started"
        and event.get("tool_name") == "edit_file"
        for event in baseline_events
    ) == 2
    assert sum(
        event.get("type") == "tool.call_started" and event.get("tool_name") == "bash"
        for event in baseline_events
    ) == 1
