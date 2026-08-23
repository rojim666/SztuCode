from __future__ import annotations

from collections.abc import Awaitable, Callable

from pydantic import BaseModel

type EventHandler = Callable[[BaseModel], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[EventHandler] = []

    # 注册一个事件处理函数
    def subscribe(self, handler: EventHandler) -> None:
        self._subscribers.append(handler)

    # 移除一个事件处理函数（run 结束后注销，防止订阅者随 run 次数累积拖慢每次分发）
    def unsubscribe(self, handler: EventHandler) -> None:
        if handler in self._subscribers:
            self._subscribers.remove(handler)

    # 按注册顺序依次调用所有订阅者
    async def publish(self, event: BaseModel) -> None:
        for handler in self._subscribers:
            await handler(event)
