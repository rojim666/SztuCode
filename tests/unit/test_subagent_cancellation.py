from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from sztu_code.core.bus.events import SubagentFinishedEvent
from sztu_code.core.config import SztuConfig
from sztu_code.core.context import ExecutionContext
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import LlmResponse, ToolCallBlock, UsageStats
from sztu_code.core.runner import AgentRunner
from sztu_code.core.subagent.registry import BackgroundTaskRegistry, BackgroundTaskStatus
from sztu_code.core.subagent.tool import SpawnAgentTool


# 永久挂起的 provider，除非被 cancel
def _blocking_provider() -> Any:
    async def chat(*args: Any, **kwargs: Any) -> LlmResponse:
        await asyncio.Event().wait()
        return LlmResponse(stop_reason="end_turn", text="", usage=UsageStats(0, 0, 0, 0, 0.0))

    provider = MagicMock()
    provider.chat = chat
    return provider


def _make_tool(
    tmp_path: Path,
    provider: Any,
    parent_run_id: str,
    registry: BackgroundTaskRegistry,
    bus: EventBus,
    depth: int = 0,
) -> SpawnAgentTool:
    return SpawnAgentTool(
        provider=provider,
        parent_bus=bus,
        parent_run_id=parent_run_id,
        permission_manager=None,
        max_steps=5,
        task_registry=registry,
        runs_dir=tmp_path,
        session_id="sess-cancel",
        depth=depth,
        max_depth=3,
    )


def _extract_run_id(content: str) -> str:
    return content.split("run_id=")[1].split(".")[0]


# 功能：cancel 后台 child 时其 task 落定且终态为 cancelled
# 设计：spawn 后台 child（阻塞 provider），cancel_descendants 后断言 task.done 且 status=cancelled
async def test_cancel_descendants_stops_child(tmp_path: Path) -> None:
    registry = BackgroundTaskRegistry()
    bus = EventBus()
    tool = _make_tool(tmp_path, _blocking_provider(), "parent-run", registry, bus)
    tool._parent_context = ExecutionContext(run_id="parent-run", goal="g", max_steps=5)
    spawn_result = await tool.invoke({
        "description": "child", "prompt": "work", "run_in_background": True,
    })
    child_id = _extract_run_id(spawn_result.content)
    assert registry.query_result(child_id).status is BackgroundTaskStatus.RUNNING

    cancelled = await registry.cancel_descendants("parent-run", reason="parent_cancelled")
    assert child_id in cancelled

    record = registry.get(child_id)
    assert record is not None and record.task is not None
    assert record.task.done()
    assert registry.query_result(child_id).status is BackgroundTaskStatus.CANCELLED


# 功能：parent→child→grandchild 后台链，cancel parent 后两层 task 均停止
# 设计：child provider 第一步 spawn 后台 grandchild（阻塞），第二步阻塞；
#       cancel parent 后断言 child 与 grandchild 均落定且 cancelled
async def test_cancel_descendants_reaches_grandchild(tmp_path: Path) -> None:
    registry = BackgroundTaskRegistry()
    bus = EventBus()
    grandchild_spawn = ToolCallBlock(
        id="g1", name="spawn_agent",
        input={"description": "grandchild", "prompt": "gc", "run_in_background": True},
    )
    spawned = {"done": False}

    async def child_chat(messages: list[dict[str, object]], **kwargs: Any) -> LlmResponse:
        # 首步：派生后台 grandchild 后继续阻塞
        if not spawned["done"]:
            spawned["done"] = True
            return LlmResponse(
                stop_reason="tool_use", tool_calls=[grandchild_spawn], text="",
                usage=UsageStats(0, 0, 0, 0, 0.0),
            )
        await asyncio.Event().wait()
        return LlmResponse(stop_reason="end_turn", text="", usage=UsageStats(0, 0, 0, 0, 0.0))

    provider = MagicMock()
    provider.chat = child_chat
    tool = _make_tool(tmp_path, provider, "parent-run", registry, bus)
    tool._parent_context = ExecutionContext(run_id="parent-run", goal="g", max_steps=5)
    spawn_result = await tool.invoke({
        "description": "child", "prompt": "child prompt", "run_in_background": True,
    })
    child_id = _extract_run_id(spawn_result.content)
    # 轮询等待 child 派生 grandchild（避免固定 sleep 在慢机器上失效）
    for _ in range(100):
        gc_ids = registry.descendants(child_id)
        if gc_ids:
            break
        await asyncio.sleep(0.01)
    assert len(gc_ids) == 1, f"expected 1 grandchild, got {gc_ids}"
    grandchild_id = gc_ids[0]

    cancelled = await registry.cancel_descendants("parent-run", reason="parent_cancelled")
    assert child_id in cancelled
    assert grandchild_id in cancelled

    child_record = registry.get(child_id)
    gc_record = registry.get(grandchild_id)
    assert child_record is not None and child_record.task is not None
    assert gc_record is not None and gc_record.task is not None
    assert child_record.task.done()
    assert gc_record.task.done()
    assert registry.query_result(child_id).status is BackgroundTaskStatus.CANCELLED
    assert registry.query_result(grandchild_id).status is BackgroundTaskStatus.CANCELLED


# 功能：parent 取消时已完成的 child 保持 completed，且不重复发终态事件
# 设计：spawn 立即完成的 child，cancel parent；注册 on_terminal 收集事件，
#       断言 child 仍 completed，且恰好一个 success 事件（cancel 不覆盖不发第二个）
async def test_completed_child_survives_parent_cancel(tmp_path: Path) -> None:
    bus = EventBus()
    finished_events: list[Any] = []

    async def _collect(e: Any) -> None:
        if isinstance(e, SubagentFinishedEvent):
            finished_events.append(e)

    bus.subscribe(_collect)

    _STATUS_MAP = {"completed": "success", "failed": "failed", "cancelled": "cancelled"}

    def _on_terminal(rid: str, status: object) -> None:
        raw = status.value if hasattr(status, "value") else str(status)
        asyncio.get_running_loop().create_task(
            bus.publish(
                SubagentFinishedEvent(
                    run_id=rid, parent_run_id="parent-run",
                    status=_STATUS_MAP.get(raw, raw), ts="t",
                )
            )
        )

    registry = BackgroundTaskRegistry(on_terminal=_on_terminal)

    async def done_chat(*args: Any, **kwargs: Any) -> LlmResponse:
        return LlmResponse(
            stop_reason="end_turn", text="child done",
            usage=UsageStats(0, 0, 0, 0, 0.0),
        )

    provider = MagicMock()
    provider.chat = done_chat
    tool = _make_tool(tmp_path, provider, "parent-run", registry, bus)
    tool._parent_context = ExecutionContext(run_id="parent-run", goal="g", max_steps=5)
    spawn_result = await tool.invoke({
        "description": "child", "prompt": "do it", "run_in_background": True,
    })
    child_id = _extract_run_id(spawn_result.content)
    record = registry.get(child_id)
    assert record is not None and record.task is not None
    await asyncio.wait_for(record.task, timeout=5.0)
    assert registry.query_result(child_id).status is BackgroundTaskStatus.COMPLETED

    await registry.cancel_descendants("parent-run", reason="parent_cancelled")
    assert registry.query_result(child_id).status is BackgroundTaskStatus.COMPLETED
    # 等待 fire-and-forget 事件落定，断言恰好一个 success 事件（cancel 未追加第二个）
    for _ in range(100):
        if finished_events:
            break
        await asyncio.sleep(0.01)
    assert len(finished_events) == 1
    assert finished_events[0].status == "success"


# 功能：并发完成与取消竞争下恰好一个终态事件，终态唯一
# 设计：child 短暂等待后完成，cancel 与完成竞争；注册 on_terminal 回调收集事件，
#       断言终态唯一（completed 或 cancelled）且恰好一个 finished 事件
async def test_concurrent_completion_and_cancel_one_event(tmp_path: Path) -> None:
    bus = EventBus()
    finished_events: list[Any] = []

    async def _collect(e: Any) -> None:
        if isinstance(e, SubagentFinishedEvent):
            finished_events.append(e)

    bus.subscribe(_collect)

    _STATUS_MAP = {"completed": "success", "failed": "failed", "cancelled": "cancelled"}

    def _on_terminal(rid: str, status: object) -> None:
        raw = status.value if hasattr(status, "value") else str(status)
        asyncio.get_running_loop().create_task(
            bus.publish(
                SubagentFinishedEvent(
                    run_id=rid, parent_run_id="parent-run",
                    status=_STATUS_MAP.get(raw, raw), ts="t",
                )
            )
        )

    registry = BackgroundTaskRegistry(on_terminal=_on_terminal)

    async def racing_chat(*args: Any, **kwargs: Any) -> LlmResponse:
        await asyncio.sleep(0.05)
        return LlmResponse(
            stop_reason="end_turn", text="raced",
            usage=UsageStats(0, 0, 0, 0, 0.0),
        )

    provider = MagicMock()
    provider.chat = racing_chat
    tool = _make_tool(tmp_path, provider, "parent-run", registry, bus)
    tool._parent_context = ExecutionContext(run_id="parent-run", goal="g", max_steps=5)
    spawn_result = await tool.invoke({
        "description": "racing", "prompt": "race", "run_in_background": True,
    })
    child_id = _extract_run_id(spawn_result.content)
    await asyncio.sleep(0.01)
    await registry.cancel_descendants("parent-run", reason="parent_cancelled")

    record = registry.get(child_id)
    assert record is not None and record.task is not None
    try:
        await asyncio.wait_for(asyncio.shield(record.task), timeout=5.0)
    except (asyncio.CancelledError, Exception):
        pass
    final = registry.query_result(child_id)
    assert final.status in (BackgroundTaskStatus.COMPLETED, BackgroundTaskStatus.CANCELLED)
    # 轮询等待 fire-and-forget 事件落定
    for _ in range(100):
        if finished_events:
            break
        await asyncio.sleep(0.01)
    assert len(finished_events) == 1, f"expected exactly 1 event, got {len(finished_events)}"


# 功能：parent 取消后 registry 无 active 记录残留
# 设计：spawn 多个后台 child，cancel parent，断言无 active 记录
async def test_no_active_task_after_parent_cleanup(tmp_path: Path) -> None:
    registry = BackgroundTaskRegistry()
    bus = EventBus()
    provider = _blocking_provider()
    for i in range(3):
        tool = _make_tool(tmp_path, provider, "parent-run", registry, bus)
        tool._parent_context = ExecutionContext(run_id="parent-run", goal="g", max_steps=5)
        await tool.invoke({
            "description": f"child-{i}", "prompt": f"work-{i}",
            "run_in_background": True,
        })
    await registry.cancel_descendants("parent-run", reason="parent_cancelled")
    active = [r for r in registry.all() if r.is_active]
    assert active == [], f"expected no active tasks, got {active}"


# 功能：registry shutdown 取消所有活动 task 并释放重型引用
# 设计：spawn 后台 child，shutdown，断言 task 与 context 引用均释放
async def test_shutdown_cancels_and_releases(tmp_path: Path) -> None:
    registry = BackgroundTaskRegistry()
    bus = EventBus()
    tool = _make_tool(tmp_path, _blocking_provider(), "parent-run", registry, bus)
    tool._parent_context = ExecutionContext(run_id="parent-run", goal="g", max_steps=5)
    await tool.invoke({
        "description": "child", "prompt": "work", "run_in_background": True,
    })
    await registry.shutdown()
    for record in registry.all():
        assert record.task is None
        assert record.context is None


# 功能：协程未调度就被取消时，on_terminal 回调仍发布唯一终态事件
# 设计：spawn 后台 child 后立即 cancel（task 可能从未跑过 body），注册 on_terminal
#       回调收集事件，断言恰好一个 cancelled 事件发布——防 _run_background 未执行导致事件丢失
async def test_cancel_publishes_terminal_event_when_coroutine_never_ran(tmp_path: Path) -> None:
    bus = EventBus()
    finished_events: list[Any] = []

    async def _collect(e: Any) -> None:
        if isinstance(e, SubagentFinishedEvent):
            finished_events.append(e)

    bus.subscribe(_collect)

    def _on_terminal(rid: str, status: object) -> None:
        raw = status.value if hasattr(status, "value") else str(status)
        # 对齐 runner 的映射：completed→success，保持与前台 spawn 事件契约一致
        event_status = {"completed": "success", "failed": "failed", "cancelled": "cancelled"}.get(
            raw, raw
        )
        asyncio.get_running_loop().create_task(
            bus.publish(
                SubagentFinishedEvent(
                    run_id=rid, parent_run_id="parent-run",
                    status=event_status, ts="t",
                )
            )
        )

    registry = BackgroundTaskRegistry(on_terminal=_on_terminal)
    tool = _make_tool(tmp_path, _blocking_provider(), "parent-run", registry, bus)
    tool._parent_context = ExecutionContext(run_id="parent-run", goal="g", max_steps=5)
    await tool.invoke({"description": "child", "prompt": "work", "run_in_background": True})

    # 立即取消（task body 可能尚未首次调度）
    await registry.cancel_descendants("parent-run", reason="parent_cancelled")
    # 轮询等待 on_terminal 回调的 fire-and-forget publish task 落定
    for _ in range(100):
        if finished_events:
            break
        await asyncio.sleep(0.01)

    assert len(finished_events) == 1, f"expected 1 finished event, got {len(finished_events)}"
    assert finished_events[0].status == "cancelled"


# ---- runner 级集成测试：普通 run 不 shutdown registry + 终态事件可靠 await ----


# 让 root agent 第一步 spawn 后台子（立即完成）、第二步 end_turn 的 provider
def _spawning_provider() -> Any:
    spawn_call = ToolCallBlock(
        id="sp1", name="spawn_agent",
        input={"description": "child", "prompt": "do work", "run_in_background": True},
    )
    state = {"spawned": False}

    async def chat(messages: list[dict[str, object]], **kwargs: Any) -> LlmResponse:
        if not state["spawned"]:
            state["spawned"] = True
            return LlmResponse(
                stop_reason="tool_use", tool_calls=[spawn_call], text="",
                usage=UsageStats(0, 0, 0, 0, 0.0),
            )
        return LlmResponse(
            stop_reason="end_turn", text="root done", usage=UsageStats(0, 0, 0, 0, 0.0)
        )

    provider = MagicMock()
    provider.chat = chat
    return provider


def _read_event_types(events_path: Path) -> list[str]:
    return [
        json.loads(line)["type"]
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line
    ]


# 功能：普通 run 结束后 registry 未被 shutdown，终态子结果在 TTL 内仍可查询
# 设计：用 AgentRunner 跑一次 spawn 后台子 + end_turn 的 run，结束后断言 registry 未 shutdown
#       且子结果可查询（status=completed）
async def test_normal_run_does_not_shutdown_registry(tmp_path: Path) -> None:
    cfg = SztuConfig()
    cfg.agent.max_steps = 5
    runner = AgentRunner(cfg, provider=_spawning_provider(), runs_dir=tmp_path)
    await runner.run_and_capture("goal", run_id="run-normal")

    # registry 未被 shutdown：_shutdown_done 仍为 False，结果保留
    assert runner._task_registry._shutdown_done is False  # noqa: SLF001
    # 子 agent 记录仍在（未被 reclaim），可查询
    records = [r for r in runner._task_registry.all() if r.status is BackgroundTaskStatus.COMPLETED]  # noqa: SLF001
    assert len(records) == 1


# 功能：同一 runner 顺序运行两次，registry 不被普通 run 永久 shutdown
# 设计：连续两次 run_and_capture，断言 registry 仍可注册（_shutdown_done=False），
#       证明普通 run 收尾未把 registry 置为 shutdown 状态
async def test_runner_reusable_across_runs(tmp_path: Path) -> None:
    cfg = SztuConfig()
    cfg.agent.max_steps = 5
    runner = AgentRunner(cfg, provider=_spawning_provider(), runs_dir=tmp_path)
    await runner.run_and_capture("goal1", run_id="run-1")
    await runner.run_and_capture("goal2", run_id="run-2")
    # 普通 run 不 shutdown：registry 仍可注册新任务
    assert runner._task_registry._shutdown_done is False  # noqa: SLF001
    # 第一轮的 completed 记录仍保留（TTL 内未回收）
    completed = [r for r in runner._task_registry.all() if r.status is BackgroundTaskStatus.COMPLETED]  # noqa: SLF001
    assert len(completed) == 1


# 功能：runner 显式 shutdown 取消活跃子任务并释放重型引用，且可重复调用
# 设计：spawn 后台阻塞子后 shutdown 两次，断言 task/context 释放且无异常
async def test_runner_shutdown_cancels_and_idempotent(tmp_path: Path) -> None:
    cfg = SztuConfig()
    cfg.agent.max_steps = 5
    blocking = _blocking_provider()
    runner = AgentRunner(cfg, provider=blocking, runs_dir=tmp_path)
    # 用 spawn 工具注册一个阻塞子（不走完整 run，直接构造工具）
    bus = EventBus()
    tool = SpawnAgentTool(
        provider=blocking, parent_bus=bus, parent_run_id="root",
        permission_manager=None, max_steps=5,
        task_registry=runner._task_registry, runs_dir=tmp_path,
        session_id="s", max_depth=3,
    )  # noqa: SLF001
    tool._parent_context = ExecutionContext(run_id="root", goal="g", max_steps=5)  # noqa: SLF001
    await tool.invoke({"description": "child", "prompt": "work", "run_in_background": True})

    await runner.shutdown()
    await runner.shutdown()  # 重复调用不报错
    for record in runner._task_registry.all():  # noqa: SLF001
        assert record.task is None
        assert record.context is None


# 功能：子任务正常完成时 subagent.finished 恰好一个，且在 run.finished 之前落盘
# 设计：用 AgentRunner 跑 spawn 后台子 + end_turn，读取 events.jsonl 断言事件顺序
async def test_subagent_finished_before_run_finished(tmp_path: Path) -> None:
    cfg = SztuConfig()
    cfg.agent.max_steps = 5
    runner = AgentRunner(cfg, provider=_spawning_provider(), runs_dir=tmp_path)
    await runner.run_and_capture("goal", run_id="run-order")
    # 找到 root run 的 events.jsonl
    jsonl = tmp_path / "run-order" / "events.jsonl"
    types = _read_event_types(jsonl)
    assert types.count("subagent.finished") == 1, f"events: {types}"
    assert types.count("run.finished") == 1
    # subagent.finished 必须在 run.finished 之前
    assert types.index("subagent.finished") < types.index("run.finished")


# 功能：子任务在协程首次调度前被取消，仍有一个可观察的 subagent.finished（runner 级）
# 设计：root spawn 后台阻塞子后，cancel root run；断言 events.jsonl 恰好一个 cancelled 事件
async def test_cancelled_run_emits_subagent_finished(tmp_path: Path) -> None:
    cfg = SztuConfig()
    cfg.agent.max_steps = 5
    spawn_call = ToolCallBlock(
        id="sp1", name="spawn_agent",
        input={"description": "child", "prompt": "work", "run_in_background": True},
    )
    state = {"spawned": False}

    async def chat(messages: list[dict[str, object]], **kwargs: Any) -> LlmResponse:
        if not state["spawned"]:
            state["spawned"] = True
            return LlmResponse(
                stop_reason="tool_use", tool_calls=[spawn_call], text="",
                usage=UsageStats(0, 0, 0, 0, 0.0),
            )
        await asyncio.Event().wait()  # root 阻塞等被 cancel
        return LlmResponse(stop_reason="end_turn", text="", usage=UsageStats(0, 0, 0, 0, 0.0))

    provider = MagicMock()
    provider.chat = chat
    runner = AgentRunner(cfg, provider=provider, runs_dir=tmp_path)
    run_task = asyncio.create_task(
        runner.run_and_capture("goal", run_id="run-cancel")
    )
    # 等 spawn 发生
    for _ in range(100):
        if state["spawned"]:
            break
        await asyncio.sleep(0.01)
    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        pass

    jsonl = tmp_path / "run-cancel" / "events.jsonl"
    types = _read_event_types(jsonl)
    finished = [t for t in types if t == "subagent.finished"]
    assert len(finished) == 1, f"expected 1 subagent.finished, events: {types}"
    # 验证 status 为 cancelled（读取完整事件）
    raw = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line]
    sub_events = [e for e in raw if e.get("type") == "subagent.finished"]
    assert sub_events[0]["status"] == "cancelled"


# ---- P0 必增测试：interrupted 父 run 必须取消后台后代 ----


# 让 root 第一步 spawn 后台阻塞子、然后耗尽 max_steps 变 interrupted 的 provider
def _spawn_then_loop_provider() -> Any:
    spawn_call = ToolCallBlock(
        id="sp1", name="spawn_agent",
        input={"description": "child", "prompt": "work", "run_in_background": True},
    )
    state = {"spawned": False}

    async def chat(messages: list[dict[str, object]], **kwargs: Any) -> LlmResponse:
        if not state["spawned"]:
            state["spawned"] = True
            return LlmResponse(
                stop_reason="tool_use", tool_calls=[spawn_call], text="",
                usage=UsageStats(0, 0, 0, 0, 0.0),
            )
        # 后续每步都调未知工具，耗尽 max_steps
        return LlmResponse(
            stop_reason="tool_use", tool_calls=[ToolCallBlock(id="t", name="unknown_tool", input={})],
            text="", usage=UsageStats(0, 0, 0, 0, 0.0),
        )

    provider = MagicMock()
    provider.chat = chat
    return provider


# 功能：max_steps 中断时 root 立即结束并取消永不返回的后台 child
# 设计：root spawn 阻塞后台子后耗尽 max_steps→interrupted，断言 root 确定性上限内结束、
#       child 被 cancel_descendants 取消且记录为 CANCELLED
async def test_max_steps_interrupt_cancels_blocking_child(tmp_path: Path) -> None:
    cfg = SztuConfig()
    cfg.agent.max_steps = 3
    runner = AgentRunner(cfg, provider=_spawn_then_loop_provider(), runs_dir=tmp_path)
    # root 在 max_steps 内结束（不卡在 _wait_for_background），确定性上限
    outcome = await asyncio.wait_for(
        runner.run_and_capture("goal", run_id="run-maxsteps"), timeout=10.0
    )
    assert outcome.status == "interrupted"
    assert outcome.reason == "exceeded_max_steps"
    # 后台 child 被取消
    cancelled = [r for r in runner._task_registry.all() if r.status is BackgroundTaskStatus.CANCELLED]  # noqa: SLF001
    assert len(cancelled) == 1


# 功能：wall_clock 中断时同样取消后台 child
# 设计：max_wall_clock_s=1 触发非 max_steps 的非成功终态，验证 child 被取消。
#       provider 后续返回 tool_use 但调用只读工具避免触发 repeated_error，让 wall_clock 优先
async def test_wall_clock_interrupt_cancels_child(tmp_path: Path) -> None:
    spawn_call = ToolCallBlock(
        id="sp1", name="spawn_agent",
        input={"description": "child", "prompt": "work", "run_in_background": True},
    )
    state = {"spawned": False}

    async def chat(messages: list[dict[str, object]], **kwargs: Any) -> LlmResponse:
        if not state["spawned"]:
            state["spawned"] = True
            return LlmResponse(
                stop_reason="tool_use", tool_calls=[spawn_call], text="",
                usage=UsageStats(0, 0, 0, 0, 0.0),
            )
        # 后续每步调 list_dir（只读，不触发 repeated_error），让 wall_clock 触发
        await asyncio.sleep(0.05)
        return LlmResponse(
            stop_reason="tool_use", tool_calls=[ToolCallBlock(id="t", name="list_dir", input={"path": "."})],
            text="", usage=UsageStats(0, 0, 0, 0, 0.0),
        )

    provider = MagicMock()
    provider.chat = chat
    cfg = SztuConfig()
    cfg.agent.max_steps = 100  # 不靠 max_steps 触发
    cfg.budget.max_wall_clock_s = 1
    runner = AgentRunner(cfg, provider=provider, runs_dir=tmp_path)
    outcome = await asyncio.wait_for(
        runner.run_and_capture("goal", run_id="run-wallclock", workspace_root=tmp_path), timeout=20.0
    )
    # 非成功终态（wall_clock 中断或 repeated_error），都应取消/清理 child
    assert outcome.status != "success"
    # 无遗留 active task（child 被取消或已完成，不应仍 running）
    active = [r for r in runner._task_registry.all() if r.is_active]  # noqa: SLF001
    assert active == [], f"expected no active tasks, got {active}"


# 功能：递归场景——root 的 child 派生阻塞 grandchild，root 中断后两者均取消
# 设计：root spawn 后台 child，child 首步派生后台 grandchild 后阻塞；root 等 grandchild 派生后
#       耗尽 max_steps 中断，断言 child 和 grandchild 均被取消、无遗留 active task
async def test_interrupt_cancels_recursive_descendants(tmp_path: Path) -> None:
    cfg = SztuConfig()
    cfg.agent.max_steps = 6  # 给 child 足够时间派生 grandchild
    grandchild_spawn = ToolCallBlock(
        id="gc1", name="spawn_agent",
        input={"description": "grandchild", "prompt": "gc work", "run_in_background": True},
    )
    root_state = {"spawned": False}
    grandchild_spawned = asyncio.Event()

    async def chat(messages: list[dict[str, object]], **kwargs: Any) -> LlmResponse:
        # 按首条 user 消息分流 root vs child vs grandchild
        first_user = next(
            (str(m["content"]) for m in messages
             if m["role"] == "user" and isinstance(m["content"], str)), ""
        )
        # grandchild：永久阻塞
        if first_user == "gc work":
            await asyncio.Event().wait()
            return LlmResponse(stop_reason="end_turn", text="", usage=UsageStats(0, 0, 0, 0, 0.0))
        # child：首步派生 grandchild 后阻塞
        if first_user == "child work":
            if not any(
                isinstance(b, dict) and b.get("name") == "spawn_agent"
                for m in messages if m["role"] == "assistant" and isinstance(m["content"], list)
                for b in m["content"]
            ):
                grandchild_spawned.set()  # 通知 root：grandchild 已派生
                return LlmResponse(
                    stop_reason="tool_use", tool_calls=[grandchild_spawn], text="",
                    usage=UsageStats(0, 0, 0, 0, 0.0),
                )
            await asyncio.Event().wait()
            return LlmResponse(stop_reason="end_turn", text="", usage=UsageStats(0, 0, 0, 0, 0.0))
        # root：首步 spawn child，等 grandchild 派生后耗尽 max_steps
        if not root_state["spawned"]:
            root_state["spawned"] = True
            return LlmResponse(
                stop_reason="tool_use", tool_calls=[ToolCallBlock(
                    id="sp1", name="spawn_agent",
                    input={"description": "child", "prompt": "child work", "run_in_background": True},
                )], text="", usage=UsageStats(0, 0, 0, 0, 0.0),
            )
        # 等 grandchild 派生后再继续（避免 root 过早失败时 child 还没派生）
        await asyncio.wait_for(grandchild_spawned.wait(), timeout=5.0)
        return LlmResponse(
            stop_reason="tool_use", tool_calls=[ToolCallBlock(id="t", name="unknown_tool", input={})],
            text="", usage=UsageStats(0, 0, 0, 0, 0.0),
        )

    provider = MagicMock()
    provider.chat = chat
    runner = AgentRunner(cfg, provider=provider, runs_dir=tmp_path)
    outcome = await asyncio.wait_for(
        runner.run_and_capture("goal", run_id="run-recursive"), timeout=20.0
    )
    # 非成功终态（max_steps 中断或 repeated_error 失败）都应递归取消后代
    assert outcome.status != "success"
    # 无遗留 active task
    active = [r for r in runner._task_registry.all() if r.is_active]  # noqa: SLF001
    assert active == [], f"expected no active tasks, got {active}"
    # child 和 grandchild 都被取消
    cancelled = [r for r in runner._task_registry.all() if r.status is BackgroundTaskStatus.CANCELLED]  # noqa: SLF001
    assert len(cancelled) >= 2


# 功能：中断场景的 events.jsonl 中每个 child 恰好一条 subagent.finished(cancelled)，早于 run.finished
# 设计：复用 max_steps 中断场景，读取 events.jsonl 断言事件顺序与唯一性
async def test_interrupt_event_order_and_uniqueness(tmp_path: Path) -> None:
    cfg = SztuConfig()
    cfg.agent.max_steps = 2
    runner = AgentRunner(cfg, provider=_spawn_then_loop_provider(), runs_dir=tmp_path)
    await asyncio.wait_for(
        runner.run_and_capture("goal", run_id="run-order-int"), timeout=15.0
    )
    jsonl = tmp_path / "run-order-int" / "events.jsonl"
    raw = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line]
    types = [e["type"] for e in raw]
    sub_finished = [i for i, t in enumerate(types) if t == "subagent.finished"]
    run_finished_idx = types.index("run.finished")
    assert len(sub_finished) == 1
    assert sub_finished[0] < run_finished_idx
    sub_event = raw[sub_finished[0]]
    assert sub_event["status"] == "cancelled"


# 功能：正常成功路径仍等待后台 child 并把摘要并入结果（P0 回归保护）
# 设计：root spawn 后台子（立即完成）、end_turn，断言 root success 且 result 含子摘要
async def test_success_path_still_waits_for_child(tmp_path: Path) -> None:
    spawn_call = ToolCallBlock(
        id="sp1", name="spawn_agent",
        input={"description": "child", "prompt": "do work", "run_in_background": True},
    )
    state = {"spawned": False}

    async def chat(messages: list[dict[str, object]], **kwargs: Any) -> LlmResponse:
        if not state["spawned"]:
            state["spawned"] = True
            return LlmResponse(
                stop_reason="tool_use", tool_calls=[spawn_call], text="",
                usage=UsageStats(0, 0, 0, 0, 0.0),
            )
        return LlmResponse(
            stop_reason="end_turn", text="root done", usage=UsageStats(0, 0, 0, 0, 0.0)
        )

    provider = MagicMock()
    provider.chat = chat
    cfg = SztuConfig()
    cfg.agent.max_steps = 5
    runner = AgentRunner(cfg, provider=provider, runs_dir=tmp_path)
    outcome = await asyncio.wait_for(
        runner.run_and_capture("goal", run_id="run-success"), timeout=10.0
    )
    assert outcome.status == "success"
    # 后台子完成（非取消），保留记录
    completed = [r for r in runner._task_registry.all() if r.status is BackgroundTaskStatus.COMPLETED]  # noqa: SLF001
    assert len(completed) == 1


# ---- P1 必增测试：终态事件所有权按 parent_run_id 绑定 ----


# 功能：两个不同 parent 的 child 终态事件只发到各自注册的 sink
# 设计：registry 注册两个 parent 的 sink（A 和 B），分别 mark_terminal 各自的 child，
#       断言 A 的 child 事件只进 A 的 sink，B 的只进 B 的
async def test_terminal_sink_routed_by_parent_run_id() -> None:
    a_events: list[str] = []
    b_events: list[str] = []

    def _sink_a(rid: str, status: object) -> None:
        a_events.append(rid)

    def _sink_b(rid: str, status: object) -> None:
        b_events.append(rid)

    registry = BackgroundTaskRegistry()
    registry.register_sink("parent-a", _sink_a)
    registry.register_sink("parent-b", _sink_b)

    # 注册两个不同 parent 的 child，owner_run_id 默认回退为 parent_run_id
    task_a = asyncio.create_task(asyncio.sleep(0))
    task_b = asyncio.create_task(asyncio.sleep(0))
    await task_a
    await task_b
    registry.register("child-a", "parent-a", task_a, ExecutionContext(run_id="child-a", goal="g", max_steps=1))
    registry.register("child-b", "parent-b", task_b, ExecutionContext(run_id="child-b", goal="g", max_steps=1))

    # grandchild：parent=child-a 但 owner=parent-a，验证按 owner 路由而非 parent
    task_ga = asyncio.create_task(asyncio.sleep(0))
    await task_ga
    registry.register(
        "grandchild-a", "child-a", task_ga,
        ExecutionContext(run_id="grandchild-a", goal="g", max_steps=1),
        owner_run_id="parent-a",
    )

    registry.mark_terminal("child-a", BackgroundTaskStatus.COMPLETED, detail="a done")
    registry.mark_terminal("child-b", BackgroundTaskStatus.FAILED, reason="b fail")
    registry.mark_terminal("grandchild-a", BackgroundTaskStatus.CANCELLED, reason="parent_interrupted")

    # child-a 和 grandchild-a 都路由到 A sink（按 owner_run_id 而非直接 parent）
    assert a_events == ["child-a", "grandchild-a"], f"A sink got: {a_events}"
    assert b_events == ["child-b"], f"B sink got: {b_events}"


# ---- P1 端到端测试：递归后代的 subagent.finished 不丢失 ----


# 功能：root 中断时 child 和 grandchild 各产生一条 subagent.finished(cancelled)，
#       parent_run_id 正确（child→root, grandchild→child），全在 run.finished 前，无重复
# 设计：root spawn 后台 child，child 派生后台 grandchild（均阻塞），root max_steps 中断；
#       读取 root events.jsonl 断言两条 finished 事件、parent 关系、顺序、唯一性
async def test_recursive_cancel_emits_finished_for_all_descendants(tmp_path: Path) -> None:
    cfg = SztuConfig()
    cfg.agent.max_steps = 6
    grandchild_spawn = ToolCallBlock(
        id="gc1", name="spawn_agent",
        input={"description": "grandchild", "prompt": "gc work", "run_in_background": True},
    )
    root_state = {"spawned": False}
    grandchild_spawned = asyncio.Event()

    async def chat(messages: list[dict[str, object]], **kwargs: Any) -> LlmResponse:
        first_user = next(
            (str(m["content"]) for m in messages
             if m["role"] == "user" and isinstance(m["content"], str)), ""
        )
        if first_user == "gc work":
            await asyncio.Event().wait()
            return LlmResponse(stop_reason="end_turn", text="", usage=UsageStats(0, 0, 0, 0, 0.0))
        if first_user == "child work":
            if not any(
                isinstance(b, dict) and b.get("name") == "spawn_agent"
                for m in messages if m["role"] == "assistant" and isinstance(m["content"], list)
                for b in m["content"]
            ):
                grandchild_spawned.set()
                return LlmResponse(
                    stop_reason="tool_use", tool_calls=[grandchild_spawn], text="",
                    usage=UsageStats(0, 0, 0, 0, 0.0),
                )
            await asyncio.Event().wait()
            return LlmResponse(stop_reason="end_turn", text="", usage=UsageStats(0, 0, 0, 0, 0.0))
        if not root_state["spawned"]:
            root_state["spawned"] = True
            return LlmResponse(
                stop_reason="tool_use", tool_calls=[ToolCallBlock(
                    id="sp1", name="spawn_agent",
                    input={"description": "child", "prompt": "child work", "run_in_background": True},
                )], text="", usage=UsageStats(0, 0, 0, 0, 0.0),
            )
        await asyncio.wait_for(grandchild_spawned.wait(), timeout=5.0)
        return LlmResponse(
            stop_reason="tool_use", tool_calls=[ToolCallBlock(id="t", name="unknown_tool", input={})],
            text="", usage=UsageStats(0, 0, 0, 0, 0.0),
        )

    provider = MagicMock()
    provider.chat = chat
    runner = AgentRunner(cfg, provider=provider, runs_dir=tmp_path)
    await asyncio.wait_for(
        runner.run_and_capture("goal", run_id="run-recursive-events"), timeout=20.0
    )

    raw = [json.loads(line) for line in (tmp_path / "run-recursive-events" / "events.jsonl")
           .read_text(encoding="utf-8").splitlines() if line]
    types = [e["type"] for e in raw]
    sub_finished = [e for e in raw if e["type"] == "subagent.finished"]
    run_finished_idx = types.index("run.finished")

    # 两条 finished（child 和 grandchild 各一），run_id 不重复
    assert len(sub_finished) == 2, f"expected 2 finished, got {len(sub_finished)}: {sub_finished}"
    run_ids = [e["run_id"] for e in sub_finished]
    assert len(set(run_ids)) == 2, f"run_ids not unique: {run_ids}"
    # parent_run_id 正确：child 的 parent=root，grandchild 的 parent=child
    root_id = "run-recursive-events"
    by_parent = {e["parent_run_id"]: e for e in sub_finished}
    assert root_id in by_parent, f"no child with parent=root: {by_parent}"
    child_id = by_parent[root_id]["run_id"]
    assert child_id in by_parent, f"no grandchild with parent=child: {by_parent}"
    # 两条 status 都为 cancelled
    assert all(e["status"] == "cancelled" for e in sub_finished), \
        f"expected all cancelled: {sub_finished}"
    # 两条 finished 都在 run.finished 之前
    for i, e in enumerate(raw):
        if e["type"] == "subagent.finished":
            assert i < run_finished_idx, f"finished at {i} after run.finished at {run_finished_idx}"


# 功能：嵌套成功场景——child 完成 grandchild，两者各一条 success finished，归属 root 事件输出
# 设计：root spawn 后台 child，child 等 grandchild 完成后 end_turn 成功；
#       断言 child 和 grandchild 各一条 subagent.finished(success)
async def test_recursive_success_emits_finished_for_all_descendants(tmp_path: Path) -> None:
    cfg = SztuConfig()
    cfg.agent.max_steps = 8
    grandchild_spawn = ToolCallBlock(
        id="gc1", name="spawn_agent",
        input={"description": "grandchild", "prompt": "gc work", "run_in_background": True},
    )

    async def chat(messages: list[dict[str, object]], **kwargs: Any) -> LlmResponse:
        first_user = next(
            (str(m["content"]) for m in messages
             if m["role"] == "user" and isinstance(m["content"], str)), ""
        )
        # grandchild：立即完成
        if first_user == "gc work":
            return LlmResponse(
                stop_reason="end_turn", text="grandchild done",
                usage=UsageStats(0, 0, 0, 0, 0.0),
            )
        # child：首步 spawn 后台 grandchild，第二步 end_turn 成功
        if first_user == "child work":
            if not any(
                isinstance(b, dict) and b.get("name") == "spawn_agent"
                for m in messages if m["role"] == "assistant" and isinstance(m["content"], list)
                for b in m["content"]
            ):
                return LlmResponse(
                    stop_reason="tool_use", tool_calls=[grandchild_spawn], text="",
                    usage=UsageStats(0, 0, 0, 0, 0.0),
                )
            return LlmResponse(
                stop_reason="end_turn", text="child done",
                usage=UsageStats(0, 0, 0, 0, 0.0),
            )
        # root：spawn 后台 child，然后 end_turn 成功
        if not any(
            isinstance(b, dict) and b.get("name") == "spawn_agent"
            for m in messages if m["role"] == "assistant" and isinstance(m["content"], list)
            for b in m["content"]
        ):
            return LlmResponse(
                stop_reason="tool_use", tool_calls=[ToolCallBlock(
                    id="sp1", name="spawn_agent",
                    input={"description": "child", "prompt": "child work", "run_in_background": True},
                )], text="", usage=UsageStats(0, 0, 0, 0, 0.0),
            )
        return LlmResponse(
            stop_reason="end_turn", text="root done", usage=UsageStats(0, 0, 0, 0, 0.0)
        )

    provider = MagicMock()
    provider.chat = chat
    runner = AgentRunner(cfg, provider=provider, runs_dir=tmp_path)
    outcome = await asyncio.wait_for(
        runner.run_and_capture("goal", run_id="run-recursive-success"), timeout=20.0
    )
    assert outcome.status == "success"

    raw = [json.loads(line) for line in (tmp_path / "run-recursive-success" / "events.jsonl")
           .read_text(encoding="utf-8").splitlines() if line]
    sub_finished = [e for e in raw if e["type"] == "subagent.finished"]
    # child 和 grandchild 各一条 success
    assert len(sub_finished) == 2, f"expected 2 finished, got {len(sub_finished)}"
    assert all(e["status"] == "success" for e in sub_finished), \
        f"expected all success: {sub_finished}"
    run_ids = [e["run_id"] for e in sub_finished]
    assert len(set(run_ids)) == 2
