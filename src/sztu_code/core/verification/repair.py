from __future__ import annotations

from pathlib import Path
from typing import Any

from sztu_code.core.verification.executor import aggregate_outcomes
from sztu_code.core.verification.models import (
    CompletionContract,
    VerificationOutcome,
    VerificationResult,
)

# 失败签名：排序后的 (condition_id, outcome, exit_code) 元组列表。
# 连续两轮验证签名相同说明修复未产生任何效果，应当熔断而非继续烧预算。
FailureSignature = tuple[tuple[str, str, int | None], ...]

# 修复提示中每条失败日志保留的尾部行数与字符上限（防止大日志撑爆上下文）
_LOG_TAIL_LINES = 20
_LOG_TAIL_MAX_CHARS = 2_000


# 从一次验证结果提取失败签名（纯函数，便于单测）。
# condition_id 在契约内唯一，仅按 (id, outcome) 排序即可稳定，
# 同时避免 exit_code 的 None 与 int 直接比较。
def failure_signature(result: VerificationResult) -> FailureSignature:
    entries = [
        (
            cond_result.condition_id,
            cond_result.outcome.value,
            cond_result.evidence.exit_code if cond_result.evidence is not None else None,
        )
        for cond_result in result.results
    ]
    return tuple(sorted(entries, key=lambda entry: (entry[0], entry[1])))


# 从 changes.json 的变更记录提取 {path: after_digest} 作为当前工作区证据摘要。
# 复用 core/changes.py 的 _digest（sha256）结果，不重新实现 hash。
def digests_from_change_records(records: list[dict[str, Any]] | None) -> dict[str, str]:
    if not records:
        return {}
    return {
        str(record["path"]): str(record["after_digest"])
        for record in records
        if record.get("after_digest")
    }


# 把与当前工作区摘要不一致的证据标记 stale=True；stale 证据不得计入通过，
# 因此依赖 stale 证据的 verified 结论降级为 stale，并重算 overall。
# 返回是否有证据被标记（供调用方记日志）。
def mark_stale_evidence(
    result: VerificationResult,
    contract: CompletionContract,
    current_digests: dict[str, str],
) -> bool:
    changed = False
    for cond_result in result.results:
        evidence = cond_result.evidence
        if evidence is None or evidence.stale:
            continue
        if evidence.workspace_digests != current_digests:
            evidence.stale = True
            changed = True
            if cond_result.outcome is VerificationOutcome.VERIFIED:
                cond_result.outcome = VerificationOutcome.STALE
    if changed:
        result.overall = aggregate_outcomes(contract.conditions, result.results)
    return changed


# 读取验证日志尾部若干行；日志缺失/不可读时返回空串（提示中省略该段）
def _log_tail(output_path: str, *, lines: int = _LOG_TAIL_LINES) -> str:
    if not output_path:
        return ""
    try:
        text = Path(output_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    tail = "\n".join(text.splitlines()[-lines:])
    return tail[-_LOG_TAIL_MAX_CHARS:]


# 构造修复提示：逐条列出失败条件的 id/描述/退出码/日志尾部，
# 日志来自 run_path/verification/<id>.log（Evidence.output_path）。
def build_repair_prompt(result: VerificationResult, contract: CompletionContract) -> str:
    descriptions = {cond.id: cond.description for cond in contract.conditions}
    sections = [
        "[Verification failed] Independent verification of the completion contract "
        "FAILED — the task is NOT complete yet.",
        "Fix the failed conditions below, then end your turn; "
        "verification will run again automatically.",
    ]
    for cond_result in result.results:
        if cond_result.outcome is not VerificationOutcome.FAILED:
            continue
        evidence = cond_result.evidence
        exit_code = evidence.exit_code if evidence is not None else None
        lines = [
            f"- condition: {cond_result.condition_id}",
            f"  description: {descriptions.get(cond_result.condition_id, '')}",
            f"  exit_code: {exit_code}",
        ]
        if cond_result.message:
            lines.append(f"  message: {cond_result.message}")
        tail = _log_tail(evidence.output_path) if evidence is not None else ""
        if tail:
            lines.extend(["  log tail:", "```", tail, "```"])
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


class RepairCircuitBreaker:
    """修复闭环三重熔断（issue #94 分支 4）。

    任一触发即停止修复，最终以最后一次真实验证结果落盘，不得伪装 verified：
    a. 修复轮数达到 max_repair_attempts；
    b. 相同失败签名：连续两次验证签名相同，说明修复无效；
    c. A/B 震荡：签名回到上上轮的值记一次翻转（A→B→A 计 1 次），累计 3 次即停。
       首次出现新签名不算翻转——那可能是修复取得了进展。
    """

    _OSCILLATION_LIMIT = 3

    def __init__(self, max_attempts: int) -> None:
        self._max_attempts = max_attempts
        self._attempts = 0
        self._signatures: list[FailureSignature] = []
        self._flips = 0

    # 记录一次验证的失败签名（含首轮验证），维护震荡翻转计数
    def record(self, signature: FailureSignature) -> None:
        if (
            len(self._signatures) >= 2
            and signature != self._signatures[-1]
            and signature == self._signatures[-2]
        ):
            self._flips += 1
        self._signatures.append(signature)

    # 记录发起了一轮修复尝试
    def note_attempt(self) -> None:
        self._attempts += 1

    # 返回熔断原因；None 表示允许继续修复
    def stop_reason(self) -> str | None:
        if self._attempts >= self._max_attempts:
            return f"max_repair_attempts reached ({self._max_attempts})"
        if len(self._signatures) >= 2 and self._signatures[-1] == self._signatures[-2]:
            return "identical failure signature across consecutive verifications"
        if self._flips >= self._OSCILLATION_LIMIT:
            return f"failure signature oscillation (flips={self._flips})"
        return None
