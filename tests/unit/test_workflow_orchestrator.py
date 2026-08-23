from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from sztu_code.core.events.bus import EventBus
from sztu_code.core.workflow.model import (
    HandoffArtifact,
    WorkflowGraph,
    WorkflowLimits,
    WorkflowTask,
)
from sztu_code.core.workflow.orchestrator import WorkflowOrchestrator, WorkflowTaskError


# 构造标准 Coder→Tester→Reviewer 图，可选加入第二个并行 Coder
def _graph(*, parallel_coders: bool = False, coder_time_budget: float = 0.0) -> WorkflowGraph:
    tasks = [
        WorkflowTask(
            id="code-core",
            title="实现核心",
            description="修改核心模块",
            owner="coder",
            completion_criteria=["核心行为已实现"],
            allowed_paths=["src/core.py"],
            time_budget_s=coder_time_budget,
        )
    ]
    coder_ids = ["code-core"]
    if parallel_coders:
        tasks.append(
            WorkflowTask(
                id="code-ui",
                title="实现界面",
                description="修改界面模块",
                owner="coder",
                completion_criteria=["界面状态可见"],
                allowed_paths=["desktop/App.vue"],
            )
        )
        coder_ids.append("code-ui")
    tasks.extend(
        [
            WorkflowTask(
                id="test-all",
                title="独立验证",
                description="运行核心与界面检查",
                owner="tester",
                dependencies=coder_ids,
                completion_criteria=["相关检查通过"],
            ),
            WorkflowTask(
                id="review-all",
                title="质量仲裁",
                description="审查 Diff、测试和安全证据",
                owner="reviewer",
                dependencies=[*coder_ids, "test-all"],
                completion_criteria=["质量门禁接受"],
            ),
        ]
    )
    return WorkflowGraph(
        workflow_id="wf-test",
        goal="完成跨模块改动",
        planner_summary="核心与界面可并行，随后独立测试和审查",
        tasks=tasks,
    )


class _Executor:
    # 初始化可控替身，支持指定任务失败、延迟和 Reviewer 退回
    def __init__(
        self,
        *,
        fail_once: set[str] | None = None,
        always_fail: set[str] | None = None,
        delay_s: float = 0.0,
        reviewer_decision: str = "accept",
        tokens: int = 10,
    ) -> None:
        self.fail_once = fail_once or set()
        self.always_fail = always_fail or set()
        self.delay_s = delay_s
        self.reviewer_decision = reviewer_decision
        self.tokens = tokens
        self.calls: dict[str, int] = {}
        self.active = 0
        self.max_active = 0

    # 按角色返回完整交接产物，并记录并发与重试次数供断言
    async def __call__(
        self,
        task: WorkflowTask,
        dependency_artifacts: list[HandoffArtifact],
        attempt: int,
    ) -> HandoffArtifact:
        self.calls[task.id] = self.calls.get(task.id, 0) + 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay_s:
                await asyncio.sleep(self.delay_s)
            if task.id in self.always_fail:
                raise WorkflowTaskError(f"{task.id} failed", tokens=self.tokens)
            if task.id in self.fail_once and attempt == 1:
                raise WorkflowTaskError(
                    f"{task.id} transient failure",
                    tokens=self.tokens,
                )
            common = {
                "workflow_id": "wf-test",
                "task_id": task.id,
                "role": task.owner,
                "status": "succeeded",
                "summary": f"{task.id} complete",
                "tokens": self.tokens,
                "attempt": attempt,
            }
            if task.owner == "coder":
                return HandoffArtifact(
                    **common,
                    changed_paths=[task.allowed_paths[0]],
                    conclusion="实现满足完成条件",
                )
            if task.owner == "tester":
                assert dependency_artifacts
                return HandoffArtifact(
                    **common,
                    commands=["pytest -q"],
                    output="5 passed",
                    conclusion="全部验证通过",
                    test_summary="5 passed",
                )
            return HandoffArtifact(
                **common,
                diff_summary="Diff 与任务范围一致",
                test_summary="Tester 提供 5 passed",
                security_summary="未发现高危问题",
                review_decision=self.reviewer_decision,
                conclusion="接受" if self.reviewer_decision == "accept" else "退回",
            )
        finally:
            self.active -= 1


# 收集调度器发布的全部协议事件并返回可复用列表
def _bus_with_events() -> tuple[EventBus, list[BaseModel]]:
    bus = EventBus()
    events: list[BaseModel] = []

    # 将事件对象原样保留，便于同时检查顺序和结构化字段
    async def collect(event: BaseModel) -> None:
        events.append(event)

    bus.subscribe(collect)
    return bus, events


# 功能：验证标准角色链成功后生成任务、交接、仲裁和完成事件
# 设计：使用确定性角色替身排除模型随机性，逐类检查统一 Trace 所需事件是否齐全
async def test_standard_workflow_emits_complete_evidence_chain() -> None:
    bus, events = _bus_with_events()
    result = await WorkflowOrchestrator(
        bus, "parent-run", WorkflowLimits(max_retries=0)
    ).run(_graph(), _Executor())
    assert result.status == "succeeded"
    assert [state.status for state in result.tasks] == [
        "succeeded",
        "succeeded",
        "succeeded",
    ]
    event_types = [event.type for event in events]  # type: ignore[attr-defined]
    assert event_types[0] == "workflow.started"
    assert event_types.count("workflow.handoff") == 3
    assert "workflow.reviewed" in event_types
    assert event_types[-1] == "workflow.finished"


# 功能：验证最大并发数允许无依赖 Coder 并行，但 Tester 仍等待全部依赖
# 设计：两个 Coder 使用短延迟放大重叠窗口，以 max_active 精确证明并发而非仅比较事件顺序
async def test_ready_tasks_respect_concurrency_and_dependencies() -> None:
    bus, _ = _bus_with_events()
    executor = _Executor(delay_s=0.02)
    result = await WorkflowOrchestrator(
        bus, "parent-run", WorkflowLimits(max_concurrency=2, max_retries=0)
    ).run(_graph(parallel_coders=True), executor)
    assert result.status == "succeeded"
    assert executor.max_active == 2
    assert executor.calls["test-all"] == 1
    assert executor.calls["review-all"] == 1


# 功能：验证角色瞬时失败会在预算内重试并最终成功
# 设计：首个 attempt 消耗 Token 后失败，断言重试和后续角色成功且失败用量也进入总预算
async def test_task_retries_within_configured_budget() -> None:
    bus, _ = _bus_with_events()
    executor = _Executor(fail_once={"code-core"})
    result = await WorkflowOrchestrator(
        bus, "parent-run", WorkflowLimits(max_retries=1)
    ).run(_graph(), executor)
    assert result.status == "succeeded"
    assert executor.calls["code-core"] == 2
    assert result.tasks[0].attempts == 2
    assert result.tasks[0].tokens == 20
    assert result.total_tokens == 40


# 功能：验证 Coder 最终失败会阻断 Tester 和 Reviewer 并传播到父工作流
# 设计：关闭重试并让首节点恒定失败，断言下游从未执行且终态为 blocked
async def test_failure_propagates_to_dependent_tasks() -> None:
    bus, _ = _bus_with_events()
    executor = _Executor(always_fail={"code-core"})
    result = await WorkflowOrchestrator(
        bus, "parent-run", WorkflowLimits(max_retries=0)
    ).run(_graph(), executor)
    assert result.status == "failed"
    assert [state.status for state in result.tasks] == ["failed", "blocked", "blocked"]
    assert "test-all" not in executor.calls
    assert "review-all" not in executor.calls


# 功能：验证任务时间预算耗尽会标记 timed_out 并阻断依赖链
# 设计：让 Coder 延迟超过极短 task budget，断言父工作流与首任务均呈超时语义
async def test_timeout_propagates_to_parent_workflow() -> None:
    bus, _ = _bus_with_events()
    result = await WorkflowOrchestrator(
        bus, "parent-run", WorkflowLimits(max_retries=0)
    ).run(_graph(coder_time_budget=0.01), _Executor(delay_s=0.05))
    assert result.status == "timed_out"
    assert result.tasks[0].status == "timed_out"
    assert result.tasks[1].status == "blocked"


# 功能：验证全局墙钟预算会取消运行中角色并停止所有尚未启动的任务
# 设计：不给任务级超时，仅设置极短工作流总时限，区分全局预算与单任务预算路径
async def test_global_wall_clock_budget_stops_workflow() -> None:
    bus, _ = _bus_with_events()
    result = await WorkflowOrchestrator(
        bus,
        "parent-run",
        WorkflowLimits(max_wall_clock_s=0.01, max_retries=0),
    ).run(_graph(), _Executor(delay_s=0.05))
    assert result.status == "timed_out"
    assert result.reason == "max_wall_clock_exceeded"
    assert all(state.status == "timed_out" for state in result.tasks)


# 功能：验证 Planner 生成的任务深度超过配置上限时在执行前被拒绝
# 设计：把首个 Coder 深度设为 2、上限设为 1，断言 executor 完全没有被调用
async def test_task_depth_budget_rejects_graph_before_execution() -> None:
    bus, _ = _bus_with_events()
    graph = _graph()
    graph.tasks[0].depth = 2
    executor = _Executor()
    with pytest.raises(ValueError, match="exceeds max depth 1"):
        await WorkflowOrchestrator(
            bus,
            "parent-run",
            WorkflowLimits(max_depth=1, max_retries=0),
        ).run(graph, executor)
    assert executor.calls == {}


# 功能：验证 Reviewer 退回是有效仲裁但会让父工作流失败
# 设计：前置角色全部成功，仅返回 review_decision=return，区分质量退回与执行异常
async def test_reviewer_return_rejects_parent_workflow() -> None:
    bus, events = _bus_with_events()
    result = await WorkflowOrchestrator(
        bus, "parent-run", WorkflowLimits(max_retries=0)
    ).run(_graph(), _Executor(reviewer_decision="return"))
    assert result.status == "failed"
    assert result.tasks[-1].status == "rejected"
    reviewed = next(event for event in events if event.type == "workflow.reviewed")  # type: ignore[attr-defined]
    assert reviewed.decision == "return"  # type: ignore[attr-defined]


# 功能：验证聚合 Token 预算耗尽后未启动任务会被停止并传播失败
# 设计：首个 Coder 单次消耗超过总预算，断言 Tester 不会启动且结果记录真实超额用量
async def test_token_budget_stops_remaining_tasks() -> None:
    bus, _ = _bus_with_events()
    executor = _Executor(tokens=60)
    result = await WorkflowOrchestrator(
        bus, "parent-run", WorkflowLimits(max_tokens=50, max_retries=0)
    ).run(_graph(), executor)
    assert result.status == "failed"
    assert result.reason == "max_tokens_exceeded"
    assert result.total_tokens == 60
    assert result.tasks[1].status == "blocked"


# 功能：验证取消调度协程会取消运行中角色并写入父工作流取消事件
# 设计：启动长延迟 Coder 后主动 cancel，捕获 CancelledError 并检查最后的 finished 状态
async def test_cancellation_propagates_and_emits_finished() -> None:
    bus, events = _bus_with_events()
    future = asyncio.create_task(
        WorkflowOrchestrator(
            bus, "parent-run", WorkflowLimits(max_retries=0)
        ).run(_graph(), _Executor(delay_s=1.0))
    )
    await asyncio.sleep(0.01)
    future.cancel()
    with pytest.raises(asyncio.CancelledError):
        await future
    finished = [event for event in events if event.type == "workflow.finished"]  # type: ignore[attr-defined]
    assert finished[-1].status == "cancelled"  # type: ignore[attr-defined]
