from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sztu_code.core.compact.canvas import TaskCanvas
    from sztu_code.core.memory.working_state import WorkingState
    from sztu_code.core.pricing import CostEstimate, PricingCatalog, UnknownPricingPolicy


# 终止原因枚举 — 仿 Claude Code 的 7 种退出条件
class TerminationReason(StrEnum):
    SUCCESS = "success"                         # LLM 返回 end_turn，正常完成
    MAX_TURNS = "max_turns"                     # 达到 max_steps 上限
    CANCELLED = "cancelled"                      # 用户手动取消
    LLM_ERROR = "llm_error"                      # LLM API 调用异常
    REPEATED_ERROR = "repeated_error"            # 同一错误连续 N 次
    MAX_BUDGET_USD = "max_budget_usd"            # 成本上限触及
    BLOCKING_LIMIT = "blocking_limit"            # 上下文窗口即将溢出，无法继续


# 继续原因 — 仿 Claude Code 的 7 种 continue transition
class ContinueReason(StrEnum):
    NEXT_TURN = "next_turn"                              # 模型调用了工具，正常继续
    REACTIVE_COMPACT = "reactive_compact"                 # 上下文不足，压缩后重试
    MAX_OUTPUT_TOKENS_RECOVERY = "max_output_tokens_rec"  # 输出超限，升级后重试


@dataclass
class ExecutionContext:
    run_id: str
    goal: str
    max_steps: int
    prefill_messages: list[dict[str, Any]] = field(default_factory=list)
    session_notes: str = ""
    global_context: str = ""
    project_context: str = ""
    project_profile_context: str = ""
    base_system_prompt: str = ""  # 分层基础提示词（runner 构建），空则回退默认
    messages: list[dict[str, Any]] = field(default_factory=list)
    step: int = 0
    status: str = "running"  # "running" | "success" | "failed" | "interrupted"
    reason: str | None = None
    result: str = ""
    # skill 或 subagent 角色可覆盖默认 system prompt
    system_prompt_override: str | None = None
    # 本 run 派生的后台 subagent run_id 集合，结束回合前等待其全部落定
    pending_background_run_ids: set[str] = field(default_factory=set)
    compacted: bool = False
    # 滑动窗口压缩计数（增量摘要上下文）
    compaction_count: int = 0
    # 连续压缩失败计数（熔断器）
    compaction_failure_count: int = 0
    # Mermaid 任务画布（Phase 2）：由 AgentLoop 维护，作为增量状态追加到消息尾部
    canvas: TaskCanvas | None = None
    # Recuris 工作记忆：证据门控的结构化任务状态，版本变化时注入消息尾部
    working_state: WorkingState | None = None
    # 已注入消息尾部的 working_state 版本；-1 表示尚未注入过
    working_state_injected_version: int = -1
    # ---- agent run 预算 ----
    max_tokens: int = 0           # 仅保留给显式子任务预算；主 Agent 不设置累计 Token 上限
    max_wall_clock_s: int = 0     # 累计墙钟秒数上限；0=不限
    total_input_tokens: int = 0   # 已累计 input tokens（每步 LLM 调用后累加）
    total_output_tokens: int = 0  # 已累计 output tokens
    total_cache_read_input_tokens: int = 0  # 已累计命中提示词缓存的 input tokens
    total_cache_creation_input_tokens: int = 0  # 已累计写入提示词缓存的 input tokens
    last_context_pct: float = 0.0  # 最近一次 LLM 调用的上下文占用百分比（用于 run 级结算透传）
    started_at: float = 0.0       # run 开始墙钟（time.monotonic()），loop 惰性初始化
    max_budget_usd: float = 0.0   # USD 成本上限（0 = 不限制）
    # --- Claude Code 风格终止/继续系统 ---
    # 错误累积器：{tool_name: {error_type: count}} — 同一工具同类错误重复 N 次触发熔断
    error_accumulator: dict[str, dict[str, int]] = field(default_factory=dict)
    # 输出 token 恢复计数：max_output_tokens 恢复尝试次数（最多 3 次）
    max_output_tokens_recovery_count: int = 0
    # 最后一次 continue 原因（调试/追踪用）
    last_continue_reason: str = ""

    # 初始化消息历史，优先使用 session 完整回放内容
    def __post_init__(self) -> None:
        if self.prefill_messages:
            self.messages = [dict(m) for m in self.prefill_messages]
        elif not self.messages:
            self.messages.append({"role": "user", "content": self.goal})

    # 返回当前 run 的 system prompt；有 override 时跳过 base，直接注入记忆层
    def system_prompt(self, base: str) -> str:
        parts = [self.system_prompt_override if self.system_prompt_override else base]
        if self.global_context.strip():
            parts.append("\n\n## Global Context\n" + self.global_context.strip())
        if self.project_context.strip():
            parts.append("\n\n## Project Context\n" + self.project_context.strip())
        if self.project_profile_context.strip():
            parts.append("\n\n## Project Profile\n" + self.project_profile_context.strip())
        if self.session_notes.strip():
            parts.append(
                "\n\n## Session Notes\n"
                + self.session_notes.strip()
                + "\n\nRemember important durable facts by calling note_save."
            )
        return "".join(parts)

    # 将动态任务状态追加到消息尾部，保持 system prompt 字节级稳定以命中前缀缓存
    def add_canvas_update(self) -> None:
        if self.canvas is None or not self.canvas.nodes:
            return
        node = self.canvas.nodes[-1]
        stats = self.canvas.stats()
        detail = node.summary.strip()[:240]
        text = (
            f"[Task progress] {node.node_id} {node.status}: {node.label[:100]}"
            f" | tools={','.join(node.tool_names[:4]) or 'none'}"
            f" | totals=done:{stats.get('done', 0)},failed:{stats.get('failed', 0)}"
        )
        if detail:
            text += f" | result={detail}"
        block = {"type": "text", "text": text}
        # 独立消息确保 OpenAI 转换后 tool_result 仍紧跟对应 assistant tool_call
        self.messages.append({"role": "user", "content": [block]})

    # 将工作记忆以紧凑形式追加到消息尾部（仅状态版本变化时）
    # 与画布更新同样走消息尾部，保持 system prompt 字节级稳定以命中前缀缓存
    def add_working_state_update(self) -> bool:
        ws = self.working_state
        # version=0 表示尚无证据门控内容（仅静态 goals），不注入
        if ws is None or ws.version == 0:
            return False
        if ws.version == self.working_state_injected_version:
            return False
        text = ws.render()
        if not text:
            return False
        self.working_state_injected_version = ws.version
        block = {"type": "text", "text": text}
        self.messages.append({"role": "user", "content": [block]})
        return True

    # 将 LLM 响应的 content blocks 追加为 assistant 消息
    def add_assistant_message(self, content: list[Any]) -> None:
        self.messages.append({"role": "assistant", "content": content})

    # 将工具调用结果追加为 user 消息；同一步的多个结果共享同一条消息
    def add_tool_result(
        self, tool_use_id: str, content: str, is_error: bool = False
    ) -> None:
        block: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content,
        }
        if is_error:
            block["is_error"] = True

        last = self.messages[-1] if self.messages else None
        if (
            last is not None
            and last["role"] == "user"
            and isinstance(last["content"], list)
            and last["content"]
            and all(b.get("type") == "tool_result" for b in last["content"])
        ):
            last["content"].append(block)
        else:
            self.messages.append({"role": "user", "content": [block]})

    # 返回 True 表示 loop 应停止（状态不再是 running）
    def is_done(self) -> bool:
        return self.status != "running"

    # 将 run 标记为成功
    def mark_success(self) -> None:
        self.status = "success"
        self.reason = TerminationReason.SUCCESS

    # 将 run 标记为失败并记录终止原因
    def mark_failed(self, reason: str) -> None:
        self.status = "failed"
        self.reason = reason

    # 将 run 标记为中断（预算/上限耗尽但可续跑），区别于真正的失败
    def mark_interrupted(self, reason: str) -> None:
        self.status = "interrupted"
        self.reason = reason

    # 返回累计 token 总数（input + output）
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    # 返回 token 预算是否已耗尽；max_tokens=0 视为不限
    def token_budget_exhausted(self) -> bool:
        return self.max_tokens > 0 and self.total_tokens() >= self.max_tokens

    # 返回 run 已运行的墙钟秒数；started_at 未初始化时返回 0
    def elapsed_s(self) -> float:
        return time.monotonic() - self.started_at if self.started_at > 0 else 0.0

    # 返回墙钟预算是否已超时；max_wall_clock_s=0 视为不限
    def wall_clock_exceeded(self) -> bool:
        return (
            self.max_wall_clock_s > 0
            and self.started_at > 0
            and self.elapsed_s() >= self.max_wall_clock_s
        )

    # --- Claude Code 风格错误累积 ---

    # 记录工具错误，返回 True 表示已触发重复错误熔断
    def record_error(self, tool_name: str, error_type: str = "runtime_error") -> bool:
        if tool_name not in self.error_accumulator:
            self.error_accumulator[tool_name] = {}
        self.error_accumulator[tool_name][error_type] = (
            self.error_accumulator[tool_name].get(error_type, 0) + 1
        )
        return self.error_accumulator[tool_name][error_type] >= 3

    # 记录成功工具调用，重置所有工具的累积错误计数
    def record_success(self) -> None:
        if self.error_accumulator:
            self.error_accumulator.clear()

    # 检查是否触发上下文阻塞限制（context_pct > 98% → 无法继续）
    def is_at_blocking_limit(self, context_pct: float) -> bool:
        return context_pct > 0.98

    # 检查 USD 预算是否已耗尽（旧版，固定价格，已弃用）
    def is_over_budget(self, cost_per_input: float = 3.0, cost_per_output: float = 15.0) -> bool:
        if self.max_budget_usd <= 0:
            return False
        cost = (
            self.total_input_tokens / 1_000_000 * cost_per_input
            + self.total_output_tokens / 1_000_000 * cost_per_output
        )
        return cost >= self.max_budget_usd

    # 计算当前累积 usage 的成本估算
    def estimate_cost(
        self,
        provider: str,
        model: str,
        catalog: PricingCatalog | None = None,
    ) -> CostEstimate:
        from sztu_code.core.pricing import (
            TokenUsage,
            calculate_cost,
            get_builtin_catalog,
        )

        if catalog is None:
            catalog = get_builtin_catalog()

        usage = TokenUsage(
            input_tokens=self.total_input_tokens,
            output_tokens=self.total_output_tokens,
            cache_read_input_tokens=self.total_cache_read_input_tokens,
            cache_creation_input_tokens=self.total_cache_creation_input_tokens,
        )

        return calculate_cost(provider, model, usage, catalog)

    # 检查是否超出 USD 预算（使用 pricing catalog）
    def is_over_budget_with_pricing(
        self,
        provider: str = "",
        model: str = "",
        pricing_catalog: PricingCatalog | None = None,
        unknown_policy: UnknownPricingPolicy | None = None,
    ) -> bool:
        from sztu_code.core.pricing import UnknownPricingPolicy

        if self.max_budget_usd <= 0:
            return False

        # 缺少模型身份时不能静默回退旧固定价格
        if not provider or not model:
            if unknown_policy is None:
                unknown_policy = UnknownPricingPolicy.FAIL_OPEN
            return unknown_policy == UnknownPricingPolicy.FAIL_CLOSED

        if unknown_policy is None:
            unknown_policy = UnknownPricingPolicy.FAIL_OPEN

        estimate = self.estimate_cost(provider, model, pricing_catalog)

        if estimate.status in {"unknown", "incomplete"}:
            # 未知或不完整定价：根据策略决定
            return unknown_policy == UnknownPricingPolicy.FAIL_CLOSED

        if estimate.amount is None:
            # 无法计算（极端情况），保守失败
            return unknown_policy == UnknownPricingPolicy.FAIL_CLOSED

        # 比较 Decimal 和 float 时需要转换
        return float(estimate.amount) >= self.max_budget_usd
