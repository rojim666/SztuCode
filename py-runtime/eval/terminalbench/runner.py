"""
容器内 runner：在 Harbor 任务容器里拉起 SztuCode daemon 并驱动其完成 Terminal-Bench 任务。

本脚本由 eval.terminalbench.agent.SztuCodeAgent（host 端 Harbor agent）通过
``environment.exec`` 在容器内执行，不要在 host 上直接运行。

流程:
  1. spawn daemon: ``.venv/bin/python -m sztu_code.core``（SZTU_PORT 指定端口，
     日志写入 --daemon-log）
  2. core.ping 重试直到 daemon 就绪
  3. permission.set_mode(auto) → event.subscribe → workspace.open(workspace)
  4. session.create(one_shot) → session.send_message(指令全文)
  5. 等待 run.finished 事件（--timeout 秒）
  6. 汇总 token 用量与状态 → 写 --result-file JSON
  7. 关闭 session，杀掉 daemon（进程组）

用法（容器内，由 agent 拼装）:
    cd /opt/sztucode && .venv/bin/python -m eval.terminalbench.runner \
        --instruction-file /tmp/sztu-instruction.txt \
        --workspace /root \
        --port 7457 \
        --result-file /tmp/sztu-result.json \
        --timeout 21600
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# daemon 就绪等待（安装后冷启动一般 <10s，留足余量）
_DAEMON_READY_TIMEOUT = 120

# agent.py 通过 exec env 注入；runner 与 daemon 子进程共享这些变量
_RUNTIME_DIR = Path(__file__).resolve().parents[2]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SztuCode Terminal-Bench runner")
    parser.add_argument("--instruction-file", required=True, help="任务指令文本文件路径")
    parser.add_argument("--workspace", required=True, help="agent 工作目录")
    parser.add_argument("--port", type=int, default=7457, help="容器内 daemon 监听端口")
    parser.add_argument("--result-file", required=True, help="结果 JSON 输出路径")
    parser.add_argument("--timeout", type=int, default=21600, help="等待 run.finished 的秒数")
    parser.add_argument("--daemon-log", default="/tmp/sztu-daemon.log", help="daemon 日志路径")
    return parser.parse_args()


def _spawn_daemon(args: argparse.Namespace) -> subprocess.Popen[bytes]:
    """后台启动 SztuCode daemon，绑定 127.0.0.1:<port>"""
    env = os.environ.copy()
    env["SZTU_HOST"] = "127.0.0.1"
    env["SZTU_PORT"] = str(args.port)
    env.setdefault("SZTU_LOG_LEVEL", "INFO")

    venv_python = _RUNTIME_DIR / ".venv" / "bin" / "python"
    if not venv_python.is_file():
        raise FileNotFoundError(f"daemon interpreter not found: {venv_python}")

    log = open(args.daemon_log, "ab")  # noqa: SIM115 - 随进程退出由 GC 回收
    return subprocess.Popen(  # noqa: S603
        [str(venv_python), "-m", "sztu_code.core"],
        cwd=str(_RUNTIME_DIR),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,  # 独立进程组，便于 killpg 清理
    )


async def _wait_daemon_ready(port: int, timeout: float) -> None:
    """轮询 core.ping 直到 daemon 接受 RPC"""
    from sztu_code.core.transport.socket_client import IpcError, SocketClient

    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        client = SocketClient("127.0.0.1", port)
        try:
            await asyncio.wait_for(client.connect(), timeout=2.0)
            await asyncio.wait_for(client.send_command("core.ping", {}), timeout=5.0)
            return
        except (OSError, TimeoutError, IpcError) as exc:
            last_error = exc
        finally:
            await client.close()
        await asyncio.sleep(1.0)
    raise TimeoutError(f"daemon not ready on port {port}: {last_error}")


class _RunEventCollector:
    """按 run_id 过滤 daemon 事件，捕获 run.finished 与 llm.usage"""

    def __init__(self) -> None:
        self.run_id: str | None = None
        self.events: list[dict[str, Any]] = []
        self.finished_event: dict[str, Any] | None = None
        self.finished = asyncio.Event()
        self._pending: list[dict[str, Any]] = []

    def record(self, event: dict[str, Any]) -> None:
        event_run_id = str(event.get("run_id", ""))
        if not event_run_id:
            return
        if self.run_id is None:
            self._pending.append(event)
            return
        self._accept(event, event_run_id)

    def set_run_id(self, run_id: str) -> None:
        self.run_id = run_id
        pending, self._pending = self._pending, []
        for event in pending:
            self._accept(event, str(event.get("run_id", "")))

    def _accept(self, event: dict[str, Any], event_run_id: str) -> None:
        if event_run_id != self.run_id:
            return
        self.events.append(event)
        if event.get("type") == "run.finished":
            self.finished_event = event
            self.finished.set()


def _summarize_tokens(events: list[dict[str, Any]]) -> dict[str, int]:
    usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    for event in events:
        if event.get("type") != "llm.usage":
            continue
        for key in usage:
            usage[key] += int(event.get(key, 0) or 0)
    return usage


def _write_result(path: str, payload: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)


async def _run_task(args: argparse.Namespace, instruction: str) -> dict[str, Any]:
    from sztu_code.core.transport.socket_client import IpcError, SocketClient

    result: dict[str, Any] = {
        "status": "error",
        "reason": None,
        "steps": 0,
        "run_id": None,
        "error": None,
        "elapsed_s": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }

    client = SocketClient("127.0.0.1", args.port)
    collector = _RunEventCollector()

    async def on_event(event: dict[str, Any]) -> None:
        collector.record(event)
        if collector.run_id is None or str(event.get("run_id", "")) != collector.run_id:
            return
        event_type = event.get("type", "")
        if event_type == "step.started":
            print(f"[runner] step {event.get('step')} planning", flush=True)
        elif event_type == "tool.call_started":
            print(f"[runner] tool {event.get('tool_name')}", flush=True)
        elif event_type == "tool.call_failed":
            print(f"[runner] tool FAIL: {event.get('error_message', '')}", flush=True)

    start = time.monotonic()
    loop_task: asyncio.Task | None = None
    session_id: str | None = None
    try:
        await client.connect()
        client.on_event(on_event)
        loop_task = asyncio.create_task(client.run_event_loop())

        # 评测场景全自动批准工具调用
        await client.send_command("permission.set_mode", {"mode": "auto"})
        print("[runner] permission mode: auto", flush=True)

        # 先订阅再发消息，避免漏掉 run.finished
        await client.send_command("event.subscribe", {
            "topics": ["run.*", "step.*", "tool.*", "llm.usage"],
            "scope": "global",
        })

        ws_result = await client.send_command("workspace.open", {"path": args.workspace})
        workspace_id = ws_result.get("workspace", {}).get("workspace_id", "")
        print(f"[runner] workspace: {workspace_id} ({args.workspace})", flush=True)

        sess_result = await client.send_command("session.create", {
            "mode": "one_shot",
            "title": "terminal-bench",
            "workspace_id": workspace_id,
        })
        session_id = sess_result.get("session_id", "")

        send_result = await client.send_command("session.send_message", {
            "session_id": session_id,
            "content": instruction,
        })
        run_id = str(send_result.get("run_id") or "")
        if not run_id:
            raise ValueError("daemon returned an empty run_id")
        collector.set_run_id(run_id)
        result["run_id"] = run_id
        print(f"[runner] run started: {run_id}", flush=True)

        try:
            await asyncio.wait_for(collector.finished.wait(), timeout=args.timeout)
        except TimeoutError:
            result["status"] = "timeout"
            result["error"] = f"run not finished within {args.timeout}s"
            try:
                await client.send_command("run.cancel", {"run_id": run_id})
            except (IpcError, OSError):
                pass
        else:
            finished = collector.finished_event or {}
            result["status"] = finished.get("status", "unknown")
            result["reason"] = finished.get("reason")
            result["steps"] = finished.get("steps", 0)

        result.update(_summarize_tokens(collector.events))

    except IpcError as exc:
        result["error"] = f"RPC error: {exc}"
    except Exception as exc:  # noqa: BLE001 - 任何失败都要落到 result JSON
        result["error"] = f"unexpected: {exc}"
        print(f"[runner] error: {exc}", file=sys.stderr, flush=True)
    finally:
        if session_id:
            try:
                await client.send_command("session.close", {"session_id": session_id})
            except Exception:  # noqa: BLE001 - 清理失败不影响结果
                pass
        if loop_task is not None:
            loop_task.cancel()
            try:
                await loop_task
            except asyncio.CancelledError:
                pass
        await client.close()
        result["elapsed_s"] = round(time.monotonic() - start, 1)

    return result


async def _main() -> int:
    args = _parse_args()
    instruction = Path(args.instruction_file).read_text(encoding="utf-8")
    if not instruction.strip():
        _write_result(args.result_file, {"status": "error", "error": "empty instruction"})
        return 2

    daemon = _spawn_daemon(args)
    print(
        f"[runner] daemon pid={daemon.pid} port={args.port} workspace={args.workspace}",
        flush=True,
    )
    try:
        await _wait_daemon_ready(args.port, _DAEMON_READY_TIMEOUT)
        print("[runner] daemon ready", flush=True)
        result = await _run_task(args, instruction)
    except Exception as exc:  # noqa: BLE001 - 任何失败都要落到 result JSON
        result = {
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_s": 0.0,
        }
    finally:
        _terminate_daemon(daemon)

    _write_result(args.result_file, result)
    print(
        f"[runner] done status={result.get('status')} "
        f"steps={result.get('steps', 0)} elapsed={result.get('elapsed_s')}s "
        f"tokens(in/out/cache)={result.get('input_tokens', 0)}/"
        f"{result.get('output_tokens', 0)}/{result.get('cache_read_input_tokens', 0)}",
        flush=True,
    )
    return 0 if result.get("status") == "success" else 1


def _terminate_daemon(daemon: subprocess.Popen[bytes]) -> None:
    """终止 daemon 进程组：先 SIGTERM，3s 后 SIGKILL 兜底"""
    if daemon.poll() is not None:
        return
    try:
        os.killpg(daemon.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        daemon.terminate()
    try:
        daemon.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(daemon.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            daemon.kill()
        daemon.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
