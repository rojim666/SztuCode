from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

from sztu_code.core.run_store import RunStore
from sztu_code.core.transport.socket_client import SocketClient


# 启动 daemon 并等待端口可连接，返回子进程；超时则强杀并报错
async def _spawn_daemon(port: int, runs_dir: Path) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["SZTU_PORT"] = str(port)
    env["SZTU_RUNS_DIR"] = str(runs_dir)
    env["SZTU_LOG_FILE"] = ""
    env["SZTU_LOG_LEVEL"] = "WARNING"

    proc = subprocess.Popen([sys.executable, "-m", "sztu_code.core"], env=env)
    # /mnt/e 的 drvfs 挂载下冷启动 import openai 较慢，放宽到 60s 避免误判为启动失败
    deadline = time.monotonic() + 60.0
    while time.monotonic() < deadline:
        await asyncio.sleep(0.05)
        try:
            _reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return proc
        except (ConnectionRefusedError, OSError):
            pass
    proc.kill()
    proc.wait()
    raise RuntimeError("daemon did not start in time")


# 强杀子进程并等待其退出，模拟崩溃而非优雅关闭
def _crash(proc: subprocess.Popen[bytes]) -> None:
    proc.kill()
    proc.wait()


# 功能：daemon 启动时把崩溃遗留的 running 记录对账为 cancelled，run.get 不再返回 unknown
# 设计：预写 running 记录后启动真实 daemon，run.get 应返回 cancelled 而非 unknown
async def test_run_get_reconciles_interrupted_run_after_restart(
    free_port: int, tmp_path: Path
) -> None:
    runs_dir = tmp_path / "runs"
    RunStore(runs_dir).start("crashed-run-1", goal="interrupted")

    proc = await _spawn_daemon(free_port, runs_dir)
    client = SocketClient("127.0.0.1", free_port)
    await client.connect()
    loop_task = asyncio.create_task(client.run_event_loop())
    try:
        result = await client.send_command("run.get", {"run_id": "crashed-run-1"})
        assert result.get("status") == "cancelled", result
    finally:
        loop_task.cancel()
        await asyncio.gather(loop_task, return_exceptions=True)
        await client.close()
        _crash(proc)


# 功能：已完成的 run 跨重启仍返回 completed，不会被对账误改
# 设计：预写 completed 记录后启动 daemon，run.get 返回 completed 而非 unknown/cancelled
async def test_completed_run_persists_after_restart(
    free_port: int, tmp_path: Path
) -> None:
    runs_dir = tmp_path / "runs"
    store = RunStore(runs_dir)
    store.start("done-run-1", goal="done")
    store.finish("done-run-1", status="completed")

    proc = await _spawn_daemon(free_port, runs_dir)
    client = SocketClient("127.0.0.1", free_port)
    await client.connect()
    loop_task = asyncio.create_task(client.run_event_loop())
    try:
        result = await client.send_command("run.get", {"run_id": "done-run-1"})
        assert result.get("status") == "completed", result
    finally:
        loop_task.cancel()
        await asyncio.gather(loop_task, return_exceptions=True)
        await client.close()
        _crash(proc)


# 功能：真实 agent.run 在崩溃重启后 run.get 仍返回有效状态，而不是 unknown
# 设计：触发 run 并等到 run.started 落盘，强杀 daemon 后在同一数据目录重启，
#       断言 run.get 返回 cancelled/completed 之一（绝不会是 unknown）
async def test_live_run_not_unknown_after_crash_restart(
    free_port: int, tmp_path: Path
) -> None:
    runs_dir = tmp_path / "runs"

    proc = await _spawn_daemon(free_port, runs_dir)
    client = SocketClient("127.0.0.1", free_port)
    await client.connect()
    started = asyncio.Event()
    run_id_holder: list[str] = []

    async def on_event(event: dict[str, object]) -> None:
        if event.get("type") == "run.started":
            run_id_holder.append(str(event.get("run_id", "")))
            started.set()

    client.on_event(on_event)
    loop_task = asyncio.create_task(client.run_event_loop())
    try:
        await client.send_command("event.subscribe", {"topics": ["run.*"], "scope": "global"})
        result = await client.send_command("agent.run", {"goal": "crash recovery"})
        run_id = str(result["run_id"])
        await asyncio.wait_for(started.wait(), timeout=8.0)
        assert run_id_holder and run_id_holder[0] == run_id
    finally:
        loop_task.cancel()
        await asyncio.gather(loop_task, return_exceptions=True)
        await client.close()

    # 崩溃：不优雅退出，直接强杀，模拟运行中断电/被杀
    _crash(proc)

    # 用同一数据目录重启，run.get 必须从持久化记录恢复，而不是返回 unknown
    proc2 = await _spawn_daemon(free_port, runs_dir)
    client2 = SocketClient("127.0.0.1", free_port)
    await client2.connect()
    loop2 = asyncio.create_task(client2.run_event_loop())
    try:
        result = await client2.send_command("run.get", {"run_id": run_id})
        assert result.get("status") in {"cancelled", "completed"}, result
    finally:
        loop2.cancel()
        await asyncio.gather(loop2, return_exceptions=True)
        await client2.close()
        _crash(proc2)
