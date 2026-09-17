"""Offline integration coverage for the run wall-clock deadline foundation."""
from __future__ import annotations

import asyncio
from typing import Any

from sztu_code.core.context import ExecutionContext, TerminationReason
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import LlmResponse, ToolCallBlock
from sztu_code.core.loop import AgentLoop
from sztu_code.core.tools.base import BaseTool, ToolResult
from sztu_code.core.tools.registry import ToolRegistry


class _DeadlineAdvancingProvider:
    """Advance the injected clock after one response, then keep the loop offline."""

    def __init__(self, clock: list[float], *, end_turn: bool = False) -> None:
        self._clock = clock
        self._end_turn = end_turn
        self.calls = 0
        self.remaining: list[float | None] = []

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tool_schemas: list[dict[str, Any]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
        usage_estimator: object | None = None,
        remaining_s: float | None = None,
    ) -> LlmResponse:
        del messages, tool_schemas, bus, run_id, step, system, usage_estimator
        self.remaining.append(remaining_s)
        self.calls += 1
        self._clock[0] = 1.0
        if self._end_turn:
            return LlmResponse(stop_reason="end_turn", text="late result")
        return LlmResponse(
            stop_reason="tool_use",
            tool_calls=[ToolCallBlock(id="unknown-1", name="missing_tool", input={})],
        )


class _BlockingTool(BaseTool):
    """Wait until the AgentLoop cancels the active call at the Run deadline."""

    name = "blocking_tool"
    description = "Blocks until cancelled"
    input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.active = False
        self._release = asyncio.Event()

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        del params
        self.active = True
        self.started.set()
        try:
            await self._release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        finally:
            self.active = False
        return ToolResult(content="unexpected completion")


class _ToolRequestProvider:
    """Return one tool request and record whether the loop starts another request."""

    def __init__(self) -> None:
        self.calls = 0
        self.remaining: list[float | None] = []

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tool_schemas: list[dict[str, Any]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
        usage_estimator: object | None = None,
        remaining_s: float | None = None,
    ) -> LlmResponse:
        del messages, tool_schemas, bus, run_id, step, system, usage_estimator
        self.calls += 1
        self.remaining.append(remaining_s)
        if self.calls > 1:
            return LlmResponse(stop_reason="end_turn", text="unexpected follow-up")
        return LlmResponse(
            stop_reason="tool_use",
            tool_calls=[ToolCallBlock(id="blocking-1", name="blocking_tool", input={})],
        )


async def test_agent_loop_stops_before_second_provider_request_after_deadline() -> None:
    clock = [0.0]
    provider = _DeadlineAdvancingProvider(clock)
    context = ExecutionContext(
        run_id="deadline-integration",
        goal="exercise the deadline",
        max_steps=5,
        max_wall_clock_s=1,
        clock=lambda: clock[0],
    )

    await AgentLoop(provider, ToolRegistry(), EventBus()).run(context)  # type: ignore[arg-type]

    assert provider.calls == 1
    assert provider.remaining == [1.0]
    assert context.status == "interrupted"
    assert context.reason == TerminationReason.MAX_WALL_CLOCK_EXCEEDED


async def test_agent_loop_discards_late_end_turn_after_deadline() -> None:
    clock = [0.0]
    provider = _DeadlineAdvancingProvider(clock, end_turn=True)
    context = ExecutionContext(
        run_id="late-end-turn",
        goal="discard the late result",
        max_steps=5,
        max_wall_clock_s=1,
        clock=lambda: clock[0],
    )

    await AgentLoop(provider, ToolRegistry(), EventBus()).run(context)  # type: ignore[arg-type]

    assert provider.calls == 1
    assert provider.remaining == [1.0]
    assert context.status == "interrupted"
    assert context.reason == TerminationReason.MAX_WALL_CLOCK_EXCEEDED
    assert context.result == ""


async def test_agent_loop_cancels_tool_and_does_not_start_another_request() -> None:
    tool = _BlockingTool()
    registry = ToolRegistry()
    registry.register(tool)
    bus = EventBus()
    events: list[Any] = []

    async def collect(event: Any) -> None:
        events.append(event)

    bus.subscribe(collect)
    provider = _ToolRequestProvider()
    context = ExecutionContext(
        run_id="tool-deadline-integration",
        goal="cancel the blocking tool",
        max_steps=5,
        max_wall_clock_s=0.05,
    )

    await asyncio.wait_for(AgentLoop(provider, registry, bus).run(context), timeout=0.5)

    assert tool.started.is_set()
    assert tool.cancelled.is_set()
    assert not tool.active
    assert provider.calls == 1
    assert provider.remaining[0] is not None
    assert context.status == "interrupted"
    assert context.reason == TerminationReason.MAX_WALL_CLOCK_EXCEEDED
    assert not any(event.type == "tool.call_finished" for event in events)
    failed = [event for event in events if event.type == "tool.call_failed"]
    assert len(failed) == 1
    assert failed[0].error_class == "deadline_exceeded"
    assert failed[0].execution_state == "unknown"
