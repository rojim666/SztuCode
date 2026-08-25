from __future__ import annotations

import asyncio

import pytest

from sztu_code.core.context import ExecutionContext
from sztu_code.core.subagent.registry import (
    BackgroundTaskRegistry,
    BackgroundTaskStatus,
)


# 构造一个最小可用的 ExecutionContext，供注册时传入
def _ctx(run_id: str = "child", result: str = "") -> ExecutionContext:
    ctx = ExecutionContext(run_id=run_id, goal="g", max_steps=1)
    ctx.result = result
    return ctx


# 注册一个永不完成的任务，便于观察 running 状态
def _running_task() -> asyncio.Task[None]:
    async def _forever() -> None:
        await asyncio.Event().wait()

    return asyncio.create_task(_forever())


# 功能：register 存储 parent_run_id，且可通过 children 索引递归遍历
# 设计：注册 parent->child 关系，断言 descendants 能从父找到子
async def test_register_stores_parent_relation() -> None:
    reg = BackgroundTaskRegistry()
    task = _running_task()
    try:
        reg.register("child-1", "parent-1", task, _ctx("child-1"))
        assert reg.descendants("parent-1") == ["child-1"]
        record = reg.get("child-1")
        assert record is not None
        assert record.parent_run_id == "parent-1"
        assert record.status is BackgroundTaskStatus.RUNNING
    finally:
        task.cancel()


# 功能：重复注册仍处于活动状态的 run_id 应被拒绝，而非静默覆盖
# 设计：先用活动 run_id 注册，再注册同名，断言抛 ValueError 且原记录未变
async def test_duplicate_active_registration_rejected() -> None:
    reg = BackgroundTaskRegistry()
    task1 = _running_task()
    try:
        reg.register("dup", "parent", task1, _ctx("dup"))
        with pytest.raises(ValueError, match="already registered"):
            reg.register("dup", "parent", _running_task(), _ctx("dup"))
        # 原记录仍指向首个 task
        record = reg.get("dup")
        assert record is not None
        assert record.task is task1
    finally:
        task1.cancel()


# 功能：终态记录的同名 run_id 可被重新注册（墓碑不阻止重建）
# 设计：先注册并标记终态，再用同名注册新任务，断言成功且状态为 running
async def test_terminal_run_id_can_be_reregistered() -> None:
    reg = BackgroundTaskRegistry()
    first_task = asyncio.create_task(asyncio.sleep(0))
    await first_task
    reg.register("reuse", "parent", first_task, _ctx("reuse"))
    reg.mark_terminal("reuse", BackgroundTaskStatus.COMPLETED, detail="done")
    # 重新注册同名
    new_task = _running_task()
    try:
        reg.register("reuse", "parent", new_task, _ctx("reuse"))
        record = reg.get("reuse")
        assert record is not None
        assert record.status is BackgroundTaskStatus.RUNNING
    finally:
        new_task.cancel()


# 功能：running 状态查询返回 running
# 设计：注册未完成任务，断言 query_result 返回 RUNNING 且 is_running
async def test_query_running() -> None:
    reg = BackgroundTaskRegistry()
    task = _running_task()
    try:
        reg.register("r1", "parent", task, _ctx("r1"))
        q = reg.query_result("r1")
        assert q.status is BackgroundTaskStatus.RUNNING
        assert q.is_running
    finally:
        task.cancel()


# 功能：completed 终态查询返回结果文本
# 设计：标记 completed，断言 query_result 返回 COMPLETED 且 result_text 含上下文结果
async def test_query_completed() -> None:
    reg = BackgroundTaskRegistry()
    task = _running_task()
    try:
        reg.register("c1", "parent", task, _ctx("c1", result="done text"))
        won = reg.mark_terminal("c1", BackgroundTaskStatus.COMPLETED, detail="done text")
        assert won is True
        q = reg.query_result("c1")
        assert q.status is BackgroundTaskStatus.COMPLETED
        assert "done text" in q.result_text
    finally:
        task.cancel()


# 功能：failed 终态查询返回失败详情
# 设计：标记 failed，断言 query_result 返回 FAILED 且 reason 携带失败信息
async def test_query_failed() -> None:
    reg = BackgroundTaskRegistry()
    task = _running_task()
    try:
        reg.register("f1", "parent", task, _ctx("f1"))
        reg.mark_terminal("f1", BackgroundTaskStatus.FAILED, detail="boom")
        q = reg.query_result("f1")
        assert q.status is BackgroundTaskStatus.FAILED
        assert "boom" in q.reason
    finally:
        task.cancel()


# 功能：cancelled 终态查询返回取消状态，不复用 failed
# 设计：标记 cancelled，断言 query_result 返回 CANCELLED
async def test_query_cancelled() -> None:
    reg = BackgroundTaskRegistry()
    task = _running_task()
    try:
        reg.register("x1", "parent", task, _ctx("x1"))
        reg.mark_terminal("x1", BackgroundTaskStatus.CANCELLED, reason="parent_cancelled")
        q = reg.query_result("x1")
        assert q.status is BackgroundTaskStatus.CANCELLED
        assert q.status is not BackgroundTaskStatus.FAILED
    finally:
        task.cancel()


# 功能：未知 run_id 查询返回 running+reason=unknown（不与 reclaimed 混淆）
# 设计：查询从未注册的 run_id，断言 status=RUNNING 且 reason=unknown
async def test_query_unknown_run_id() -> None:
    reg = BackgroundTaskRegistry()
    q = reg.query_result("never-registered")
    assert q.status is BackgroundTaskStatus.RUNNING
    assert q.reason == "unknown"


# 功能：首次终态转换胜出并返回 True，后续转换返回 False
# 设计：连续两次 mark_terminal，断言首次返回 True、第二次返回 False，且终态保持首次值
async def test_first_terminal_transition_wins() -> None:
    reg = BackgroundTaskRegistry()
    task = _running_task()
    try:
        reg.register("w1", "parent", task, _ctx("w1"))
        first = reg.mark_terminal("w1", BackgroundTaskStatus.COMPLETED, detail="first")
        second = reg.mark_terminal("w1", BackgroundTaskStatus.CANCELLED, reason="late_cancel")
        assert first is True
        assert second is False
        record = reg.get("w1")
        assert record is not None
        # 取消不得覆盖先到的完成结果
        assert record.status is BackgroundTaskStatus.COMPLETED
        assert record.terminal_detail == "first"
    finally:
        task.cancel()


# 功能：consume_result 首次读取成功并回收记录，第二次查询返回 reclaimed
# 设计：标记 completed 后 consume 一次成功，再 consume 同一 run_id 断言返回 RECLAIMED
async def test_consume_then_reclaimed() -> None:
    reg = BackgroundTaskRegistry()
    task = _running_task()
    try:
        reg.register("k1", "parent", task, _ctx("k1", result="payload"))
        reg.mark_terminal("k1", BackgroundTaskStatus.COMPLETED, detail="payload")
        first = reg.consume_result("k1")
        assert first.status is BackgroundTaskStatus.COMPLETED
        assert "payload" in first.result_text
        second = reg.consume_result("k1")
        assert second.status is BackgroundTaskStatus.RECLAIMED
    finally:
        task.cancel()


# 功能：消费/裁剪后释放 task 与 context.messages 引用，避免内存泄漏
# 设计：注册带大 messages 的上下文，consume 后断言 record.task 和 context 为 None
async def test_consume_releases_heavy_references() -> None:
    reg = BackgroundTaskRegistry()
    task = _running_task()
    try:
        ctx = _ctx("heavy")
        ctx.messages = [{"role": "user", "content": "x" * 10_000}]  # 重型历史
        reg.register("heavy", "parent", task, ctx)
        reg.mark_terminal("heavy", BackgroundTaskStatus.COMPLETED, detail="ok")
        reg.consume_result("heavy")
        record = reg.get("heavy")
        assert record is not None
        assert record.task is None
        assert record.context is None  # context.messages 引用链已断开
    finally:
        task.cancel()


# 功能：TTL 过期使终态记录变为 reclaimed，无需 sleep（注入时钟）
# 设计：注册完成后标记终态 finished_at=100，推进注入时钟 now=120 超过 TTL=10，断言查询返回 RECLAIMED
async def test_ttl_expiry_without_sleep() -> None:
    reg = BackgroundTaskRegistry(retention_ttl_s=10.0)
    task = _running_task()
    try:
        reg.register("t1", "parent", task, _ctx("t1", result="r"))
        reg.mark_terminal("t1", BackgroundTaskStatus.COMPLETED, detail="r", finished_at=100.0)
        # 推进时钟超过 TTL 触发裁剪（公共 prune 入口，注入 now）
        reg.prune(now=120.0)
        q = reg.query_result("t1")
        assert q.status is BackgroundTaskStatus.RECLAIMED
    finally:
        task.cancel()


# 功能：max_retained_terminal 容量上限淘汰最旧终态记录，永不淘汰活动记录
# 设计：max=2，注册 3 个终态记录，断言最旧的被回收、活动的仍在
async def test_max_capacity_evicts_oldest_terminal() -> None:
    reg = BackgroundTaskRegistry(retention_ttl_s=0.0, max_retained_terminal=2)
    active_task = _running_task()
    try:
        reg.register("active", "parent", active_task, _ctx("active"))
        for rid in ("a", "b", "c"):
            t = asyncio.create_task(asyncio.sleep(0))
            await t
            reg.register(rid, "parent", t, _ctx(rid))
            reg.mark_terminal(rid, BackgroundTaskStatus.COMPLETED, detail=rid)
        # 容量 2，3 条终态中 "a" 最旧应被回收
        assert reg.query_result("a").status is BackgroundTaskStatus.RECLAIMED
        # 活动记录未被淘汰
        assert reg.query_result("active").status is BackgroundTaskStatus.RUNNING
    finally:
        active_task.cancel()


# 功能：cancel_descendants 递归取消整个后代树并等待落定
# 设计：parent->child->grandchild 三层，取消 parent 的后代，断言全部变为 cancelled
async def test_cancel_descendants_recurses_tree() -> None:
    reg = BackgroundTaskRegistry()
    gate = asyncio.Event()

    async def _blocked() -> None:
        await gate.wait()

    child_task = asyncio.create_task(_blocked())
    grandchild_task = asyncio.create_task(_blocked())
    try:
        reg.register("child", "parent", child_task, _ctx("child"))
        reg.register("grandchild", "child", grandchild_task, _ctx("grandchild"))
        cancelled = await reg.cancel_descendants("parent", reason="parent_cancelled")
        assert set(cancelled) == {"child", "grandchild"}
        assert reg.query_result("child").status is BackgroundTaskStatus.CANCELLED
        assert reg.query_result("grandchild").status is BackgroundTaskStatus.CANCELLED
    finally:
        gate.set()


# 功能：已完成的子在父取消时保持 completed，不被取消覆盖
# 设计：child 先标记 completed，再 cancel parent 的后代，断言 child 仍为 completed
async def test_completed_child_survives_parent_cancel() -> None:
    reg = BackgroundTaskRegistry()
    child_task = asyncio.create_task(asyncio.sleep(0))
    await child_task
    grandchild_task = _running_task()
    try:
        reg.register("child", "parent", child_task, _ctx("child", result="ok"))
        reg.mark_terminal("child", BackgroundTaskStatus.COMPLETED, detail="ok")
        reg.register("grandchild", "child", grandchild_task, _ctx("grandchild"))
        await reg.cancel_descendants("parent", reason="parent_cancelled")
        # 已完成的 child 保持 completed
        assert reg.query_result("child").status is BackgroundTaskStatus.COMPLETED
        # 活动的 grandchild 被取消
        assert reg.query_result("grandchild").status is BackgroundTaskStatus.CANCELLED
    finally:
        grandchild_task.cancel()


# 功能：shutdown 取消所有活动 task 并释放引用，且可安全重复调用
# 设计：注册活动任务，shutdown 两次，断言全部回收且无异常
async def test_shutdown_idempotent_and_cancels_all() -> None:
    reg = BackgroundTaskRegistry()
    t1 = _running_task()
    t2 = _running_task()
    try:
        reg.register("s1", "parent", t1, _ctx("s1"))
        reg.register("s2", "parent", t2, _ctx("s2"))
        await reg.shutdown()
        assert reg.query_result("s1").status is BackgroundTaskStatus.RECLAIMED
        assert reg.query_result("s2").status is BackgroundTaskStatus.RECLAIMED
        # 重复调用安全
        await reg.shutdown()
    finally:
        t1.cancel()
        t2.cancel()


# 功能：1000 个已完成短任务不留 1000 份完整 context/messages 引用（内存释放回归）
# 设计：注册 1000 个终态任务并 consume，断言所有记录的 context 均为 None
async def test_thousand_completed_tasks_release_contexts() -> None:
    reg = BackgroundTaskRegistry(retention_ttl_s=0.0, max_retained_terminal=10_000)
    for i in range(1000):
        t = asyncio.create_task(asyncio.sleep(0))
        await t
        ctx = _ctx(f"task-{i}", result=f"r{i}")
        ctx.messages = [{"role": "user", "content": "data" * 100}]
        reg.register(f"task-{i}", "parent", t, ctx)
        reg.mark_terminal(f"task-{i}", BackgroundTaskStatus.COMPLETED, detail=f"r{i}")
        reg.consume_result(f"task-{i}")
    # 全部消费后 context 引用应已释放
    leaked = [
        rid
        for rid, record in reg._records.items()  # noqa: SLF001
        if record.context is not None
    ]
    assert leaked == [], f"{len(leaked)} records still hold context"
