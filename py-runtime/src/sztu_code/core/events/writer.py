from __future__ import annotations

import logging
from pathlib import Path
from typing import IO

from pydantic import BaseModel

from sztu_code.core.events.bus import EventBus

logger = logging.getLogger(__name__)

# 每写满 N 个事件才 flush 一次：高频流式事件（llm.token/llm.thinking）不再逐条触发磁盘 syscall
_FLUSH_INTERVAL = 32
# 流式增量事件走批量 flush；其余事件视为生命周期关键事件，写入后立即 flush（落盘 barrier）
_STREAM_EVENT_TYPES = frozenset({"llm.token", "llm.thinking"})


class EventWriter:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._file: IO[str] | None = None
        self._bus: EventBus | None = None
        self._pending = 0

    # 打开事件文件（追加模式），供 async with 使用
    async def __aenter__(self) -> EventWriter:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self._path, "a", encoding="utf-8")
        return self

    # 关闭事件文件：先补 flush 未落盘的事件，再注销 bus 订阅（防止订阅者随 run 次数累积）
    async def __aexit__(self, *args: object) -> None:
        if self._bus is not None:
            self._bus.unsubscribe(self.handle)
            self._bus = None
        if self._file is not None:
            if self._pending:
                self._pending = 0
                self._file.flush()
            self._file.close()
            self._file = None

    # 将事件序列化为 JSON 行并写入文件，每 _FLUSH_INTERVAL 条 flush 一次；
    # 写入失败时记录日志但不抛出异常
    async def handle(self, event: BaseModel) -> None:
        if self._file is None:
            return
        try:
            self._file.write(event.model_dump_json() + "\n")
            self._pending += 1
            if getattr(event, "type", "") not in _STREAM_EVENT_TYPES:
                # 生命周期事件即时落盘，崩溃后 events.jsonl 也保有完整的事件序列
                self._pending = 0
                self._file.flush()
            elif self._pending >= _FLUSH_INTERVAL:
                self._pending = 0
                self._file.flush()
        except (OSError, ValueError) as e:
            logger.error("EventWriter: failed to write event: %s", e)

    # 将 handle 注册为 bus 的订阅者
    def subscribe(self, bus: EventBus) -> None:
        self._bus = bus
        bus.subscribe(self.handle)
