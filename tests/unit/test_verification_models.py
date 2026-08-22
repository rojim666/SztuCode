from __future__ import annotations

import pytest
from pydantic import ValidationError

from sztu_code.core.verification import (
    CompletionCondition,
    CompletionContract,
    ConditionResult,
    ContractSource,
    Evidence,
    EvidenceKind,
    VerificationOutcome,
    VerificationResult,
)


# 功能：验证 CompletionCondition 可选字段的默认值符合契约（check_command=None、required=True、priority=0）
# 设计：只提供必填字段构造，逐一断言默认值，锁定向后兼容基线
def test_completion_condition_defaults() -> None:
    cond = CompletionCondition(
        id="c1", description="tests pass", source=ContractSource.USER
    )
    assert cond.check_command is None
    assert cond.required is True
    assert cond.priority == 0


# 功能：验证 Evidence 可选字段的默认值（command=""、exit_code=None、output_path=""、workspace_digests={}、stale=False）
# 设计：只提供必填字段构造，确认所有默认值，采集器未填的字段不应携带垃圾数据
def test_evidence_defaults() -> None:
    ev = Evidence(
        condition_id="c1",
        kind=EvidenceKind.COMMAND_EXIT_CODE,
        collected_at="2026-08-17T10:00:00Z",
    )
    assert ev.command == ""
    assert ev.exit_code is None
    assert ev.output_path == ""
    assert ev.workspace_digests == {}
    assert ev.stale is False


# 功能：验证 VerificationResult.results 默认空列表且 default_factory 不跨实例共享
# 设计：构造两个实例并向其一追加元素，另一实例不受影响，防御可变默认值陷阱
def test_verification_result_defaults_isolated() -> None:
    r1 = VerificationResult(
        run_id="r1", overall=VerificationOutcome.UNVERIFIED, verified_at="2026-08-17T10:00:00Z"
    )
    r2 = VerificationResult(
        run_id="r2", overall=VerificationOutcome.UNVERIFIED, verified_at="2026-08-17T10:00:00Z"
    )
    r1.results.append(
        ConditionResult(condition_id="c1", outcome=VerificationOutcome.VERIFIED)
    )
    assert r2.results == []


# 功能：验证 CompletionContract 的 JSON 序列化/反序列化 round-trip 无损
# 设计：构造含嵌套条件的契约，dump 后再 validate，断言对象相等，保证跨进程传输不丢字段
def test_completion_contract_json_round_trip() -> None:
    contract = CompletionContract(
        run_id="r1",
        conditions=[
            CompletionCondition(
                id="c1",
                description="unit tests pass",
                source=ContractSource.PROJECT_CONFIG,
                check_command=["uv", "run", "pytest", "-q"],
                priority=10,
            ),
        ],
        created_at="2026-08-17T10:00:00Z",
    )
    restored = CompletionContract.model_validate_json(contract.model_dump_json())
    assert restored == contract
    # StrEnum 序列化为纯字符串值
    assert restored.conditions[0].source == "project_config"


# 功能：验证 VerificationResult（含嵌套 Evidence）的 JSON round-trip 无损
# 设计：填满 Evidence 的所有字段后 round-trip，覆盖 workspace_digests 等嵌套结构
def test_verification_result_json_round_trip() -> None:
    result = VerificationResult(
        run_id="r1",
        results=[
            ConditionResult(
                condition_id="c1",
                outcome=VerificationOutcome.VERIFIED,
                evidence=Evidence(
                    condition_id="c1",
                    kind=EvidenceKind.TEST_OUTPUT,
                    command="uv run pytest -q",
                    exit_code=0,
                    output_path="runs/r1/verification/c1.log",
                    workspace_digests={"src/a.py": "a" * 64},
                    collected_at="2026-08-17T10:00:00Z",
                ),
                message="all tests passed",
            ),
        ],
        overall=VerificationOutcome.VERIFIED,
        verified_at="2026-08-17T10:00:01Z",
    )
    restored = VerificationResult.model_validate_json(result.model_dump_json())
    assert restored == result


# 功能：验证 extra=forbid 生效，未知字段在构造时被拒绝
# 设计：对每个模型注入一个多余字段并断言 ValidationError，防止协议漂移被静默吞掉
def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        CompletionCondition(
            id="c1", description="d", source=ContractSource.CI, bogus=1  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError):
        CompletionContract(
            run_id="r1", conditions=[], created_at="t", bogus=1  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError):
        Evidence(
            condition_id="c1",
            kind=EvidenceKind.FILE_STATE,
            collected_at="t",
            bogus=1,  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError):
        ConditionResult(
            condition_id="c1", outcome=VerificationOutcome.FAILED, bogus=1  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError):
        VerificationResult(
            run_id="r1",
            overall=VerificationOutcome.FAILED,
            verified_at="t",
            bogus=1,  # type: ignore[call-arg]
        )


# 功能：验证三个 StrEnum 的成员值与 wire 协议约定的字符串一致
# 设计：逐一比对枚举值字符串，任何改名都会破坏已落盘的 JSON，必须显式失败
def test_str_enum_values() -> None:
    assert ContractSource.USER == "user"
    assert ContractSource.PROJECT_CONFIG == "project_config"
    assert ContractSource.CI == "ci"
    assert ContractSource.INFERRED == "inferred"
    assert ContractSource.AGENT_SUGGESTED == "agent_suggested"

    assert EvidenceKind.COMMAND_EXIT_CODE == "command_exit_code"
    assert EvidenceKind.TEST_OUTPUT == "test_output"
    assert EvidenceKind.FILE_STATE == "file_state"
    assert EvidenceKind.MODEL_ASSERTION == "model_assertion"

    assert VerificationOutcome.VERIFIED == "verified"
    assert VerificationOutcome.PARTIAL == "partial"
    assert VerificationOutcome.UNVERIFIED == "unverified"
    assert VerificationOutcome.FAILED == "failed"
    assert VerificationOutcome.ENV_BLOCKED == "env_blocked"
    assert VerificationOutcome.STALE == "stale"
