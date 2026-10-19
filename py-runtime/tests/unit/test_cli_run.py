from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from sztu_code.cli.commands.run import _run_async
from sztu_code.core.config import SztuConfig
from sztu_code.core.transport.socket_client import IpcError


class _RunClient:
    def __init__(
        self,
        early_events: list[dict[str, Any]] | None = None,
        rpc_error: Exception | None = None,
        loop_error: Exception | None = None,
    ) -> None:
        self.early_events = early_events or []
        self.rpc_error = rpc_error
        self.loop_error = loop_error
        self.launch_requested = asyncio.Event()
        self.loop_end = asyncio.Event()
        self.loop_stopped = False
        self.closed = False
        self.handler: Callable[[dict[str, Any]], Awaitable[None]] | None = None

    async def connect(self) -> None:
        pass

    def on_event(self, handler: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        self.handler = handler

    async def emit(self, event: dict[str, Any]) -> None:
        assert self.handler is not None
        await self.handler(event)

    async def run_event_loop(self) -> None:
        try:
            await self.loop_end.wait()
            if self.loop_error is not None:
                raise self.loop_error
        finally:
            self.loop_stopped = True

    async def send_command(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "event.subscribe":
            # Global traffic during subscription must not reach the printer.
            await self.emit({"type": "llm.token", "run_id": "other", "token": "subscribe noise"})
            return {}
        assert method == "agent.run"
        assert params == {"goal": "our goal"}
        self.launch_requested.set()
        if self.rpc_error is not None:
            raise self.rpc_error
        for event in self.early_events:
            await self.emit(event)
        return {"run_id": "parent"}

    async def close(self) -> None:
        self.closed = True


def _install_client(monkeypatch: pytest.MonkeyPatch, client: _RunClient) -> None:
    monkeypatch.setattr("sztu_code.cli.commands.run.SocketClient", lambda host, port: client)


async def test_run_ignores_other_and_child_runs(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = _RunClient(
        [
            {"type": "llm.token", "run_id": "other", "token": "early noise"},
            {"type": "run.finished", "run_id": "other", "status": "failed", "steps": 1},
            {"type": "run.started", "run_id": "parent"},
        ]
    )
    _install_client(monkeypatch, client)
    task = asyncio.create_task(_run_async("our goal", SztuConfig()))
    await asyncio.wait_for(client.launch_requested.wait(), timeout=1)

    for run_id in ("other", "child"):
        await client.emit({"type": "llm.token", "run_id": run_id, "token": f"{run_id} noise"})
        await client.emit({"type": "run.finished", "run_id": run_id, "status": "failed", "steps": 1})
    await asyncio.sleep(0)
    assert not task.done()

    await client.emit({"type": "llm.token", "run_id": "parent", "token": "our output"})
    await client.emit({"type": "run.finished", "run_id": "parent", "status": "success", "steps": 2})

    assert await asyncio.wait_for(task, timeout=1) == 0
    output = capsys.readouterr()
    assert "[run] parent" in output.out
    assert "our output" in output.out
    assert "success" in output.out
    assert "noise" not in output.out
    assert "failed" not in output.out
    assert output.err == ""
    assert client.closed
    assert client.loop_stopped


async def test_run_replays_own_events_before_rpc_response(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = _RunClient(
        [
            {"type": "run.started", "run_id": "parent"},
            {"type": "llm.token", "run_id": "parent", "token": "early output"},
            {"type": "run.finished", "run_id": "child", "status": "failed", "steps": 1},
            {"type": "run.finished", "run_id": "parent", "status": "success", "steps": 2},
        ]
    )
    _install_client(monkeypatch, client)

    assert await asyncio.wait_for(_run_async("our goal", SztuConfig()), timeout=1) == 0
    output = capsys.readouterr()
    assert output.out.index("[run] parent") < output.out.index("early output")
    assert output.out.index("early output") < output.out.index("success")
    assert "failed" not in output.out
    assert output.err == ""
    assert client.closed


async def test_run_returns_failure_for_own_failed_run(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _RunClient(
        [{"type": "run.finished", "run_id": "parent", "status": "failed", "steps": 0}]
    )
    _install_client(monkeypatch, client)

    assert await asyncio.wait_for(_run_async("our goal", SztuConfig()), timeout=1) == 1
    assert client.closed


@pytest.mark.parametrize("loop_error", [None, ValueError("invalid event frame")])
async def test_run_fails_when_event_loop_ends_before_finished(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    loop_error: Exception | None,
) -> None:
    client = _RunClient(loop_error=loop_error)
    _install_client(monkeypatch, client)
    task = asyncio.create_task(_run_async("our goal", SztuConfig()))
    await asyncio.wait_for(client.launch_requested.wait(), timeout=1)
    client.loop_end.set()

    assert await asyncio.wait_for(task, timeout=1) == 1
    error = capsys.readouterr().err
    assert (str(loop_error) if loop_error else "connection closed before run finished") in error
    assert client.closed
    assert client.loop_stopped


@pytest.mark.parametrize(
    "rpc_error",
    [ConnectionError("closed before response"), IpcError(-32000, "launch failed")],
)
async def test_run_cleans_up_after_rpc_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    rpc_error: Exception,
) -> None:
    client = _RunClient(rpc_error=rpc_error)
    _install_client(monkeypatch, client)

    assert await asyncio.wait_for(_run_async("our goal", SztuConfig()), timeout=1) == 1
    assert str(rpc_error) in capsys.readouterr().err
    assert client.closed


async def test_run_cleans_up_when_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _RunClient()
    _install_client(monkeypatch, client)
    task = asyncio.create_task(_run_async("our goal", SztuConfig()))
    await asyncio.wait_for(client.launch_requested.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.closed
    assert client.loop_stopped
