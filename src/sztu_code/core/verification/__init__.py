# 完成契约与独立验证：数据模型（issue #94 第一阶段）+ 验证执行器（第二阶段）
from sztu_code.core.verification.executor import VerificationExecutor, aggregate_outcomes
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

__all__ = [
    "CompletionCondition",
    "CompletionContract",
    "ConditionResult",
    "ContractSource",
    "Evidence",
    "EvidenceKind",
    "VerificationExecutor",
    "VerificationOutcome",
    "VerificationResult",
    "aggregate_outcomes",
]
