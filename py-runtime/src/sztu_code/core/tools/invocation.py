from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import ValidationError

from sztu_code.core.bus.events import (
    PermissionDeniedEvent,
    PermissionGrantedEvent,
    PermissionRequestedEvent,
    TestResultEvent,
    ToolCallFailedEvent,
    ToolCallFinishedEvent,
    ToolCallStartedEvent,
    ToolSchedulerMode,
)
from sztu_code.core.events.bus import EventBus
from sztu_code.core.llm.types import ToolCallBlock
from sztu_code.core.tools.base import (
    _PERMISSION_GRANT_KEY,
    _PERMISSION_GRANT_TOKEN,
    ToolExecutionState,
    ToolPermission,
    ToolResult,
)
from sztu_code.core.tools.errors import RateLimitedError
from sztu_code.core.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from sztu_code.core.permissions.manager import PermissionManager

_DEFAULT_TIMEOUT: float = 120.0
_MAX_RETRIES: int = 1
_RETRY_BASE_S: float = 2.0  # backoff base; tests can monkeypatch to 0
# 超时操作可能仍在运行，绝不自动重试；仅重试明确可恢复的瞬时错误
_RETRYABLE: frozenset[str] = frozenset({"runtime_error", "rate_limited"})


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _retry_reason(
    error_class: str,
    retryable: bool,
    execution_state: ToolExecutionState,
    tool_retry_safe: bool,
    attempt: int,
) -> str:
    if execution_state == ToolExecutionState.UNKNOWN:
        return "execution_state_is_unknown"
    if error_class not in _RETRYABLE:
        return "error_is_not_explicitly_transient"
    if not retryable:
        return "failure_is_not_explicitly_retryable"
    if not tool_retry_safe:
        return "tool_is_not_declared_retry_safe"
    if attempt > _MAX_RETRIES:
        return "retry_limit_exhausted"
    return "explicit_transient_failure_on_retry_safe_tool"


def _retry_explanation(reason: str) -> str:
    explanations = {
        "execution_state_is_unknown": (
            "Automatic retry was skipped because the operation may still be running."
        ),
        "error_is_not_explicitly_transient": (
            "Automatic retry was skipped because the failure was not explicitly transient."
        ),
        "failure_is_not_explicitly_retryable": (
            "Automatic retry was skipped because the failure was not marked retryable."
        ),
        "tool_is_not_declared_retry_safe": (
            "Automatic retry was skipped because the tool did not declare this call safe to retry."
        ),
        "retry_limit_exhausted": "Automatic retry stopped because the retry limit was exhausted.",
    }
    return explanations.get(reason, "")


# 判断 bash 调用是否为可汇总的常见测试命令
def _is_test_command(tool_call: ToolCallBlock) -> bool:
    if tool_call.name != "bash":
        return False
    command = str(tool_call.input.get("command", "")).lower()
    markers = ("pytest", "vitest", "jest", "cargo test", "npm test", "pnpm test", "yarn test")
    return any(marker in command for marker in markers)


# 从测试输出中提取最有信息量的一行，避免将整段终端日志塞入事件流
def _test_summary(command: str, output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    markers = ("passed", "failed", "error", "tests")
    candidates = [line for line in lines if any(token in line.lower() for token in markers)]
    return (candidates[-1] if candidates else (lines[-1] if lines else command))[:300]


# 为测试型 bash 调用发布可持久回放的验证结果事件
async def _publish_test_result(
    bus: EventBus,
    run_id: str,
    tool_call: ToolCallBlock,
    status: Literal["passed", "failed"],
    output: str,
) -> None:
    if not _is_test_command(tool_call):
        return
    command = str(tool_call.input.get("command", ""))
    await bus.publish(
        TestResultEvent(
            run_id=run_id,
            tool_use_id=tool_call.id,
            status=status,
            summary=_test_summary(command, output),
            ts=_now(),
        )
    )


# 发布 ToolCallFailedEvent 并返回对应 ToolResult
async def _fail(
    bus: EventBus,
    run_id: str,
    tool_call: ToolCallBlock,
    error_class: str,
    error_message: str,
    elapsed_ms: int,
    *,
    attempt: int = 1,
    batch_id: str = "",
    scheduler_mode: ToolSchedulerMode = "serial",
    queue_ms: int = 0,
    queued_at: str = "",
    started_at: str = "",
    retryable: bool = False,
    execution_state: ToolExecutionState = ToolExecutionState.COMPLETED,
    retry_reason: str = "",
    tool_retry_safe: bool = False,
) -> ToolResult:
    if not retry_reason:
        retry_reason = _retry_reason(
            error_class,
            retryable,
            execution_state,
            tool_retry_safe,
            attempt,
        )
    finished_at = _now()
    await bus.publish(
        ToolCallFailedEvent(
            run_id=run_id,
            tool_use_id=tool_call.id,
            tool_name=tool_call.name,
            error_class=error_class,
            error_message=error_message,
            elapsed_ms=elapsed_ms,
            attempt=attempt,
            retry_reason=retry_reason,
            tool_retry_safe=tool_retry_safe,
            execution_state=execution_state.value,
            batch_id=batch_id,
            scheduler_mode=scheduler_mode,
            queue_ms=queue_ms,
            queued_at=queued_at,
            started_at=started_at,
            finished_at=finished_at,
            ts=finished_at,
        )
    )
    await _publish_test_result(bus, run_id, tool_call, "failed", error_message)
    explanation = _retry_explanation(retry_reason)
    result_content = f"{error_message}\n{explanation}" if explanation else error_message
    return ToolResult(
        content=result_content,
        is_error=True,
        error_type=error_class,
        metadata={
            "retry_decision": "stop",
            "retry_reason": retry_reason,
            "tool_retry_safe": tool_retry_safe,
            "execution_state": execution_state.value,
        },
        retryable=retryable,
        execution_state=execution_state,
    )


# 校验参数、检查权限、限时调用工具、发布进度事件，失败时指数退避重试，返回 ToolResult（不抛异常）
async def invoke_tool(
    registry: ToolRegistry,
    tool_call: ToolCallBlock,
    bus: EventBus,
    run_id: str,
    timeout: float = _DEFAULT_TIMEOUT,
    *,
    permission_manager: PermissionManager | None = None,
    session_id: str = "",
    batch_id: str = "",
    scheduler_mode: ToolSchedulerMode = "serial",
    queued_at: str = "",
    queued_monotonic: float | None = None,
    classified_permission: ToolPermission | None = None,
) -> ToolResult:
    t0 = time.monotonic()
    started_at = _now()
    queue_ms = max(0, int((t0 - queued_monotonic) * 1000)) if queued_monotonic is not None else 0
    tool_call.input = registry.enrich_tool_input(tool_call.name, tool_call.input)
    runtime_params = dict(tool_call.input)
    runtime_params.pop("description", None)
    runtime_params.pop(_PERMISSION_GRANT_KEY, None)

    def elapsed() -> int:
        return int((time.monotonic() - t0) * 1000)

    try:
        await bus.publish(
            ToolCallStartedEvent(
                run_id=run_id,
                tool_use_id=tool_call.id,
                tool_name=tool_call.name,
                params=dict(tool_call.input),
                batch_id=batch_id,
                scheduler_mode=scheduler_mode,
                queue_ms=queue_ms,
                queued_at=queued_at,
                started_at=started_at,
                ts=started_at,
            )
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return ToolResult(content=str(exc), is_error=True, error_type="runtime_error")

    tool = registry.get(tool_call.name)
    if tool is None:
        return await _fail(
            bus,
            run_id,
            tool_call,
            "runtime_error",
            f"unknown tool: {tool_call.name}",
            elapsed(),
            batch_id=batch_id,
            scheduler_mode=scheduler_mode,
            queue_ms=queue_ms,
            queued_at=queued_at,
            started_at=started_at,
        )

    if tool.params_model is not None:
        try:
            tool.params_model.model_validate(runtime_params)
        except ValidationError as exc:
            return await _fail(
                bus,
                run_id,
                tool_call,
                "schema_error",
                str(exc),
                elapsed(),
                batch_id=batch_id,
                scheduler_mode=scheduler_mode,
                queue_ms=queue_ms,
                queued_at=queued_at,
                started_at=started_at,
            )

    # 结构化提问本身就是用户交互，不进入危险操作审批通道
    if permission_manager is not None and not tool.is_interactive:
        async def _emit_permission(raw: dict[str, Any]) -> None:
            await bus.publish(PermissionRequestedEvent(**raw, run_id=run_id))

        try:
            # 并发预检已确认的权限直接复用，避免同一调用被动态分类两次
            tool_permission = classified_permission
            if tool_permission is None:
                tool_permission = tool.classify_permission(runtime_params)

            allowed, decision = await permission_manager.check_and_wait(
                tool_use_id=tool_call.id,
                tool_name=tool_call.name,
                params=dict(tool_call.input),
                session_id=session_id,
                run_id=run_id,
                event_emitter=_emit_permission,
                tool_permission=tool_permission,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return await _fail(
                bus,
                run_id,
                tool_call,
                "runtime_error",
                str(exc),
                elapsed(),
                batch_id=batch_id,
                scheduler_mode=scheduler_mode,
                queue_ms=queue_ms,
                queued_at=queued_at,
                started_at=started_at,
            )
        if allowed:
            if tool_permission == ToolPermission.DANGER_FULL_ACCESS:
                # 不可序列化的身份令牌只在权限系统放行后注入，防止模型伪造越权
                runtime_params[_PERMISSION_GRANT_KEY] = _PERMISSION_GRANT_TOKEN
            if decision not in ("auto_allow",):
                await bus.publish(
                    PermissionGrantedEvent(
                        run_id=run_id,
                        tool_use_id=tool_call.id,
                        decision=decision,
                        ts=_now(),
                    )
                )
        else:
            if decision != "auto_deny":
                await bus.publish(
                    PermissionDeniedEvent(
                        run_id=run_id,
                        tool_use_id=tool_call.id,
                        decision=decision,
                        ts=_now(),
                    )
                )
            return await _fail(
                bus,
                run_id,
                tool_call,
                "permission_denied",
                "Permission denied by user. You may not execute this command. "
                "Try an alternative approach or ask the user what to do.",
                elapsed(),
                batch_id=batch_id,
                scheduler_mode=scheduler_mode,
                queue_ms=queue_ms,
                queued_at=queued_at,
                started_at=started_at,
            )

    tool_retry_safe = tool.is_retry_safe(runtime_params)

    for attempt in range(1, _MAX_RETRIES + 2):
        error_class: str | None = None
        error_message: str | None = None
        retryable = False
        execution_state = ToolExecutionState.COMPLETED

        try:
            if tool.allows_indefinite_wait or tool.manages_timeout:
                result = await tool.invoke(runtime_params)
            else:
                result = await asyncio.wait_for(
                    tool.invoke(runtime_params), timeout=timeout
                )
            ms = elapsed()

            if result.is_error:
                error_class = result.error_type or "runtime_error"
                error_message = result.content
                retryable = result.retryable
                execution_state = result.execution_state
            else:
                finished_at = _now()
                await bus.publish(
                    ToolCallFinishedEvent(
                        run_id=run_id,
                        tool_use_id=tool_call.id,
                        tool_name=tool_call.name,
                        elapsed_ms=ms,
                        output=result.content,
                        batch_id=batch_id,
                        scheduler_mode=scheduler_mode,
                        queue_ms=queue_ms,
                        queued_at=queued_at,
                        started_at=started_at,
                        finished_at=finished_at,
                        ts=finished_at,
                    )
                )
                await _publish_test_result(bus, run_id, tool_call, "passed", result.content)
                return result

        except RateLimitedError as exc:
            error_class = "rate_limited"
            error_message = str(exc)
            retryable = True
            execution_state = ToolExecutionState.NOT_STARTED
        except TimeoutError:
            error_class = "timeout"
            execution_state = ToolExecutionState.UNKNOWN
            error_message = (
                f"tool timed out after {timeout}s; the operation may still be running. "
                "Retry the call, increase the timeout, or break it into smaller steps."
            )
        except Exception as exc:
            error_class = "runtime_error"
            error_message = str(exc)

        assert error_class is not None and error_message is not None
        ms = elapsed()

        should_retry = (
            error_class in _RETRYABLE
            and retryable
            and execution_state != ToolExecutionState.UNKNOWN
            and tool_retry_safe
            and attempt <= _MAX_RETRIES
        )
        if should_retry:
            failed_at = _now()
            retry_delay_s = _RETRY_BASE_S * (2 ** (attempt - 1))
            await bus.publish(
                ToolCallFailedEvent(
                    run_id=run_id,
                    tool_use_id=tool_call.id,
                    tool_name=tool_call.name,
                    error_class=error_class,
                    error_message=error_message,
                    elapsed_ms=ms,
                    attempt=attempt,
                    retry_decision="retry",
                    retry_reason=_retry_reason(
                        error_class,
                        retryable,
                        execution_state,
                        tool_retry_safe,
                        attempt,
                    ),
                    retry_delay_ms=int(retry_delay_s * 1000),
                    tool_retry_safe=tool_retry_safe,
                    execution_state=execution_state.value,
                    batch_id=batch_id,
                    scheduler_mode=scheduler_mode,
                    queue_ms=queue_ms,
                    queued_at=queued_at,
                    started_at=started_at,
                    finished_at=failed_at,
                    ts=failed_at,
                )
            )
            await asyncio.sleep(retry_delay_s)
            continue

        return await _fail(
            bus,
            run_id,
            tool_call,
            error_class,
            error_message,
            ms,
            attempt=attempt,
            batch_id=batch_id,
            scheduler_mode=scheduler_mode,
            queue_ms=queue_ms,
            queued_at=queued_at,
            started_at=started_at,
            retryable=retryable,
            execution_state=execution_state,
            retry_reason=_retry_reason(
                error_class,
                retryable,
                execution_state,
                tool_retry_safe,
                attempt,
            ),
            tool_retry_safe=tool_retry_safe,
        )

    # unreachable, but keeps mypy happy
    return ToolResult(content="internal error", is_error=True, error_type="runtime_error")
