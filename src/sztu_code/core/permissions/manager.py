<<<<<<< HEAD
from __future__ import annotations

import asyncio
import datetime
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Any

from sztu_code.core.permissions.policy import (
    DEFAULT_POLICIES,
    PermissionDecision,
    PermissionMode,
    ToolPolicy,
    _any_segment_matches_deny,
    _any_segment_matches_outside_cwd,
    is_edit_tool,
    is_readonly_tool,
    is_write_exec_tool,
    param_preview,
)
from sztu_code.core.permissions.storage import load_policy_file, save_policy_file

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.datetime.now(UTC).isoformat()


@dataclass
class _PendingRequest:
    future: asyncio.Future[str]
    session_id: str
    tool_name: str
    run_id: str


# 管理工具调用权限：策略评估、用户审批挂起、session 级和持久化 always 缓存、超时、模式控制
class PermissionManager:
    def __init__(
        self,
        policies: dict[str, ToolPolicy] | None = None,
        *,
        policy_file: Path | None = None,
        timeout_s: float = 60.0,
        mode: PermissionMode = PermissionMode.NORMAL,
    ) -> None:
        self._policies: dict[str, ToolPolicy] = policies or dict(DEFAULT_POLICIES)
        # tool_use_id → pending Future + metadata
        self._pending: dict[str, _PendingRequest] = {}
        # (session_id, tool_name) → "allow" | "deny"（session 内存，重启丢失）
        self._session_always: dict[tuple[str, str], str] = {}
        # tool_name → "allow" | "deny"（持久化，从 policy_file 加载）
        self._policy_file = policy_file
        self._persistent_always: dict[str, str] = (
            load_policy_file(policy_file) if policy_file is not None else {}
        )
        # 0 表示不超时
        self._timeout_s = timeout_s
        # 权限模式
        self._mode = mode
        # 模式变更回调列表：参数为 (old_mode, new_mode)
        self._mode_listeners: list[Callable[[PermissionMode, PermissionMode], Awaitable[None]]] = []

    # 对工具名 + 参数执行 4 层静态评估，不挂起
    def evaluate(self, tool_name: str, params: dict[str, Any]) -> PermissionDecision:
        from sztu_code.core.permissions.policy import evaluate
        policy = self._policies.get(tool_name)
        return evaluate(tool_name, params, policy)

    # 返回当前权限模式
    def get_mode(self) -> PermissionMode:
        return self._mode

    # 设置权限模式并通知所有监听器
    async def set_mode(self, mode: PermissionMode) -> None:
        if mode == self._mode:
            return
        old = self._mode
        self._mode = mode
        logger.info("permission: mode changed old=%s new=%s", old, mode)
        for listener in self._mode_listeners:
            try:
                await listener(old, mode)
            except Exception:
                logger.exception("permission: mode listener error")

    # 注册模式变更监听器
    def on_mode_change(
        self, listener: Callable[[PermissionMode, PermissionMode], Awaitable[None]],
    ) -> None:
        self._mode_listeners.append(listener)

    # 根据当前模式评估工具权限，在进入完整 check 流程之前应用模式策略
    def _evaluate_mode(
        self, tool_name: str, tool_permission: Any | None = None,
    ) -> tuple[bool, str] | None:
        """返回 (allowed, reason) 或 None 表示继续正常流程。

        tool_permission: 来自 ToolRegistry 的工具权限级别（ToolPermission enum），
                         若为 None 则回退到静态分类。
        """
        # 从 ToolPermission 推导工具类别
        from sztu_code.core.tools.base import ToolPermission
        is_readonly = (
            tool_permission == ToolPermission.READ_ONLY
            if tool_permission is not None
            else is_readonly_tool(tool_name)
        )
        is_edit = (
            tool_permission in (ToolPermission.WORKSPACE_WRITE, ToolPermission.READ_ONLY)
            if tool_permission is not None
            else is_edit_tool(tool_name)
        )
        is_write = (
            tool_permission in (ToolPermission.WORKSPACE_WRITE, ToolPermission.DANGER_FULL_ACCESS)
            if tool_permission is not None
            else is_write_exec_tool(tool_name)
        )

        if self._mode == PermissionMode.AUTO:
            return True, "auto_mode"
        if self._mode == PermissionMode.ACCEPT_EDITS:
            if tool_permission == ToolPermission.DANGER_FULL_ACCESS:
                return None
            if is_edit or tool_name in ("write_file", "edit_file", "note_save"):
                return True, "accept_edits_mode"
            return None
        if self._mode == PermissionMode.PLAN:
            if is_readonly or tool_name in ("read_file", "list_dir", "task_get", "task_list"):
                return True, "plan_mode_readonly"
            if is_write or tool_name in ("write_file", "edit_file", "bash", "note_save",
                                          "task_create", "task_update"):
                return False, "plan_mode_blocked"
            return None
        return None

    # 检查权限；如需 ask 则向客户端发事件并等待响应；返回 (allowed, decision_str)
    async def check_and_wait(
        self,
        tool_use_id: str,
        tool_name: str,
        params: dict[str, Any],
        session_id: str,
        run_id: str,
        event_emitter: Callable[[dict[str, Any]], Awaitable[None]],
        *,
        tool_permission: Any | None = None,
    ) -> tuple[bool, str]:
        # 动态权限分级：若提供 registry，以此覆盖工具默认权限级别
        actual_permission = tool_permission
        # 模式优先检查 — AUTO/ACCEPT_EDITS/PLAN 模式下跳过权限审批
        mode_result = self._evaluate_mode(tool_name, actual_permission)
        if mode_result is not None:
            allowed, reason = mode_result
            logger.debug(
                "permission: mode=%s tool=%s allowed=%s reason=%s permission=%s",
                self._mode, tool_name, allowed, reason, actual_permission,
            )
            return allowed, reason

        from sztu_code.core.tools.base import ToolPermission

        force_full_access_ask = actual_permission == ToolPermission.DANGER_FULL_ACCESS
        command = str(params.get("command", "")) if tool_name == "bash" else ""
        policy = self._policies.get(tool_name)

        # Tier 1: deny_patterns（bash only，不可被缓存绕过）— 逐段检查复合命令
        if command and policy and policy.deny_patterns:
            if _any_segment_matches_deny(command, policy.deny_patterns):
                logger.debug("permission: deny_pattern hit tool=%s", tool_name)
                return False, "auto_deny"

        # Tier 2: OUTSIDE_CWD_HEURISTICS（bash only，强制 ASK）
        # 不可被任何缓存绕过 — 逐段检查复合命令
        outside_cwd = bool(command and _any_segment_matches_outside_cwd(command))

        if not outside_cwd and not force_full_access_ask:
            # Tier 3: session always 缓存
            session_key = (session_id, tool_name)
            if session_key in self._session_always:
                cached = self._session_always[session_key]
                logger.debug("permission: session cache hit tool=%s decision=%s", tool_name, cached)
                return cached == "allow", f"auto_{cached}"

            # Tier 4: persistent always（跨 session）
            if tool_name in self._persistent_always:
                cached = self._persistent_always[tool_name]
                logger.debug(
                    "permission: persistent cache hit tool=%s decision=%s",
                    tool_name,
                    cached,
                )
                return cached == "allow", f"auto_{cached}"

            # Tier 5: allow_patterns（bash only）
            if command and policy:
                for pat in policy.allow_patterns:
                    if re.search(pat, command):
                        return True, "auto_allow"

            # Tier 6: tool default
            if policy is not None:
                if policy.default == PermissionDecision.ALLOW:
                    return True, "auto_allow"
                if policy.default == PermissionDecision.DENY:
                    return False, "auto_deny"
            # default == ASK（bash、unknown tool）→ fall through to Future

        # ASK 路径（来自 OUTSIDE_CWD 强制 ASK，或 default=ASK）
        loop = asyncio.get_event_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._pending[tool_use_id] = _PendingRequest(
            future=future,
            session_id=session_id,
            tool_name=tool_name,
            run_id=run_id,
        )

        await event_emitter(
            {
                "type": "permission.requested",
                "tool_use_id": tool_use_id,
                "tool_name": tool_name,
                "params": params,
                "param_preview": param_preview(tool_name, params),
                "session_id": session_id,
                "ts": _now(),
            }
        )

        try:
            if self._timeout_s > 0:
                raw = await asyncio.wait_for(future, timeout=self._timeout_s)
            else:
                raw = await future
        except TimeoutError:
            self._pending.pop(tool_use_id, None)
            logger.info("permission: timeout tool_use_id=%s tool=%s", tool_use_id, tool_name)
            return False, "timeout"

        allowed = self._apply_response(raw, session_id, tool_name)
        return allowed, raw

    # 处理客户端返回的审批决策，resolve 对应 Future
    def respond(self, tool_use_id: str, decision: str, run_id: str, session_id: str) -> None:
        req = self._pending.pop(tool_use_id, None)
        if req is None:
            logger.warning("permission.respond: unknown tool_use_id=%s", tool_use_id)
            return
        # 验证 run_id 和 session_id 匹配，防止不同上下文的请求被错误处理
        if req.run_id != run_id or req.session_id != session_id:
            logger.warning(
                "permission.respond: context mismatch tool_use_id=%s "
                "expected (run_id=%s, session_id=%s) got (run_id=%s, session_id=%s)",
                tool_use_id, req.run_id, req.session_id, run_id, session_id
            )
            # 将请求重新放回待处理队列，以避免丢失
            self._pending[tool_use_id] = req
            return
        if not req.future.done():
            req.future.set_result(decision)

    # 应用审批决策，更新 session + persistent 缓存，返回是否放行
    def _apply_response(self, decision: str, session_id: str, tool_name: str) -> bool:
        allow = decision in ("allow_once", "always_allow")
        if decision == "always_allow":
            self._session_always[(session_id, tool_name)] = "allow"
            self._persistent_always[tool_name] = "allow"
            logger.info(
                "permission: always allow tool=%s policy_file=%s persistent=%s",
                tool_name, self._policy_file, self._persistent_always,
            )
            if self._policy_file is not None:
                try:
                    save_policy_file(self._persistent_always, self._policy_file)
                    logger.info("permission: policy.toml written path=%s", self._policy_file)
                except Exception:
                    logger.exception(
                        "permission: failed to write policy.toml path=%s", self._policy_file
                    )
            else:
                logger.warning("permission: policy_file is None, skipping persistence")
        elif decision == "always_deny":
            self._session_always[(session_id, tool_name)] = "deny"
            self._persistent_always[tool_name] = "deny"
            logger.info(
                "permission: always deny tool=%s policy_file=%s persistent=%s",
                tool_name, self._policy_file, self._persistent_always,
            )
            if self._policy_file is not None:
                try:
                    save_policy_file(self._persistent_always, self._policy_file)
                    logger.info("permission: policy.toml written path=%s", self._policy_file)
                except Exception:
                    logger.exception(
                        "permission: failed to write policy.toml path=%s", self._policy_file
                    )
            else:
                logger.warning("permission: policy_file is None, skipping persistence")
        return allow

    # 客户端断连时拒绝该 session 所有待审批请求，防止 Future 永久挂起
    def cancel_session(self, session_id: str, reason: str = "client_disconnected") -> None:
        to_cancel = [
            uid for uid, req in self._pending.items()
            if req.session_id == session_id
        ]
        for uid in to_cancel:
            req = self._pending.pop(uid)
            if not req.future.done():
                logger.debug(
                    "permission: cancel pending tool_use_id=%s reason=%s", uid, reason
                )
                req.future.set_result("deny_once")
=======
from __future__ import annotations

import asyncio
import datetime
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Any

from sztu_code.core.permissions.policy import (
    DEFAULT_POLICIES,
    PermissionDecision,
    PermissionMode,
    ToolPolicy,
    _any_segment_matches_deny,
    _any_segment_matches_outside_cwd,
    is_edit_tool,
    is_readonly_tool,
    is_write_exec_tool,
    param_preview,
)
from sztu_code.core.permissions.storage import load_policy_file, save_policy_file

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.datetime.now(UTC).isoformat()


@dataclass
class _PendingRequest:
    future: asyncio.Future[str]
    session_id: str
    tool_name: str
    run_id: str


# 管理工具调用权限：策略评估、用户审批挂起、session 级和持久化 always 缓存、超时、模式控制
class PermissionManager:
    def __init__(
        self,
        policies: dict[str, ToolPolicy] | None = None,
        *,
        policy_file: Path | None = None,
        timeout_s: float = 60.0,
        mode: PermissionMode = PermissionMode.NORMAL,
    ) -> None:
        self._policies: dict[str, ToolPolicy] = policies or dict(DEFAULT_POLICIES)
        # tool_use_id → pending Future + metadata
        self._pending: dict[str, _PendingRequest] = {}
        # (session_id, tool_name) → "allow" | "deny"（session 内存，重启丢失）
        self._session_always: dict[tuple[str, str], str] = {}
        # tool_name → "allow" | "deny"（持久化，从 policy_file 加载）
        self._policy_file = policy_file
        self._persistent_always: dict[str, str] = (
            load_policy_file(policy_file) if policy_file is not None else {}
        )
        # 0 表示不超时
        self._timeout_s = timeout_s
        # 权限模式
        self._mode = mode
        # 模式变更回调列表：参数为 (old_mode, new_mode)
        self._mode_listeners: list[Callable[[PermissionMode, PermissionMode], Awaitable[None]]] = []

    # 对工具名 + 参数执行 4 层静态评估，不挂起
    def evaluate(self, tool_name: str, params: dict[str, Any]) -> PermissionDecision:
        from sztu_code.core.permissions.policy import evaluate
        policy = self._policies.get(tool_name)
        return evaluate(tool_name, params, policy)

    # 返回当前权限模式
    def get_mode(self) -> PermissionMode:
        return self._mode

    # 设置权限模式并通知所有监听器
    async def set_mode(self, mode: PermissionMode) -> None:
        if mode == self._mode:
            return
        old = self._mode
        self._mode = mode
        logger.info("permission: mode changed old=%s new=%s", old, mode)
        for listener in self._mode_listeners:
            try:
                await listener(old, mode)
            except Exception:
                logger.exception("permission: mode listener error")

    # 注册模式变更监听器
    def on_mode_change(
        self, listener: Callable[[PermissionMode, PermissionMode], Awaitable[None]],
    ) -> None:
        self._mode_listeners.append(listener)

    # 根据当前模式评估工具权限，在进入完整 check 流程之前应用模式策略
    def _evaluate_mode(
        self, tool_name: str, tool_permission: Any | None = None,
    ) -> tuple[bool, str] | None:
        """返回 (allowed, reason) 或 None 表示继续正常流程。

        tool_permission: 来自 ToolRegistry 的工具权限级别（ToolPermission enum），
                         若为 None 则回退到静态分类。
        """
        # 从 ToolPermission 推导工具类别
        from sztu_code.core.tools.base import ToolPermission
        is_readonly = (
            tool_permission == ToolPermission.READ_ONLY
            if tool_permission is not None
            else is_readonly_tool(tool_name)
        )
        is_edit = (
            tool_permission in (ToolPermission.WORKSPACE_WRITE, ToolPermission.READ_ONLY)
            if tool_permission is not None
            else is_edit_tool(tool_name)
        )
        is_write = (
            tool_permission in (ToolPermission.WORKSPACE_WRITE, ToolPermission.DANGER_FULL_ACCESS)
            if tool_permission is not None
            else is_write_exec_tool(tool_name)
        )

        if self._mode == PermissionMode.AUTO:
            return True, "auto_mode"
        if self._mode == PermissionMode.ACCEPT_EDITS:
            if tool_permission == ToolPermission.DANGER_FULL_ACCESS:
                return None
            if is_edit or tool_name in ("write_file", "edit_file", "note_save"):
                return True, "accept_edits_mode"
            return None
        if self._mode == PermissionMode.PLAN:
            if is_readonly or tool_name in ("read_file", "list_dir", "task_get", "task_list"):
                return True, "plan_mode_readonly"
            if is_write or tool_name in ("write_file", "edit_file", "bash", "note_save",
                                          "task_create", "task_update"):
                return False, "plan_mode_blocked"
            return None
        return None

    # 检查权限；如需 ask 则向客户端发事件并等待响应；返回 (allowed, decision_str)
    async def check_and_wait(
        self,
        tool_use_id: str,
        tool_name: str,
        params: dict[str, Any],
        session_id: str,
        run_id: str,
        event_emitter: Callable[[dict[str, Any]], Awaitable[None]],
        *,
        tool_permission: Any | None = None,
    ) -> tuple[bool, str]:
        # 动态权限分级：若提供 registry，以此覆盖工具默认权限级别
        actual_permission = tool_permission
        # 模式优先检查 — AUTO/ACCEPT_EDITS/PLAN 模式下跳过权限审批
        mode_result = self._evaluate_mode(tool_name, actual_permission)
        if mode_result is not None:
            allowed, reason = mode_result
            logger.debug(
                "permission: mode=%s tool=%s allowed=%s reason=%s permission=%s",
                self._mode, tool_name, allowed, reason, actual_permission,
            )
            return allowed, reason

        from sztu_code.core.tools.base import ToolPermission

        force_full_access_ask = actual_permission == ToolPermission.DANGER_FULL_ACCESS
        command = str(params.get("command", "")) if tool_name == "bash" else ""
        policy = self._policies.get(tool_name)

        # Tier 1: deny_patterns（bash only，不可被缓存绕过）— 逐段检查复合命令
        if command and policy and policy.deny_patterns:
            if _any_segment_matches_deny(command, policy.deny_patterns):
                logger.debug("permission: deny_pattern hit tool=%s", tool_name)
                return False, "auto_deny"

        # Tier 2: OUTSIDE_CWD_HEURISTICS（bash only，强制 ASK）
        # 不可被任何缓存绕过 — 逐段检查复合命令
        outside_cwd = bool(command and _any_segment_matches_outside_cwd(command))

        if not outside_cwd and not force_full_access_ask:
            # Tier 3: session always 缓存
            session_key = (session_id, tool_name)
            if session_key in self._session_always:
                cached = self._session_always[session_key]
                logger.debug("permission: session cache hit tool=%s decision=%s", tool_name, cached)
                return cached == "allow", f"auto_{cached}"

            # Tier 4: persistent always（跨 session）
            if tool_name in self._persistent_always:
                cached = self._persistent_always[tool_name]
                logger.debug(
                    "permission: persistent cache hit tool=%s decision=%s",
                    tool_name,
                    cached,
                )
                return cached == "allow", f"auto_{cached}"

            # Tier 5: allow_patterns（bash only）
            if command and policy:
                for pat in policy.allow_patterns:
                    if re.search(pat, command):
                        return True, "auto_allow"

            # Tier 6: tool default
            if policy is not None:
                if policy.default == PermissionDecision.ALLOW:
                    return True, "auto_allow"
                if policy.default == PermissionDecision.DENY:
                    return False, "auto_deny"
            # default == ASK（bash、unknown tool）→ fall through to Future

        # ASK 路径（来自 OUTSIDE_CWD 强制 ASK，或 default=ASK）
        loop = asyncio.get_event_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._pending[tool_use_id] = _PendingRequest(
            future=future,
            session_id=session_id,
            tool_name=tool_name,
            run_id=run_id,
        )

        await event_emitter(
            {
                "type": "permission.requested",
                "tool_use_id": tool_use_id,
                "tool_name": tool_name,
                "params": params,
                "param_preview": param_preview(tool_name, params),
                "session_id": session_id,
                "ts": _now(),
            }
        )

        try:
            if self._timeout_s > 0:
                raw = await asyncio.wait_for(future, timeout=self._timeout_s)
            else:
                raw = await future
        except TimeoutError:
            self._pending.pop(tool_use_id, None)
            logger.info("permission: timeout tool_use_id=%s tool=%s", tool_use_id, tool_name)
            return False, "timeout"

        allowed = self._apply_response(raw, session_id, tool_name)
        return allowed, raw

    # 处理客户端返回的审批决策，resolve 对应 Future
    def respond(self, tool_use_id: str, decision: str, run_id: str, session_id: str) -> None:
        req = self._pending.pop(tool_use_id, None)
        if req is None:
            logger.warning("permission.respond: unknown tool_use_id=%s", tool_use_id)
            return
        # 验证 run_id 和 session_id 匹配，防止不同上下文的请求被错误处理
        if req.run_id != run_id or req.session_id != session_id:
            logger.warning(
                "permission.respond: context mismatch tool_use_id=%s "
                "expected (run_id=%s, session_id=%s) got (run_id=%s, session_id=%s)",
                tool_use_id, req.run_id, req.session_id, run_id, session_id
            )
            # 不重新放回队列，直接拒绝以避免 Future 泄漏
            if not req.future.done():
                req.future.set_result("deny_once")
            return
        if not req.future.done():
            req.future.set_result(decision)

    # 应用审批决策，更新 session + persistent 缓存，返回是否放行
    def _apply_response(self, decision: str, session_id: str, tool_name: str) -> bool:
        allow = decision in ("allow_once", "always_allow")
        if decision == "always_allow":
            self._session_always[(session_id, tool_name)] = "allow"
            self._persistent_always[tool_name] = "allow"
            logger.info(
                "permission: always allow tool=%s policy_file=%s persistent=%s",
                tool_name, self._policy_file, self._persistent_always,
            )
            if self._policy_file is not None:
                try:
                    save_policy_file(self._persistent_always, self._policy_file)
                    logger.info("permission: policy.toml written path=%s", self._policy_file)
                except Exception:
                    logger.exception(
                        "permission: failed to write policy.toml path=%s", self._policy_file
                    )
            else:
                logger.warning("permission: policy_file is None, skipping persistence")
        elif decision == "always_deny":
            self._session_always[(session_id, tool_name)] = "deny"
            self._persistent_always[tool_name] = "deny"
            logger.info(
                "permission: always deny tool=%s policy_file=%s persistent=%s",
                tool_name, self._policy_file, self._persistent_always,
            )
            if self._policy_file is not None:
                try:
                    save_policy_file(self._persistent_always, self._policy_file)
                    logger.info("permission: policy.toml written path=%s", self._policy_file)
                except Exception:
                    logger.exception(
                        "permission: failed to write policy.toml path=%s", self._policy_file
                    )
            else:
                logger.warning("permission: policy_file is None, skipping persistence")
        return allow

    # 客户端断连时拒绝该 session 所有待审批请求，防止 Future 永久挂起
    def cancel_session(self, session_id: str, reason: str = "client_disconnected") -> None:
        to_cancel = [
            uid for uid, req in self._pending.items()
            if req.session_id == session_id
        ]
        for uid in to_cancel:
            req = self._pending.pop(uid)
            if not req.future.done():
                logger.debug(
                    "permission: cancel pending tool_use_id=%s reason=%s", uid, reason
                )
                req.future.set_result("deny_once")

    # 取消特定 run 在指定 session 下的待审批请求，避免 Future 泄漏和过期响应
    def cancel_run(self, run_id: str, session_id: str) -> None:
        to_cancel = [
            uid for uid, req in self._pending.items()
            if req.run_id == run_id and req.session_id == session_id
        ]
        for uid in to_cancel:
            req = self._pending.pop(uid)
            if not req.future.done():
                logger.debug(
                    "permission: cancel pending for run tool_use_id=%s reason=run_cancelled", uid
                )
                req.future.set_result("deny_once")
>>>>>>> 5d8e626 (fix: 为权限管理器添加run和session作用域，防止工具使用ID冲突和Future泄漏)
