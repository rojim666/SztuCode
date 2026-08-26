from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_MAX_CONSECUTIVE = 3
_DEFAULT_MAX_TOTAL = 20


class DenialTracker:
    """追踪工具调用的权限拒绝，连续拒绝或总量超限时触发熔断干预。

    参考 Claude Code 的 denialTracking.ts：
    - maxConsecutive=3：同工具连续被拒 3 次触发干预
    - maxTotal=20：跨所有工具累计 20 次拒绝触发干预
    - record_success() 重置对应工具的连续计数器
    - should_intervene() 返回 True 后需调用 reset_intervention() 防止重复注入
    """

    # 初始化拒绝追踪器，可覆盖连续和总量阈值
    def __init__(
        self,
        max_consecutive: int = _DEFAULT_MAX_CONSECUTIVE,
        max_total: int = _DEFAULT_MAX_TOTAL,
    ) -> None:
        self._max_consecutive = max_consecutive
        self._max_total = max_total
        # 按工具名记录连续拒绝次数
        self._consecutive: dict[str, int] = {}
        # 跨所有工具的拒绝总数
        self._total: int = 0
        # 是否已在本轮注入过干预消息（防止同一轮重复注入）
        self._intervened_this_cycle: bool = False

    # 记录一次拒绝，返回 True 表示已达到干预阈值
    def record_denial(self, tool_name: str) -> bool:
        self._consecutive[tool_name] = self._consecutive.get(tool_name, 0) + 1
        self._total += 1
        logger.debug(
            "denial_tracker: tool=%s consecutive=%d total=%d",
            tool_name, self._consecutive[tool_name], self._total,
        )
        return self.should_intervene()

    # 记录一次成功调用，重置该工具的连续拒绝计数并结束干预周期
    def record_success(self, tool_name: str) -> None:
        if tool_name in self._consecutive:
            old = self._consecutive[tool_name]
            self._consecutive[tool_name] = 0
            logger.debug(
                "denial_tracker: reset tool=%s was=%d", tool_name, old,
            )
        # 成功调用表示 AI 已改变策略，结束当前干预周期，允许后续再次触发干预
        self._intervened_this_cycle = False

    # 检查是否应触发熔断干预
    # 连续计数器在 reset 后被清空，重新累积即代表新一轮，始终允许触发
    # 总量超限时检查 _intervened_this_cycle 防止同一 total 阈值反复注入
    def should_intervene(self) -> bool:
        for count in self._consecutive.values():
            if count >= self._max_consecutive:
                return True
        if self._total >= self._max_total and not self._intervened_this_cycle:
            return True
        return False

    # 生成人类可读的干预消息，列出被拒工具和次数
    def intervention_message(self) -> str:
        denied = sorted(
            [(n, c) for n, c in self._consecutive.items() if c > 0],
            key=lambda x: -x[1],
        )
        parts = [f"  {name} ({count} time{'s' if count > 1 else ''})" for name, count in denied]
        return (
            "Your previous tool calls have been repeatedly rejected. "
            "The following tools were denied:\n"
            + "\n".join(parts)
            + "\n\nPlease change your approach — try a different tool, "
            "modify your parameters, or ask the user for guidance."
        )

    # 标记本轮已注入干预消息，防止后续步骤重复注入
    def reset_intervention(self) -> None:
        self._intervened_this_cycle = True
        # 重置连续计数器，给 AI 一个"干净的 slate"重新尝试
        self._consecutive.clear()
        logger.info(
            "denial_tracker: intervention injected, counters reset (total=%d)",
            self._total,
        )

    # 返回追踪器当前状态快照，供事件和日志使用
    def snapshot(self) -> dict[str, Any]:
        return {
            "consecutive": dict(self._consecutive),
            "total": self._total,
            "intervened": self._intervened_this_cycle,
        }
