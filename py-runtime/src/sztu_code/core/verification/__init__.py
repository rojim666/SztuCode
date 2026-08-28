# 完成契约与独立验证（issue #94）：数据模型 + 验证执行器 + 检查发现 + 修复闭环
from sztu_code.core.verification.discovery import (
    build_completion_contract,
    select_relevant_checks,
)
from sztu_code.core.verification.executor import (
    VerificationExecutor,
    aggregate_outcomes,
    modification_status_summary,
)
from sztu_code.core.verification.models import (
    CompletionCondition,
    CompletionContract,
    ConditionResult,
    ContractSource,
    Evidence,
    EvidenceKind,
    VerificationOutcome,
    VerificationResult,
)
from sztu_code.core.verification.repair import (
    FailureSignature,
    RepairCircuitBreaker,
    build_repair_prompt,
    digests_from_change_records,
    failure_signature,
    mark_stale_evidence,
)

__all__ = [
    "CompletionCondition",
    "CompletionContract",
    "ConditionResult",
    "ContractSource",
    "Evidence",
    "EvidenceKind",
    "FailureSignature",
    "RepairCircuitBreaker",
    "VerificationExecutor",
    "VerificationOutcome",
    "VerificationResult",
    "aggregate_outcomes",
    "modification_status_summary",
    "build_completion_contract",
    "build_repair_prompt",
    "digests_from_change_records",
    "failure_signature",
    "mark_stale_evidence",
    "select_relevant_checks",
]
