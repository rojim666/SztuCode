from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path

from sztu_code.core.verification.models import (
    CompletionCondition,
    CompletionContract,
    ConditionResult,
    Evidence,
    EvidenceKind,
    VerificationOutcome,
    VerificationResult,
)

# 落盘文件名只保留安全字符，防止 condition.id 携带路径分隔符逃逸出 verification/ 目录
_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_filename(condition_id: str) -> str:
    return _SAFE_ID_RE.sub("_", condition_id) or "condition"


# 将各条件结论聚合为 run 级结论（纯函数，便于单测）：
# - 任一 required 条件 failed → failed
# - 无任何条件产生通过证据（全部 unverified/env_blocked，或契约为空）→ unverified
# - 全部 required 条件 verified → verified（可选条件不阻塞整体结论）
# - 其余（required 中存在 unverified/env_blocked）→ 最多 partial
# env_blocked 不算失败也不算通过：环境受限不应把 run 判死，但也不构成完成证据
def aggregate_outcomes(
    conditions: list[CompletionCondition],
    results: list[ConditionResult],
) -> VerificationOutcome:
    if not results:
        return VerificationOutcome.UNVERIFIED
    required_ids = {cond.id for cond in conditions if cond.required}
    if any(
        r.outcome is VerificationOutcome.FAILED and r.condition_id in required_ids
        for r in results
    ):
        return VerificationOutcome.FAILED
    if not any(r.outcome is VerificationOutcome.VERIFIED for r in results):
        return VerificationOutcome.UNVERIFIED
    required_results = [r for r in results if r.condition_id in required_ids]
    if all(r.outcome is VerificationOutcome.VERIFIED for r in required_results):
        return VerificationOutcome.VERIFIED
    return VerificationOutcome.PARTIAL


class VerificationExecutor:
    """完成契约验证执行器（issue #94 分支 2）。

    仿 evaluation/harness.py 的子进程验证模式：直接以 argv 形式执行
    CompletionCondition.check_command，绕过 ToolRegistry 与权限系统——
    验证是 Harness 的独立判定，不受 Agent 工具链干预。stdout/stderr 落盘
    到 run_path/verification/<condition_id>.log，不内联大输出。
    """

    def __init__(
        self,
        workspace_root: Path,
        run_path: Path,
        *,
        check_timeout_s: int = 60,
    ) -> None:
        self._workspace_root = workspace_root
        self._output_dir = run_path / "verification"
        self._check_timeout_s = check_timeout_s

    # 按 priority 降序逐条检查并聚合为 VerificationResult
    async def verify(
        self,
        contract: CompletionContract,
        *,
        workspace_digests: dict[str, str] | None = None,
    ) -> VerificationResult:
        digests = workspace_digests or {}
        ordered = sorted(contract.conditions, key=lambda cond: -cond.priority)
        results = [await self._check_condition(cond, digests) for cond in ordered]
        return VerificationResult(
            run_id=contract.run_id,
            results=results,
            overall=aggregate_outcomes(contract.conditions, results),
            verified_at=_now(),
        )

    # 执行单条完成条件的检查命令，每条独立超时，超时 kill 进程并判 failed
    async def _check_condition(
        self,
        condition: CompletionCondition,
        digests: dict[str, str],
    ) -> ConditionResult:
        # 无检查命令：无法机器验证；required 条件会在聚合时把整体压到最多 partial
        if not condition.check_command:
            return ConditionResult(
                condition_id=condition.id,
                outcome=VerificationOutcome.UNVERIFIED,
                message="no check_command; cannot verify automatically",
            )
        try:
            proc = await asyncio.create_subprocess_exec(
                *condition.check_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(self._workspace_root),
            )
        except OSError as exc:
            # 命令无法启动（可执行文件缺失/权限不足等）：环境受限，不算失败也不算通过
            return ConditionResult(
                condition_id=condition.id,
                outcome=VerificationOutcome.ENV_BLOCKED,
                message=f"cannot start check command: {exc}",
            )
        timed_out = False
        try:
            stdout_bytes, _ = await asyncio.wait_for(
                proc.communicate(), timeout=self._check_timeout_s
            )
        except TimeoutError:
            timed_out = True
            proc.kill()
            stdout_bytes, _ = await proc.communicate()
        evidence = Evidence(
            condition_id=condition.id,
            kind=EvidenceKind.COMMAND_EXIT_CODE,
            command=" ".join(condition.check_command),
            exit_code=None if timed_out else proc.returncode,
            output_path=self._write_output(condition.id, stdout_bytes),
            workspace_digests=digests,
            collected_at=_now(),
        )
        if timed_out:
            return ConditionResult(
                condition_id=condition.id,
                outcome=VerificationOutcome.FAILED,
                evidence=evidence,
                message=f"check timed out after {self._check_timeout_s}s",
            )
        if proc.returncode == 0:
            return ConditionResult(
                condition_id=condition.id,
                outcome=VerificationOutcome.VERIFIED,
                evidence=evidence,
            )
        return ConditionResult(
            condition_id=condition.id,
            outcome=VerificationOutcome.FAILED,
            evidence=evidence,
            message=f"check command exited with code {proc.returncode}",
        )

    # 将命令输出落盘并返回路径字符串；写入失败时返回空串（证据仍保留退出码）
    def _write_output(self, condition_id: str, data: bytes) -> str:
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            path = self._output_dir / f"{_safe_filename(condition_id)}.log"
            path.write_bytes(data)
        except OSError:
            return ""
        return str(path)
