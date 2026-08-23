from __future__ import annotations

import json
import socket
from pathlib import Path

from sztu_code.tui import launcher
from sztu_code.tui.app import KamaTuiApp


# 功能：验证 daemon 端口已开通时 ensure_daemon 直接返回 True 且不拉起进程
# 设计：绑定一个真实监听 socket 作为 daemon 探针，_spawn_daemon 设为计数桩，断言未被调用
def test_ensure_daemon_returns_true_when_port_open(monkeypatch) -> None:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    probe.listen(1)
    port = probe.getsockname()[1]
    spawned = []
    monkeypatch.setattr(launcher, "_spawn_daemon", lambda: spawned.append(True))
    try:
        assert launcher.ensure_daemon("127.0.0.1", port, timeout=1.0) is True
    finally:
        probe.close()
    assert spawned == []


# 功能：验证 daemon 端口始终不通时 ensure_daemon 在超时内返回 False
# 设计：用已关闭的端口并注入短超时，_spawn_daemon 置为无操作，避免测试真拉起后台进程
def test_ensure_daemon_returns_false_when_unreachable(monkeypatch) -> None:
    monkeypatch.setattr(launcher, "_spawn_daemon", lambda: None)

    assert launcher.ensure_daemon("127.0.0.1", 1, timeout=0.5) is False


# 功能：验证只读或显式信任时跳过信任确认屏
# 设计：构造 KamaTuiApp 并直接调用 _needs_trust_check，覆盖 read_only/trust 两条短路路径
def test_needs_trust_check_skipped_for_read_only_or_trust(
    tmp_path: Path, monkeypatch,
) -> None:
    project = tmp_path / "proj"
    monkeypatch.setenv("SZTU_TRUSTED_PROJECTS", str(tmp_path / "trusted.json"))

    assert KamaTuiApp(
        "127.0.0.1", 7437, project_path=str(project), read_only=True
    )._needs_trust_check() is False
    assert KamaTuiApp(
        "127.0.0.1", 7437, project_path=str(project), trust=True
    )._needs_trust_check() is False


# 功能：验证已信任的目录不弹信任屏，未信任目录需要弹
# 设计：用 SZTU_TRUSTED_PROJECTS 指向 tmp 文件并写入信任项，对比受信任/未受信任路径的返回值
def test_needs_trust_check_depends_on_trust_store(
    tmp_path: Path, monkeypatch,
) -> None:
    trusted_dir = tmp_path / "code"
    trusted_dir.mkdir()
    untrusted_dir = tmp_path / "other"
    store_path = tmp_path / "trusted.json"
    store_path.write_text(
        json.dumps({"trusted": [str(trusted_dir.resolve())]}), encoding="utf-8"
    )
    monkeypatch.setenv("SZTU_TRUSTED_PROJECTS", str(store_path))

    assert KamaTuiApp(
        "127.0.0.1", 7437, project_path=str(trusted_dir)
    )._needs_trust_check() is False
    assert KamaTuiApp(
        "127.0.0.1", 7437, project_path=str(untrusted_dir)
    )._needs_trust_check() is True


# 功能：验证未信任目录启动时弹出 TrustScreen，Esc 取消后直接退出
# 设计：用 Textual run_test 无头运行，断言屏幕栈顶部为 TrustScreen，再按 Esc 走 abort 退出
async def test_trust_screen_shown_and_escape_aborts(
    tmp_path: Path, monkeypatch,
) -> None:
    from sztu_code.tui.app import KamaTuiApp, TrustScreen

    monkeypatch.setenv("SZTU_TRUSTED_PROJECTS", str(tmp_path / "trusted.json"))
    app = KamaTuiApp("127.0.0.1", 7437, project_path=str(tmp_path / "proj"))
    async with app.run_test() as pilot:
        assert isinstance(app.screen_stack[-1], TrustScreen)
        await pilot.press("escape")


# 功能：验证在信任屏按 Enter 确认后记录信任并继续
# 设计：monkeypatch _start_socket_loop 为 no-op 避免真实连 daemon，断言信任落盘
async def test_trust_screen_enter_records_trust(
    tmp_path: Path, monkeypatch,
) -> None:
    from sztu_code.core.trust import is_trusted
    from sztu_code.tui.app import KamaTuiApp, TrustScreen

    store_path = tmp_path / "trusted.json"
    project = tmp_path / "proj"
    monkeypatch.setenv("SZTU_TRUSTED_PROJECTS", str(store_path))
    monkeypatch.setattr(KamaTuiApp, "_start_socket_loop", lambda self: None)
    app = KamaTuiApp("127.0.0.1", 7437, project_path=str(project))
    async with app.run_test() as pilot:
        assert isinstance(app.screen_stack[-1], TrustScreen)
        await pilot.press("enter")

    assert is_trusted(project) is True


# 功能：验证一次 run 的所有输出合并进单个 RunBlock，而不是散成多个日志行
# 设计：用合成事件喂给 TUI（run.started→step→token→usage→finished），断言只产生一个块且含 LLM 流
async def test_run_outputs_merged_into_single_block(
    tmp_path: Path, monkeypatch,
) -> None:
    from sztu_code.tui.app import KamaTuiApp, RunBlock

    monkeypatch.setenv("SZTU_TRUSTED_PROJECTS", str(tmp_path / "trusted.json"))
    monkeypatch.setattr(KamaTuiApp, "_start_socket_loop", lambda self: None)
    app = KamaTuiApp("127.0.0.1", 7437, project_path=str(tmp_path / "proj"), trust=True)
    async with app.run_test() as pilot:
        for event in [
            {"type": "run.started", "run_id": "run-1", "goal": "hi"},
            {"type": "step.started", "run_id": "run-1", "step": 1},
            {"type": "llm.token", "run_id": "run-1", "token": "hel"},
            {"type": "llm.token", "run_id": "run-1", "token": "lo"},
            {"type": "llm.usage", "run_id": "run-1", "input_tokens": 1,
             "output_tokens": 2, "cache_read_input_tokens": 0,
             "cache_creation_input_tokens": 0, "context_pct": 0.1, "model": "m"},
            {"type": "run.finished", "run_id": "run-1", "status": "success", "steps": 1},
        ]:
            app._handle_event(event)
        await pilot.pause()
        blocks = app.query(RunBlock)
        assert len(blocks) == 1
        assert any(type(child).__name__ == "LLMStreamBlock" for child in blocks[0].children)
