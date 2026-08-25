from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sztu_code.core.bus.commands import (
    UserQuestionAnswer,
    UserQuestionItem,
    UserQuestionPending,
)
from sztu_code.core.bus.events import UserQuestionRequestedEvent, UserQuestionResolvedEvent
from sztu_code.core.events.bus import EventBus


# 返回当前 UTC 时间，供提问事件使用统一 ISO 8601 时间戳
def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class _PendingQuestion:
    rpc_id: str
    session_id: str
    run_id: str
    questions: list[UserQuestionItem]
    future: asyncio.Future[list[UserQuestionAnswer]]


class UserQuestionManager:
    # 初始化用户提问管理器，挂起项在 daemon 生命周期内跨客户端连接保留
    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._pending: dict[str, _PendingQuestion] = {}

    # 创建待回答问题并暂停调用方，直到客户端提交结构化回答或 run 被取消
    async def ask(
        self,
        *,
        session_id: str,
        run_id: str,
        questions: list[UserQuestionItem],
    ) -> list[UserQuestionAnswer]:
        if not session_id:
            raise ValueError("ask_user_question requires a session-owned run")
        rpc_id = f"question-{uuid.uuid4().hex}"
        future: asyncio.Future[list[UserQuestionAnswer]] = (
            asyncio.get_running_loop().create_future()
        )
        pending = _PendingQuestion(
            rpc_id=rpc_id,
            session_id=session_id,
            run_id=run_id,
            questions=questions,
            future=future,
        )
        self._pending[rpc_id] = pending
        try:
            await self._bus.publish(self._requested_event(pending))
            return await future
        except asyncio.CancelledError:
            if self._pending.pop(rpc_id, None) is pending:
                await self._bus.publish(
                    UserQuestionResolvedEvent(
                        rpc_id=rpc_id,
                        session_id=session_id,
                        run_id=run_id,
                        outcome="cancelled",
                        ts=_now(),
                    )
                )
            raise
        except Exception:
            self._pending.pop(rpc_id, None)
            raise

    # 校验并提交完整回答批次，成功后恢复原 ask 调用
    async def respond(
        self,
        *,
        rpc_id: str,
        session_id: str,
        answers: list[UserQuestionAnswer],
    ) -> None:
        pending = self._pending.get(rpc_id)
        if pending is None:
            raise ValueError("question is no longer pending")
        normalized = self._validate_answers(pending, session_id, answers)
        if self._pending.pop(rpc_id, None) is not pending:
            raise ValueError("question is no longer pending")
        pending.future.set_result(normalized)
        await self._bus.publish(
            UserQuestionResolvedEvent(
                rpc_id=rpc_id,
                session_id=pending.session_id,
                run_id=pending.run_id,
                outcome="answered",
                ts=_now(),
            )
        )

    # 返回当前所有待回答问题的稳定快照，供浏览器刷新或重连后恢复
    def list_pending(self, session_id: str | None = None) -> list[UserQuestionPending]:
        return [
            UserQuestionPending(
                rpc_id=pending.rpc_id,
                session_id=pending.session_id,
                run_id=pending.run_id,
                questions=pending.questions,
            )
            for pending in self._pending.values()
            if session_id is None or pending.session_id == session_id
        ]

    # 将内部挂起项转换为可广播的 question.requested 事件
    @staticmethod
    def _requested_event(pending: _PendingQuestion) -> UserQuestionRequestedEvent:
        return UserQuestionRequestedEvent(
            rpc_id=pending.rpc_id,
            session_id=pending.session_id,
            run_id=pending.run_id,
            questions=pending.questions,
            ts=_now(),
        )

    # 对照原问题逐项校验 ID、选项、单多选约束与自定义回答
    @staticmethod
    def _validate_answers(
        pending: _PendingQuestion,
        session_id: str,
        answers: list[UserQuestionAnswer],
    ) -> list[UserQuestionAnswer]:
        if session_id != pending.session_id:
            raise ValueError("question session does not match")
        if len(answers) != len(pending.questions):
            raise ValueError("answers must cover every question in order")

        normalized: list[UserQuestionAnswer] = []
        for question, answer in zip(pending.questions, answers, strict=True):
            if answer.id != question.id:
                raise ValueError("answer id does not match question order")
            if len(set(answer.selected)) != len(answer.selected):
                raise ValueError(f"answer {answer.id} contains duplicate selections")
            custom = answer.custom.strip() if answer.custom is not None else None
            if custom == "":
                raise ValueError(f"answer {answer.id} contains an empty custom value")
            if not question.multi_select:
                if len(answer.selected) > 1:
                    raise ValueError(f"answer {answer.id} allows only one selection")
                if custom is not None and answer.selected:
                    raise ValueError(
                        f"answer {answer.id} cannot mix a selection with custom text"
                    )
            labels = {option.label for option in question.options}
            if any(label not in labels for label in answer.selected):
                raise ValueError(f"answer {answer.id} contains an unknown option")
            normalized.append(
                UserQuestionAnswer(
                    id=answer.id,
                    selected=list(answer.selected),
                    custom=custom,
                )
            )
        return normalized
