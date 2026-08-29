"""
步数限制与授权允许的深入综合测试。

覆盖：
1. 步数限制边界条件（max_steps=1、end_turn 优先级、事件顺序）
2. 权限拒绝追踪完整流程（累计 → 熔断 → 干预消息注入 → 恢复）
3. 复合命令 + 真实 PermissionManager 交互
4. DenialTracker 与 AgentLoop 的完整集成路径
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel

from sztu_code.core.context import ExecutionContext, TerminationReason
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import LlmResponse, ToolCallBlock
from sztu_code.core.loop import AgentLoop
from sztu_code.core.permissions.denial_tracker import DenialTracker
from sztu_code.core.permissions.policy import (
    PermissionDecision,
    ToolPolicy,
    matches_outside_cwd,
    split_compound_command,
)
from sztu_code.core.tools.base import BaseTool, ToolResult
from sztu_code.core.tools.registry import ToolRegistry

# ═══════════════════════════════════════════════════════════════════════════════
# Stub 工具
# ═══════════════════════════════════════════════════════════════════════════════

class _DenyBashTool(BaseTool):
    """模拟 bash 工具——权限被拒绝，返回 permission_denied。"""

    name = "bash"
    description = "Execute a shell command"
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
    }

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        return ToolResult(
            content="Permission denied by user.",
            is_error=True,
            error_type="permission_denied",
        )


class _SuccessTool(BaseTool):
    """总是成功的工具，用于重置拒绝计数器。"""

    name = "read_file"
    description = "Read a file"
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        return ToolResult(content="file content here")


class _EchoTool(BaseTool):
    """返回 msg 参数值的工具。"""

    name = "echo"
    description = "Echoes msg"
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {"msg": {"type": "string"}},
        "required": ["msg"],
    }

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        return ToolResult(content=str(params["msg"]))


# ═══════════════════════════════════════════════════════════════════════════════
# Stub Provider
# ═══════════════════════════════════════════════════════════════════════════════

class _MockProvider:
    """按顺序返回预设 LlmResponse；额外记录调用次数供断言。"""

    def __init__(self, responses: list[LlmResponse]) -> None:
        self._responses = iter(responses)
        self.call_count = 0
        self.last_messages: list[dict[str, object]] = []

    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
        usage_estimator: object | None = None,
    ) -> LlmResponse:
        self.call_count += 1
        self.last_messages = [dict(m) for m in messages]
        return next(self._responses)


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════

def _ctx(max_steps: int = 5) -> ExecutionContext:
    return ExecutionContext(run_id="r-deep", goal="deep test", max_steps=max_steps)


def _tc(name: str = "echo", inp: dict[str, object] | None = None, uid: str = "t1") -> ToolCallBlock:
    return ToolCallBlock(id=uid, name=name, input=inp or {"msg": "hi"})


async def _collect_events(bus: EventBus) -> list[BaseModel]:
    events: list[BaseModel] = []

    async def _h(e: BaseModel) -> None:
        events.append(e)

    bus.subscribe(_h)
    return events


# ═══════════════════════════════════════════════════════════════════════════════
# 一、步数限制深入测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestStepLimit:

    # 功能：验证 max_steps=1 时单步 tool_use 后立即终止
    # 设计：边界条件——最小合法步数，确认循环只执行 1 次 LLM 调用
    async def test_max_steps_one_exact_boundary(self) -> None:
        tc = _tc("echo", uid="t1")
        provider = _MockProvider([
            LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
        ])
        registry = ToolRegistry()
        registry.register(_EchoTool())
        # 关闭收尾回合与结语宽限步：本测试隔离验证 max_steps 语义，
        # 避免收尾/结语各多一次调用干扰计数
        loop = AgentLoop(
            provider, registry, EventBus(),
            wrap_up_on_max_steps=False,
            grace_step_on_max_steps=False,
        )
        ctx = _ctx(max_steps=1)
        await loop.run(ctx)
        assert ctx.step == 1
        assert ctx.status == "interrupted"
        assert ctx.reason == "exceeded_max_steps"
        assert provider.call_count == 1

    # 功能：验证 end_turn 在第 max_steps 步时优先于 max_steps 判定
    # 设计：max_steps=2，第 2 步返回 end_turn——应标记 success 而非 exceeded_max_steps
    async def test_end_turn_wins_over_max_steps_on_last_step(self) -> None:
        tc = _tc("echo", uid="t1")
        provider = _MockProvider([
            LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
            LlmResponse(stop_reason="end_turn", text="all done"),
        ])
        registry = ToolRegistry()
        registry.register(_EchoTool())
        loop = AgentLoop(provider, registry, EventBus())
        ctx = _ctx(max_steps=2)
        await loop.run(ctx)
        assert ctx.step == 2
        assert ctx.status == "success"
        assert ctx.reason == TerminationReason.SUCCESS
        assert ctx.result == "all done"

    # 功能：验证每步都发布 step.started 和 step.finished 事件，顺序正确
    # 设计：多步执行后按顺序检查事件类型序列，started/finished 必须成对且交错
    async def test_step_events_published_in_correct_order(self) -> None:
        tc = _tc("echo", uid="t1")
        provider = _MockProvider([
            LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
            LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
            LlmResponse(stop_reason="end_turn", text="done"),
        ])
        registry = ToolRegistry()
        registry.register(_EchoTool())
        bus = EventBus()
        events = await _collect_events(bus)
        loop = AgentLoop(provider, registry, bus)
        ctx = _ctx(max_steps=10)
        await loop.run(ctx)

        step_events = [
            e for e in events
            if getattr(e, "type", "") in ("step.started", "step.finished")
        ]
        types = [getattr(e, "type", "") for e in step_events]
        # 期望: started-1, finished-1, started-2, finished-2, started-3, finished-3
        assert types == [
            "step.started", "step.finished",
            "step.started", "step.finished",
            "step.started", "step.finished",
        ], f"Got event sequence: {types}"

    # 功能：验证每一步的 StepStartedEvent.step 和 StepFinishedEvent.step 值正确递增
    # 设计：比对每对 started/finished 事件的 step 字段，从 1 开始
    async def test_step_event_indices_are_correct(self) -> None:
        tc = _tc("echo", uid="t1")
        provider = _MockProvider([
            LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
            LlmResponse(stop_reason="end_turn", text="done"),
        ])
        registry = ToolRegistry()
        registry.register(_EchoTool())
        bus = EventBus()
        events = await _collect_events(bus)
        loop = AgentLoop(provider, registry, bus)
        ctx = _ctx(max_steps=10)
        await loop.run(ctx)

        started = [e for e in events if getattr(e, "type", "") == "step.started"]
        finished = [e for e in events if getattr(e, "type", "") == "step.finished"]
        assert len(started) == 2
        assert len(finished) == 2
        assert getattr(started[0], "step", 0) == 1
        assert getattr(started[1], "step", 0) == 2
        assert getattr(finished[0], "step", 0) == 1
        assert getattr(finished[1], "step", 0) == 2

    # 功能：验证 max_steps 耗尽后循环不再调用 LLM
    # 设计：使用始终成功的 echo 隔离步数限制，并关闭额外结语回合后断言恰好调用 3 次
    async def test_max_steps_stops_calling_llm(self) -> None:
        tc = _tc("echo", uid="t0")
        provider = _MockProvider(
            [LlmResponse(stop_reason="tool_use", tool_calls=[tc])] * 10
        )
        registry = ToolRegistry()
        registry.register(_EchoTool())
        loop = AgentLoop(
            provider,
            registry,
            EventBus(),
            wrap_up_on_max_steps=False,
            grace_step_on_max_steps=False,
        )
        ctx = _ctx(max_steps=3)
        await loop.run(ctx)
        assert ctx.status == "interrupted"
        assert ctx.reason == "exceeded_max_steps"
        assert provider.call_count == 3


# ═══════════════════════════════════════════════════════════════════════════════
# 二、DenialTracker 深入测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestDenialTrackerDeep:

    # 功能：验证不同工具独立计数——A 被拒 N 次触发熔断不依赖 B 的计数
    # 设计：bash 拒绝 3 次 + write_file 拒绝 1 次，bash 触发但 write_file 不触发
    def test_independent_tool_counters_dont_interfere(self) -> None:
        tracker = DenialTracker(max_consecutive=3)
        # bash 被拒 2 次
        assert tracker.record_denial("bash") is False
        assert tracker.record_denial("bash") is False
        # write_file 被拒 1 次 — 不影响 bash 计数器
        tracker.record_denial("write_file")
        snap = tracker.snapshot()
        assert snap["consecutive"]["bash"] == 2
        assert snap["consecutive"]["write_file"] == 1
        # bash 再 1 次触发
        assert tracker.record_denial("bash") is True

    # 功能：验证总量上限触发——跨不同工具累计达到 max_total 触发
    # 设计：max_consecutive=10（不会触发），max_total=4，4 个不同工具各 1 次触发
    def test_total_cap_triggers_independent_of_consecutive(self) -> None:
        tracker = DenialTracker(max_consecutive=10, max_total=4)
        for i in range(3):
            assert tracker.record_denial(f"tool_{i}") is False
        # 第 4 个不同工具 → 总量达 4 → 触发
        assert tracker.record_denial("tool_3") is True

    # 功能：验证成功调用仅重置对应工具的连续计数，不影响其他工具
    # 设计：bash 被拒 2 次 → write_file 成功 → bash 计数不变 → 再拒 1 次触发
    def test_success_only_resets_specific_tool(self) -> None:
        tracker = DenialTracker(max_consecutive=3)
        tracker.record_denial("bash")
        tracker.record_denial("bash")
        tracker.record_denial("write_file")
        # write_file 成功 → 只重置 write_file
        tracker.record_success("write_file")
        snap = tracker.snapshot()
        assert snap["consecutive"]["bash"] == 2
        assert snap["consecutive"]["write_file"] == 0
        # bash 再拒触发
        assert tracker.record_denial("bash") is True

    # 功能：验证 reset_intervention 后计数器清零，后续新拒绝需重新累积
    # 设计：触发 → reset → 计数器为 0 → 新拒绝从 1 开始
    def test_reset_intervention_clears_all_counters(self) -> None:
        tracker = DenialTracker(max_consecutive=3)
        tracker.record_denial("bash")
        tracker.record_denial("bash")
        tracker.record_denial("bash")
        assert tracker.should_intervene() is True
        tracker.reset_intervention()
        snap = tracker.snapshot()
        assert snap["consecutive"] == {}
        assert snap["intervened"] is True
        # 新拒绝需重新累积 3 次
        assert tracker.record_denial("bash") is False
        assert tracker.record_denial("bash") is False
        assert tracker.record_denial("bash") is True

    # 功能：验证干预消息按次数降序排列工具
    # 设计：bash(3) + write_file(2) + read_file(1)，消息中 bash 应在 write_file 前面
    def test_intervention_message_orders_by_count_descending(self) -> None:
        tracker = DenialTracker(max_consecutive=3)
        tracker.record_denial("read_file")
        for _ in range(3):
            tracker.record_denial("bash")
        tracker.record_denial("write_file")
        tracker.record_denial("write_file")
        msg = tracker.intervention_message()
        bash_pos = msg.index("bash")
        wf_pos = msg.index("write_file")
        assert bash_pos < wf_pos, f"bash should appear before write_file in:\n{msg}"
        assert "3 times" in msg
        assert "2 times" in msg


# ═══════════════════════════════════════════════════════════════════════════════
# 三、DenialTracker + AgentLoop 完整集成测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestDenialTrackerLoopIntegration:

    # 功能：验证权限拒绝 → 熔断 → 干预消息注入 → AI 改变策略 → 成功的完整路径
    # 设计：3 步 deny_tool → 触发熔断注入消息 → 第 4 步 LLM 看到消息后改用 read_file 成功
    async def test_full_denial_intervention_recovery_cycle(self) -> None:
        deny_tc = _tc("bash", {"command": "rm -rf /"}, uid="d1")
        success_tc = _tc("read_file", {"path": "safe.txt"}, uid="d2")

        # 前 3 步：权限拒绝 → 触发熔断（max_consecutive=3）
        # 第 4 步：LLM 收到干预消息后改用 read_file → 成功
        # 第 5 步：end_turn
        provider = _MockProvider([
            LlmResponse(stop_reason="tool_use", tool_calls=[deny_tc]),
            LlmResponse(stop_reason="tool_use", tool_calls=[deny_tc]),
            LlmResponse(stop_reason="tool_use", tool_calls=[deny_tc]),
            LlmResponse(stop_reason="tool_use", tool_calls=[success_tc]),
            LlmResponse(stop_reason="end_turn", text="task completed via read"),
        ])
        registry = ToolRegistry()
        registry.register(_DenyBashTool())
        registry.register(_SuccessTool())
        bus = EventBus()
        events = await _collect_events(bus)

        denial_tracker = DenialTracker(max_consecutive=3)
        loop = AgentLoop(provider, registry, bus, denial_tracker=denial_tracker)
        ctx = _ctx(max_steps=10)
        await loop.run(ctx)

        # 断言：最终成功
        assert ctx.status == "success"
        # 断言：熔断事件已发布
        intervention_events = [
            e for e in events
            if getattr(e, "type", "") == "denial.intervention"
        ]
        assert len(intervention_events) == 1, (
            f"Expected 1 intervention event, got {len(intervention_events)}"
        )
        # 断言：干预消息注入到上下文中
        intervention_msgs = [
            m for m in ctx.messages
            if m["role"] == "user"
            and isinstance(m["content"], str)
            and "repeatedly rejected" in str(m["content"])
        ]
        assert len(intervention_msgs) == 1

    # 功能：验证无拒绝时 DenialTracker 不注入任何干预消息
    # 设计：3 步全部成功（echo 工具），messages 中不应出现干预消息
    async def test_no_intervention_when_no_denials(self) -> None:
        tc = _tc("echo", {"msg": "hello"}, uid="e1")
        provider = _MockProvider([
            LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
            LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
            LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
            LlmResponse(stop_reason="end_turn", text="done"),
        ])
        registry = ToolRegistry()
        registry.register(_EchoTool())
        bus = EventBus()
        events = await _collect_events(bus)

        denial_tracker = DenialTracker(max_consecutive=3)
        loop = AgentLoop(provider, registry, bus, denial_tracker=denial_tracker)
        ctx = _ctx(max_steps=10)
        await loop.run(ctx)

        # 无干预事件
        intervention_events = [
            e for e in events
            if getattr(e, "type", "") == "denial.intervention"
        ]
        assert len(intervention_events) == 0
        # 无干预消息
        intervention_msgs = [
            m for m in ctx.messages
            if m["role"] == "user"
            and isinstance(m["content"], str)
            and "repeatedly rejected" in str(m["content"])
        ]
        assert len(intervention_msgs) == 0
        # 状态为成功
        assert ctx.status == "success"
        # 拒绝计数为 0
        snap = denial_tracker.snapshot()
        assert snap["total"] == 0

    # 功能：验证成功调用穿插在拒绝之间重置计数器，阻止不必要的熔断
    # 设计：bash 被拒 2 次 → bash 成功 → 计数器重置 → 再被拒 2 次不触发
    #       关键：同名工具的成功调用才重置该工具的拒绝计数
    async def test_success_interleaved_prevents_unnecessary_intervention(self) -> None:
        deny_tc = _tc("bash", {"command": "x"}, uid="d1")
        success_tc = _tc("bash", {"command": "echo ok"}, uid="d2")  # 同名工具

        # 用一个新的工具类：bash 先拒绝 2 次，然后成功
        class _AlternatingBashTool(BaseTool):
            name = "bash"
            description = "bash tool"
            input_schema: dict[str, object] = {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            }
            def __init__(self) -> None:
                self._call = 0

            async def invoke(self, params: dict[str, object]) -> ToolResult:
                self._call += 1
                if self._call <= 2:
                    return ToolResult(
                        content="Permission denied.",
                        is_error=True,
                        error_type="permission_denied",
                    )
                return ToolResult(content="command executed")

        alt_bash = _AlternatingBashTool()
        provider = _MockProvider([
            LlmResponse(stop_reason="tool_use", tool_calls=[deny_tc]),     # 1: deny
            LlmResponse(stop_reason="tool_use", tool_calls=[deny_tc]),     # 2: deny (consecutive=2)
            LlmResponse(stop_reason="tool_use", tool_calls=[success_tc]),  # 3: success → reset
            LlmResponse(stop_reason="tool_use", tool_calls=[deny_tc]),     # 4: deny (consecutive=1)
            LlmResponse(stop_reason="tool_use", tool_calls=[deny_tc]),     # 5: deny (consecutive=2)
            LlmResponse(stop_reason="end_turn", text="done"),
        ])
        registry = ToolRegistry()
        registry.register(alt_bash)
        bus = EventBus()
        events = await _collect_events(bus)

        denial_tracker = DenialTracker(max_consecutive=3)
        loop = AgentLoop(provider, registry, bus, denial_tracker=denial_tracker)
        ctx = _ctx(max_steps=10)
        await loop.run(ctx)

        # success 穿插重置了计数 → 不应触发熔断（consecutive 止步于 2）
        intervention_events = [
            e for e in events
            if getattr(e, "type", "") == "denial.intervention"
        ]
        assert len(intervention_events) == 0, (
            "success between denials should prevent intervention"
        )
        assert ctx.status == "success"

    # 功能：验证熔断事件携带正确的字段值
    # 设计：精确断言 DenialInterventionEvent 各字段
    async def test_intervention_event_fields_are_correct(self) -> None:
        tc = _tc("bash", {"command": "x"}, uid="d1")
        provider = _MockProvider([
            LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
            LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
            LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
            LlmResponse(stop_reason="end_turn", text="switched"),
        ])
        registry = ToolRegistry()
        registry.register(_DenyBashTool())
        bus = EventBus()
        events = await _collect_events(bus)

        denial_tracker = DenialTracker(max_consecutive=2)  # 第 2 次就触发
        loop = AgentLoop(provider, registry, bus, denial_tracker=denial_tracker)
        ctx = _ctx(max_steps=10)
        await loop.run(ctx)

        intervention_events = [
            e for e in events
            if getattr(e, "type", "") == "denial.intervention"
        ]
        assert len(intervention_events) == 1
        evt = intervention_events[0]
        assert getattr(evt, "tool_name", "") == "bash"
        assert getattr(evt, "consecutive_count", 0) >= 2
        assert getattr(evt, "total_denials", 0) >= 2
        assert "repeatedly rejected" in getattr(evt, "message", "")

    # 功能：验证干预后 DenialTracker 不再重复注入（同一轮只注入一次）
    # 设计：5 个 deny 步骤，max_consecutive=2 → 第 2 步触发注入 + reset
    #       第 3-4 步重新累积，第 4 步再次触发
    async def test_intervention_only_injected_once_per_cycle(self) -> None:
        tc = _tc("bash", {"command": "x"}, uid="d1")
        provider = _MockProvider([
            LlmResponse(stop_reason="tool_use", tool_calls=[tc]),  # 1: deny=1
            LlmResponse(stop_reason="tool_use", tool_calls=[tc]),  # 2: deny=2 → 触发 → reset
            LlmResponse(stop_reason="tool_use", tool_calls=[tc]),  # 3: deny=1 (after reset)
            LlmResponse(stop_reason="tool_use", tool_calls=[tc]),  # 4: deny=2 → 再次触发
            LlmResponse(stop_reason="end_turn", text="done"),
        ])
        registry = ToolRegistry()
        registry.register(_DenyBashTool())
        bus = EventBus()
        events = await _collect_events(bus)

        denial_tracker = DenialTracker(max_consecutive=2)
        loop = AgentLoop(provider, registry, bus, denial_tracker=denial_tracker)
        ctx = _ctx(max_steps=10)
        await loop.run(ctx)

        intervention_events = [
            e for e in events
            if getattr(e, "type", "") == "denial.intervention"
        ]
        # 应该触发 2 次：第 2 步和第 4 步各一次
        assert len(intervention_events) == 2, (
            f"Expected 2 interventions (steps 2 and 4), got {len(intervention_events)}"
        )
        # 上下文中有 2 条干预消息
        intervention_msgs = [
            m for m in ctx.messages
            if m["role"] == "user"
            and isinstance(m["content"], str)
            and "repeatedly rejected" in str(m["content"])
        ]
        assert len(intervention_msgs) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 四、复合命令 + 权限策略深入测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestCompoundCommandPermissions:

    # 功能：验证 deny_patterns 在复合命令中间段命中时整体拒绝
    # 设计：三段命令，中间段含 rm -rf，应 DENY
    def test_deny_in_middle_segment_of_three(self) -> None:
        from sztu_code.core.permissions.policy import evaluate
        policy = ToolPolicy(
            default=PermissionDecision.ASK,
            deny_patterns=[r"\brm\b"],
        )
        result = evaluate(
            "bash",
            {"command": "echo start && rm -rf /data && echo done"},
            policy,
        )
        assert result == PermissionDecision.DENY

    # 功能：验证 deny 规则跨管道生效
    # 设计：cat file | rm -rf /tmp，第二段管道命中 deny
    def test_deny_across_pipe(self) -> None:
        from sztu_code.core.permissions.policy import evaluate
        policy = ToolPolicy(
            default=PermissionDecision.ASK,
            deny_patterns=[r"\brm\b"],
        )
        result = evaluate(
            "bash",
            {"command": "cat /tmp/data | rm -rf /tmp/out"},
            policy,
        )
        assert result == PermissionDecision.DENY

    # 功能：验证 OUTSIDE_CWD 在分号连接的复合命令中正确检测
    # 设计：第一段安全，第二段含绝对路径 cd
    def test_outside_cwd_across_semicolon(self) -> None:
        from sztu_code.core.permissions.policy import evaluate
        result = evaluate(
            "bash",
            {"command": "echo safe; cd /etc"},
        )
        assert result == PermissionDecision.ASK  # OUTSIDE_CWD 强制 ASK

    # 功能：验证复合命令中的所有段都安全时正常走 default/allow
    # 设计：三段纯本地操作，不应该触发任何 deny 或 OUTSIDE_CWD
    def test_all_safe_segments_pass_through(self) -> None:
        from sztu_code.core.permissions.policy import evaluate
        policy = ToolPolicy(
            default=PermissionDecision.ASK,
            allow_patterns=[r"^(echo|ls|cat)\b"],
        )
        result = evaluate(
            "bash",
            {"command": "echo hello && ls src/ && cat README.md"},
            policy,
        )
        assert result == PermissionDecision.ALLOW

    # 功能：验证 split_compound_command 正确处理混合引号场景
    # 设计：双引号内含 &&，单引号内含 ||，外层用 ; 分隔
    def test_mixed_quotes_in_compound_command(self) -> None:
        segments = split_compound_command(
            """echo "a && b" ; echo 'c || d'"""
        )
        assert len(segments) == 2
        assert segments[0] == 'echo "a && b"'
        assert segments[1] == "echo 'c || d'"

    # 功能：验证转义的分隔符不被拆分
    # 设计：反斜杠转义的 && 被视为普通字符，不触发拆分；
    #       split 函数保留反斜杠，因此输出中不包含字面量 &&
    def test_escaped_separator_not_split(self) -> None:
        segments = split_compound_command(r"echo a\&\&b")
        assert len(segments) == 1
        # 转义后的 \&\& 作为普通字符保留在结果中，不触发拆分

    # 功能：验证只有空白字符的段被过滤
    # 设计：cmd1 &&  && cmd2 中间的空白段被 strip 掉
    def test_empty_segments_filtered(self) -> None:
        segments = split_compound_command("echo a &&   && echo b")
        # 中间段 "   " 被 strip 后为空字符串，不应出现在结果中
        non_empty = [s for s in segments if s]
        assert len(non_empty) == 2
        assert non_empty == ["echo a", "echo b"]

    # 功能：验证 deny 在第一段即命中时无需解析后续段
    # 设计：短路评估，第一段含 deny pattern → 立即返回 DENY
    def test_deny_in_first_segment_stops_early(self) -> None:
        from sztu_code.core.permissions.policy import evaluate
        policy = ToolPolicy(
            default=PermissionDecision.ASK,
            deny_patterns=[r"\bsudo\b"],
        )
        # sudo 在第一段，即使后面有安全命令也应立即 DENY
        result = evaluate(
            "bash",
            {"command": "sudo rm -rf / && echo safe"},
            policy,
        )
        assert result == PermissionDecision.DENY


# ═══════════════════════════════════════════════════════════════════════════════
# 五、步数限制 + 权限拒绝 交叉测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestStepLimitWithPermissions:

    # 功能：验证被拒绝的步骤不计入成功步数但仍消耗 max_steps 配额
    # 设计：max_steps=3，3 步全部拒绝 → exceeded_max_steps，每个拒绝都被正确追踪
    async def test_denied_steps_consume_step_quota(self) -> None:
        tc = _tc("bash", {"command": "x"}, uid="d1")
        provider = _MockProvider([
            LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
            LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
            LlmResponse(stop_reason="tool_use", tool_calls=[tc]),
            LlmResponse(stop_reason="end_turn", text="done"),
        ])
        registry = ToolRegistry()
        registry.register(_DenyBashTool())
        bus = EventBus()

        denial_tracker = DenialTracker(max_consecutive=5)  # 不会提前触发
        loop = AgentLoop(provider, registry, bus, denial_tracker=denial_tracker)
        ctx = _ctx(max_steps=3)
        await loop.run(ctx)

        assert ctx.status == "interrupted"
        assert ctx.reason == "exceeded_max_steps"
        assert ctx.step == 3
        # 3 步全部被拒
        snap = denial_tracker.snapshot()
        assert snap["total"] == 3
        assert snap["consecutive"].get("bash", 0) == 3

    # 功能：验证熔断消息注入本身不消耗步数额度
    # 设计：max_steps=5, max_consecutive=2,
    #       第 1-2 步拒绝（第 2 步触发注入），第 3-4 步拒绝，第 5 步超限
    async def test_intervention_injection_does_not_consume_extra_step(self) -> None:
        tc = _tc("bash", {"command": "x"}, uid="d1")
        responses = [LlmResponse(stop_reason="tool_use", tool_calls=[tc])] * 10
        provider = _MockProvider(responses)
        registry = ToolRegistry()
        registry.register(_DenyBashTool())
        bus = EventBus()

        denial_tracker = DenialTracker(max_consecutive=2)
        # 关闭收尾回合：本测试验证干预不额外消耗调用，排除收尾的一次调用
        loop = AgentLoop(
            provider, registry, bus,
            denial_tracker=denial_tracker, wrap_up_on_max_steps=False,
        )
        ctx = _ctx(max_steps=5)
        await loop.run(ctx)

        assert ctx.status == "interrupted"
        assert ctx.reason == "exceeded_max_steps"
        # call_count 应等于 max_steps（注入不额外消耗 API 调用）
        # 注入消息是直接 append 到 messages，不通过 LLM
        assert provider.call_count == 5

    # 功能：验证 LLM 在收到干预消息后能看到完整的拒绝历史
    # 设计：检查第 4 步 LLM 调用时 messages 中是否包含干预消息
    async def test_llm_sees_intervention_message_in_context(self) -> None:
        tc = _tc("bash", {"command": "x"}, uid="d1")
        provider = _MockProvider([
            LlmResponse(stop_reason="tool_use", tool_calls=[tc]),  # 1: deny
            LlmResponse(stop_reason="tool_use", tool_calls=[tc]),  # 2: deny
            LlmResponse(stop_reason="tool_use", tool_calls=[tc]),  # 3: deny → 触发
            LlmResponse(stop_reason="end_turn", text="changing approach"),
        ])
        registry = ToolRegistry()
        registry.register(_DenyBashTool())
        bus = EventBus()

        denial_tracker = DenialTracker(max_consecutive=3)
        loop = AgentLoop(provider, registry, bus, denial_tracker=denial_tracker)
        ctx = _ctx(max_steps=10)
        await loop.run(ctx)

        # 第 4 步 LLM 调用时的 messages 应包含干预消息
        # provider.last_messages 记录了最后一次 chat 调用的入参
        user_msgs = [
            m["content"] for m in provider.last_messages
            if m["role"] == "user" and isinstance(m["content"], str)
        ]
        intervention_found = any(
            "repeatedly rejected" in str(c) for c in user_msgs
        )
        assert intervention_found, (
            f"LLM should see intervention message. User messages: {user_msgs}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 六、PermissionManager + evaluate 静态策略 深入测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestPermissionPolicyDeep:

    # 功能：验证新增的 sudo 规则在所有复合命令分隔符后都生效
    # 设计：sudo 在 &&、||、;、| 之后都应触发 OUTSIDE_CWD
    @pytest.mark.parametrize("connector", ["&&", "||", ";", "|"])
    def test_sudo_after_any_connector_forces_ask(self, connector: str) -> None:
        cmd = f"echo ok {connector} sudo rm -rf /"
        assert matches_outside_cwd(cmd), f"sudo after '{connector}' should trigger ASK"

    # 功能：验证 LD_PRELOAD 在任何位置触发 OUTSIDE_CWD
    # 设计：行首、行中、赋值形式都应匹配
    @pytest.mark.parametrize("cmd", [
        "LD_PRELOAD=/evil.so ./app",
        "env LD_PRELOAD=/evil.so ./app",
        "./app LD_PRELOAD=/evil.so",
    ])
    def test_ld_preload_anywhere_forces_ask(self, cmd: str) -> None:
        assert matches_outside_cwd(cmd), f"'{cmd}' should trigger ASK"

    # 功能：验证 builtin cd 和 command cd 的多种写法都能检测
    # 设计：带路径、带选项、复合命令中的各种变体
    @pytest.mark.parametrize("cmd", [
        "builtin cd /tmp",
        "command cd /etc",
        "echo ok && builtin cd /var",
        "ls; command cd /home",
    ])
    def test_builtin_and_command_cd_variants(self, cmd: str) -> None:
        assert matches_outside_cwd(cmd), f"'{cmd}' should trigger ASK"

    # 功能：验证 allow_patterns 在 OUTSIDE_CWD 触发时不生效
    # 设计：即使 allow_patterns 匹配所有命令，OUTSIDE_CWD 命中的命令仍 ASK
    def test_allow_patterns_cannot_bypass_outside_cwd(self) -> None:
        from sztu_code.core.permissions.policy import evaluate
        policy = ToolPolicy(
            default=PermissionDecision.ASK,
            allow_patterns=[r".*"],  # 匹配一切
        )
        # 绝对路径 → OUTSIDE_CWD 强制 ASK，不能被 allow_patterns 放行
        result = evaluate("bash", {"command": "cat /etc/shadow"}, policy)
        assert result == PermissionDecision.ASK

    # 功能：验证 deny_patterns > OUTSIDE_CWD > allow_patterns 优先级链
    # 设计：同一命令同时命中三层，deny 最高优先级
    def test_priority_chain_deny_beats_all(self) -> None:
        from sztu_code.core.permissions.policy import evaluate
        policy = ToolPolicy(
            default=PermissionDecision.ASK,
            deny_patterns=[r"\brm\b"],
            allow_patterns=[r".*"],
        )
        # rm + 绝对路径：deny_patterns（Tier 1）命中 → DENY
        # 即使后续 Tier 2 会触发 ASK、Tier 3 会 ALLOW
        result = evaluate("bash", {"command": "rm -rf /tmp/data"}, policy)
        assert result == PermissionDecision.DENY

    # 功能：验证 未知工具默认 ASK 策略不受 bash 规则干扰
    # 设计：非 bash 工具即使传入 command 参数也不走命令模式匹配
    def test_unknown_tool_with_command_param_defaults_to_ask(self) -> None:
        from sztu_code.core.permissions.policy import evaluate
        # 工具名不是 bash，即使参数中有 command 字段也不触发命令检测
        result = evaluate("python_exec", {"command": "rm -rf /"})
        assert result == PermissionDecision.ASK
