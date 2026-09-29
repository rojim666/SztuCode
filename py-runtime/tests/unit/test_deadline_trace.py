from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from sztu_code.core.config import SztuConfig
from sztu_code.core.llm.types import LlmResponse, ToolCallBlock, UsageStats
from sztu_code.core.permissions.manager import PermissionManager
from sztu_code.core.runner import AgentRunner
from sztu_code.core.tools.base import BaseTool, ToolPermission, ToolResult
from sztu_code.core.tools.registry import ToolRegistry
from sztu_code.core.trace.writer import TraceWriter


class _SlowCancellableTool(BaseTool):
    """阻塞直到被 Run deadline 取消，确保 deadline 确定在工具调用内触发。"""

    name = "slow_cancellable"
    description = "Waits until the run cancels it"
    required_permission = ToolPermission.READ_ONLY
    input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        self.started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        raise AssertionError("unreachable")  # pragma: no cover


def _blocking_provider() -> Any:
    """阻塞直到被取消，确保 deadline 确定在 LLM 请求内触发（阶段无歧义）。"""

    async def chat(*_args: Any, **_kwargs: Any) -> LlmResponse:
        await asyncio.Future()
        raise AssertionError("unreachable")  # pragma: no cover

    provider = MagicMock()
    provider.chat = chat
    return provider


class _PermissionDeadlineProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: object,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
        usage_estimator: object | None = None,
        max_output_tokens: int | None = None,
    ) -> LlmResponse:
        self.calls += 1
        if self.calls == 1:
            return LlmResponse(
                stop_reason="tool_use",
                tool_calls=[
                    ToolCallBlock(
                        id="permission-deadline-tool",
                        name="bash",
                        input={"command": "echo should-not-run"},
                    )
                ],
            )
        return LlmResponse(stop_reason="end_turn", text="unexpected follow-up")


class _CompactingProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: object,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
        usage_estimator: object | None = None,
        remaining_s: float | None = None,
        max_output_tokens: int | None = None,
    ) -> LlmResponse:
        if run_id == "compact":
            await asyncio.Future()
        self.calls += 1
        return LlmResponse(
            stop_reason="tool_use",
            tool_calls=[ToolCallBlock(id=f"tool-{self.calls}", name="missing", input={})],
            usage=UsageStats(
                input_tokens=100_000,
                output_tokens=1,
                context_pct=0.9,
            ),
        )


def _read_trace(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


# 功能：验证 Run 因 wall-clock deadline 终止时，trace 里产出恰好一条 deadline 记录
# 设计：阻塞 provider + 1 秒预算，使 deadline 确定在 LLM 请求内触发；断言记录唯一、
#       阶段为 llm、原因与 run 终态一致、run_id 正确。
async def test_deadline_emits_single_trace_record_matching_outcome(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    writer = TraceWriter(trace_path)
    await writer.start()

    cfg = SztuConfig()
    cfg.agent.max_steps = 100  # 不靠 max_steps 触发
    cfg.budget.max_wall_clock_s = 1
    runner = AgentRunner(
        cfg,
        provider=_blocking_provider(),
        runs_dir=tmp_path,
        trace=writer,
    )

    outcome = await asyncio.wait_for(
        runner.run_and_capture("goal", run_id="run-trace", workspace_root=tmp_path),
        timeout=20.0,
    )
    await writer.stop()

    assert outcome.status == "interrupted"
    assert outcome.reason == "max_wall_clock_exceeded"

    records = _read_trace(trace_path)
    deadline_records = [r for r in records if r.get("kind") == "deadline"]
    assert len(deadline_records) == 1, (
        f"expected exactly 1 deadline record, got {len(deadline_records)}; "
        f"kinds present: {[r.get('kind') for r in records]}"
    )
    record = deadline_records[0]
    assert record["run_id"] == "run-trace"
    assert record["data"]["reason"] == outcome.reason
    assert record["data"]["stage"] == "llm"


# 功能：验证 deadline 在工具调用内触发时，trace 记录阶段为 tool
# 设计：注册一个阻塞的可取消工具，provider 首步发起该工具调用；1 秒预算内工具被
#       deadline 取消，断言记录唯一且 stage == "tool"。
async def test_deadline_in_tool_call_records_tool_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace_path = tmp_path / "trace.jsonl"
    writer = TraceWriter(trace_path)
    await writer.start()

    tool = _SlowCancellableTool()
    registry = ToolRegistry()
    registry.register(tool)

    async def chat(*_args: Any, **_kwargs: Any) -> LlmResponse:
        return LlmResponse(
            stop_reason="tool_use",
            tool_calls=[ToolCallBlock(id="t1", name="slow_cancellable", input={})],
            text="",
            usage=None,
        )

    provider = MagicMock()
    provider.chat = chat

    # AgentRunner 自己构建工具注册表，没有注入点；在构建完成后追加本测试的工具
    original_build = AgentRunner._build_registry

    def _build_with_slow_tool(self: Any, *args: Any, **kwargs: Any) -> Any:
        built = original_build(self, *args, **kwargs)
        built.register(tool)
        return built

    monkeypatch.setattr(AgentRunner, "_build_registry", _build_with_slow_tool)

    cfg = SztuConfig()
    cfg.agent.max_steps = 100
    cfg.budget.max_wall_clock_s = 1
    runner = AgentRunner(
        cfg,
        provider=provider,
        runs_dir=tmp_path,
        trace=writer,
    )

    outcome = await asyncio.wait_for(
        runner.run_and_capture("goal", run_id="run-tool", workspace_root=tmp_path),
        timeout=20.0,
    )
    await writer.stop()

    assert tool.cancelled.is_set(), "tool was not cancelled by the deadline"
    assert outcome.reason == "max_wall_clock_exceeded"
    deadline_records = [r for r in _read_trace(trace_path) if r.get("kind") == "deadline"]
    assert len(deadline_records) == 1
    assert deadline_records[0]["data"]["stage"] == "tool"


async def test_deadline_in_permission_wait_records_permission_stage(
    tmp_path: Path,
) -> None:
    trace_path = tmp_path / "trace.jsonl"
    writer = TraceWriter(trace_path)
    await writer.start()

    cfg = SztuConfig()
    cfg.agent.max_steps = 5
    cfg.budget.max_wall_clock_s = 1
    runner = AgentRunner(
        cfg,
        provider=_PermissionDeadlineProvider(),  # type: ignore[arg-type]
        permission_manager=PermissionManager(timeout_s=60.0),
        runs_dir=tmp_path,
        trace=writer,
    )

    outcome = await asyncio.wait_for(
        runner.run_and_capture("wait for permission", run_id="run-permission", workspace_root=tmp_path),
        timeout=20.0,
    )
    await writer.stop()

    assert outcome.reason == "max_wall_clock_exceeded"
    deadline_records = [r for r in _read_trace(trace_path) if r.get("kind") == "deadline"]
    assert len(deadline_records) == 1
    assert deadline_records[0]["data"]["stage"] == "permission"


async def test_deadline_while_waiting_for_compaction_records_compact_stage(
    tmp_path: Path,
) -> None:
    trace_path = tmp_path / "trace.jsonl"
    writer = TraceWriter(trace_path)
    await writer.start()

    cfg = SztuConfig()
    cfg.agent.max_steps = 10
    cfg.budget.max_wall_clock_s = 1
    cfg.compaction.auto_threshold = 0.8
    runner = AgentRunner(
        cfg,
        provider=_CompactingProvider(),  # type: ignore[arg-type]
        runs_dir=tmp_path,
        trace=writer,
    )

    outcome = await asyncio.wait_for(
        runner.run_and_capture("compact context", run_id="run-compact", workspace_root=tmp_path),
        timeout=20.0,
    )
    await writer.stop()

    assert outcome.reason == "max_wall_clock_exceeded"
    deadline_records = [r for r in _read_trace(trace_path) if r.get("kind") == "deadline"]
    assert len(deadline_records) == 1
    assert deadline_records[0]["data"]["stage"] == "compact"


# 功能：验证 deadline 在等待后台子 Agent 时触发，trace 记录阶段为 subagent
# 设计：预注册一个永不自行结束的后台任务并放入 pending_background_run_ids，父用
#       end_turn 收尾进入 _wait_for_background；小预算下等待超时。任务协程吞掉一次
#      取消后正常返回，使取消后的 gather 不会挂住（对应"无法自行终断的子 Agent"）。
async def test_deadline_while_waiting_for_subagent_records_subagent_stage() -> None:
    from sztu_code.core.context import ExecutionContext
    from sztu_code.core.events.bus import EventBus
    from sztu_code.core.loop import AgentLoop
    from sztu_code.core.subagent.registry import BackgroundTaskRegistry

    registry = BackgroundTaskRegistry()
    bus = EventBus()
    child_id = "child-stubborn"

    async def _stubborn() -> None:
        try:
            await asyncio.Event().wait()  # 永不设置
        except asyncio.CancelledError:
            return  # 吞掉一次取消后正常结束，避免 gather 挂住

    child_ctx = ExecutionContext(run_id=child_id, goal="child work", max_steps=5)
    task = asyncio.create_task(_stubborn())
    registry.register(child_id, "root-run", task, child_ctx)

    async def chat(*_args: Any, **_kwargs: Any) -> LlmResponse:
        return LlmResponse(stop_reason="end_turn", text="done", usage=None)

    provider = MagicMock()
    provider.chat = chat
    loop = AgentLoop(provider, ToolRegistry(), bus, task_registry=registry)

    ctx = ExecutionContext(
        run_id="root-run", goal="goal", max_steps=10, max_wall_clock_s=1
    )
    ctx.pending_background_run_ids = {child_id}

    await asyncio.wait_for(loop.run(ctx), timeout=20.0)

    assert ctx.reason == "max_wall_clock_exceeded"
    assert ctx.deadline_stage == "subagent"


# 功能：验证 wait_pending 在 Run deadline 到达时回报 True，使调用方能记录 compact 阶段
# 设计：启动一个后台压缩，其 provider 阻塞且吞掉一次取消后返回（避免取消后的 gather
#       挂住）；用远小于任务自身边界的 remaining_s 调用 wait_pending，断言回报 True。
#       正常完成与不设边界两种情形回报 False。
async def test_wait_pending_reports_deadline_hit(tmp_path: Path) -> None:
    from sztu_code.core.compact.compactor import Compactor
    from sztu_code.core.context import ExecutionContext
    from sztu_code.core.events.bus import EventBus

    async def chat(*_args: Any, **_kwargs: Any) -> LlmResponse:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # 吞掉一次取消后返回：压缩任务随之结束，取消后的 gather 不会挂住
            return LlmResponse(
                stop_reason="end_turn",
                text="## 1. Original Goal\nx\n## 2. Completed\n- y",
                usage=None,
            )
        raise AssertionError("unreachable")  # pragma: no cover

    provider = MagicMock()
    provider.chat = chat
    compactor = Compactor(EventBus(), tmp_path, "sess-trace")
    ctx = ExecutionContext(run_id="r1", goal="test", max_steps=5)
    ctx.messages = [
        {"role": "user", "content": "u " + "x" * 400},
        {"role": "assistant", "content": "a " + "y" * 400},
    ] * 4

    task = compactor.compact_async(ctx, provider)
    assert task is not None
    await asyncio.sleep(0)  # 让后台压缩进入 provider 调用

    hit = await compactor.wait_pending(remaining_s=0.05)

    assert hit is True, "wait_pending should report that the run deadline was hit"


# 功能：验证清理结果三态及其优先级
# 设计：工具调用被 deadline 取消且执行状态为 UNKNOWN（无法确认底层调用已停止）时，
#       cleanup 必须为 unknown——即使同时有后代被取消，unknown 也优先。
async def test_cleanup_result_is_unknown_when_tool_state_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trace_path = tmp_path / "trace.jsonl"
    writer = TraceWriter(trace_path)
    await writer.start()

    tool = _SlowCancellableTool()
    original_build = AgentRunner._build_registry

    def _build_with_slow_tool(self: Any, *args: Any, **kwargs: Any) -> Any:
        built = original_build(self, *args, **kwargs)
        built.register(tool)
        return built

    monkeypatch.setattr(AgentRunner, "_build_registry", _build_with_slow_tool)

    async def chat(*_args: Any, **_kwargs: Any) -> LlmResponse:
        return LlmResponse(
            stop_reason="tool_use",
            tool_calls=[ToolCallBlock(id="t1", name="slow_cancellable", input={})],
            text="",
            usage=None,
        )

    provider = MagicMock()
    provider.chat = chat
    cfg = SztuConfig()
    cfg.agent.max_steps = 100
    cfg.budget.max_wall_clock_s = 1
    runner = AgentRunner(cfg, provider=provider, runs_dir=tmp_path, trace=writer)

    await asyncio.wait_for(
        runner.run_and_capture("goal", run_id="run-unknown", workspace_root=tmp_path),
        timeout=20.0,
    )
    await writer.stop()

    deadline_records = [r for r in _read_trace(trace_path) if r.get("kind") == "deadline"]
    assert len(deadline_records) == 1
    data = deadline_records[0]["data"]
    assert data["stage"] == "tool"
    assert data["cleanup"] == "unknown"


# 功能：验证没有任何待清理工作时，清理结果为 completed
# 设计：阻塞 provider 让 deadline 在 LLM 请求内触发，无工具、无子 Agent、无压缩，
#       断言 cleanup == completed 且 cancelled_descendants == 0。
async def test_cleanup_result_is_completed_when_nothing_pending(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.jsonl"
    writer = TraceWriter(trace_path)
    await writer.start()

    cfg = SztuConfig()
    cfg.agent.max_steps = 100
    cfg.budget.max_wall_clock_s = 1
    runner = AgentRunner(
        cfg, provider=_blocking_provider(), runs_dir=tmp_path, trace=writer
    )

    await asyncio.wait_for(
        runner.run_and_capture("goal", run_id="run-clean", workspace_root=tmp_path),
        timeout=20.0,
    )
    await writer.stop()

    deadline_records = [r for r in _read_trace(trace_path) if r.get("kind") == "deadline"]
    assert len(deadline_records) == 1
    data = deadline_records[0]["data"]
    assert data["cleanup"] == "completed"
    assert data["cancelled_descendants"] == 0


async def test_cleanup_result_is_cancelled_bounded_when_descendants_are_cancelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace_path = tmp_path / "trace.jsonl"
    writer = TraceWriter(trace_path)
    await writer.start()

    cfg = SztuConfig()
    cfg.agent.max_steps = 100
    cfg.budget.max_wall_clock_s = 1
    runner = AgentRunner(
        cfg,
        provider=_blocking_provider(),
        runs_dir=tmp_path,
        trace=writer,
    )

    async def _cancel_descendants(*args: Any, **kwargs: Any) -> list[str]:
        return ["child-1"]

    monkeypatch.setattr(runner._task_registry, "cancel_descendants", _cancel_descendants)

    await asyncio.wait_for(
        runner.run_and_capture("goal", run_id="run-cancelled-bounded"),
        timeout=20.0,
    )
    await writer.stop()

    deadline_records = [r for r in _read_trace(trace_path) if r.get("kind") == "deadline"]
    assert len(deadline_records) == 1
    data = deadline_records[0]["data"]
    assert data["cleanup"] == "cancelled_bounded"
    assert data["cancelled_descendants"] == 1


# 功能：验证 sztu trace 对 deadline 记录有专门渲染，不走原始 dict 兜底
# 设计：直接调用 _summarize，断言输出含阶段、原因与清理结果三个键，且不是
#       str(data) 截断（兜底分支）。
async def test_trace_cli_summarizes_deadline_record() -> None:
    from sztu_code.cli.commands.trace import _summarize
    from sztu_code.core.trace.record import TraceRecord

    record = TraceRecord(
        ts="2026-09-23T00:00:00.000Z",
        direction="CORE",
        layer="event",
        kind="deadline",
        run_id="run-x",
        step=3,
        data={
            "stage": "tool",
            "reason": "max_wall_clock_exceeded",
            "cleanup": "unknown",
            "cancelled_descendants": 2,
        },
    )

    summary = _summarize(record)

    assert "stage=tool" in summary
    assert "max_wall_clock_exceeded" in summary
    assert "cleanup=unknown" in summary
    # 不得走兜底的 str(data)[:60]
    assert not summary.startswith("{")
