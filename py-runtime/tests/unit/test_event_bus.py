from __future__ import annotations

import asyncio
import time

import pytest
from pydantic import BaseModel

from sztu_code.core.bus.events import (
    LlmTokenEvent,
    RunFinishedEvent,
    RunStartedEvent,
    StepFinishedEvent,
    StepStartedEvent,
)
from sztu_code.core.events import bus as event_bus_module
from sztu_code.core.events.bus import EventBus


class _FakeEvent(BaseModel):
    value: str


# 功能：验证 publish 后订阅者能收到事件对象
# 设计：用内联 handler 收集事件引用，断言 is 而非 ==，排除序列化中间步骤的干扰
async def test_publish_reaches_subscriber() -> None:
    bus = EventBus()
    received: list[BaseModel] = []

    async def handler(event: BaseModel) -> None:
        received.append(event)

    bus.subscribe(handler)
    event = _FakeEvent(value="hello")
    await bus.publish(event)
    assert received == [event]


# 功能：验证多个订阅者都能独立收到同一事件
# 设计：两个独立计数器分别累加，避免共享状态掩盖某一订阅者未被调用的情况
async def test_multiple_subscribers_all_receive() -> None:
    bus = EventBus()
    counts = [0, 0]

    async def h1(e: BaseModel) -> None:
        counts[0] += 1

    async def h2(e: BaseModel) -> None:
        counts[1] += 1

    bus.subscribe(h1)
    bus.subscribe(h2)
    await bus.publish(_FakeEvent(value="x"))
    assert counts == [1, 1]


# 功能：验证多个订阅者按注册顺序被依次调用
# 设计：用追加整数到列表来记录调用次序，因为 bus 的顺序语义是 AgentLoop 事件序列正确性的前提
async def test_subscribers_called_in_order() -> None:
    bus = EventBus()
    order: list[int] = []

    async def h1(e: BaseModel) -> None:
        order.append(1)

    async def h2(e: BaseModel) -> None:
        order.append(2)

    bus.subscribe(h1)
    bus.subscribe(h2)
    await bus.publish(_FakeEvent(value="x"))
    assert order == [1, 2]


# 功能：验证无订阅者时 publish 不抛异常（空 bus 边界条件）
# 设计：只调用 publish，不断言返回值，以"不引发异常"作为唯一判据
async def test_no_subscribers_publish_is_noop() -> None:
    bus = EventBus()
    await bus.publish(_FakeEvent(value="x"))  # should not raise


# ---------------------------------------------------------------------------
# 观测订阅者（subscribe_observer）：有界队列、异常隔离、合并/丢弃策略
# ---------------------------------------------------------------------------


def _token(run_id: str, token: str) -> LlmTokenEvent:
    return LlmTokenEvent(run_id=run_id, token=token, ts="2026-08-28T00:00:00Z")


# 功能：验证慢观测订阅者不阻塞 publish（issue #75 核心验收标准）
# 设计：观测者每事件 sleep 100ms，publish 20 个 token 事件；若 publish 被同步
# await 会阻塞约 2s，异步投递则应在远小于该值的时间内返回
async def test_slow_observer_does_not_block_publish() -> None:
    bus = EventBus()

    async def slow_observer(event: BaseModel) -> None:
        await asyncio.sleep(0.1)

    handle = bus.subscribe_observer(slow_observer)
    events = [_token("r", "t") for _ in range(20)]

    start = time.monotonic()
    for event in events:
        await bus.publish(event)
    elapsed = time.monotonic() - start

    assert elapsed < 0.5, f"publish 被慢观测订阅者阻塞了 {elapsed:.2f}s"
    assert handle.stats.dropped == 0
    undelivered = await handle.unsubscribe(drain_timeout=5.0)
    assert undelivered == 0
    assert handle.stats.delivered == 20


# 功能：验证可靠订阅者与观测订阅者互不干扰，且观测者异常不影响他人
# 设计：观测者持续抛异常，可靠订阅者正常收集；publish 不应抛出，最终状态不受影响
async def test_observer_exception_isolated() -> None:
    bus = EventBus()
    received: list[BaseModel] = []

    async def reliable(event: BaseModel) -> None:
        received.append(event)

    async def bad_observer(event: BaseModel) -> None:
        raise RuntimeError("observer boom")

    bus.subscribe(reliable)
    handle = bus.subscribe_observer(bad_observer)

    first, second = _FakeEvent(value="1"), _FakeEvent(value="2")
    await bus.publish(first)  # 不应抛出
    await bus.publish(second)
    assert received == [first, second]

    await handle.unsubscribe()
    assert handle.stats.errors == 2


# 功能：验证可靠订阅者异常只隔离自身，后续订阅者仍收到事件
# 设计：第一个 handler 抛异常，第二个正常收集；旧行为异常会中断后续订阅者，此为回归保护
async def test_reliable_subscriber_exception_does_not_block_next() -> None:
    bus = EventBus()
    received: list[BaseModel] = []

    async def bad(event: BaseModel) -> None:
        raise RuntimeError("reliable boom")

    async def good(event: BaseModel) -> None:
        received.append(event)

    bus.subscribe(bad)
    bus.subscribe(good)
    event = _FakeEvent(value="x")
    await bus.publish(event)  # 不应抛出
    assert received == [event]


# 功能：验证观测订阅者按 FIFO 顺序收到事件
# 设计：观测者带延迟消费，发布序列化生命周期事件，断言收到的 type 顺序与发布一致
async def test_observer_preserves_order() -> None:
    bus = EventBus()
    received: list[str] = []
    started = asyncio.Event()
    gate = asyncio.Event()

    async def slow_observer(event: BaseModel) -> None:
        if not started.is_set():
            started.set()
            await gate.wait()
        received.append(getattr(event, "type", "fake"))
        await asyncio.sleep(0.01)

    handle = bus.subscribe_observer(slow_observer)
    sequence: list[BaseModel] = [
        RunStartedEvent(run_id="r", goal="g", ts="t"),
        StepStartedEvent(run_id="r", step=1, ts="t"),
        StepFinishedEvent(run_id="r", step=1, ts="t"),
        RunFinishedEvent(run_id="r", status="success", steps=1, ts="t"),
    ]
    for event in sequence:
        await bus.publish(event)
    gate.set()
    await handle.unsubscribe(drain_timeout=5.0)
    assert received == [getattr(e, "type") for e in sequence]


# 功能：验证观测队列满时同源 token 增量被合并，拼接后文本零丢失
# 设计：首个事件在 handler 内被 gate 挂起，随后塞满小队列再发布新 token；
# 断言 merged 计数为 1 且收到的 token 拼接与发布拼接一致
async def test_stream_events_merge_when_queue_full() -> None:
    bus = EventBus()
    received: list[LlmTokenEvent] = []
    started = asyncio.Event()
    gate = asyncio.Event()

    async def blocked_observer(event: BaseModel) -> None:
        if not started.is_set():
            started.set()
            await gate.wait()
        if isinstance(event, LlmTokenEvent):
            received.append(event)

    handle = bus.subscribe_observer(blocked_observer, queue_size=2)
    await bus.publish(_token("r", "a"))  # worker 取走并在 handler 中挂起
    await started.wait()
    await bus.publish(_token("r", "b"))
    await bus.publish(_token("r", "c"))  # 队列已满
    await bus.publish(_token("r", "d"))  # 触发队尾合并

    assert handle.stats.merged == 1
    gate.set()
    await handle.unsubscribe(drain_timeout=5.0)
    assert "".join(e.token for e in received) == "abcd"
    assert handle.stats.dropped == 0


# 功能：验证队列满且队尾不可合并（不同 run）时，淘汰最旧流式事件保新事件
# 设计：run r1 的 token 塞满队列后发布 run r2 的 token；断言 dropped=1、
# r2 事件仍在且投递顺序保持 FIFO
async def test_unmergeable_stream_event_evicts_oldest() -> None:
    bus = EventBus()
    received: list[LlmTokenEvent] = []
    started = asyncio.Event()
    gate = asyncio.Event()

    async def blocked_observer(event: BaseModel) -> None:
        if not started.is_set():
            started.set()
            await gate.wait()
        if isinstance(event, LlmTokenEvent):
            received.append(event)

    handle = bus.subscribe_observer(blocked_observer, queue_size=2)
    await bus.publish(_token("r1", "a"))
    await started.wait()
    await bus.publish(_token("r1", "b"))
    await bus.publish(_token("r1", "c"))  # 满
    await bus.publish(_token("r2", "x"))  # 不可合并 → 淘汰最旧

    assert handle.stats.dropped == 1
    gate.set()
    await handle.unsubscribe(drain_timeout=5.0)
    # a 是 worker 已取走的在途事件，gate 释放后补记；被淘汰的是队首 b
    assert [e.token for e in received] == ["a", "c", "x"]


# 功能：验证观测队列满时生命周期关键事件有限等待后仍被投递，不静默丢失
# 设计：worker 挂起、队列塞满后发布 RunStarted；publish 作为任务运行，
# 短暂等待后仍未完成（背压生效），释放 gate 后关键事件最终送达且 dropped=0
async def test_lifecycle_event_backpressures_then_delivered() -> None:
    bus = EventBus()
    received: list[BaseModel] = []
    started = asyncio.Event()
    gate = asyncio.Event()

    async def blocked_observer(event: BaseModel) -> None:
        if not started.is_set():
            started.set()
            await gate.wait()
        received.append(event)

    handle = bus.subscribe_observer(blocked_observer, queue_size=1)
    await bus.publish(_token("r", "a"))  # worker 取走并挂起
    await started.wait()
    await bus.publish(_token("r", "b"))  # 队列满
    critical = RunStartedEvent(run_id="r", goal="g", ts="t")
    publish_task = asyncio.create_task(bus.publish(critical))

    await asyncio.sleep(0.2)
    assert not publish_task.done(), "关键事件应在队列满时背压等待"

    gate.set()
    await asyncio.wait_for(publish_task, timeout=5.0)
    await handle.unsubscribe(drain_timeout=5.0)
    assert critical in received
    assert handle.stats.dropped == 0


# 功能：验证关键事件等待超时后淘汰最旧事件也要完成投递（不允许被丢弃的是关键事件）
# 设计：monkeypatch 缩短 _ENQUEUE_TIMEOUT_S；worker 永久挂起、队列满，关键事件
# 超时后淘汰队首 token 入队，断言关键事件入队且被淘汰者计入 dropped
async def test_lifecycle_event_timeout_evicts_oldest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(event_bus_module, "_ENQUEUE_TIMEOUT_S", 0.1)
    bus = EventBus()
    started = asyncio.Event()
    gate = asyncio.Event()

    async def never_ready(event: BaseModel) -> None:
        if not started.is_set():
            started.set()
            await gate.wait()

    handle = bus.subscribe_observer(never_ready, queue_size=1)
    await bus.publish(_token("r", "a"))  # worker 取走并挂起
    await started.wait()
    await bus.publish(_token("r", "b"))  # 队列满
    critical = RunFinishedEvent(run_id="r", status="success", steps=1, ts="t")
    await asyncio.wait_for(bus.publish(critical), timeout=5.0)

    assert handle.stats.dropped == 1  # 淘汰的是 token b，关键事件保留
    gate.set()
    await handle.unsubscribe(drain_timeout=5.0)


# 功能：验证高频事件压力下观测队列内存有界、投递计数可查询
# 设计：慢观测者 + 小队列，发布 500 个 token；断言队内积压始终不超过容量，
# drain 后 delivered 数量与发布总量一致
async def test_observer_queue_bounded_under_load() -> None:
    bus = EventBus()
    max_pending = 0

    async def slow_observer(event: BaseModel) -> None:
        await asyncio.sleep(0.002)

    handle = bus.subscribe_observer(slow_observer, queue_size=32)
    for i in range(500):
        await bus.publish(_token("r", str(i)))
        max_pending = max(max_pending, handle.pending)

    assert max_pending <= 32
    assert handle.stats.dropped == 0
    await handle.unsubscribe(drain_timeout=10.0)
    # 合并保真：发布 500 条，drain 后"已投递 + 已合并"必须覆盖全部内容
    assert handle.stats.delivered + handle.stats.merged == 500


# 功能：验证退订时有界 drain 并如实上报未投递数量
# 设计：worker 挂起期间堆积事件后退订（短 drain 超时），断言 undelivered 等于
# 未消费的事件数，且 worker 被取消后不再继续消费
async def test_unsubscribe_reports_undelivered() -> None:
    bus = EventBus()
    started = asyncio.Event()
    gate = asyncio.Event()
    count = 0

    async def suspended_observer(event: BaseModel) -> None:
        nonlocal count
        if not started.is_set():
            started.set()
            await gate.wait()
        count += 1

    handle = bus.subscribe_observer(suspended_observer, queue_size=8)
    await bus.publish(_FakeEvent(value="first"))  # worker 取走并挂起
    await started.wait()
    for i in range(5):
        await bus.publish(_FakeEvent(value=str(i)))

    undelivered = await handle.unsubscribe(drain_timeout=0.05)
    assert undelivered == 6  # 队列中 5 条 + 被取消的在途事件 1 条
    gate.set()
    assert count == 0  # 在途 handler 在 gate 处被取消，未计入 count
