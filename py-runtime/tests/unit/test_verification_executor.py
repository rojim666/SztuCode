from __future__ import annotations

import sys
from pathlib import Path

from sztu_code.core.verification import (
    CompletionCondition,
    CompletionContract,
    ConditionResult,
    ContractSource,
    EvidenceKind,
    VerificationExecutor,
    VerificationOutcome,
    aggregate_outcomes,
    modification_status_summary,
)


def _cond(
    cid: str,
    command: list[str] | None = None,
    *,
    required: bool = True,
    priority: int = 0,
) -> CompletionCondition:
    return CompletionCondition(
        id=cid,
        description=cid,
        source=ContractSource.USER,
        check_command=command,
        required=required,
        priority=priority,
    )


def _contract(*conds: CompletionCondition) -> CompletionContract:
    return CompletionContract(
        run_id="run-1", conditions=list(conds), created_at="2026-08-19T00:00:00Z"
    )


def _result(cid: str, outcome: VerificationOutcome) -> ConditionResult:
    return ConditionResult(condition_id=cid, outcome=outcome)


def _executor(tmp_path: Path, *, timeout: int = 30) -> VerificationExecutor:
    return VerificationExecutor(tmp_path, tmp_path / "run", check_timeout_s=timeout)


# 功能：验证成功命令（退出码 0）产出 verified 条件结果与完整证据
# 设计：用 sys.executable -c 保证跨平台；断言证据的退出码、落盘日志内容与摘要透传
async def test_executor_success_command_yields_verified(tmp_path: Path) -> None:
    contract = _contract(
        _cond("c1", [sys.executable, "-c", "print('ok'); import sys; sys.exit(0)"])
    )
    result = await _executor(tmp_path).verify(
        contract, workspace_digests={"a.txt": "abc123"}
    )
    assert result.overall is VerificationOutcome.VERIFIED
    assert result.run_id == "run-1"
    [cr] = result.results
    assert cr.outcome is VerificationOutcome.VERIFIED
    assert cr.evidence is not None
    assert cr.evidence.kind is EvidenceKind.COMMAND_EXIT_CODE
    assert cr.evidence.exit_code == 0
    assert cr.evidence.workspace_digests == {"a.txt": "abc123"}
    log = Path(cr.evidence.output_path)
    assert log == tmp_path / "run" / "verification" / "c1.log"
    assert "ok" in log.read_text(encoding="utf-8")


# 功能：验证失败命令（非零退出码）产出 failed 条件结果，整体判 failed
# 设计：required 条件退出码 7，断言证据保留真实退出码且 message 说明失败原因
async def test_executor_failing_command_yields_failed(tmp_path: Path) -> None:
    contract = _contract(_cond("c1", [sys.executable, "-c", "import sys; sys.exit(7)"]))
    result = await _executor(tmp_path).verify(contract)
    assert result.overall is VerificationOutcome.FAILED
    [cr] = result.results
    assert cr.outcome is VerificationOutcome.FAILED
    assert cr.evidence is not None
    assert cr.evidence.exit_code == 7
    assert "exited with code 7" in cr.message


# 功能：验证超时的检查命令被 kill 并判 failed，证据退出码为 None
# 设计：睡眠 30s 的命令配 1s 超时，断言 message 标注超时且整体 failed
async def test_executor_timeout_kills_process_and_fails(tmp_path: Path) -> None:
    contract = _contract(_cond("c1", [sys.executable, "-c", "import time; time.sleep(30)"]))
    result = await _executor(tmp_path, timeout=1).verify(contract)
    assert result.overall is VerificationOutcome.FAILED
    [cr] = result.results
    assert cr.outcome is VerificationOutcome.FAILED
    assert cr.evidence is not None
    assert cr.evidence.exit_code is None
    assert "timed out after 1s" in cr.message


# 功能：验证不存在的可执行文件判 env_blocked，且不算失败也不算通过
# 设计：单条 env_blocked 时整体 unverified（无任何通过证据）；与 verified 条件共存时整体 partial
async def test_executor_missing_executable_is_env_blocked(tmp_path: Path) -> None:
    contract = _contract(_cond("c1", ["sztu-definitely-missing-exe-94"]))
    result = await _executor(tmp_path).verify(contract)
    [cr] = result.results
    assert cr.outcome is VerificationOutcome.ENV_BLOCKED
    assert cr.evidence is None
    assert "cannot start check command" in cr.message
    assert result.overall is VerificationOutcome.UNVERIFIED

    mixed = _contract(
        _cond("ok", [sys.executable, "-c", "raise SystemExit(0)"]),
        _cond("blocked", ["sztu-definitely-missing-exe-94"]),
    )
    assert (await _executor(tmp_path).verify(mixed)).overall is VerificationOutcome.PARTIAL


# 功能：验证 check_command=None 的条件判 unverified；required 无法验证时整体最多 partial
# 设计：纯 None 契约整体 unverified；None+verified 混合契约整体 partial
async def test_executor_none_command_is_unverified(tmp_path: Path) -> None:
    result = await _executor(tmp_path).verify(_contract(_cond("c1")))
    [cr] = result.results
    assert cr.outcome is VerificationOutcome.UNVERIFIED
    assert "no check_command" in cr.message
    assert result.overall is VerificationOutcome.UNVERIFIED

    mixed = _contract(
        _cond("manual"),
        _cond("auto", [sys.executable, "-c", "raise SystemExit(0)"]),
    )
    assert (await _executor(tmp_path).verify(mixed)).overall is VerificationOutcome.PARTIAL


# 功能：验证条件按 priority 降序执行，落盘文件名对非法字符做净化
# 设计：低优先级条件放前面，断言结果顺序反转；条件 id 带路径分隔符仍落在 verification/ 内
async def test_executor_priority_order_and_safe_log_name(tmp_path: Path) -> None:
    ok = [sys.executable, "-c", "raise SystemExit(0)"]
    contract = _contract(
        _cond("low", ok, priority=0),
        _cond("high../x", ok, priority=10),
    )
    result = await _executor(tmp_path).verify(contract)
    assert [cr.condition_id for cr in result.results] == ["high../x", "low"]
    evidence = result.results[0].evidence
    assert evidence is not None
    log = Path(evidence.output_path)
    assert log.parent == tmp_path / "run" / "verification"
    assert log.exists()


# 功能：验证聚合纯函数的全部分支（failed/verified/partial/unverified 与 required/optional 组合）
# 设计：直接构造 ConditionResult 列表覆盖每条聚合规则，不启动任何子进程
def test_aggregate_outcomes_branches() -> None:
    v, f = VerificationOutcome.VERIFIED, VerificationOutcome.FAILED
    u, e = VerificationOutcome.UNVERIFIED, VerificationOutcome.ENV_BLOCKED
    req, opt = _cond("req"), _cond("opt", required=False)

    # 空契约 → unverified
    assert aggregate_outcomes([], []) is VerificationOutcome.UNVERIFIED
    # required 失败 → failed（即使其余全通过）
    assert (
        aggregate_outcomes([req, opt], [_result("req", f), _result("opt", v)])
        is VerificationOutcome.FAILED
    )
    # optional 失败不阻塞：全部 required 通过 → verified
    assert (
        aggregate_outcomes([req, opt], [_result("req", v), _result("opt", f)])
        is VerificationOutcome.VERIFIED
    )
    # 全部 required 通过 → verified
    assert aggregate_outcomes([req], [_result("req", v)]) is VerificationOutcome.VERIFIED
    # required unverified + 其他通过 → 最多 partial
    other = _cond("other")
    assert (
        aggregate_outcomes([req, other], [_result("req", u), _result("other", v)])
        is VerificationOutcome.PARTIAL
    )
    # required env_blocked：不算失败但不算通过 → partial
    assert (
        aggregate_outcomes([req, other], [_result("req", e), _result("other", v)])
        is VerificationOutcome.PARTIAL
    )
    # 无任何通过证据（全部 env_blocked/unverified）→ unverified
    assert (
        aggregate_outcomes([req, other], [_result("req", e), _result("other", u)])
        is VerificationOutcome.UNVERIFIED
    )


# 功能：验证 modification_status_summary 摘要规则（None 透传 / 空记录 clean / 有记录 modified:N）
# 设计：runner 门禁的纯函数拆分单测，避免依赖挂起的 test_runner 场景
def test_modification_status_summary() -> None:
    assert modification_status_summary(None) is None
    assert modification_status_summary([]) == "clean"
    assert modification_status_summary([{"path": "a"}, {"path": "b"}]) == "modified:2"
