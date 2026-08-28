from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel

from sztu_code.core.bus.events import LlmThinkingEvent, LlmTokenEvent

type EventHandler = Callable[[BaseModel], Awaitable[None]]

logger = logging.getLogger(__name__)

# 高频流式事件（逐 token/逐思考块）：观测队列满时可合并或丢弃；
# 其余事件视为生命周期关键事件，任何情况下不允许静默丢失
STREAM_EVENT_TYPES = frozenset({"llm.token", "llm.thinking"})
# 观测队列默认容量：正常渲染消费远快于填充速度，压满说明订阅者已卡死
_DEFAULT_OBSERVER_QUEUE_SIZE = 256
_DEFAULT_DRAIN_TIMEOUT_S = 2.0
# 关键事件在观测队列满时的最长等待；超时后淘汰最旧事件腾位，避免无限阻塞核心 loop
_ENQUEUE_TIMEOUT_S = 5.0


@dataclass
class ObserverStats:
    """观测订阅者的投递计数，用于压测断言和运行时可观测"""

    delivered: int = 0
    dropped: int = 0
    merged: int = 0
    errors: int = 0
    undelivered: int = 0


def _is_stream_event(event: BaseModel) -> bool:
    return getattr(event, "type", "") in STREAM_EVENT_TYPES


# 把相邻同源的 token/thinking 增量合并为单条事件；返回 None 表示不可合并。
# 增量文本拼接即客户端的渲染方式，因此合并不丢内容。
def _merge_stream_events(prev: BaseModel, new: BaseModel) -> BaseModel | None:
    if isinstance(prev, LlmTokenEvent) and isinstance(new, LlmTokenEvent):
        if prev.run_id == new.run_id:
            return new.model_copy(update={"token": prev.token + new.token, "ts": new.ts})
        return None
    if isinstance(prev, LlmThinkingEvent) and isinstance(new, LlmThinkingEvent):
        if prev.run_id == new.run_id and prev.step == new.step:
            return new.model_copy(
                update={"thinking": prev.thinking + new.thinking, "ts": new.ts}
            )
        return None
    return None


class _EventQueue:
    """观测订阅者的有界 FIFO 队列。基于 deque 实现，以便合并时检视队尾、
    淘汰时移除队首；put/get 的唤醒语义与 asyncio.Queue 一致"""

    def __init__(self, maxsize: int) -> None:
        self.items: deque[BaseModel] = deque()
        self._maxsize = max(1, maxsize)
        self._not_empty = asyncio.Event()
        self._space_available = asyncio.Event()
        self._space_available.set()

    def qsize(self) -> int:
        return len(self.items)

    def full(self) -> bool:
        return len(self.items) >= self._maxsize

    def put_nowait(self, item: BaseModel) -> None:
        self.items.append(item)
        self._not_empty.set()
        if self.full():
            self._space_available.clear()

    def pop_oldest(self) -> BaseModel:
        item = self.items.popleft()
        self._space_available.set()
        return item

    async def put(self, item: BaseModel) -> None:
        while self.full():
            self._space_available.clear()
            await self._space_available.wait()
        self.put_nowait(item)

    async def get(self) -> BaseModel:
        while not self.items:
            self._not_empty.clear()
            await self._not_empty.wait()
        item = self.items.popleft()
        self._space_available.set()
        return item


class _ObserverWorker:
    """每个观测订阅者一个 worker task：FIFO 保序，handler 异常只计数不外泄"""

    def __init__(self, handler: EventHandler, queue_size: int) -> None:
        self._handler = handler
        self._queue = _EventQueue(queue_size)
        self.stats = ObserverStats()
        self._closed = False
        self._task: asyncio.Task[None] | None = None
        # idle=在 get() 等待新事件；clear 表示正在执行 handler（在途事件）
        self._idle = asyncio.Event()
        self._idle.set()
        self._inflight_cancelled = False

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            while True:
                event = await self._queue.get()
                self._idle.clear()
                try:
                    await self._handler(event)
                    self.stats.delivered += 1
                except Exception:
                    self.stats.errors += 1
                    logger.exception(
                        "event bus: observer subscriber failed on %s",
                        type(event).__name__,
                    )
                self._idle.set()
        except asyncio.CancelledError:
            # 在途事件被取消即未投递；在 get() 中被取消则无在途事件（idle 已置位）
            if not self._idle.is_set():
                self._inflight_cancelled = True

    async def enqueue(self, event: BaseModel) -> None:
        if self._closed:
            self.stats.undelivered += 1
            return
        queue = self._queue
        if not queue.full():
            queue.put_nowait(event)
            return
        if _is_stream_event(event):
            # 队尾同源流式事件直接合并，内容零丢失
            merged = _merge_stream_events(queue.items[-1], event) if queue.items else None
            if merged is not None:
                queue.items[-1] = merged
                self.stats.merged += 1
                return
            # 不同源：淘汰最旧的流式事件给新事件腾位
            for existing in queue.items:
                if _is_stream_event(existing):
                    queue.items.remove(existing)
                    self.stats.dropped += 1
                    break
            if not queue.full():
                queue.put_nowait(event)
            else:
                self.stats.dropped += 1
            return
        # 生命周期关键事件：有限等待腾位；超时淘汰最旧事件，保证关键事件最终入队
        try:
            await asyncio.wait_for(queue.put(event), timeout=_ENQUEUE_TIMEOUT_S)
        except TimeoutError:
            evicted = queue.pop_oldest()
            self.stats.dropped += 1
            logger.error(
                "event bus: observer queue full for %.1fs, evicted %s to deliver %s",
                _ENQUEUE_TIMEOUT_S,
                type(evicted).__name__,
                type(event).__name__,
            )
            queue.put_nowait(event)

    async def close(self, drain_timeout: float) -> int:
        """停止接收新事件，有界等待队列清空且在途事件处理完成，返回未投递事件数"""
        self._closed = True
        loop = asyncio.get_running_loop()
        deadline = loop.time() + drain_timeout
        while (
            self._queue.qsize() > 0 or not self._idle.is_set()
        ) and loop.time() < deadline:
            await asyncio.sleep(0.005)
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        undelivered = self._queue.qsize() + (1 if self._inflight_cancelled else 0)
        self.stats.undelivered = undelivered
        return undelivered


class ObserverHandle:
    """观测订阅的句柄：查询统计并负责有界 drain 后退订"""

    def __init__(self, bus: EventBus, worker: _ObserverWorker) -> None:
        self._bus = bus
        self._worker = worker

    @property
    def stats(self) -> ObserverStats:
        return self._worker.stats

    @property
    def pending(self) -> int:
        return self._worker._queue.qsize()

    async def unsubscribe(self, drain_timeout: float = _DEFAULT_DRAIN_TIMEOUT_S) -> int:
        self._bus._remove_observer(self._worker)
        return await self._worker.close(drain_timeout)


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[EventHandler] = []
        self._observers: list[_ObserverWorker] = []

    # 注册一个事件处理函数
    def subscribe(self, handler: EventHandler) -> None:
        self._subscribers.append(handler)

    # 移除一个事件处理函数（run 结束后注销，防止订阅者随 run 次数累积拖慢每次分发）
    def unsubscribe(self, handler: EventHandler) -> None:
        if handler in self._subscribers:
            self._subscribers.remove(handler)

    # 注册观测订阅者：慢 UI/遥测等 best-effort 订阅者经有界队列异步投递，
    # 不阻塞 publish；返回句柄用于退订和统计查询
    def subscribe_observer(
        self,
        handler: EventHandler,
        *,
        queue_size: int = _DEFAULT_OBSERVER_QUEUE_SIZE,
    ) -> ObserverHandle:
        worker = _ObserverWorker(handler, queue_size)
        self._observers.append(worker)
        worker.start()
        return ObserverHandle(self, worker)

    def _remove_observer(self, worker: _ObserverWorker) -> None:
        if worker in self._observers:
            self._observers.remove(worker)

    # 可靠订阅者按注册顺序依次 await（事件序是生命周期正确性的前提）；
    # 单个订阅者异常只记录日志，不再中断后续订阅者或改变 run 状态；
    # 观测订阅者仅入队，投递在各自 worker 中异步完成
    async def publish(self, event: BaseModel) -> None:
        for handler in list(self._subscribers):
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "event bus: reliable subscriber failed on %s", type(event).__name__
                )
        for observer in list(self._observers):
            await observer.enqueue(event)

    # 有界 drain 所有观测队列（shutdown 用），返回仍未投递的事件总数
    async def close_observers(self, timeout: float = _DEFAULT_DRAIN_TIMEOUT_S) -> int:
        total = 0
        for worker in list(self._observers):
            total += await worker.close(timeout)
        return total
