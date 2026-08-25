from __future__ import annotations

import json
import logging
from typing import Any

from sztu_code.core.llm.types import ToolCallBlock

logger = logging.getLogger(__name__)


# 生成稳定的"卡死"签名：bash 用完整 command（保留参数），读写类用 path，其余用稳定 JSON
def stuck_signature(tool_call: ToolCallBlock) -> tuple[str, str]:
    name = tool_call.name
    if name == "bash":
        return (name, str(tool_call.input.get("command", "")).strip())
    for key in ("path", "file_path"):
        if key in tool_call.input:
            return (name, str(tool_call.input[key]))
    try:
        return (name, json.dumps(tool_call.input, sort_keys=True, default=str))
    except (TypeError, ValueError):
        return (name, str(tool_call.input))


# 追踪"同一操作反复失败"的卡死：连续同签名失败达阈值触发软干预，累计干预达阈值可硬停
class StuckLoopTracker:
    # 初始化卡死追踪器，可覆盖连续失败阈值与硬停阈值
    def __init__(self, max_failures: int = 2, max_total: int = 0) -> None:
        self._max_failures = max_failures
        self._max_total = max_total
        self._consecutive: dict[tuple[str, str], int] = {}
        self._interventions = 0
        self._intervened_this_cycle = False

    # 记录一次失败，返回 True 表示已达干预阈值
    def record_failure(self, signature: tuple[str, str]) -> bool:
        self._consecutive[signature] = self._consecutive.get(signature, 0) + 1
        logger.debug(
            "stuck_tracker: sig=%s consecutive=%d",
            signature, self._consecutive[signature],
        )
        return self.should_intervene()

    # 记录一次成功，重置该签名连续失败计数并结束干预周期
    def record_success(self, signature: tuple[str, str]) -> None:
        if signature in self._consecutive:
            self._consecutive[signature] = 0
        self._intervened_this_cycle = False

    # 检查是否应注入卡死干预；max_failures<=0 时关闭
    def should_intervene(self) -> bool:
        if self._max_failures <= 0:
            return False
        return any(count >= self._max_failures for count in self._consecutive.values())

    # 生成人类可读的干预消息，列出连续失败最严重的签名
    def intervention_message(self) -> str:
        worst = max(self._consecutive.items(), key=lambda kv: kv[1], default=(("", ""), 0))
        (name, key), count = worst
        return (
            "Your previous tool call has failed repeatedly and appears to be stuck.\n"
            f"  {name} → {key!r} ({count} consecutive failures)\n\n"
            "Please change your approach — do not retry the same failing call. "
            "Try different parameters, another tool, or re-plan the task."
        )

    # 标记本轮已注入干预并累计次数；重置连续计数给 AI 干净的起点
    def reset_intervention(self) -> None:
        self._intervened_this_cycle = True
        self._interventions += 1
        self._consecutive.clear()

    # 返回是否达到硬停阈值；max_total<=0 表示永不硬停
    def hard_stop_reached(self) -> bool:
        return self._max_total > 0 and self._interventions >= self._max_total

    # 返回追踪器状态快照，供事件和日志使用
    def snapshot(self) -> dict[str, Any]:
        worst = max(self._consecutive.items(), key=lambda kv: kv[1], default=(("", ""), 0))
        return {
            "consecutive": {
                f"{name}:{key}": c for (name, key), c in self._consecutive.items()
            },
            "worst_signature": f"{worst[0][0]}:{worst[0][1]}",
            "worst_count": worst[1],
            "interventions": self._interventions,
            "intervened": self._intervened_this_cycle,
        }
