from __future__ import annotations

import asyncio
import json
import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from sztu_code.core.transport.socket_client import IpcError, SocketClient
from sztu_code.evaluation.models import EvaluationTask, FailureReason, InternalTask
from sztu_code.evaluation.tasks import public_task_payload
from sztu_code.evaluation.workspace import apply_reference_changes, git_patch

_MAX_CAPTURE_CHARS = 8_000


@dataclass(slots=True)
class RunnerOutcome:
    failure_reason: FailureReason | None = None
    error_message: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    tool_calls: int = 0
    steps: int = 0
    patch: str = ""
    output: str = ""


class EvaluationRunner(Protocol):
    name: str

    # 在隔离工作区中执行单个任务并返回结构化过程指标
    def run(
        self,
        task: EvaluationTask,
        workspace: Path,
        artifacts_dir: Path,
        timeout_seconds: float,
    ) -> RunnerOutcome: ...


class ReferenceRunner:
    name = "reference"

    # 应用内部任务参考修改，用于离线验证 fixture、评分器和报告链路
    def run(
        self,
        task: EvaluationTask,
        workspace: Path,
        artifacts_dir: Path,
        timeout_seconds: float,
    ) -> RunnerOutcome:
        del artifacts_dir, timeout_seconds
        if not isinstance(task, InternalTask):
            return RunnerOutcome(
                failure_reason=FailureReason.UNSUPPORTED_TASK,
                error_message="reference runner only supports internal tasks",
            )
        apply_reference_changes(task, workspace)
        return RunnerOutcome(tool_calls=len(task.reference_changes), steps=1)


class CommandRunner:
    name = "command"

    # 保存外部 Agent 命令，执行时始终使用 argv 而不经过 Shell
    def __init__(self, command: Sequence[str]) -> None:
        if not command:
            raise ValueError("command runner requires a command")
        self._command = list(command)

    # 读取外部 Agent 可选写出的过程指标文件并校验非负整数
    def _load_metrics(self, path: Path) -> dict[str, int]:
        if not path.exists():
            return {}
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("metrics payload must be an object")
        allowed = {
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
            "tool_calls",
            "steps",
        }
        metrics: dict[str, int] = {}
        for key, value in raw.items():
            if key not in allowed:
                continue
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"metric {key} must be a non-negative integer")
            metrics[key] = value
        return metrics

    # 通过环境变量向外部 Agent 传递任务、工作区和指标输出位置
    def run(
        self,
        task: EvaluationTask,
        workspace: Path,
        artifacts_dir: Path,
        timeout_seconds: float,
    ) -> RunnerOutcome:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        task_path = artifacts_dir / "task.json"
        metrics_path = artifacts_dir / "metrics.json"
        task_path.write_text(
            json.dumps(public_task_payload(task), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        environment = os.environ.copy()
        environment.update(
            {
                "SZTU_EVAL_TASK_FILE": str(task_path.resolve()),
                "SZTU_EVAL_WORKSPACE": str(workspace.resolve()),
                "SZTU_EVAL_METRICS_FILE": str(metrics_path.resolve()),
            }
        )
        try:
            completed = subprocess.run(
                self._command,
                cwd=workspace,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return RunnerOutcome(
                failure_reason=FailureReason.TIMEOUT,
                error_message=f"runner timed out after {timeout_seconds:g}s",
            )

        combined_output = (completed.stdout + completed.stderr)[-_MAX_CAPTURE_CHARS:]
        try:
            metrics = self._load_metrics(metrics_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return RunnerOutcome(
                failure_reason=FailureReason.INVALID_METRICS,
                error_message=str(exc),
                output=combined_output,
            )
        failure_reason = None
        error_message = ""
        if completed.returncode != 0:
            failure_reason = FailureReason.RUNNER_FAILED
            error_message = f"runner exited with code {completed.returncode}"
        return RunnerOutcome(
            failure_reason=failure_reason,
            error_message=error_message,
            input_tokens=metrics.get("input_tokens", 0),
            output_tokens=metrics.get("output_tokens", 0),
            cache_read_input_tokens=metrics.get("cache_read_input_tokens", 0),
            cache_creation_input_tokens=metrics.get("cache_creation_input_tokens", 0),
            tool_calls=metrics.get("tool_calls", 0),
            steps=metrics.get("steps", 0),
            output=combined_output,
        )


class SztuRpcRunner:
    name = "sztucode-rpc"

    # 保存 daemon 地址和评测权限模式，评测结束后恢复 daemon 原权限模式
    def __init__(self, host: str, port: int, permission_mode: str) -> None:
        self._host = host
        self._port = port
        self._permission_mode = permission_mode

    # 汇总 llm.usage 事件，兼容旧 daemon 缺少 run.finished token 汇总的情况
    def _usage_from_events(self, events: list[dict[str, Any]]) -> tuple[int, int, int, int]:
        input_tokens = 0
        output_tokens = 0
        cache_read = 0
        cache_creation = 0
        for event in events:
            if event.get("type") != "llm.usage":
                continue
            input_tokens += int(event.get("input_tokens", 0) or 0)
            output_tokens += int(event.get("output_tokens", 0) or 0)
            cache_read += int(event.get("cache_read_input_tokens", 0) or 0)
            cache_creation += int(event.get("cache_creation_input_tokens", 0) or 0)
        return input_tokens, output_tokens, cache_read, cache_creation

    # 连接生产 daemon，订阅事件并执行一个 one_shot 会话
    async def _run_async(
        self,
        task: EvaluationTask,
        workspace: Path,
        timeout_seconds: float,
    ) -> RunnerOutcome:
        client = SocketClient(self._host, self._port)
        events_by_run: dict[str, list[dict[str, Any]]] = {}
        finished_by_run: dict[str, dict[str, Any]] = {}
        finished = asyncio.Event()
        final_event: dict[str, Any] = {}
        run_id = ""

        # 按 run_id 隔离全局事件，并在当前 run.finished 时唤醒等待者
        async def on_event(event: dict[str, Any]) -> None:
            event_run_id = str(event.get("run_id", ""))
            if not event_run_id:
                return
            events_by_run.setdefault(event_run_id, []).append(event)
            if event.get("type") == "run.finished":
                finished_by_run[event_run_id] = event
                if event_run_id == run_id:
                    final_event.update(event)
                    finished.set()

        try:
            await client.connect()
        except (ConnectionRefusedError, OSError) as exc:
            return RunnerOutcome(
                failure_reason=FailureReason.RUNNER_FAILED,
                error_message=f"cannot connect to daemon: {exc}",
            )

        client.on_event(on_event)
        loop_task = asyncio.create_task(client.run_event_loop())
        session_id = ""
        original_permission_mode = ""
        permission_restore_needed = False
        try:
            settings = await client.send_command("settings.get", {})
            original_permission_mode = str(
                settings.get("settings", {}).get("permission_mode", "")
            )
            if original_permission_mode not in {
                "normal",
                "accept_edits",
                "plan",
                "auto",
            }:
                raise ValueError("daemon returned an invalid permission mode")
            if original_permission_mode != self._permission_mode:
                permission_restore_needed = True
                mode_result = await client.send_command(
                    "permission.set_mode", {"mode": self._permission_mode}
                )
                if mode_result.get("ok") is not True:
                    raise RuntimeError(
                        str(mode_result.get("error") or "cannot set permission mode")
                    )
            opened = await client.send_command(
                "workspace.open", {"path": str(workspace.resolve())}
            )
            workspace_id = str(opened.get("workspace", {}).get("workspace_id", ""))
            await client.send_command(
                "event.subscribe",
                {"topics": ["run.*", "step.*", "tool.*", "llm.usage"], "scope": "global"},
            )
            created = await client.send_command(
                "session.create",
                {"mode": "one_shot", "title": task.id, "workspace_id": workspace_id},
            )
            session_id = str(created.get("session_id", ""))
            sent = await client.send_command(
                "session.send_message",
                {"session_id": session_id, "content": task.prompt},
            )
            run_id = str(sent.get("run_id", ""))
            if not run_id:
                raise ValueError("daemon returned an empty run_id")
            if run_id in finished_by_run:
                final_event.update(finished_by_run[run_id])
                finished.set()
            try:
                await asyncio.wait_for(finished.wait(), timeout=timeout_seconds)
            except TimeoutError:
                if run_id:
                    try:
                        await client.send_command("run.cancel", {"run_id": run_id})
                    except (IpcError, RuntimeError):
                        pass
                current_events = events_by_run.get(run_id, [])
                return RunnerOutcome(
                    failure_reason=FailureReason.TIMEOUT,
                    error_message=f"daemon run timed out after {timeout_seconds:g}s",
                    tool_calls=sum(
                        event.get("type") == "tool.call_started"
                        for event in current_events
                    ),
                )

            current_events = events_by_run.get(run_id, [])
            usage = self._usage_from_events(current_events)
            status = str(final_event.get("status", ""))
            reason = str(final_event.get("reason") or "")
            failure_reason = None if status == "success" else FailureReason.RUNNER_FAILED
            return RunnerOutcome(
                failure_reason=failure_reason,
                error_message=reason if failure_reason else "",
                input_tokens=int(final_event.get("total_input_tokens", usage[0]) or usage[0]),
                output_tokens=int(final_event.get("total_output_tokens", usage[1]) or usage[1]),
                cache_read_input_tokens=usage[2],
                cache_creation_input_tokens=usage[3],
                tool_calls=sum(
                    event.get("type") == "tool.call_started"
                    for event in current_events
                ),
                steps=int(final_event.get("steps", 0) or 0),
                patch=git_patch(workspace) if (workspace / ".git").is_dir() else "",
                output=json.dumps(
                    {"run_id": run_id, "status": status, "reason": reason},
                    ensure_ascii=False,
                ),
            )
        except (IpcError, OSError, RuntimeError, ValueError) as exc:
            return RunnerOutcome(
                failure_reason=FailureReason.RUNNER_FAILED,
                error_message=str(exc),
            )
        finally:
            if session_id:
                try:
                    await client.send_command("session.close", {"session_id": session_id})
                except (IpcError, RuntimeError):
                    pass
            if permission_restore_needed:
                try:
                    await client.send_command(
                        "permission.set_mode", {"mode": original_permission_mode}
                    )
                except (IpcError, OSError, RuntimeError):
                    pass
            loop_task.cancel()
            try:
                await loop_task
            except asyncio.CancelledError:
                pass
            await client.close()

    # 在同步 CLI 中运行异步 daemon 客户端并返回统一结果
    def run(
        self,
        task: EvaluationTask,
        workspace: Path,
        artifacts_dir: Path,
        timeout_seconds: float,
    ) -> RunnerOutcome:
        del artifacts_dir
        return asyncio.run(self._run_async(task, workspace, timeout_seconds))
