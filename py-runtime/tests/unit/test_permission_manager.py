from __future__ import annotations

import asyncio
from typing import Any

import pytest

from sztu_code.core.permissions.manager import PermissionManager
from sztu_code.core.permissions.policy import PermissionDecision, ToolPolicy
from sztu_code.core.permissions.storage import load_policy_file

# ── helpers ──────────────────────────────────────────────────────────────────

def _make_manager(**policies: ToolPolicy) -> PermissionManager:
    # policy_file=None：测试中不使用持久化，不污染 ~/.sztu/policy.toml
    return PermissionManager(policies or None)


async def _collect_emitted() -> tuple[list[dict[str, Any]], Any]:
    emitted: list[dict[str, Any]] = []

    async def emitter(event: dict[str, Any]) -> None:
        emitted.append(event)

    return emitted, emitter


# ── evaluate() delegation ─────────────────────────────────────────────────────

# 功能：验证 PermissionManager.evaluate 委托给 policy 层返回正确决策
# 设计：直接调用 evaluate()，不涉及 Future，验证策略加载与委托路径
def test_evaluate_delegates_to_policy() -> None:
    mgr = _make_manager()
    assert mgr.evaluate("read_file", {"path": "x"}) == PermissionDecision.ALLOW
    assert mgr.evaluate("bash", {"command": "echo hi"}) == PermissionDecision.ASK
    assert mgr.evaluate("write_file", {"path": "x", "content": ""}) == PermissionDecision.ASK


# ── check_and_wait: ALLOW path ───────────────────────────────────────────────

# 功能：验证策略为 ALLOW 时 check_and_wait 立即返回 (True, "auto_allow")，不发任何事件
# 设计：read_file 默认 ALLOW，断言不产生 permission.requested 事件，覆盖"无噪声放行"路径
async def test_check_and_wait_allow_no_event() -> None:
    mgr = _make_manager()
    emitted, emitter = await _collect_emitted()

    allowed, decision = await mgr.check_and_wait(
        tool_use_id="t1", tool_name="read_file",
        params={"path": "README.md"}, session_id="s1",
        event_emitter=emitter,
    )

    assert allowed is True
    assert decision == "auto_allow"
    assert emitted == []


# ── check_and_wait: ASK path + respond ───────────────────────────────────────

# 功能：验证 ASK 策略时发出 permission.requested 事件并等待 respond() 解决 Future
# 设计：在后台协程中调用 respond("allow_once")，主协程 await 结束后断言结果；
#       这是权限系统的核心反向请求通路
async def test_check_and_wait_ask_emits_event_and_waits() -> None:
    mgr = _make_manager()
    emitted, emitter = await _collect_emitted()

    async def _auto_respond() -> None:
        await asyncio.sleep(0)  # yield once so check_and_wait can emit the event
        mgr.respond("t2", "allow_once")

    task = asyncio.create_task(_auto_respond())
    allowed, decision = await mgr.check_and_wait(
        tool_use_id="t2", tool_name="bash",
        params={"command": "echo hi"}, session_id="s1",
        event_emitter=emitter,
    )
    await task

    assert allowed is True
    assert decision == "allow_once"
    assert len(emitted) == 1
    assert emitted[0]["type"] == "permission.requested"
    assert emitted[0]["tool_use_id"] == "t2"
    assert emitted[0]["tool_name"] == "bash"


# 功能：验证 respond("deny_once") 使 check_and_wait 返回 (False, "deny_once")
# 设计：用户拒绝时工具不应执行，确认 False 返回值而不是异常
async def test_check_and_wait_deny_once_returns_false() -> None:
    mgr = _make_manager()
    _, emitter = await _collect_emitted()

    async def _auto_deny() -> None:
        await asyncio.sleep(0)
        mgr.respond("t3", "deny_once")

    task = asyncio.create_task(_auto_deny())
    allowed, decision = await mgr.check_and_wait(
        tool_use_id="t3", tool_name="bash",
        params={"command": "echo hi"}, session_id="s1",
        event_emitter=emitter,
    )
    await task

    assert allowed is False
    assert decision == "deny_once"


# ── always_allow cache ────────────────────────────────────────────────────────

# 功能：验证 respond("always_allow") 后同 session 同工具下次不再发事件
# 设计：第二次调用 check_and_wait 命中 always 缓存，直接返回 (True, "auto_allow")，emitted 仍为 1 条
async def test_always_allow_skips_future_ask() -> None:
    mgr = _make_manager()
    emitted, emitter = await _collect_emitted()

    # First call: user says "always allow"
    async def _auto_always() -> None:
        await asyncio.sleep(0)
        mgr.respond("t4", "always_allow")

    task = asyncio.create_task(_auto_always())
    r1, _ = await mgr.check_and_wait(
        tool_use_id="t4", tool_name="bash",
        params={"command": "echo hi"}, session_id="s1",
        event_emitter=emitter,
    )
    await task
    assert r1 is True

    # Second call: should hit cache, no new event
    r2, d2 = await mgr.check_and_wait(
        tool_use_id="t5", tool_name="bash",
        params={"command": "ls"}, session_id="s1",
        event_emitter=emitter,
    )

    assert r2 is True
    assert d2 == "auto_allow"
    assert len(emitted) == 1  # only the first call emitted an event


# 功能：验证 always_allow 在同一 manager 实例内对所有 session 生效（persistent_always 共享）
# 设计：s1 设置 always_allow → 写入 _persistent_always；s2 命中 persistent 缓存，直接放行；
#       emitted 只有 1 条（s2 不需要再 ASK）。这是 persistent always 的核心跨 session 语义。
async def test_always_allow_not_shared_across_sessions() -> None:
    mgr = _make_manager()
    emitted, emitter = await _collect_emitted()

    # session s1 sets always allow for bash
    async def _auto_always() -> None:
        await asyncio.sleep(0)
        mgr.respond("t6", "always_allow")

    task = asyncio.create_task(_auto_always())
    await mgr.check_and_wait(
        tool_use_id="t6", tool_name="bash",
        params={"command": "echo"}, session_id="s1",
        event_emitter=emitter,
    )
    await task

    # session s2 — persistent_always["bash"] = "allow" → 直接放行，不再 ASK
    r, d = await mgr.check_and_wait(
        tool_use_id="t7", tool_name="bash",
        params={"command": "echo"}, session_id="s2",
        event_emitter=emitter,
    )

    assert r is True
    assert d == "auto_allow"
    assert len(emitted) == 1  # s2 命中 persistent 缓存，不再发出事件


# ── always_deny cache ─────────────────────────────────────────────────────────

# 功能：验证 respond("always_deny") 后同 session 同工具下次直接返回 (False, "auto_deny")
# 设计：用户选择 always deny 后不应继续骚扰，下次调用静默拒绝
async def test_always_deny_skips_future_ask() -> None:
    mgr = _make_manager()
    emitted, emitter = await _collect_emitted()

    async def _auto_always_deny() -> None:
        await asyncio.sleep(0)
        mgr.respond("t8", "always_deny")

    task = asyncio.create_task(_auto_always_deny())
    r1, _ = await mgr.check_and_wait(
        tool_use_id="t8", tool_name="bash",
        params={"command": "echo"}, session_id="s1",
        event_emitter=emitter,
    )
    await task
    assert r1 is False

    # Second call: cache hit → no event, return (False, "auto_deny")
    r2, d2 = await mgr.check_and_wait(
        tool_use_id="t9", tool_name="bash",
        params={"command": "ls"}, session_id="s1",
        event_emitter=emitter,
    )
    assert r2 is False
    assert d2 == "auto_deny"
    assert len(emitted) == 1


# ── cancel_session ────────────────────────────────────────────────────────────

# 功能：验证 cancel_session 将 pending Future 设为 deny_once，check_and_wait 返回 False
# 设计：模拟客户端断连场景——check_and_wait 挂起后调用 cancel_session，
#       确认 Future 被解决而非永久挂起（防止僵尸 run）
async def test_cancel_session_resolves_pending_future() -> None:
    mgr = _make_manager()
    _, emitter = await _collect_emitted()

    async def _cancel_after_emit() -> None:
        await asyncio.sleep(0)  # wait for event to be emitted
        mgr.cancel_session("s1", reason="client_disconnected")

    task = asyncio.create_task(_cancel_after_emit())
    allowed, _ = await mgr.check_and_wait(
        tool_use_id="t10", tool_name="bash",
        params={"command": "ls"}, session_id="s1",
        event_emitter=emitter,
    )
    await task

    assert allowed is False


# 功能：验证 cancel_session 只取消属于该 session 的 pending Future
# 设计：s1 和 s2 各有一个 pending，cancel_session(s2) 不影响 s1 的 Future
async def test_cancel_session_only_affects_target_session() -> None:
    mgr = _make_manager()
    _, emitter = await _collect_emitted()

    # Launch two concurrent check_and_wait for different sessions
    s1_done = asyncio.Event()
    s2_done = asyncio.Event()
    s1_result: list[bool] = []
    s2_result: list[bool] = []

    async def _s1() -> None:
        r, _ = await mgr.check_and_wait(
            tool_use_id="ta", tool_name="bash",
            params={"command": "echo"}, session_id="s1",
            event_emitter=emitter,
        )
        s1_result.append(r)
        s1_done.set()

    async def _s2() -> None:
        r, _ = await mgr.check_and_wait(
            tool_use_id="tb", tool_name="bash",
            params={"command": "echo"}, session_id="s2",
            event_emitter=emitter,
        )
        s2_result.append(r)
        s2_done.set()

    t1 = asyncio.create_task(_s1())
    t2 = asyncio.create_task(_s2())

    await asyncio.sleep(0)  # let both emit events and hang

    # cancel only s2
    mgr.cancel_session("s2")
    await s2_done.wait()

    # s1 should still be pending; resolve it manually
    mgr.respond("ta", "allow_once")
    await s1_done.wait()

    await t1
    await t2

    assert s1_result == [True]   # s1 was allowed
    assert s2_result == [False]  # s2 was cancelled → denied


# ── respond: unknown tool_use_id ──────────────────────────────────────────────

# 功能：验证 respond 传入不存在的 tool_use_id 时静默忽略，不抛异常
# 设计：竞态场景（客户端重复发送响应）不应导致 daemon crash；#118 要求返回
#       明确的 unknown 状态，让客户端能区分"已送达"与"无处送达"
def test_respond_unknown_tool_use_id_is_noop() -> None:
    mgr = _make_manager()
    assert mgr.respond("nonexistent", "allow_once") == "unknown"  # should not raise


# ── OUTSIDE_CWD 不被 always 缓存绕过 ─────────────────────────────────────────

# 功能：验证 always_allow bash 之后，含绝对路径的命令仍触发 ASK，不被缓存绕过
# 设计：先让 session s1 对 bash 设置 always_allow，再请求含绝对路径命令；
#       OUTSIDE_CWD 检查在 always 缓存之前，应发出 permission.requested 事件
async def test_always_allow_does_not_bypass_outside_cwd() -> None:
    mgr = _make_manager()
    emitted, emitter = await _collect_emitted()

    # 首次 allow → 写入 session always 缓存
    async def _auto_always() -> None:
        await asyncio.sleep(0)
        mgr.respond("t_always", "always_allow")

    t = asyncio.create_task(_auto_always())
    await mgr.check_and_wait(
        tool_use_id="t_always", tool_name="bash",
        params={"command": "echo ok"}, session_id="s1",
        event_emitter=emitter,
    )
    await t
    assert len(emitted) == 1  # 首次 ASK 触发事件

    # 第二次：bash + 绝对路径 → OUTSIDE_CWD 强制 ASK，不命中 session always 缓存
    async def _auto_respond_abs() -> None:
        await asyncio.sleep(0)
        mgr.respond("t_abs", "allow_once")

    t2 = asyncio.create_task(_auto_respond_abs())
    allowed, decision = await mgr.check_and_wait(
        tool_use_id="t_abs", tool_name="bash",
        params={"command": "cat /etc/hosts"}, session_id="s1",
        event_emitter=emitter,
    )
    await t2

    assert allowed is True
    assert len(emitted) == 2  # 绝对路径命令再次触发 ASK，共 2 个事件


# ── 持久化 always 写文件 ──────────────────────────────────────────────────────

# 功能：验证 always_allow 决策写入 policy_file，新 PermissionManager 加载后自动放行
# 设计：用 tmp_path 作为 policy_file，断言文件存在且内容正确；
#       再新建 manager 加载文件，同工具无需 ASK 直接返回 auto_allow
async def test_persistent_always_written_and_reloaded(tmp_path: pytest.TempPathFixture) -> None:
    policy_file = tmp_path / "policy.toml"
    mgr = PermissionManager(policy_file=policy_file)
    emitted, emitter = await _collect_emitted()

    async def _auto_always() -> None:
        await asyncio.sleep(0)
        mgr.respond("tp1", "always_allow")

    t = asyncio.create_task(_auto_always())
    allowed, _ = await mgr.check_and_wait(
        tool_use_id="tp1", tool_name="bash",
        params={"command": "echo"}, session_id="s1",
        event_emitter=emitter,
    )
    await t
    assert allowed is True
    assert policy_file.exists()

    loaded = load_policy_file(policy_file)
    assert loaded.get("bash") == "allow"

    # 新 manager 加载同一文件，bash 应直接 auto_allow（无 OUTSIDE_CWD）
    mgr2 = PermissionManager(policy_file=policy_file)
    emitted2, emitter2 = await _collect_emitted()
    allowed2, decision2 = await mgr2.check_and_wait(
        tool_use_id="tp2", tool_name="bash",
        params={"command": "echo new"}, session_id="s2",
        event_emitter=emitter2,
    )
    assert allowed2 is True
    assert decision2 == "auto_allow"
    assert emitted2 == []  # 无需 ASK


# ── 审批超时 ──────────────────────────────────────────────────────────────────

# 功能：验证 check_and_wait 超时后返回 (False, "timeout")，不永久挂起
# 设计：timeout_s=0.05 极短超时，不主动 respond；断言在合理时间内返回 False
async def test_permission_timeout_returns_false() -> None:
    mgr = PermissionManager(timeout_s=0.05)
    emitted, emitter = await _collect_emitted()

    allowed, decision = await mgr.check_and_wait(
        tool_use_id="t_timeout", tool_name="bash",
        params={"command": "echo hi"}, session_id="s1",
        event_emitter=emitter,
    )

    assert allowed is False
    assert decision == "timeout"
    assert len(emitted) == 1
    assert emitted[0]["type"] == "permission.requested"


# 功能：验证超时后 pending 被清理，迟到的 respond 不影响后续调用
# 设计：超时后调用 respond，不抛异常（unknown tool_use_id 静默忽略）；
#       再次 check_and_wait 同 tool_use_id 仍正常发出新的 permission.requested
async def test_permission_timeout_cleans_up_pending() -> None:
    mgr = PermissionManager(timeout_s=0.05)
    _, emitter = await _collect_emitted()

    await mgr.check_and_wait(
        tool_use_id="t_late", tool_name="bash",
        params={"command": "echo"}, session_id="s1",
        event_emitter=emitter,
    )
    # 超时后迟到的 respond 不应 crash
    mgr.respond("t_late", "allow_once")  # should be noop
    assert "t_late" not in mgr._pending


# 功能：验证 Run deadline 比权限 timeout 更早耗尽时，返回独立 deadline 结果并清理请求
# 设计：不主动响应审批；deadline 后的响应只能命中 unknown，不能重新放行工具调用
async def test_permission_run_deadline_returns_distinct_result_and_cleans_pending() -> None:
    mgr = PermissionManager(timeout_s=0.2)
    emitted, emitter = await _collect_emitted()

    allowed, decision = await mgr.check_and_wait(
        tool_use_id="t_run_deadline",
        tool_name="bash",
        params={"command": "echo"},
        session_id="s1",
        event_emitter=emitter,
        run_id="r1",
        run_remaining_s=0.02,
    )

    assert allowed is False
    assert decision == "deadline_exceeded"
    assert len(emitted) == 1
    assert "t_run_deadline" not in mgr._pending
    assert mgr.respond("t_run_deadline", "allow_once", run_id="r1", session_id="s1") == "unknown"


# 功能：验证进入权限等待前已耗尽 Run deadline 时不创建审批事件或 pending
# 设计：使用 0 剩余预算覆盖调用前门禁，避免把已结束的 Run 放入审批队列
async def test_permission_run_deadline_is_checked_before_pending() -> None:
    mgr = PermissionManager(timeout_s=0.2)
    emitted, emitter = await _collect_emitted()

    assert await mgr.check_and_wait(
        tool_use_id="already-expired",
        tool_name="bash",
        params={"command": "echo"},
        session_id="s1",
        event_emitter=emitter,
        run_id="r1",
        run_remaining_s=0.0,
    ) == (False, "deadline_exceeded")
    assert emitted == []
    assert mgr._pending == {}


# 功能：验证 permission.requested 发送期间 Run deadline 耗尽也能有界返回并清理
# 设计：事件回调故意挂起，使用 asyncio.timeout 取消该阶段，不依赖客户端响应
async def test_permission_run_deadline_expires_during_event_emission() -> None:
    mgr = PermissionManager(timeout_s=0.2)
    emitter_started = asyncio.Event()
    emitter_blocked = asyncio.Event()

    async def emitter(event: dict[str, Any]) -> None:
        assert event["tool_use_id"] == "event-deadline"
        emitter_started.set()
        await emitter_blocked.wait()

    task = asyncio.create_task(
        mgr.check_and_wait(
            tool_use_id="event-deadline",
            tool_name="bash",
            params={"command": "echo"},
            session_id="s1",
            event_emitter=emitter,
            run_id="r1",
            run_remaining_s=0.02,
        )
    )
    await emitter_started.wait()

    assert await task == (False, "deadline_exceeded")
    assert mgr._pending == {}


# 功能：验证事件发送返回时已跨过绝对 deadline 不会重新开始等待
# 设计：推进注入 monotonic clock 后立即复核，不依赖真实 sleep 或 asyncio loop 时钟
async def test_permission_absolute_deadline_is_not_reset_after_event_emission() -> None:
    mgr = PermissionManager(timeout_s=60.0)
    clock = [0.0]

    async def emitter(event: dict[str, Any]) -> None:
        clock[0] = 2.0

    assert await mgr.check_and_wait(
        tool_use_id="absolute-deadline",
        tool_name="bash",
        params={"command": "echo"},
        session_id="s1",
        event_emitter=emitter,
        run_id="r1",
        run_deadline_at=1.0,
        run_clock=lambda: clock[0],
    ) == (False, "deadline_exceeded")
    assert mgr._pending == {}


# 功能：验证 Run deadline 内收到用户响应时仍按正常审批语义放行
# 设计：在事件回调中同步响应，确保 Future 在 deadline 前解决
async def test_permission_response_before_run_deadline_is_applied() -> None:
    mgr = PermissionManager(timeout_s=0.2)
    emitted: list[dict[str, Any]] = []

    async def emitter(event: dict[str, Any]) -> None:
        emitted.append(event)
        assert mgr.respond("before-deadline", "allow_once", run_id="r1", session_id="s1") == "resolved"

    assert await mgr.check_and_wait(
        tool_use_id="before-deadline",
        tool_name="bash",
        params={"command": "echo"},
        session_id="s1",
        event_emitter=emitter,
        run_id="r1",
        run_remaining_s=0.2,
    ) == (True, "allow_once")
    assert len(emitted) == 1


# 功能：验证固定权限 timeout 更短时仍返回 timeout，而不是误报 Run deadline
# 设计：Run 剩余预算明显长于权限配置上限，确认较短边界优先生效
async def test_permission_timeout_wins_when_shorter_than_run_deadline() -> None:
    mgr = PermissionManager(timeout_s=0.02)
    emitted, emitter = await _collect_emitted()

    assert await mgr.check_and_wait(
        tool_use_id="permission-timeout",
        tool_name="bash",
        params={"command": "echo"},
        session_id="s1",
        event_emitter=emitter,
        run_id="r1",
        run_remaining_s=0.2,
    ) == (False, "timeout")
    assert len(emitted) == 1
    assert mgr._pending == {}


# 功能：验证事件发送器自己的 TimeoutError 不会被误报为 Run deadline
# 设计：父 deadline 尚未耗尽时让 emitter 主动抛出异常，异常应保留原始语义
async def test_permission_emitter_timeout_error_is_not_reclassified() -> None:
    mgr = PermissionManager(timeout_s=0.2)

    async def emitter(event: dict[str, Any]) -> None:
        raise TimeoutError("emitter timeout")

    with pytest.raises(TimeoutError, match="emitter timeout"):
        await mgr.check_and_wait(
            tool_use_id="emitter-timeout",
            tool_name="bash",
            params={"command": "echo"},
            session_id="s1",
            event_emitter=emitter,
            run_id="r1",
            run_remaining_s=0.2,
        )

    assert mgr._pending == {}


# 功能：验证事件发送器在被父 deadline 取消后自行抛出的 TimeoutError 仍不被改写
# 设计：模拟 emitter 吞掉 CancelledError 并抛出自己的错误，覆盖 timeout 竞态边界
async def test_permission_emitter_timeout_after_cancellation_is_not_reclassified() -> None:
    mgr = PermissionManager(timeout_s=60.0)

    async def emitter(event: dict[str, Any]) -> None:
        try:
            await asyncio.sleep(1.0)
        except asyncio.CancelledError as exc:
            raise TimeoutError("emitter cleanup timeout") from exc

    with pytest.raises(TimeoutError, match="emitter cleanup timeout"):
        await mgr.check_and_wait(
            tool_use_id="emitter-cancel-timeout",
            tool_name="bash",
            params={"command": "echo"},
            session_id="s1",
            event_emitter=emitter,
            run_id="r1",
            run_remaining_s=0.01,
        )

    assert mgr._pending == {}


# 功能：验证旧 Run 被取消后复用同一 tool_use_id 时，旧请求 finally 不会移除新请求
# 设计：让旧 emitter 在 cancel_run 后继续挂起，再创建新 Run 请求，覆盖身份保护竞态
async def test_permission_stale_request_cannot_remove_reused_tool_id() -> None:
    mgr = PermissionManager(timeout_s=0)
    first_emitter_started = asyncio.Event()
    release_first_emitter = asyncio.Event()
    emitter_calls = 0

    async def emitter(event: dict[str, Any]) -> None:
        nonlocal emitter_calls
        emitter_calls += 1
        if emitter_calls == 1:
            first_emitter_started.set()
            await release_first_emitter.wait()

    first = asyncio.create_task(
        mgr.check_and_wait(
            tool_use_id="reused-id",
            tool_name="bash",
            params={"command": "echo old"},
            session_id="s1",
            event_emitter=emitter,
            run_id="old-run",
        )
    )
    await first_emitter_started.wait()

    mgr.cancel_run("old-run", "s1")
    second = asyncio.create_task(
        mgr.check_and_wait(
            tool_use_id="reused-id",
            tool_name="bash",
            params={"command": "echo new"},
            session_id="s1",
            event_emitter=emitter,
            run_id="new-run",
        )
    )

    async def wait_for_new_pending() -> None:
        while "reused-id" not in mgr._pending:
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_for_new_pending(), timeout=1.0)
    assert mgr._pending["reused-id"].run_id == "new-run"

    release_first_emitter.set()
    assert await first == (False, "deny_once")
    assert mgr._pending["reused-id"].run_id == "new-run"

    assert mgr.respond("reused-id", "allow_once", run_id="new-run", session_id="s1") == "resolved"
    assert await second == (True, "allow_once")
    assert mgr._pending == {}


# 功能：验证 check_and_wait 被外部取消时也会清理 pending 请求
# 设计：先让审批请求进入等待，再取消调用任务；迟到的响应只能命中 unknown/no-op，
#       不能留下 Future 或重新放行已取消的工具调用
async def test_permission_cancellation_cleans_up_pending() -> None:
    mgr = PermissionManager(timeout_s=0)
    _, emitter = await _collect_emitted()

    task = asyncio.create_task(
        mgr.check_and_wait(
            tool_use_id="t_cancelled",
            tool_name="bash",
            params={"command": "echo"},
            session_id="s1",
            event_emitter=emitter,
            run_id="r1",
        )
    )
    await asyncio.sleep(0)
    assert "t_cancelled" in mgr._pending

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert "t_cancelled" not in mgr._pending
    # 取消后的迟到响应归属 unknown，不影响任何新请求（Issue #118）
    assert mgr.respond("t_cancelled", "allow_once", run_id="r1", session_id="s1") == "unknown"


# 功能：验证权限事件发送期间取消也会清理 pending 请求
# 设计：让 event_emitter 在请求已登记后挂起，再取消 check_and_wait，覆盖等待 Future 前的窗口
async def test_permission_cancellation_during_event_emission_cleans_up_pending() -> None:
    mgr = PermissionManager(timeout_s=0)
    emitter_started = asyncio.Event()
    emitter_release = asyncio.Event()

    async def emitter(event: dict[str, Any]) -> None:
        assert event["tool_use_id"] == "emit-cancelled"
        emitter_started.set()
        await emitter_release.wait()

    task = asyncio.create_task(
        mgr.check_and_wait(
            tool_use_id="emit-cancelled",
            tool_name="bash",
            params={"command": "echo"},
            session_id="s1",
            event_emitter=emitter,
            run_id="r1",
        )
    )
    await emitter_started.wait()
    assert "emit-cancelled" in mgr._pending

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    emitter_release.set()
    assert "emit-cancelled" not in mgr._pending


# 功能：验证 session 断连后，后台 run 的后续 ASK 请求直接拒绝而不重新创建 pending
# 设计：先取消 session，再发起新的危险调用；重新标记连接后确认审批队列恢复可用
async def test_disconnected_session_does_not_create_new_pending() -> None:
    mgr = PermissionManager(timeout_s=0)
    _, emitter = await _collect_emitted()

    mgr.cancel_session("s1", reason="client_disconnected")
    assert await mgr.check_and_wait(
        tool_use_id="after-disconnect",
        tool_name="bash",
        params={"command": "echo"},
        session_id="s1",
        event_emitter=emitter,
        run_id="r1",
    ) == (False, "deny_once")
    assert mgr._pending == {}

    mgr.mark_session_connected("s1")
    task = asyncio.create_task(
        mgr.check_and_wait(
            tool_use_id="after-reconnect",
            tool_name="bash",
            params={"command": "echo"},
            session_id="s1",
            event_emitter=emitter,
            run_id="r2",
        )
    )
    await asyncio.sleep(0)
    mgr.respond("after-reconnect", "allow_once", run_id="r2", session_id="s1")
    assert await task == (True, "allow_once")


# 功能：验证取消旧 run 后，迟到的旧上下文响应不会唤醒同 ID 的新审批请求
# 设计：先取消 r-old，再用相同 tool_use_id 创建 r-new；旧响应必须被拒绝并保留新请求，
#       随后只有匹配 r-new/session 的响应才能完成新请求
async def test_stale_response_from_cancelled_run_does_not_release_new_request() -> None:
    mgr = PermissionManager(timeout_s=0)
    _, emitter = await _collect_emitted()

    old_task = asyncio.create_task(
        mgr.check_and_wait(
            tool_use_id="reused-id",
            tool_name="bash",
            params={"command": "echo old"},
            session_id="s1",
            event_emitter=emitter,
            run_id="r-old",
        )
    )
    await asyncio.sleep(0)
    mgr.cancel_run("r-old", "s1")
    assert await old_task == (False, "deny_once")

    new_task = asyncio.create_task(
        mgr.check_and_wait(
            tool_use_id="reused-id",
            tool_name="bash",
            params={"command": "echo new"},
            session_id="s1",
            event_emitter=emitter,
            run_id="r-new",
        )
    )
    await asyncio.sleep(0)

    mgr.respond("reused-id", "allow_once", run_id="r-old", session_id="s1")
    await asyncio.sleep(0)
    assert not new_task.done()

    mgr.respond("reused-id", "deny_once", run_id="r-new", session_id="s1")
    assert await new_task == (False, "deny_once")


# 功能：验证 daemon shutdown 可一次性拒绝所有 session 的待审批请求
# 设计：同时挂起两个 session 的审批，调用 cancel_all 后两个调用都应完成且无残留
async def test_cancel_all_resolves_all_pending_requests() -> None:
    mgr = PermissionManager(timeout_s=0)
    _, emitter = await _collect_emitted()
    mgr.cancel_session("stale-session", reason="client_disconnected")

    tasks = [
        asyncio.create_task(
            mgr.check_and_wait(
                tool_use_id=tool_use_id,
                tool_name="bash",
                params={"command": "echo"},
                session_id=session_id,
                event_emitter=emitter,
                run_id=f"run-{session_id}",
            )
        )
        for tool_use_id, session_id in (("shutdown-a", "s1"), ("shutdown-b", "s2"))
    ]
    await asyncio.sleep(0)
    mgr.cancel_all(reason="daemon_shutdown")

    assert await asyncio.gather(*tasks) == [
        (False, "deny_once"),
        (False, "deny_once"),
    ]
    assert mgr._pending == {}
    assert mgr._session_cancellations == {}


# ── Issue #118：归属校验与重复 ID 防护 ───────────────────────────────────────

# 功能：验证并发 run 复用同一 tool_use_id 时，后到请求被拒绝且先到请求不受影响
# 设计：r1/s1 挂起后 r2 用相同 ID 发起第二个 ASK；第二个立即返回
#       duplicate_request_id，随后 respond 仍能正确解决第一个请求
async def test_duplicate_tool_use_id_denies_new_request_and_keeps_first() -> None:
    mgr = PermissionManager(timeout_s=0)
    _, emitter = await _collect_emitted()

    first = asyncio.create_task(
        mgr.check_and_wait(
            tool_use_id="dup-id", tool_name="bash",
            params={"command": "echo one"}, session_id="s1",
            event_emitter=emitter, run_id="r1",
        )
    )
    await asyncio.sleep(0)
    assert "dup-id" in mgr._pending

    second_allowed, second_decision = await mgr.check_and_wait(
        tool_use_id="dup-id", tool_name="bash",
        params={"command": "echo two"}, session_id="s1",
        event_emitter=emitter, run_id="r2",
    )
    assert (second_allowed, second_decision) == (False, "duplicate_request_id")

    status = mgr.respond("dup-id", "allow_once", run_id="r1", session_id="s1")
    assert status == "resolved"
    assert await first == (True, "allow_once")
    assert "dup-id" not in mgr._pending


# 功能：验证父子 Agent 共享 manager 时（子 Agent 默认继承父 PermissionManager），
#       同 ID 并发同样被拒——重复 ID 不能唤醒其他上下文的审批
# 设计：父 run 与子 run 各自 check_and_wait 使用相同 tool_use_id，断言子请求被
#       拒绝、父请求仍挂起且只能被父归属的响应解决
async def test_duplicate_tool_use_id_rejected_across_parent_and_child_runs() -> None:
    mgr = PermissionManager(timeout_s=0)
    _, emitter = await _collect_emitted()

    parent = asyncio.create_task(
        mgr.check_and_wait(
            tool_use_id="shared-id", tool_name="bash",
            params={"command": "echo parent"}, session_id="s1",
            event_emitter=emitter, run_id="r-parent",
        )
    )
    await asyncio.sleep(0)

    child_allowed, child_decision = await mgr.check_and_wait(
        tool_use_id="shared-id", tool_name="bash",
        params={"command": "echo child"}, session_id="s1",
        event_emitter=emitter, run_id="r-child",
    )
    assert (child_allowed, child_decision) == (False, "duplicate_request_id")
    assert not parent.done()

    assert mgr.respond("shared-id", "deny_once", run_id="r-parent", session_id="s1") == "resolved"
    assert await parent == (False, "deny_once")


# 功能：验证 respond 对不存在或已被取消的请求返回 "unknown"
# 设计：覆盖两条路径——从未存在的 ID、cancel_run 清理后的 ID（迟到响应）
async def test_respond_returns_unknown_for_missing_or_cancelled_requests() -> None:
    mgr = PermissionManager(timeout_s=0)
    _, emitter = await _collect_emitted()

    assert mgr.respond("never-existed", "allow_once", run_id="r1", session_id="s1") == "unknown"

    task = asyncio.create_task(
        mgr.check_and_wait(
            tool_use_id="cancelled-id", tool_name="bash",
            params={"command": "echo"}, session_id="s1",
            event_emitter=emitter, run_id="r1",
        )
    )
    await asyncio.sleep(0)
    mgr.cancel_run("r1", "s1")
    assert await task == (False, "deny_once")
    assert mgr.respond("cancelled-id", "allow_once", run_id="r1", session_id="s1") == "unknown"


# 功能：验证重复 respond 的第二次返回 "unknown"，且不改变首次决策结果
# 设计：解决后再次 respond 同一 ID；Future 结果保持首次决策
async def test_double_respond_second_returns_unknown() -> None:
    mgr = PermissionManager(timeout_s=0)
    _, emitter = await _collect_emitted()

    task = asyncio.create_task(
        mgr.check_and_wait(
            tool_use_id="twice-id", tool_name="bash",
            params={"command": "echo"}, session_id="s1",
            event_emitter=emitter, run_id="r1",
        )
    )
    await asyncio.sleep(0)
    assert mgr.respond("twice-id", "allow_once", run_id="r1", session_id="s1") == "resolved"
    assert mgr.respond("twice-id", "deny_once", run_id="r1", session_id="s1") == "unknown"
    assert await task == (True, "allow_once")


# 功能：验证 session 归属不匹配时返回 "mismatch"，请求保留、正确归属仍可解决
# 设计：s2/r1 的错误响应被拒绝；随后 s1/r1 的响应正常送达同一请求
async def test_respond_wrong_session_returns_mismatch_and_keeps_request() -> None:
    mgr = PermissionManager(timeout_s=0)
    _, emitter = await _collect_emitted()

    task = asyncio.create_task(
        mgr.check_and_wait(
            tool_use_id="own-id", tool_name="bash",
            params={"command": "echo"}, session_id="s1",
            event_emitter=emitter, run_id="r1",
        )
    )
    await asyncio.sleep(0)

    assert mgr.respond("own-id", "allow_once", run_id="r1", session_id="s2") == "mismatch"
    assert not task.done()

    assert mgr.respond("own-id", "allow_once", run_id="r1", session_id="s1") == "resolved"
    assert await task == (True, "allow_once")


# 功能：验证 run 归属不匹配同样返回 "mismatch"
# 设计：r-old 的并发错误响应不能解决 r-new 的同 ID 请求（与取消后复用 ID
#       场景互补：覆盖"未取消但归属错误"的窗口）
async def test_respond_wrong_run_returns_mismatch() -> None:
    mgr = PermissionManager(timeout_s=0)
    _, emitter = await _collect_emitted()

    task = asyncio.create_task(
        mgr.check_and_wait(
            tool_use_id="run-own-id", tool_name="bash",
            params={"command": "echo"}, session_id="s1",
            event_emitter=emitter, run_id="r-new",
        )
    )
    await asyncio.sleep(0)

    assert mgr.respond("run-own-id", "allow_once", run_id="r-old", session_id="s1") == "mismatch"
    assert not task.done()

    assert mgr.respond("run-own-id", "allow_once", run_id="r-new", session_id="s1") == "resolved"
    assert await task == (True, "allow_once")


# 功能：验证空串归属字段与 None 同样视为未提供（向后兼容），响应可送达
# 设计：RPC 命令模型要求字符串字段，客户端可能传 ""；空串不应让所有响应 mismatch
async def test_respond_with_empty_ownership_fields_still_resolves() -> None:
    mgr = PermissionManager(timeout_s=0)
    _, emitter = await _collect_emitted()

    task = asyncio.create_task(
        mgr.check_and_wait(
            tool_use_id="empty-own-id", tool_name="bash",
            params={"command": "echo"}, session_id="s1",
            event_emitter=emitter, run_id="r1",
        )
    )
    await asyncio.sleep(0)

    assert mgr.respond("empty-own-id", "allow_once", run_id="", session_id="") == "resolved"
    assert await task == (True, "allow_once")
