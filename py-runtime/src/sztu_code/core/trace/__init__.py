from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sztu_code.core.trace.record import TraceRecord
from sztu_code.core.trace.writer import TraceWriter

if TYPE_CHECKING:
    from sztu_code.core.trace.provider import TracingProvider

__all__ = ["TraceRecord", "TraceWriter", "TracingProvider"]


# 惰性加载 TracingProvider：客户端仅查看 trace 记录时不再引入事件总线与 LLM 类型
def __getattr__(name: str) -> Any:
    if name == "TracingProvider":
        from sztu_code.core.trace.provider import TracingProvider

        return TracingProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
