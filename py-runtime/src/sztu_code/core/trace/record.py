from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class TraceRecord(BaseModel):
    """一条 trace 记录。

    `kind` 与 `data` 是自由字段，新增记录类型不需要改这个结构；但为了让消费方
    （`sztu trace` 的 `_summarize`、外部分析）有稳定契约，约定如下：

    - `kind="deadline"`（Issue #69）：Run 因 wall-clock deadline 终止时，由终态边界
      在清理完成后发一条。`data` 必须含：
      - `stage`: str —— 撞上 deadline 的阶段，取值 `llm` / `tool` / `permission` /
        `subagent` / `compact` / `wrap_up` / `loop`
      - `reason`: str —— 终止原因，与同 run 的 `run.finished` 一致
        （时间耗尽场景为 `max_wall_clock_exceeded`）
      - `cleanup`: str —— 清理结果，取值 `completed` / `cancelled_bounded` / `unknown`
      - `cancelled_descendants`: int —— 被取消的后代 run 数量
    """

    ts: str
    direction: Literal[
        "CLIENT→CORE",
        "CORE→CLIENT",
        "CORE",
        "CORE→LLM",
        "LLM→CORE",
    ]
    layer: Literal["ipc", "event", "llm"]
    # 约定取值：command / response / error / push / event / api_call / api_response / deadline
    kind: str
    run_id: str | None = None
    step: int | None = None
    client_id: str | None = None
    data: dict[str, Any]
