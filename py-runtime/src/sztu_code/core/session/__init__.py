from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sztu_code.core.session.model import Session, SessionMode, SessionStatus
from sztu_code.core.session.store import MessageContent, SessionStore

if TYPE_CHECKING:
    from sztu_code.core.session.manager import SessionManager

__all__ = [
    "MessageContent",
    "Session",
    "SessionManager",
    "SessionMode",
    "SessionStatus",
    "SessionStore",
]


# 惰性加载 SessionManager：客户端仅需会话模型时不再引入 manager 及其依赖树
def __getattr__(name: str) -> Any:
    if name == "SessionManager":
        from sztu_code.core.session.manager import SessionManager

        return SessionManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
