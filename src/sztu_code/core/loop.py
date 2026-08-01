from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sztu_code.core.bus.events import StepFinishedEvent, StepStartedEvent
from sztu_code.core.context import ExecutionContext
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.base import LLMProvider
from sztu_code.core.tools.invocation import invoke_tool
from sztu_code.core.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from sztu_code.core.compact.compactor import Compactor
    from sztu_code.core.permissions.denial_tracker import DenialTracker
    from sztu_code.core.permissions.manager import PermissionManager
    from sztu_code.core.subagent.registry import BackgroundTaskRegistry


log = logging.getLogger(__name__)

def _now() -> str:
    return datetime.now(UTC).isoformat()


class AgentLoop:
    # 初始化循环所需依赖：LLM provider、工具注册表、事件总线、
    # 以及可选的权限管理器、拒绝追踪器、压缩器和 session ID
    def __init__(
        self,
        provider: LLMProvider,
        registry: ToolRegistry,
        bus: EventBus,
        *,
        permission_manager: PermissionManager | None = None,
        denial_tracker: DenialTracker | None = None,
        compactor: Compactor | None = None,
        compact_threshold: float = 0.80,
        session_id: str = "",
        task_registry: BackgroundTaskRegistry | None = None,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._bus = bus
        self._permission_manager = permission_manager
        self._denial_tracker = denial_tracker
        self._compactor = compactor
        self._compact_threshold = compact_threshold
        self._session_id = session_id
        self._task_registry = task_registry

    # 驱动 plan→act→observe 循环直到上下文终止；CancelledError 向上传播
    async def run(self, context: ExecutionContext) -> None:
        while not context.is_done():
            context.step += 1
            await self._bus.publish(
                StepStartedEvent(run_id=context.run_id, step=context.step, ts=_now())
            )

            # [intervene] 连续拒绝达到阈值时注入熔断消息，强制 LLM 换策略
            if self._denial_tracker is not None and self._denial_tracker.should_intervene():
                msg = self._denial_tracker.intervention_message()
                context.messages.append({"role": "user", "content": msg})
                # 发布熔断事件供 TUI 渲染
                snap = self._denial_tracker.snapshot()
                from sztu_code.core.bus.events import DenialInterventionEvent
                if snap["consecutive"]:
                    worst_tool = max(snap["consecutive"], key=snap["consecutive"].get)
                    worst_count = snap["consecutive"][worst_tool]
                else:
                    worst_tool = "unknown"
                    worst_count = 0
                await self._bus.publish(
                    DenialInterventionEvent(
                        run_id=context.run_id,
                        tool_name=str(worst_tool),
                        consecutive_count=worst_count,
                        total_denials=snap["total"],
                        message=msg,
                        ts=_now(),
                    )
                )
                self._denial_tracker.reset_intervention()

            # [plan] call LLM — API errors terminate the run
            try:
                response = await self._provider.chat(
                    messages=context.messages,
                    tool_schemas=self._registry.tool_schemas(),
                    bus=self._bus,
                    run_id=context.run_id,
                    step=context.step,
                    system=context.system_prompt(
                        "You are a helpful AI assistant. "
                        "Use the available tools to complete the user's goal. "
                        "When the goal is fully achieved, respond with a final answer "
                        "and do not call any more tools."
                    ),
                )
            except asyncio.CancelledError:
                context.mark_failed("cancelled")
                raise
            except Exception:
                logging.getLogger(__name__).exception(
                    "LLM call failed run_id=%s step=%d", context.run_id, context.step
                )
                context.mark_failed("llm_error")
                break

            # 在写入历史前补齐工具调用标题，确保回放与实时事件使用同一份参数
            for tool_call in response.tool_calls:
                tool_call.input = self._registry.enrich_tool_input(tool_call.name, tool_call.input)

            # [observe] append assistant content blocks to context
            # thinking blocks must come first and be preserved verbatim for extended thinking mode
            blocks: list[dict[str, object]] = list(response.thinking_blocks)
            if response.text:
                blocks.append({"type": "text", "text": response.text})
            for tc in response.tool_calls:
                blocks.append(
                    {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.input}
                )
            context.add_assistant_message(blocks)

            # [act] execute each requested tool; errors become tool results so loop continues
            if response.stop_reason == "tool_use":
                for tc in response.tool_calls:
                    result = await invoke_tool(
                        self._registry, tc, self._bus, context.run_id,
                        permission_manager=self._permission_manager,
                        session_id=self._session_id,
                    )
                    context.add_tool_result(tc.id, result.content, is_error=result.is_error)

                    # [track] 追踪权限拒绝，触发熔断干预
                    if self._denial_tracker is not None:
                        if result.error_type == "permission_denied":
                            self._denial_tracker.record_denial(tc.name)
                        elif not result.is_error:
                            self._denial_tracker.record_success(tc.name)
            elif response.stop_reason == "max_tokens" and response.tool_calls:
                # Output token limit hit mid-tool-call; input is incomplete.
                # Add synthetic error results so the conversation stays balanced.
                for tc in response.tool_calls:
                    context.add_tool_result(
                        tc.id,
                        "Error: output token limit reached before this tool call could be completed. "
                        "Please break the task into smaller steps and try again.",
                        is_error=True,
                    )

            # 仅在真正终止的那一步（end_turn 或 max_steps 已到）才等待后台 subagent 落定，
            # 避免中间 tool_use 步骤过早清空 pending 导致最终摘要丢失
            pending_summaries: list[str] = []
            if context.pending_background_run_ids and (
                response.stop_reason == "end_turn" or context.step >= context.max_steps
            ):
                pending_summaries = await self._wait_for_background(context)

            # Termination check — end_turn wins over max_steps if both hit on same step
            if response.stop_reason == "end_turn":
                base = response.text or ""
                if pending_summaries:
                    base += "\n\n" + "\n".join(pending_summaries)
                context.result = base
                context.mark_success()
            elif context.step >= context.max_steps:
                if pending_summaries:
                    context.result = "\n".join(pending_summaries)
                context.mark_failed("exceeded_max_steps")

            # 工具结果追加完毕（messages 末尾为 user）后检查压缩，仅在 run 继续时触发
            # 此时压缩结果 [user_summary, assistant_ack] 对下一次 LLM 调用是合法输入
            if (
                not context.is_done()
                and response.stop_reason == "tool_use"
                and self._compactor is not None
                and self._compact_threshold > 0
                and response.usage is not None
                and response.usage.context_pct >= self._compact_threshold
            ):
                await self._compactor.compact(context, self._provider)

            await self._bus.publish(
                StepFinishedEvent(run_id=context.run_id, step=context.step, ts=_now())
            )

    # 等待本 run 派生的后台 subagent 全部结束，返回每条的结果摘要
    async def _wait_for_background(
        self, context: ExecutionContext
    ) -> list[str]:
        if self._task_registry is None or not context.pending_background_run_ids:
            return []
        run_ids = sorted(context.pending_background_run_ids)
        context.pending_background_run_ids.clear()
        entries = [self._task_registry.get(rid) for rid in run_ids]
        tasks = [e[0] for e in entries if e is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        summaries: list[str] = []
        for rid, entry in zip(run_ids, entries):
            if entry is None:
                summaries.append(f"[subagent {rid}] status=unknown")
                continue
            task, child_ctx = entry
            if task.cancelled():
                summaries.append(f"[subagent {rid}] status=cancelled")
            elif task.exception() is not None:
                summaries.append(f"[subagent {rid}] status=error: {task.exception()!r}")
            else:
                text = (child_ctx.result or "").strip()[:200]
                summaries.append(f"[subagent {rid}] status={child_ctx.status}: {text}")
        return summaries
