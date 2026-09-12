from __future__ import annotations

import inspect
from typing import Any


class RunDeadlineExceeded(Exception):
    """Internal signal that a run-level wall-clock deadline was reached."""


def supports_keyword(callable_obj: Any, keyword: str) -> bool:
    """Check whether a callable accepts a keyword, preserving legacy doubles."""
    try:
        parameters = inspect.signature(callable_obj).parameters.values()
    except (TypeError, ValueError):
        # Dynamic callables cannot be inspected reliably; use the new contract.
        return True
    return any(
        parameter.name == keyword or parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )


def add_remaining_s(
    callable_obj: Any,
    kwargs: dict[str, Any],
    remaining_s: float | None,
) -> None:
    """Add the optional budget unless a legacy callable cannot accept it."""
    if remaining_s is not None and supports_keyword(callable_obj, "remaining_s"):
        kwargs["remaining_s"] = remaining_s
