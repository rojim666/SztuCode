from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from sztu_code.core.config import SztuConfig
from sztu_code.core.llm.types import LlmResponse
from sztu_code.core.loop import AgentLoop
from sztu_code.core.runner import AgentRunner
from sztu_code.core.verification import (
    CompletionCondition,
    CompletionContract,
    ConditionResult,
    ContractSource,
    Evidence,
    EvidenceKind,
    RepairCircuitBreaker,
    VerificationOutcome,
    VerificationResult,
    build_repair_prompt,
    failure_signature,
    mark_stale_evidence,
)

# ---- 构造辅助：直接拼装模型对象，不启动任何子进程 ----


def _cond(cid: str, *, required: bool = True) -> CompletionCondition:
    return CompletionCondition(
        id=cid,
        description=f"desc-{cid}",
        source=ContractSource.USER,
        check_command=["echo", cid],
        required=required,
    )


def _contract(*conds: CompletionCondition) -> CompletionContract:
    return CompletionContract(
        run_id="run-1", conditions=list(conds), created_at="2026-08-19T00:00:00Z"
    )


def _evidence(
    cid: str,
    exit_code: int | None,
    *,
    digests: dict[str, str] | None = None,
    output_path: str = "",
) -> Evidence:
    return Evidence(
        condition_id=cid,
        kind=EvidenceKind.COMMAND_EXIT_CODE,
        command=f"check {cid}",
        exit_code=exit_code,
        output_path=output_path,
        workspace_digests=digests or {},
        collected_at="2026-08-19T00:00:00Z",
    )


def _cond_result(
    cid: str,
    outcome: VerificationOutcome,
    *,
    exit_code: int | None = None,
    evidence: Evidence | None = None,
    message: str = "",
) -> ConditionResult:
    if evidence is None and exit_code is not None:
        evidence = _evidence(cid, exit_code)
    return ConditionResult(
        condition_id=cid, outcome=outcome, evidence=evidence, message=message
    )


def _vresult(
    overall: VerificationOutcome, *results: ConditionResult
) -> VerificationResult:
    return VerificationResult(
        run_id="run-1",
        results=list(results),
        overall=overall,
        verified_at="2026-08-19T00:00:00Z",
    )


def _failed(cid: str = "tests", exit_code: int = 1) -> VerificationResult:
    return _vresult(
        VerificationOutcome.FAILED,
        _cond_result(cid, VerificationOutcome.FAILED, exit_code=exit_code),
    )


def _verified(cid: str = "tests") -> VerificationResult:
    return _vresult(
        VerificationOutcome.VERIFIED,
        _cond_result(cid, VerificationOutcome.VERIFIED, exit_code=0),
    )


# 每次 chat 直接 end_turn 的 provider：一次 loop.run == 一次 chat 调用，
# 用调用次数断言"初始回合 + 修复回合"的轮数
class _EndTurnProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.user_prompts: list[str] = []

    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: object,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> LlmResponse:
        self.calls += 1
        last = messages[-1]
        if isinstance(last.get("content"), str):
            self.user_prompts.append(str(last["content"]))
        return LlmResponse(stop_reason="end_turn", text=f"round {self.calls}")


# 每次 chat 往工作区写入不同内容再 end_turn，模拟修复回合真实改动文件
class _WritingProvider(_EndTurnProvider):
    def __init__(self, target: Path) -> None:
        super().__init__()
        self._target = target

    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: object,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> LlmResponse:
        response = await super().chat(
            messages, tool_schemas, bus, run_id, step=step, system=system
        )
        self._target.write_text(f"v{self.calls}", encoding="utf-8")
        return response


# 生成按脚本顺序吐出验证结果的 fake executor 类（替换 runner.VerificationExecutor），
# 同时记录每次 verify 收到的 workspace_digests，不起任何真子进程
def _scripted_executor(
    script: list[VerificationResult],
    digest_calls: list[dict[str, str]] | None = None,
) -> type:
    class _Fake:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def verify(
            self,
            contract: CompletionContract,
            *,
            workspace_digests: dict[str, str] | None = None,
        ) -> VerificationResult:
            if digest_calls is not None:
                digest_calls.append(dict(workspace_digests or {}))
            return script.pop(0)

    return _Fake


# 组装并执行一次带脚本化验证的 run；返回 (RunOutcome, provider, 收集到的事件)
async def _run_with_script(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    script: list[VerificationResult],
    *,
    max_attempts: int = 2,
    require: bool = True,
    provider: _EndTurnProvider | None = None,
    workspace_root: Path | None = None,
    digest_calls: list[dict[str, str]] | None = None,
) -> tuple[Any, _EndTurnProvider, list[BaseModel]]:
    config = SztuConfig()
    config.agent.require_verification = require
    config.agent.max_repair_attempts = max_attempts
    # main 既有破坏：AgentLoop.__init__ 未初始化 _steering_queue，_drain_steering 直接 AttributeError。
    # 与本分支无关且禁改 loop.py，这里补一个类属性绕过（修复后实例属性会自然遮盖它）
    monkeypatch.setattr(AgentLoop, "_steering_queue", None, raising=False)
    contract = _contract(_cond("tests"))
    monkeypatch.setattr(
        "sztu_code.core.runner.build_completion_contract",
        lambda run_id, profile, root: contract,
    )
    monkeypatch.setattr(
        "sztu_code.core.runner.VerificationExecutor",
        _scripted_executor(script, digest_calls),
    )
    provider = provider or _EndTurnProvider()
    events: list[BaseModel] = []

    async def _collect(event: BaseModel) -> None:
        events.append(event)

    runner = AgentRunner(
        config,
        provider=provider,
        runs_dir=tmp_path / "runs",
        extra_handlers=[_collect],
    )
    outcome = await runner.run_and_capture(
        "goal",
        system_prompt_override="You are a test agent.",
        workspace_root=workspace_root,
    )
    return outcome, provider, events


# 功能：验证失败签名按 (condition_id, outcome) 排序稳定，且透传证据退出码/无证据为 None
# 设计：乱序构造两个条件（一个带退出码证据、一个无证据），断言排序结果与元组内容
def test_failure_signature_sorted_and_carries_exit_code() -> None:
    result = _vresult(
        VerificationOutcome.FAILED,
        _cond_result("z-late", VerificationOutcome.FAILED, exit_code=7),
        _cond_result("a-early", VerificationOutcome.UNVERIFIED),
    )
    assert failure_signature(result) == (
        ("a-early", "unverified", None),
        ("z-late", "failed", 7),
    )


# 功能：验证熔断器 a——修复轮数达到 max_repair_attempts 即停
# 设计：max_attempts=2，每轮签名互不相同（排除签名熔断干扰），第 3 次询问返回熔断原因
def test_circuit_breaker_stops_at_max_attempts() -> None:
    breaker = RepairCircuitBreaker(2)
    breaker.record(failure_signature(_failed(exit_code=1)))
    assert breaker.stop_reason() is None
    breaker.note_attempt()
    breaker.record(failure_signature(_failed(exit_code=2)))
    assert breaker.stop_reason() is None
    breaker.note_attempt()
    breaker.record(failure_signature(_failed(exit_code=3)))
    reason = breaker.stop_reason()
    assert reason is not None and "max_repair_attempts" in reason


# 功能：验证熔断器 b——连续两次验证签名相同（修复无效）即停，优先于轮数上限
# 设计：max_attempts 给足 5，两次记录相同签名后 stop_reason 返回相同签名原因
def test_circuit_breaker_stops_on_identical_signature() -> None:
    breaker = RepairCircuitBreaker(5)
    breaker.record(failure_signature(_failed(exit_code=1)))
    breaker.note_attempt()
    breaker.record(failure_signature(_failed(exit_code=1)))
    reason = breaker.stop_reason()
    assert reason is not None and "identical failure signature" in reason


# 功能：验证熔断器 c——签名 A/B 来回震荡累计 3 次翻转即停
# 设计：翻转定义为签名回到上上轮的值（A→B→A 计 1 次）；序列 A,B,A,B,A 产生 3 次翻转，
# 期间每步 stop_reason 保持 None，最后一步返回震荡原因
def test_circuit_breaker_stops_on_oscillation() -> None:
    breaker = RepairCircuitBreaker(10)
    sig_a = failure_signature(_failed(exit_code=1))
    sig_b = failure_signature(_failed(exit_code=2))
    for signature in (sig_a, sig_b, sig_a, sig_b):
        breaker.record(signature)
        assert breaker.stop_reason() is None
        breaker.note_attempt()
    breaker.record(sig_a)  # 第 3 次翻转
    reason = breaker.stop_reason()
    assert reason is not None and "oscillation" in reason


# 功能：验证 stale 标记——证据摘要与当前工作区摘要不一致时标 stale，verified 结论降级不计入通过
# 设计：verified 证据摘要为旧值 → stale=True、条件降级 stale、overall 由 verified 重算为 unverified；
# 摘要一致的结果不被误标
def test_mark_stale_evidence_downgrades_verified() -> None:
    contract = _contract(_cond("tests"))
    stale_result = _vresult(
        VerificationOutcome.VERIFIED,
        _cond_result(
            "tests",
            VerificationOutcome.VERIFIED,
            evidence=_evidence("tests", 0, digests={"a.py": "old-digest"}),
        ),
    )
    assert mark_stale_evidence(stale_result, contract, {"a.py": "new-digest"}) is True
    [cond_result] = stale_result.results
    assert cond_result.evidence is not None and cond_result.evidence.stale is True
    assert cond_result.outcome is VerificationOutcome.STALE
    assert stale_result.overall is VerificationOutcome.UNVERIFIED

    fresh_result = _vresult(
        VerificationOutcome.VERIFIED,
        _cond_result(
            "tests",
            VerificationOutcome.VERIFIED,
            evidence=_evidence("tests", 0, digests={"a.py": "same"}),
        ),
    )
    assert mark_stale_evidence(fresh_result, contract, {"a.py": "same"}) is False
    assert fresh_result.overall is VerificationOutcome.VERIFIED


# 功能：验证修复提示包含失败条件的 id/描述/退出码/日志尾部，且不含已通过条件
# 设计：落盘一个多行日志文件，断言提示含末尾行而不含超出尾部窗口的首行
def test_build_repair_prompt_contents(tmp_path: Path) -> None:
    log_path = tmp_path / "verification" / "tests.log"
    log_path.parent.mkdir(parents=True)
    log_lines = [f"line-{i}" for i in range(40)]
    log_path.write_text("\n".join(log_lines), encoding="utf-8")
    contract = _contract(_cond("tests"), _cond("lint"))
    result = _vresult(
        VerificationOutcome.FAILED,
        _cond_result(
            "tests",
            VerificationOutcome.FAILED,
            evidence=_evidence("tests", 7, output_path=str(log_path)),
            message="check command exited with code 7",
        ),
        _cond_result("lint", VerificationOutcome.VERIFIED, exit_code=0),
    )
    prompt = build_repair_prompt(result, contract)
    assert "condition: tests" in prompt
    assert "desc-tests" in prompt
    assert "exit_code: 7" in prompt
    assert "line-39" in prompt  # 日志尾部保留
    assert "line-0" not in prompt  # 超出 20 行尾部窗口被裁掉
    assert "condition: lint" not in prompt  # 已通过条件不进提示


# 功能：验证修复成功路径——首轮验证失败触发一轮修复，重验通过后落盘 verified
# 设计：脚本 [failed, verified]；断言 provider 跑了 2 个回合、修复提示被注入、
# RunOutcome 状态仍为 success 且 verification_status=verified，事件只发一对
async def test_repair_loop_success_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outcome, provider, events = await _run_with_script(
        tmp_path, monkeypatch, [_failed(), _verified()]
    )
    assert outcome.status == "success"
    assert outcome.verification_status == "verified"
    assert provider.calls == 2
    assert any("[Verification failed]" in p for p in provider.user_prompts)
    finished = [e for e in events if getattr(e, "type", "") == "verification.finished"]
    assert [getattr(e, "outcome") for e in finished] == ["verified"]


# 功能：验证 max_repair_attempts 熔断——轮数用尽后停止修复，落盘最后一次真实结果
# 设计：max_attempts=1，脚本给 2 个签名不同的 failed（排除签名熔断）；
# 断言只发生 1 轮修复（共 2 个回合）、脚本恰好耗尽、结果保持 failed 不伪装
async def test_repair_loop_max_attempts_breaker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = [_failed(exit_code=1), _failed(exit_code=2)]
    outcome, provider, events = await _run_with_script(
        tmp_path, monkeypatch, script, max_attempts=1
    )
    assert outcome.verification_status == "failed"
    assert provider.calls == 2  # 初始回合 + 1 轮修复
    assert script == []  # 两次验证全部执行
    finished = [e for e in events if getattr(e, "type", "") == "verification.finished"]
    assert [getattr(e, "outcome") for e in finished] == ["failed"]


# 功能：验证相同失败签名熔断——修复一轮后签名不变即停，不再烧掉剩余轮数
# 设计：max_attempts 给足 5，脚本两个 failed 退出码相同（签名一致）；
# 断言仅 1 轮修复后停止且结果为 failed
async def test_repair_loop_identical_signature_breaker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = [_failed(exit_code=1), _failed(exit_code=1)]
    outcome, provider, _ = await _run_with_script(
        tmp_path, monkeypatch, script, max_attempts=5
    )
    assert outcome.verification_status == "failed"
    assert provider.calls == 2  # 第 2 次验证签名相同 → 熔断，不再发起第 2 轮修复
    assert script == []


# 功能：验证 A/B 震荡熔断——签名在两个值间来回翻转累计 3 次即停
# 设计：max_attempts=10，脚本按 A,B,A,B,A 给 5 个 failed；第 5 次验证产生第 3 次翻转，
# 断言恰好 4 轮修复（共 5 个回合）后停止
async def test_repair_loop_oscillation_breaker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = [
        _failed(exit_code=1),
        _failed(exit_code=2),
        _failed(exit_code=1),
        _failed(exit_code=2),
        _failed(exit_code=1),
    ]
    outcome, provider, _ = await _run_with_script(
        tmp_path, monkeypatch, script, max_attempts=10
    )
    assert outcome.verification_status == "failed"
    assert provider.calls == 5  # 初始回合 + 4 轮修复
    assert script == []


# 功能：验证 require_verification=False 时零行为变化——不验证、不修复、不发验证事件
# 设计：脚本留一个 failed 哨兵；断言 provider 只跑 1 回合、脚本未被消费、
# verification_status 为 None 且事件流无 verification.*
async def test_repair_loop_disabled_is_zero_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = [_failed()]
    outcome, provider, events = await _run_with_script(
        tmp_path, monkeypatch, script, require=False
    )
    assert outcome.status == "success"
    assert outcome.verification_status is None
    assert provider.calls == 1
    assert script == [_failed()]  # 哨兵未被消费
    assert not [e for e in events if str(getattr(e, "type", "")).startswith("verification")]


# 功能：验证 Evidence 摘要接通真实数据源——每轮验证收到 change tracker 的 after_digest，
# 修复回合改动文件后摘要刷新，旧一轮证据被标 stale
# 设计：provider 每回合往工作区写不同内容；断言两次 verify 收到的摘要分别是 v1/v2 的
# sha256（复用 changes.py 的 digest 语义）且互不相同，首轮 failed 证据在重验前被标 stale
async def test_repair_loop_digest_wiring_and_stale_marking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    target = workspace / "f.txt"
    target.write_text("v0", encoding="utf-8")
    first = _vresult(
        VerificationOutcome.FAILED,
        _cond_result(
            "tests",
            VerificationOutcome.FAILED,
            evidence=_evidence("tests", 1, digests={"f.txt": "captured-at-round-1"}),
        ),
    )
    digest_calls: list[dict[str, str]] = []
    outcome, provider, _ = await _run_with_script(
        tmp_path,
        monkeypatch,
        [first, _verified()],
        provider=_WritingProvider(target),
        workspace_root=workspace,
        digest_calls=digest_calls,
    )
    assert outcome.verification_status == "verified"
    assert provider.calls == 2
    assert digest_calls[0]["f.txt"] == hashlib.sha256(b"v1").hexdigest()
    assert digest_calls[1]["f.txt"] == hashlib.sha256(b"v2").hexdigest()
    assert digest_calls[0] != digest_calls[1]
    # 重验前旧证据与新摘要不一致 → stale，且不再计入通过
    [first_cond] = first.results
    assert first_cond.evidence is not None and first_cond.evidence.stale is True
    assert first_cond.outcome is VerificationOutcome.FAILED  # failed 保持原判，不被改写
