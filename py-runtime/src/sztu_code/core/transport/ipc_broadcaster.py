from __future__ import annotations

import asyncio
import fnmatch
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel

from sztu_code.core.bus.envelope import EventPushEnvelope
from sztu_code.core.trace.record import TraceRecord
from sztu_code.core.trace.writer import TraceWriter

logger = logging.getLogger(__name__)

# 高频流式事件（逐 token/逐思考块到达）：跳过逐事件 drain，由事件循环异步发送，
# 仅当客户端写缓冲超过阈值才等待排空（有界背压），避免 LLM 流式输出被慢客户端拖住
_DRAIN_THRESHOLD = 64 * 1024
_STREAM_EVENT_TYPES = frozenset({"llm.token", "llm.thinking"})
_DRAIN_TIMEOUT_S = 2.0


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class _Subscription:
    sub_id: str
    writer: asyncio.StreamWriter
    topics: list[str]
    scope: str


class IpcEventBroadcaster:
    def __init__(self, trace: TraceWriter | None = None) -> None:
        self._subscriptions: list[_Subscription] = []
        self._trace = trace

    # 注册一个客户端订阅，返回 subscription_id
    def subscribe(
        self,
        writer: asyncio.StreamWriter,
        topics: list[str],
        scope: str = "global",
    ) -> str:
        sub_id = f"sub-{uuid.uuid4().hex[:8]}"
        sub = _Subscription(sub_id=sub_id, writer=writer, topics=topics, scope=scope)
        self._subscriptions.append(sub)
        return sub_id

    # 移除指定 writer 的所有订阅
    def unsubscribe(self, writer: asyncio.StreamWriter) -> None:
        self._subscriptions = [s for s in self._subscriptions if s.writer is not writer]

    # 将事件推送到所有匹配的订阅客户端，写入失败时延迟清理死连接
    async def handle(self, event: BaseModel) -> None:
        event_dict = event.model_dump()
        event_type: str = event_dict.get("type", "")
        run_id: str | None = event_dict.get("run_id")

        # 一次序列化，所有订阅者共享同一字节负载，避免高频事件被重复序列化
        payload = EventPushEnvelope(event=event_dict).model_dump_json().encode() + b"\n"
        is_stream = event_type in _STREAM_EVENT_TYPES

        dead: list[asyncio.StreamWriter] = []

        for sub in list(self._subscriptions):
            if not self._matches_topic(event_type, sub.topics):
                continue
            if not self._matches_scope(run_id, sub.scope):
                continue
            try:
                sub.writer.write(payload)
                if not is_stream or self._buffered_bytes(sub.writer) > _DRAIN_THRESHOLD:
                    await asyncio.wait_for(sub.writer.drain(), timeout=_DRAIN_TIMEOUT_S)
                if self._trace is not None:
                    client_id = str(sub.writer.get_extra_info("peername", "<unknown>"))
                    self._trace.emit(
                        TraceRecord(
                            ts=_now(),
                            direction="CORE→CLIENT",
                            layer="ipc",
                            kind="push",
                            run_id=run_id,
                            client_id=client_id,
                            data={"sub_id": sub.sub_id, "event_type": event_type},
                        )
                    )
            except (ConnectionResetError, BrokenPipeError, OSError, TimeoutError):
                logger.debug("dead connection for sub %s, scheduling cleanup", sub.sub_id)
                dead.append(sub.writer)

        for writer in dead:
            self.unsubscribe(writer)

    # 读取当前写缓冲字节数；transport 缺失（连接已关闭）或不可用时按 0 处理
    @staticmethod
    def _buffered_bytes(writer: asyncio.StreamWriter) -> int:
        try:
            buffered = writer.transport.get_write_buffer_size()
        except (AttributeError, TypeError, OSError):
            return 0
        return buffered if isinstance(buffered, int) else 0

    # 检查事件类型是否匹配订阅的 topic 列表（支持 fnmatch glob 模式）
    @staticmethod
    def _matches_topic(event_type: str, topics: list[str]) -> bool:
        return any(fnmatch.fnmatch(event_type, pattern) for pattern in topics)

    # 检查事件 run_id 是否匹配订阅的 scope（global 全通，run:<id> 精确匹配）
    @staticmethod
    def _matches_scope(run_id: str | None, scope: str) -> bool:
        if scope == "global":
            return True
        if scope.startswith("run:"):
            return run_id == scope[4:]
        return False
