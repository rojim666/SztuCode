"""End-to-end consistency coverage for a Run terminated by the wall-clock deadline.

These tests verify the ADR 0004 claim that timeout state, reason, cleanup result and
the terminal event can be *consistently verified* — asserted together rather than in
isolated per-stage tests.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from sztu_code.core.config import SztuConfig
from sztu_code.core.llm.types import LlmResponse, ToolCallBlock, UsageStats
from sztu_code.core.runner import AgentRunner
from sztu_code.core.subagent.registry import BackgroundTaskStatus
from sztu_code.core.trace.writer import TraceWriter

_RUN_ID = "run-lifecycle"


def _blocking_provider() -> Any:
    """Blocks until cancelled, so the deadline lands inside the LLM request."""

    async def chat(*_args: Any, **_kwargs: Any) -> LlmResponse:
        await asyncio.Future()
        raise AssertionError("unreachable")  # pragma: no cover

    provider = MagicMock()
    provider.chat = chat
    return provider


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


async def _run_deadline_scenario(
    tmp_path: Path, *, provider: Any
) -> tuple[Any, list[dict[str, Any]], list[dict[str, Any]]]:
    """Drive one deadline-terminated run; return (outcome, events, trace records)."""
    trace_path = tmp_path / "trace.jsonl"
    writer = TraceWriter(trace_path)
    await writer.start()

    cfg = SztuConfig()
    cfg.agent.max_steps = 100  # 不靠 max_steps 触发
    cfg.budget.max_wall_clock_s = 1
    runner = AgentRunner(cfg, provider=provider, runs_dir=tmp_path, trace=writer)

    outcome = await asyncio.wait_for(
        runner.run_and_capture("goal", run_id=_RUN_ID, workspace_root=tmp_path),
        timeout=20.0,
    )
    await writer.stop()

    events = _read_jsonl(tmp_path / _RUN_ID / "events.jsonl")
    return outcome, events, _read_jsonl(trace_path)


# 功能：验证 deadline 终止时事件流与 Trace 的终态原因一致，且都只有一个终态
# 设计：阻塞 provider + 1 秒预算；断言 events.jsonl 中 run.finished 恰好一条且
#       status/reason 正确，trace 中 deadline 记录恰好一条且 reason 与之一致。
async def test_deadline_terminal_event_and_trace_agree(
    tmp_path: Path,
) -> None:
    outcome, events, trace_records = await _run_deadline_scenario(
        tmp_path, provider=_blocking_provider()
    )

    # --- 事件流：唯一终态 ---
    types = [e.get("type") for e in events]
    assert types.count("run.finished") == 1, (
        f"expected exactly 1 run.finished, got {types.count('run.finished')}: {types}"
    )
    run_finished = next(e for e in events if e.get("type") == "run.finished")
    assert run_finished["status"] == "interrupted"
    assert run_finished["reason"] == "max_wall_clock_exceeded"
    assert outcome.status == run_finished["status"]
    assert outcome.reason == run_finished["reason"]

    # --- Trace：唯一 deadline 记录，且原因与终态事件一致 ---
    deadline_records = [r for r in trace_records if r.get("kind") == "deadline"]
    assert len(deadline_records) == 1, (
        f"expected exactly 1 deadline record, got {len(deadline_records)}; "
        f"kinds present: {[r.get('kind') for r in trace_records]}"
    )
    record = deadline_records[0]
    assert record["run_id"] == _RUN_ID
    assert record["data"]["reason"] == run_finished["reason"]


def _spawn_then_loop_provider(root_id: str) -> Any:
    """Parent spawns one blocking background child, then keeps stepping."""
    spawn_call = ToolCallBlock(
        id="sp1",
        name="spawn_agent",
        input={"description": "child", "prompt": "work", "run_in_background": True},
    )
    state = {"spawned": False}

    async def chat(*args: Any, **kwargs: Any) -> LlmResponse:
        # run_id 有两种到达方式：AgentLoop 直接调用时是 kwarg；经 TracingProvider
        # 包装时是第 4 个位置参数（messages, tool_schemas, bus, run_id）。两种都要认。
        run_id = kwargs.get("run_id")
        if run_id is None and len(args) >= 4:
            run_id = args[3]
        if run_id != root_id:
            # 子 Agent 的调用：阻塞到被取消
            await asyncio.Future()
            raise AssertionError("unreachable")  # pragma: no cover
        if not state["spawned"]:
            state["spawned"] = True
            return LlmResponse(
                stop_reason="tool_use", tool_calls=[spawn_call], text="",
                usage=UsageStats(0, 0, 0, 0, 0.0),
            )
        # 后续每步调只读工具并稍作等待，让 wall_clock 先于 max_steps 触发
        await asyncio.sleep(0.05)
        return LlmResponse(
            stop_reason="tool_use",
            tool_calls=[ToolCallBlock(id="t", name="list_dir", input={"path": "."})],
            text="",
            usage=UsageStats(0, 0, 0, 0, 0.0),
        )

    provider = MagicMock()
    provider.chat = chat
    return provider


# 功能：验证 deadline 中断时子 Agent 终态事件先于父终态落盘，且无残留活动记录
# 设计：root spawn 阻塞后台子 + 1 秒 wall_clock 预算；断言 events.jsonl 中
#       subagent.finished 恰好一个且早于唯一的 run.finished，registry 无 active 记录，
#       且 trace 的 deadline 记录清理结果为 cancelled_bounded。
async def test_deadline_child_terminal_precedes_run_finished(
    tmp_path: Path,
) -> None:
    trace_path = tmp_path / "trace.jsonl"
    writer = TraceWriter(trace_path)
    await writer.start()

    cfg = SztuConfig()
    cfg.agent.max_steps = 100  # 不靠 max_steps 触发
    cfg.budget.max_wall_clock_s = 1
    runner = AgentRunner(
        cfg, provider=_spawn_then_loop_provider(_RUN_ID), runs_dir=tmp_path, trace=writer
    )

    outcome = await asyncio.wait_for(
        runner.run_and_capture("goal", run_id=_RUN_ID, workspace_root=tmp_path),
        timeout=20.0,
    )
    await writer.stop()

    assert outcome.status == "interrupted"
    assert outcome.reason == "max_wall_clock_exceeded"

    # --- 事件顺序：子终态先于父终态，且各只有一个 ---
    types = [e.get("type") for e in _read_jsonl(tmp_path / _RUN_ID / "events.jsonl")]
    assert types.count("subagent.finished") == 1, f"events: {types}"
    assert types.count("run.finished") == 1, f"events: {types}"
    assert types.index("subagent.finished") < types.index("run.finished")

    # --- 无残留活动记录 ---
    active = [r for r in runner._task_registry.all() if r.is_active]  # noqa: SLF001
    assert active == [], f"expected no active records, got {active}"
    cancelled = [
        r for r in runner._task_registry.all() if r.status is BackgroundTaskStatus.CANCELLED
    ]
    assert len(cancelled) == 1

    # --- Trace 与事件流一致 ---
    deadline_records = [r for r in _read_jsonl(trace_path) if r.get("kind") == "deadline"]
    assert len(deadline_records) == 1
    assert deadline_records[0]["data"]["cleanup"] == "cancelled_bounded"
    assert deadline_records[0]["data"]["reason"] == outcome.reason


# 功能：验证 deadline 终止的 run 在预算 + margin 内结束
# 设计：阻塞 provider + 1 秒预算；断言 run 在 1.3 秒内结束（Issue #69 验收标准：
#      "使用可取消的 slow fake provider/tool 时，run 在预算后 200 ms 内结束"）。
async def test_deadline_run_finishes_within_budget_margin(
    tmp_path: Path,
) -> None:
    cfg = SztuConfig()
    cfg.agent.max_steps = 100
    cfg.budget.max_wall_clock_s = 1
    runner = AgentRunner(cfg, provider=_blocking_provider(), runs_dir=tmp_path)

    started = time.monotonic()
    outcome = await asyncio.wait_for(
        runner.run_and_capture("goal", run_id=_RUN_ID, workspace_root=tmp_path),
        timeout=20.0,
    )
    elapsed = time.monotonic() - started

    assert outcome.reason == "max_wall_clock_exceeded"
    assert elapsed <= 1.2, f"run overshot its 1s budget by {elapsed - 1:.3f}s"
