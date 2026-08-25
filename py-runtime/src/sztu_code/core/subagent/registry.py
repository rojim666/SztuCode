from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from sztu_code.core.context import ExecutionContext

log = logging.getLogger(__name__)


# 后台 subagent 的生命周期状态
class BackgroundTaskStatus(StrEnum):
    RUNNING = "running"
    CANCELING = "canceling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    # reclaimed 是存储状态：终态记录被回收后的墓碑标记，而非第二种执行结果
    RECLAIMED = "reclaimed"


# 终态集合：completed / failed / cancelled 三者互斥，reclaimed 不属于执行终态
_TERMINAL_OUTCOMES = frozenset(
    {BackgroundTaskStatus.COMPLETED, BackgroundTaskStatus.FAILED, BackgroundTaskStatus.CANCELLED}
)


# 终态回调：run_id + 终态状态，由 registry 在 mark_terminal 赢家时触发。
# 调用方（SpawnAgentTool）注册它来发布 SubagentFinishedEvent，使终态事件发布
# 不依赖 _run_background 协程是否已执行（协程可能在首次调度前就被取消）。
TerminalCallback = Callable[[str, "BackgroundTaskStatus"], object]


# agent_result 查询的结构化返回：用一个值对象取代对原始 task 的直接解包，
# 避免 agent_result 把"未知 ID"和"已被回收的已完成记录"混为一谈。
@dataclass(frozen=True)
class AgentResultQuery:
    status: BackgroundTaskStatus
    # 终态时携带的小型响应文本，避免暴露 traceback 内部
    result_text: str = ""
    reason: str = ""

    @property
    def is_running(self) -> bool:
        return self.status is BackgroundTaskStatus.RUNNING

    @property
    def is_terminal_outcome(self) -> bool:
        return self.status in _TERMINAL_OUTCOMES


# 后台 subagent 的完整生命周期记录。一个后台子 agent 有且仅有一个 owner parent；
# parent 终态或 daemon 关闭时，所有后代被取消并等待落定后清理才算完成。
@dataclass
class BackgroundTaskRecord:
    run_id: str
    parent_run_id: str
    task: asyncio.Task[None] | None
    context: ExecutionContext | None
    status: BackgroundTaskStatus = BackgroundTaskStatus.RUNNING
    created_at: float = 0.0
    finished_at: float = 0.0
    result_consumed: bool = False
    # 终态详情：cancel 原因 / 失败消息 / 完成摘要，供 agent_result 返回
    terminal_detail: str = ""
    # owner_run_id：该子 Agent 所属的 root run id（整个后代树的根）。
    # 与 parent_run_id（直接父，用于事件 payload）不同：owner 是 sink 路由键，
    # 使 grandchild 的终态事件也能路由回 root 的 sink，而非因 parent=child 找不到 sink 丢失。
    owner_run_id: str = ""

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL_OUTCOMES or self.status is BackgroundTaskStatus.RECLAIMED

    @property
    def is_active(self) -> bool:
        return self.status in (BackgroundTaskStatus.RUNNING, BackgroundTaskStatus.CANCELING)

    # 回收重型引用：释放 task 与 context.messages，避免 1000 条已完成记录留存 1000 份完整上下文。
    # 保留 run_id / parent_run_id / 状态 / 终态详情，使 agent_result 仍能区分 reclaimed 与 unknown。
    def reclaim(self, reason: str = "") -> None:
        self.task = None
        # context.messages 是主要内存占用；保留 context 仅会延续其引用链，故整体释放
        self.context = None
        self.status = BackgroundTaskStatus.RECLAIMED
        if reason:
            self.terminal_detail = reason


# 管理后台 subagent 任务的生命周期：注册、查询、递归取消、有界保留、关闭清理
class BackgroundTaskRegistry:
    def __init__(
        self,
        *,
        retention_ttl_s: float = 300.0,
        max_retained_terminal: int = 256,
        on_terminal: TerminalCallback | None = None,
    ) -> None:
        # run_id -> 记录；reclaimed 后以墓碑形式短暂保留，使 expired 与 unknown 可区分
        self._records: dict[str, BackgroundTaskRecord] = {}
        # parent_run_id -> 直接子 run_id 集合；reclaimed 时从索引移除
        self._children: dict[str, set[str]] = {}
        self._retention_ttl_s = retention_ttl_s
        self._max_retained_terminal = max_retained_terminal
        # 墓碑队列：按回收时间排序，供 max_retained_terminal 容量淘汰使用
        self._tombstones: deque[tuple[str, float]] = deque()
        self._shutdown_done = False
        # 终态回调按 parent_run_id 路由：多 root run 并发时 A 的 child 终态事件
        # 只发到 A 的 sink，不会被后注册的 B 覆盖。"_default" 为无匹配时的回退 sink。
        self._sinks: dict[str, TerminalCallback] = {}
        if on_terminal is not None:
            self._sinks["_default"] = on_terminal

    # 注册一个后台任务，记录所有权（parent_run_id + owner_run_id）使其在 task 可被
    # agent_result 观察前就持久化。owner_run_id 为所属 root run，用于终态 sink 路由；
    # parent_run_id 为直接父，用于事件 payload。owner 为空时回退为 parent_run_id。
    def register(
        self,
        run_id: str,
        parent_run_id: str,
        task: asyncio.Task[None],
        context: ExecutionContext,
        *,
        owner_run_id: str = "",
    ) -> None:
        existing = self._records.get(run_id)
        if existing is not None and not existing.is_terminal:
            # 活动中的 run_id 重复注册会静默覆盖 task，导致原任务泄漏，故拒绝
            raise ValueError(
                f"background task already registered and active: run_id={run_id} "
                f"status={existing.status.value}"
            )
        self._records[run_id] = BackgroundTaskRecord(
            run_id=run_id,
            parent_run_id=parent_run_id,
            task=task,
            context=context,
            status=BackgroundTaskStatus.RUNNING,
            created_at=_now(),
            owner_run_id=owner_run_id or parent_run_id,
        )
        self._children.setdefault(parent_run_id, set()).add(run_id)
        # 注册是安全生命周期点：触发有界保留清理（TTL + 容量），保持注册表不无限增长
        self.prune()

    # 查询记录；不存在或已回收时返回 None。调用方应改用 query_result 获取区分语义。
    def get(self, run_id: str) -> BackgroundTaskRecord | None:
        return self._records.get(run_id)

    # 返回所有已注册记录的浅拷贝列表，用于 daemon 退出时批量清理
    def all(self) -> list[BackgroundTaskRecord]:
        return list(self._records.values())

    # 记录终态并返回本次调用是否赢得了终态发布权。幂等：只有首个终态转换胜出，
    # 由胜出方发布 SubagentFinishedEvent，杜绝重复终态事件。
    def mark_terminal(
        self,
        run_id: str,
        status: BackgroundTaskStatus,
        *,
        reason: str = "",
        detail: str = "",
        finished_at: float | None = None,
    ) -> bool:
        record = self._records.get(run_id)
        if record is None:
            return False
        # 已是终态（含 reclaimed 墓碑）：绝不覆盖先到的终态
        if record.is_terminal:
            return False
        if status not in _TERMINAL_OUTCOMES:
            raise ValueError(f"mark_terminal requires a terminal outcome, got {status!r}")
        record.status = status
        # reason 优先（取消/失败原因），否则用 detail（完成结果文本）；统一存入 terminal_detail
        record.terminal_detail = reason or detail
        record.finished_at = finished_at if finished_at is not None else _now()
        self._tombstones.append((run_id, record.finished_at))
        self.prune(now=record.finished_at)
        self._notify_terminal(run_id, status)
        return True

    # 返回 parent_run_id 的整个后代树（任意嵌套深度），按广度优先展开
    def descendants(self, parent_run_id: str) -> list[str]:
        ordered: list[str] = []
        queue: deque[str] = deque(self._children.get(parent_run_id, ()))
        seen: set[str] = set()
        while queue:
            rid = queue.popleft()
            if rid in seen:
                continue
            seen.add(rid)
            ordered.append(rid)
            queue.extend(self._children.get(rid, ()))
        return ordered

    # 递归取消 parent_run_id 的所有后代：先标记 cancelling 再取消，等待全部落定后安全终结。
    # snapshot 在首个 await 前完成，避免并发完成发布第二次终态。
    async def cancel_descendants(
        self,
        parent_run_id: str,
        *,
        reason: str = "parent_cancelled",
        now: float | None = None,
    ) -> list[str]:
        now_val = now if now is not None else _now()
        tree = self.descendants(parent_run_id)
        if not tree:
            return []
        # 第一阶段（同步）：把仍为 running 的后代标记为 cancelling，收集待取消的 task
        to_cancel: list[asyncio.Task[None]] = []
        cancelled_ids: list[str] = []
        for rid in tree:
            record = self._records.get(rid)
            if record is None or not record.is_active:
                continue
            record.status = BackgroundTaskStatus.CANCELING
            if record.task is not None and not record.task.done():
                to_cancel.append(record.task)
            cancelled_ids.append(rid)
        # 第二阶段（await）：取消所有活动 task，单条失败不得阻断兄弟清理
        for task in to_cancel:
            task.cancel()
        if to_cancel:
            await asyncio.gather(*to_cancel, return_exceptions=True)
        # 第三阶段（同步）：把仍在 cancelling 的后代安全终结为 cancelled；
        # 已 completed/failed 的保持原终态，不可被取消覆盖。
        # 用 mark_terminal 而非直接赋值，使终态回调触发且与协程路径共享赢家语义
        # （若协程已在 mark_terminal 赢过，此处 won=False，不重复发事件）。
        for rid in cancelled_ids:
            record = self._records.get(rid)
            if record is None:
                continue
            if record.status is BackgroundTaskStatus.CANCELING:
                self.mark_terminal(
                    rid, BackgroundTaskStatus.CANCELLED, reason=reason, finished_at=now_val
                )
        self.prune(now=now_val)
        return cancelled_ids

    # 消费终态结果：成功的终态读取在捕获小型响应后回收记录，使第二次查询返回 reclaimed
    def consume_result(self, run_id: str, *, now: float | None = None) -> AgentResultQuery:
        now_val = now if now is not None else _now()
        record = self._records.get(run_id)
        if record is None:
            return AgentResultQuery(status=BackgroundTaskStatus.RUNNING, reason="unknown")
        if record.status in (BackgroundTaskStatus.RUNNING, BackgroundTaskStatus.CANCELING):
            return AgentResultQuery(status=BackgroundTaskStatus.RUNNING)
        if record.status is BackgroundTaskStatus.RECLAIMED:
            return AgentResultQuery(
                status=BackgroundTaskStatus.RECLAIMED,
                reason=record.terminal_detail or "expired_or_consumed",
            )
        # 终态（completed/failed/cancelled）：捕获小型响应后回收重型引用
        result_text = self._terminal_text(record)
        query = AgentResultQuery(
            status=record.status, result_text=result_text, reason=record.terminal_detail
        )
        record.result_consumed = True
        record.reclaim(reason="consumed")
        self._drop_from_index(run_id)
        self.prune(now=now_val)
        return query

    # agent_result 查询入口：区分 running / completed / cancelled / failed / reclaimed / unknown
    def query_result(self, run_id: str) -> AgentResultQuery:
        record = self._records.get(run_id)
        if record is None:
            return AgentResultQuery(status=BackgroundTaskStatus.RUNNING, reason="unknown")
        if record.status in (BackgroundTaskStatus.RUNNING, BackgroundTaskStatus.CANCELING):
            return AgentResultQuery(status=BackgroundTaskStatus.RUNNING)
        if record.status is BackgroundTaskStatus.RECLAIMED:
            return AgentResultQuery(
                status=BackgroundTaskStatus.RECLAIMED,
                reason=record.terminal_detail or "expired_or_consumed",
            )
        return AgentResultQuery(
            status=record.status,
            result_text=self._terminal_text(record),
            reason=record.terminal_detail,
        )

    # 回收终态文本：优先用 context.result，失败/取消时用 terminal_detail，避免暴露 traceback
    def _terminal_text(self, record: BackgroundTaskRecord) -> str:
        if record.status is BackgroundTaskStatus.COMPLETED:
            if record.context is not None and record.context.result:
                return record.context.result
            return record.terminal_detail or "Subagent completed with no text result."
        if record.status is BackgroundTaskStatus.FAILED:
            return record.terminal_detail or "Subagent failed."
        if record.status is BackgroundTaskStatus.CANCELLED:
            return record.terminal_detail or "Subagent was cancelled."
        return record.terminal_detail

    # 按容量淘汰最旧的终态记录（含墓碑），永不淘汰活动记录
    def _prune_tombstones_by_count(self) -> None:
        while len(self._tombstones) > self._max_retained_terminal:
            run_id, _ = self._tombstones.popleft()
            record = self._records.get(run_id)
            if record is not None and record.is_terminal:
                record.reclaim(reason="capacity_evicted")
                self._drop_from_index(run_id)

    # 在安全生命周期点执行的有界保留清理：TTL 过期 + 容量上限。
    # 不持有可变迭代器跨 await，全程同步且廉价。公共入口供测试与生命周期点注入时钟调用。
    def prune(self, *, now: float | None = None) -> None:
        now_val = now if now is not None else _now()
        # TTL 过期：终态记录超过保留窗口则回收并移出索引
        if self._retention_ttl_s <= 0:
            self._prune_tombstones_by_count()
            return
        retained: deque[tuple[str, float]] = deque()
        for run_id, finished_at in self._tombstones:
            record = self._records.get(run_id)
            if record is None:
                continue
            if not record.is_terminal:
                # 活动记录不应出现在墓碑队列，保留以备后续清理
                retained.append((run_id, finished_at))
                continue
            if now_val - finished_at >= self._retention_ttl_s:
                record.reclaim(reason="ttl_expired")
                self._drop_from_index(run_id)
            else:
                retained.append((run_id, finished_at))
        self._tombstones = retained
        self._prune_tombstones_by_count()

    # 按 owner_run_id（root run）注册终态回调，使该 root 的整棵后代树（含 grandchild
    # 及更深）的终态事件都路由到同一 sink。多 root run 并发时互不覆盖；
    # runner 在 run 结束时应调 unregister_sink 清理。
    def register_sink(self, owner_run_id: str, callback: TerminalCallback) -> None:
        self._sinks[owner_run_id] = callback

    # 注销 owner_run_id 的 sink，避免 run 结束后回调闭包（bus/pending_publishes）泄漏
    def unregister_sink(self, owner_run_id: str) -> None:
        self._sinks.pop(owner_run_id, None)

    # 设置终态回调：向后兼容别名，注册为默认 sink（无 owner_run_id 匹配时回退）。
    # 新代码应改用 register_sink(owner_run_id, callback) 做精确路由。
    def set_on_terminal(self, callback: TerminalCallback) -> None:
        self._sinks["_default"] = callback

    # 终态回调通知：仅 mark_terminal 赢家触发。按 record.owner_run_id 路由到对应 sink，
    # 使 grandchild（owner=root，parent=child）也能路由回 root sink；
    # 找不到则回退默认 sink，保证终态事件发布唯一且不依赖协程是否已执行。
    def _notify_terminal(self, run_id: str, status: BackgroundTaskStatus) -> None:
        record = self._records.get(run_id)
        sink: TerminalCallback | None = None
        if record is not None:
            sink = self._sinks.get(record.owner_run_id)
        if sink is None:
            sink = self._sinks.get("_default")
        if sink is None:
            return
        try:
            sink(run_id, status)
        except Exception:
            log.exception("on_terminal callback failed run_id=%s status=%s", run_id, status)

    # 从父->子索引中移除指定 run_id（自身作为父节点的子树保留，因为孙节点仍可能被引用）
    def _drop_from_index(self, run_id: str) -> None:
        record = self._records.get(run_id)
        if record is None:
            return
        siblings = self._children.get(record.parent_run_id)
        if siblings is not None:
            siblings.discard(run_id)
            if not siblings:
                self._children.pop(record.parent_run_id, None)

    # 取消并等待所有活动 task 落定，再释放保留的重型引用。可安全重复调用。
    async def shutdown(self, *, now: float | None = None) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True
        now_val = now if now is not None else _now()
        # snapshot 活动 task，避免跨 await 持有可变迭代器
        active = [
            (rid, rec.task)
            for rid, rec in self._records.items()
            if rec.is_active and rec.task is not None and not rec.task.done()
        ]
        for _, task in active:
            task.cancel()
        if active:
            await asyncio.gather(*[t for _, t in active], return_exceptions=True)
        # 活动记录用 mark_terminal 终结为 cancelled（不覆盖已完成的终态），
        # 并通过 on_terminal 回调发布终态事件；已终态记录保持原结果。
        for record in self._records.values():
            if record.is_active:
                self.mark_terminal(
                    record.run_id,
                    BackgroundTaskStatus.CANCELLED,
                    reason="daemon_shutdown",
                    finished_at=now_val,
                )
        # 全部回收重型引用（终态记录保留状态详情，释放 task/context）
        for record in self._records.values():
            if record.status is not BackgroundTaskStatus.RECLAIMED:
                record.reclaim(reason="shutdown")
        self._children.clear()
        self._tombstones.clear()
        self._sinks.clear()


def _now() -> float:
    # 使用事件循环时间基，避免引入 wall-clock 依赖；测试通过注入 now= 覆盖
    import time

    return time.monotonic()
