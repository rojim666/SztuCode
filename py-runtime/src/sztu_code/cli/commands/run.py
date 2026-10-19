from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Any

from sztu_code.core.config import SztuConfig
from sztu_code.core.transport.socket_client import SocketClient


class StdoutPrinter:
    # 接收 dict 格式的事件并将运行进度格式化打印到终端
    def __init__(self) -> None:
        self._inline = False  # True while LLM tokens are mid-line
        self._run_start: float = 0.0

    # 若当前行有未换行的 token，补一个换行符
    def _ensure_newline(self) -> None:
        if self._inline:
            print()
            self._inline = False

    # 根据事件 type 字段分发并格式化打印到 stdout/stderr
    async def handle(self, event: dict[str, Any]) -> None:
        t = event.get("type", "")

        if t == "run.started":
            self._run_start = time.monotonic()
            print(f"[run] {event.get('run_id', '')}")

        elif t == "step.started":
            self._ensure_newline()
            print(f"[step {event.get('step')}] planning...")

        elif t == "llm.token":
            print(event.get("token", ""), end="", flush=True)
            self._inline = True

        elif t == "tool.call_started":
            self._ensure_newline()
            params_str = json.dumps(event.get("params", {}), ensure_ascii=False)
            print(f"[tool] {event.get('tool_name', '')} {params_str}")

        elif t == "tool.call_finished":
            print(f"[tool] {event.get('tool_name', '')} ✓  {event.get('elapsed_ms')}ms")

        elif t == "tool.call_failed":
            print(
                f"[tool] {event.get('tool_name', '')} ✗  {event.get('error_message', '')}",
                file=sys.stderr,
            )

        elif t == "step.finished":
            self._ensure_newline()
            print(f"[step {event.get('step')}] done")

        elif t == "run.finished":
            self._ensure_newline()
            elapsed = time.monotonic() - self._run_start
            print(f"[run] {event.get('status', '')}  {event.get('steps')} steps  {elapsed:.1f}s")


# 异步核心：连接 daemon，订阅事件，触发 run，等待 run.finished
async def _run_async(goal: str, config: SztuConfig) -> int:
    client = SocketClient(config.host, config.port)
    printer = StdoutPrinter()
    finished = asyncio.Event()
    exit_code = 0
    run_id: str | None = None
    launch_requested = False
    pending_events: list[dict[str, Any]] = []
    loop_task: asyncio.Task[None] | None = None
    finished_task: asyncio.Task[bool] | None = None

    async def on_event(event: dict[str, Any]) -> None:
        nonlocal exit_code
        if run_id is None:
            # run.started may arrive before the agent.run RPC response.
            if launch_requested and event.get("run_id"):
                pending_events.append(event)
            return
        if event.get("run_id") != run_id:
            return
        await printer.handle(event)
        if event.get("type") == "run.finished":
            if event.get("status") != "success":
                exit_code = 1
            finished.set()

    try:
        try:
            await client.connect()
        except OSError:
            print(f"error: core not running ({config.host}:{config.port})", file=sys.stderr)
            return 1

        client.on_event(on_event)
        loop_task = asyncio.create_task(client.run_event_loop())
        await client.send_command(
            "event.subscribe",
            {
                "topics": ["run.*", "step.*", "tool.*", "llm.token", "llm.usage"],
                "scope": "global",
            },
        )
        launch_requested = True
        result = await client.send_command("agent.run", {"goal": goal})
        returned_run_id = result.get("run_id")
        if not isinstance(returned_run_id, str) or not returned_run_id:
            raise ValueError("core returned an invalid run_id")
        run_id = returned_run_id
        for event in pending_events:
            await on_event(event)
        pending_events.clear()

        finished_task = asyncio.create_task(finished.wait())
        await asyncio.wait((finished_task, loop_task), return_when=asyncio.FIRST_COMPLETED)
        if finished.is_set():
            return exit_code
        if not loop_task.cancelled():
            await loop_task
        raise ConnectionError("core connection closed before run finished")
    except Exception as e:
        printer._ensure_newline()
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        tasks = [task for task in (finished_task, loop_task) if task is not None]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await client.close()


# 执行 sztu run --goal "..." 命令
def cmd_run(goal: str, config: SztuConfig) -> None:
    try:
        exit_code = asyncio.run(_run_async(goal, config))
    except KeyboardInterrupt:
        sys.exit(130)
    sys.exit(exit_code)
