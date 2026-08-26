from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Protocol

from sztu_code.core.bus.events import (
    WorkflowFinishedEvent,
    WorkflowHandoffEvent,
    WorkflowHandoffSnapshot,
    WorkflowReviewEvent,
    WorkflowStartedEvent,
    WorkflowTaskSnapshot,
    WorkflowTaskUpdatedEvent,
)
from sztu_code.core.events.bus import EventBus
from sztu_code.core.workflow.model import (
    HandoffArtifact,
    WorkflowGraph,
    WorkflowLimits,
    WorkflowResult,
    WorkflowTask,
    WorkflowTaskResult,
)
from sztu_code.core.workflow.scope import normalize_workspace_relative, path_is_allowed


# 返回当前 UTC ISO 时间，统一工作流事件时间戳格式
def _now() -> str:
    return datetime.now(UTC).isoformat()


class RoleExecutor(Protocol):
    # 执行一个角色任务并返回可验证的结构化交接产物
    async def __call__(
        self,
        task: WorkflowTask,
        dependency_artifacts: list[HandoffArtifact],
        attempt: int,
    ) -> HandoffArtifact: ...


class WorkflowTaskError(RuntimeError):
    # 保留失败子运行已经消耗的 Token，使重试不会低估父工作流预算
    def __init__(self, message: str, *, tokens: int = 0) -> None:
        super().__init__(message)
        self.tokens = tokens


class WorkflowOrchestrator:
    # 初始化有界 DAG 调度器，并绑定父运行事件总线
    def __init__(self, bus: EventBus, run_id: str, limits: WorkflowLimits) -> None:
        self._bus = bus
        self._run_id = run_id
        self._limits = limits

    # 校验任务图后按依赖和并发预算执行，并传播失败、取消与超时
    async def run(
        self,
        graph: WorkflowGraph,
        executor: RoleExecutor,
        *,
        initial_tokens: int = 0,
    ) -> WorkflowResult:
        self.validate_graph(graph)
        started_at = time.monotonic()
        states = {task.id: WorkflowTaskResult(task=task) for task in graph.tasks}
        await self._bus.publish(
            WorkflowStartedEvent(
                run_id=self._run_id,
                workflow_id=graph.workflow_id,
                goal=graph.goal,
                planner_summary=graph.planner_summary,
                tasks=[self._snapshot(state) for state in states.values()],
                ts=_now(),
            )
        )

        pending = set(states)
        running: dict[asyncio.Task[HandoffArtifact], str] = {}
        total_tokens = initial_tokens
        stop_reason = ""
        terminal_status = "failed"

        try:
            while pending or running:
                elapsed = time.monotonic() - started_at
                if self._limits.max_wall_clock_s and elapsed >= self._limits.max_wall_clock_s:
                    stop_reason = "max_wall_clock_exceeded"
                    terminal_status = "timed_out"
                    await self._stop_outstanding(
                        graph.workflow_id,
                        pending,
                        running,
                        states,
                        "timed_out",
                        stop_reason,
                    )
                    break
                if self._limits.max_tokens and total_tokens >= self._limits.max_tokens:
                    stop_reason = "max_tokens_exceeded"
                    await self._stop_outstanding(
                        graph.workflow_id,
                        pending,
                        running,
                        states,
                        "blocked",
                        stop_reason,
                    )
                    break

                await self._propagate_dependency_failures(
                    graph.workflow_id, pending, states
                )
                ready = [
                    task_id
                    for task_id in sorted(pending)
                    if all(
                        states[dependency].status == "succeeded"
                        for dependency in states[task_id].task.dependencies
                    )
                ]
                capacity = self._limits.max_concurrency - len(running)
                for task_id in ready[: max(0, capacity)]:
                    state = states[task_id]
                    dependencies: list[HandoffArtifact] = []
                    for dependency in state.task.dependencies:
                        artifact = states[dependency].artifact
                        if artifact is not None:
                            dependencies.append(artifact)
                    future = asyncio.create_task(
                        self._execute_with_retries(
                            graph.workflow_id,
                            state,
                            dependencies,
                            executor,
                        )
                    )
                    running[future] = task_id
                    pending.remove(task_id)

                if not running:
                    if pending:
                        stop_reason = "task_graph_deadlock"
                        await self._stop_outstanding(
                            graph.workflow_id,
                            pending,
                            running,
                            states,
                            "blocked",
                            stop_reason,
                        )
                    break

                timeout = None
                if self._limits.max_wall_clock_s:
                    timeout = max(
                        0.0,
                        self._limits.max_wall_clock_s - (time.monotonic() - started_at),
                    )
                done, _ = await asyncio.wait(
                    running,
                    timeout=timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if not done:
                    stop_reason = "max_wall_clock_exceeded"
                    terminal_status = "timed_out"
                    await self._stop_outstanding(
                        graph.workflow_id,
                        pending,
                        running,
                        states,
                        "timed_out",
                        stop_reason,
                    )
                    break

                for future in done:
                    task_id = running.pop(future)
                    state = states[task_id]
                    try:
                        artifact = future.result()
                    except TimeoutError:
                        state.status = "timed_out"
                        state.error = "task_time_budget_exceeded"
                    except WorkflowTaskError as exc:
                        state.status = "failed"
                        state.error = str(exc)
                    except Exception as exc:
                        state.status = "failed"
                        state.error = f"unexpected executor error: {exc}"
                    else:
                        state.artifact = artifact
                        state.status = (
                            "rejected"
                            if artifact.role == "reviewer"
                            and artifact.review_decision == "return"
                            else "succeeded"
                        )
                        if artifact.role == "reviewer" and artifact.review_decision is not None:
                            await self._publish_review(graph.workflow_id, artifact)
                    total_tokens += state.tokens
                    await self._publish_task(graph.workflow_id, state)

            if not stop_reason:
                failed_states = [state for state in states.values() if state.status != "succeeded"]
                if failed_states:
                    stop_reason = failed_states[0].error or failed_states[0].status
                    if any(state.status == "timed_out" for state in failed_states):
                        terminal_status = "timed_out"
                    elif any(state.status == "cancelled" for state in failed_states):
                        terminal_status = "cancelled"
                else:
                    terminal_status = "succeeded"
        except asyncio.CancelledError:
            stop_reason = "cancelled"
            terminal_status = "cancelled"
            await self._stop_outstanding(
                graph.workflow_id,
                pending,
                running,
                states,
                "cancelled",
                stop_reason,
            )
            result = self._result(
                graph,
                states,
                terminal_status,
                stop_reason,
                total_tokens,
                started_at,
            )
            await self._publish_finished(result)
            raise

        result = self._result(
            graph,
            states,
            terminal_status,
            stop_reason,
            total_tokens,
            started_at,
        )
        await self._publish_finished(result)
        return result

    # 校验任务 ID、依赖、深度、写入范围和 DAG 无环不变式
    def validate_graph(self, graph: WorkflowGraph) -> None:
        task_ids = [task.id for task in graph.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("workflow task ids must be unique")
        known = set(task_ids)
        for task in graph.tasks:
            if task.id in task.dependencies:
                raise ValueError(f"workflow task cannot depend on itself: {task.id}")
            missing = set(task.dependencies) - known
            if missing:
                raise ValueError(
                    f"workflow task {task.id} has unknown dependencies: {sorted(missing)}"
                )
            if task.depth > self._limits.max_depth:
                raise ValueError(
                    f"workflow task {task.id} exceeds max depth {self._limits.max_depth}"
                )
            if task.owner == "coder" and not task.allowed_paths:
                raise ValueError(f"coder task {task.id} must declare allowed_paths")
            for path in task.allowed_paths:
                normalize_workspace_relative(path)

        indegree = {task.id: len(task.dependencies) for task in graph.tasks}
        dependents: dict[str, list[str]] = {task.id: [] for task in graph.tasks}
        for task in graph.tasks:
            for dependency in task.dependencies:
                dependents[dependency].append(task.id)
        queue = [task_id for task_id, degree in indegree.items() if degree == 0]
        visited = 0
        while queue:
            task_id = queue.pop()
            visited += 1
            for dependent in dependents[task_id]:
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    queue.append(dependent)
        if visited != len(graph.tasks):
            raise ValueError("workflow task graph must be acyclic")

    # 在任务级时间与重试预算内执行角色，并逐次发布运行状态
    async def _execute_with_retries(
        self,
        workflow_id: str,
        state: WorkflowTaskResult,
        dependencies: list[HandoffArtifact],
        executor: RoleExecutor,
    ) -> HandoffArtifact:
        retry_limit = (
            self._limits.max_retries
            if state.task.max_retries is None
            else min(state.task.max_retries, self._limits.max_retries)
        )
        last_error = "role execution failed"
        for attempt in range(1, retry_limit + 2):
            state.status = "running"
            state.attempts = attempt
            state.error = ""
            await self._publish_task(workflow_id, state)
            try:
                execution: Awaitable[HandoffArtifact] = executor(
                    state.task, dependencies, attempt
                )
                if state.task.time_budget_s > 0:
                    artifact = await asyncio.wait_for(
                        execution, timeout=state.task.time_budget_s
                    )
                else:
                    artifact = await execution
                state.tokens += artifact.tokens
                self._validate_artifact(workflow_id, state.task, artifact)
                await self._publish_handoff(workflow_id, artifact)
                if artifact.status == "failed":
                    raise WorkflowTaskError(artifact.summary)
                return artifact.model_copy(update={"attempt": attempt})
            except asyncio.CancelledError:
                raise
            except TimeoutError:
                last_error = "task_time_budget_exceeded"
            except WorkflowTaskError as exc:
                state.tokens += exc.tokens
                last_error = str(exc)
            except (PermissionError, ValueError) as exc:
                last_error = str(exc)
            if attempt <= retry_limit:
                state.error = last_error
                await self._publish_task(workflow_id, state)
        if last_error == "task_time_budget_exceeded":
            raise TimeoutError(last_error)
        raise WorkflowTaskError(last_error)

    # 验证交接身份、Coder 写入边界及 Tester/Reviewer 的证据完整性
    def _validate_artifact(
        self,
        workflow_id: str,
        task: WorkflowTask,
        artifact: HandoffArtifact,
    ) -> None:
        if artifact.workflow_id != workflow_id or artifact.task_id != task.id:
            raise ValueError("handoff artifact does not match workflow task identity")
        if artifact.role != task.owner:
            raise ValueError("handoff artifact role does not match task owner")
        if task.owner == "coder":
            outside = [
                path
                for path in artifact.changed_paths
                if not path_is_allowed(path, task.allowed_paths)
            ]
            if sorted(outside) != sorted(artifact.scope_escalations):
                raise ValueError(
                    "coder scope escalation evidence does not match actual changed paths"
                )
        if task.owner == "tester":
            if (
                not artifact.commands
                or not artifact.output.strip()
                or not artifact.conclusion.strip()
            ):
                raise ValueError("tester handoff requires commands, output, and conclusion")
        if task.owner == "reviewer":
            if artifact.review_decision is None:
                raise ValueError("reviewer handoff requires accept or return decision")
            required = (
                artifact.diff_summary,
                artifact.test_summary,
                artifact.security_summary,
                artifact.conclusion,
            )
            if not all(value.strip() for value in required):
                raise ValueError(
                    "reviewer handoff requires diff, test, security, and conclusion evidence"
                )

    # 将依赖失败的未启动任务标为 blocked，并把原因写入事件流
    async def _propagate_dependency_failures(
        self,
        workflow_id: str,
        pending: set[str],
        states: dict[str, WorkflowTaskResult],
    ) -> None:
        terminal_failures = {
            "failed", "blocked", "cancelled", "timed_out", "rejected"
        }
        blocked = [
            task_id
            for task_id in pending
            if any(
                states[dependency].status in terminal_failures
                for dependency in states[task_id].task.dependencies
            )
        ]
        for task_id in blocked:
            state = states[task_id]
            failed_dependencies = [
                dependency
                for dependency in state.task.dependencies
                if states[dependency].status in terminal_failures
            ]
            state.status = "blocked"
            state.error = f"dependency_failed: {', '.join(failed_dependencies)}"
            pending.remove(task_id)
            await self._publish_task(workflow_id, state)

    # 取消运行中协程并把所有未落定任务统一标记为指定终态
    async def _stop_outstanding(
        self,
        workflow_id: str,
        pending: set[str],
        running: dict[asyncio.Task[HandoffArtifact], str],
        states: dict[str, WorkflowTaskResult],
        status: str,
        reason: str,
    ) -> None:
        for future in running:
            future.cancel()
        if running:
            await asyncio.gather(*running, return_exceptions=True)
        task_ids = list(pending) + list(running.values())
        pending.clear()
        running.clear()
        for task_id in task_ids:
            state = states[task_id]
            state.status = status  # type: ignore[assignment]
            state.error = reason
            await self._publish_task(workflow_id, state)

    # 将内部任务状态转换为稳定的协议快照
    def _snapshot(self, state: WorkflowTaskResult) -> WorkflowTaskSnapshot:
        task = state.task
        return WorkflowTaskSnapshot(
            id=task.id,
            title=task.title,
            owner=task.owner,
            status=state.status,
            dependencies=task.dependencies,
            completion_criteria=task.completion_criteria,
            allowed_paths=task.allowed_paths,
            attempt=state.attempts,
            error=state.error,
        )

    # 发布单个任务状态变化，供 Trace、TUI 与桌面端共同消费
    async def _publish_task(self, workflow_id: str, state: WorkflowTaskResult) -> None:
        await self._bus.publish(
            WorkflowTaskUpdatedEvent(
                run_id=self._run_id,
                workflow_id=workflow_id,
                task=self._snapshot(state),
                ts=_now(),
            )
        )

    # 发布完整结构化交接产物，保证执行证据进入统一 Trace
    async def _publish_handoff(
        self, workflow_id: str, artifact: HandoffArtifact
    ) -> None:
        payload = artifact.model_dump(
            exclude={"workflow_id"},
        )
        await self._bus.publish(
            WorkflowHandoffEvent(
                run_id=self._run_id,
                workflow_id=workflow_id,
                artifact=WorkflowHandoffSnapshot.model_validate(payload),
                ts=_now(),
            )
        )

    # 额外发布 Reviewer 仲裁事件，使接受或退回结论可单独检索
    async def _publish_review(self, workflow_id: str, artifact: HandoffArtifact) -> None:
        assert artifact.review_decision is not None
        await self._bus.publish(
            WorkflowReviewEvent(
                run_id=self._run_id,
                workflow_id=workflow_id,
                task_id=artifact.task_id,
                decision=artifact.review_decision,
                diff_summary=artifact.diff_summary,
                test_summary=artifact.test_summary,
                security_summary=artifact.security_summary,
                conclusion=artifact.conclusion,
                ts=_now(),
            )
        )

    # 汇总调度结果并保留任务原始顺序，便于稳定回放和评测
    def _result(
        self,
        graph: WorkflowGraph,
        states: dict[str, WorkflowTaskResult],
        status: str,
        reason: str,
        total_tokens: int,
        started_at: float,
    ) -> WorkflowResult:
        return WorkflowResult(
            workflow_id=graph.workflow_id,
            status=status,  # type: ignore[arg-type]
            reason=reason,
            tasks=[states[task.id] for task in graph.tasks],
            total_tokens=total_tokens,
            elapsed_s=time.monotonic() - started_at,
        )

    # 发布工作流最终状态与预算消耗，作为父任务收敛证据
    async def _publish_finished(self, result: WorkflowResult) -> None:
        await self._bus.publish(
            WorkflowFinishedEvent(
                run_id=self._run_id,
                workflow_id=result.workflow_id,
                status=result.status,
                reason=result.reason,
                total_tokens=result.total_tokens,
                elapsed_s=result.elapsed_s,
                ts=_now(),
            )
        )
