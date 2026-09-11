"""Offline integration coverage for the run wall-clock deadline foundation."""
from __future__ import annotations

from typing import Any

from sztu_code.core.context import ExecutionContext, TerminationReason
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import LlmResponse, ToolCallBlock
from sztu_code.core.loop import AgentLoop
from sztu_code.core.tools.registry import ToolRegistry


class _DeadlineAdvancingProvider:
    """Advance the injected clock after one response, then keep the loop offline."""

    def __init__(self, clock: list[float], *, end_turn: bool = False) -> None:
        self._clock = clock
        self._end_turn = end_turn
        self.calls = 0

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
    ) -> LlmResponse:
        del messages, tool_schemas, bus, run_id, step, system, usage_estimator
        self.calls += 1
        self._clock[0] = 1.0
        if self._end_turn:
            return LlmResponse(stop_reason="end_turn", text="late result")
        return LlmResponse(
            stop_reason="tool_use",
            tool_calls=[ToolCallBlock(id="unknown-1", name="missing_tool", input={})],
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
    assert context.status == "interrupted"
    assert context.reason == TerminationReason.MAX_WALL_CLOCK_EXCEEDED


async def test_agent_loop_preserves_late_end_turn_result_as_interrupted() -> None:
    clock = [0.0]
    provider = _DeadlineAdvancingProvider(clock, end_turn=True)
    context = ExecutionContext(
        run_id="late-end-turn",
        goal="preserve the late result",
        max_steps=5,
        max_wall_clock_s=1,
        clock=lambda: clock[0],
    )

    await AgentLoop(provider, ToolRegistry(), EventBus()).run(context)  # type: ignore[arg-type]

    assert provider.calls == 1
    assert context.status == "interrupted"
    assert context.reason == TerminationReason.MAX_WALL_CLOCK_EXCEEDED
    assert context.result == "late result"
