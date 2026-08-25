from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


# 完成条件的来源 — 决定条件的可信度排序（用户显式声明 > 项目配置 > CI > 推断 > Agent 自述）
class ContractSource(StrEnum):
    USER = "user"                          # 用户在目标中显式声明
    PROJECT_CONFIG = "project_config"      # 项目配置文件（Makefile/pyproject 等）
    CI = "ci"                              # CI 流水线定义
    INFERRED = "inferred"                  # 从上下文推断
    AGENT_SUGGESTED = "agent_suggested"    # Agent 自行建议


# 单条完成条件：可验证的最小验收单元
class CompletionCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    source: ContractSource
    # 可执行的检查命令（argv 形式）；None 表示无法自动检查
    check_command: list[str] | None = None
    required: bool = True
    # 越大越先检查
    priority: int = 0


# 一次 run 的完成契约：run 开始前固化的验收条件集合
class CompletionContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    conditions: list[CompletionCondition]
    created_at: str  # ISO 8601


class EvidenceKind(StrEnum):
    """证据种类。

    model_assertion 永不作为通过依据，仅记录：模型的自我断言不构成独立验证证据。
    """

    COMMAND_EXIT_CODE = "command_exit_code"  # 命令退出码
    TEST_OUTPUT = "test_output"              # 测试输出
    FILE_STATE = "file_state"                # 文件状态（存在性/摘要）
    MODEL_ASSERTION = "model_assertion"      # 模型自述（仅记录，不作通过依据）


# 单条验证证据：记录检查执行的原始事实
class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condition_id: str
    kind: EvidenceKind
    command: str = ""
    exit_code: int | None = None
    # 原始输出落盘路径，不内联
    output_path: str = ""
    # 采集时相关文件 sha256，与 core/changes.py 的 _digest 格式一致
    workspace_digests: dict[str, str] = Field(default_factory=dict)
    collected_at: str  # ISO 8601
    # 证据采集后工作区又发生变化，证据已过期
    stale: bool = False


# 验证结论枚举 — 条件级与 run 级共用
class VerificationOutcome(StrEnum):
    VERIFIED = "verified"          # 有独立证据证明通过
    PARTIAL = "partial"            # 部分条件通过
    UNVERIFIED = "unverified"      # 未执行验证或无可用证据
    FAILED = "failed"              # 有证据证明未通过
    ENV_BLOCKED = "env_blocked"    # 环境原因无法执行检查
    STALE = "stale"                # 证据已过期


# 单条完成条件的验证结果
class ConditionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condition_id: str
    outcome: VerificationOutcome
    evidence: Evidence | None = None
    message: str = ""


# 一次 run 的整体验证结果
class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    results: list[ConditionResult] = Field(default_factory=list)
    overall: VerificationOutcome
    verified_at: str  # ISO 8601
