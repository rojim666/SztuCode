from __future__ import annotations

import asyncio

import pytest

from sztu_code.core.context import ExecutionContext
from sztu_code.core.subagent.registry import BackgroundTaskRegistry, BackgroundTaskStatus


@pytest.mark.parametrize("started", [False, True])
async def test_parent_cause_wins_regardless_of_terminal_publisher(started: bool) -> None:
    notifications = []
    registry = BackgroundTaskRegistry(on_terminal=lambda run_id, status: notifications.append(
        (run_id, status, registry.query_result(run_id).reason)
    ))
    ready = asyncio.Event()

    async def child() -> None:
        ready.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            registry.mark_terminal("child", BackgroundTaskStatus.CANCELLED, reason="cancelled")
            raise

    task = asyncio.create_task(child())
    registry.register("child", "parent", task, ExecutionContext(run_id="child", goal="test", max_steps=5))
    if started:
        await ready.wait()
    await registry.cancel_descendants("parent", reason="max_wall_clock_exceeded")
    assert task.done()
    assert registry.query_result("child").reason == "max_wall_clock_exceeded"
    assert notifications == [("child", BackgroundTaskStatus.CANCELLED, "max_wall_clock_exceeded")]
    assert not registry.mark_terminal("child", BackgroundTaskStatus.CANCELLED, reason="later")


async def test_concurrent_cancellations_preserve_first_cause() -> None:
    registry = BackgroundTaskRegistry()
    ready = asyncio.Event()
    cancelling = asyncio.Event()

    async def child() -> None:
        ready.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelling.set()
            try:
                await asyncio.Event().wait()
            finally:
                registry.mark_terminal("child", BackgroundTaskStatus.CANCELLED, reason="cancelled")
            raise

    task = asyncio.create_task(child())
    registry.register("child", "parent", task, ExecutionContext(run_id="child", goal="test", max_steps=5))
    await ready.wait()
    first = asyncio.create_task(registry.cancel_descendants("parent", reason="deadline"))
    await cancelling.wait()
    second = asyncio.create_task(registry.cancel_descendants("parent", reason="shutdown"))
    await asyncio.wait_for(asyncio.gather(first, second), timeout=2)
    assert registry.query_result("child").reason == "deadline"


@pytest.mark.parametrize("outcome", [BackgroundTaskStatus.COMPLETED, BackgroundTaskStatus.FAILED])
async def test_cancel_cause_does_not_overwrite_other_terminal_outcomes(outcome: BackgroundTaskStatus) -> None:
    registry = BackgroundTaskRegistry()
    ready = asyncio.Event()

    async def child() -> None:
        ready.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            registry.mark_terminal("child", outcome, detail="original result")

    task = asyncio.create_task(child())
    registry.register("child", "parent", task, ExecutionContext(run_id="child", goal="test", max_steps=5))
    await ready.wait()
    await registry.cancel_descendants("parent", reason="deadline")
    result = registry.query_result("child")
    assert result.status == outcome and result.reason == "original result"


async def test_child_own_cancellation_cause_unchanged() -> None:
    registry = BackgroundTaskRegistry()

    async def child() -> None:
        registry.mark_terminal("child", BackgroundTaskStatus.CANCELLED, reason="own_deadline")

    task = asyncio.create_task(child())
    registry.register("child", "parent", task, ExecutionContext(run_id="child", goal="test", max_steps=5))
    await task
    await registry.cancel_descendants("parent", reason="parent_deadline")
    assert registry.query_result("child").reason == "own_deadline"
