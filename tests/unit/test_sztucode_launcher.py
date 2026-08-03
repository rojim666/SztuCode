from __future__ import annotations

import socket

from sztu_code.tui import launcher


# 功能：验证已信任或显式 --trust 时直接以 trust 模式打开并记录
# 设计：覆盖两条短路路径——already_trusted 不重复记录，want_trust 且未信任时记录为 True
def test_classify_launch_trust_paths() -> None:
    assert launcher.classify_launch(True) == ("trust", False)
    assert launcher.classify_launch(False, want_trust=True) == ("trust", True)
    assert launcher.classify_launch(True, want_trust=True) == ("trust", False)


# 功能：验证 --read-only 与交互式 r 回答都进入只读模式且不记录信任
# 设计：覆盖显式 flag 与交互回答两条入口，断言 should_record 恒为 False
def test_classify_launch_read_only_paths() -> None:
    assert launcher.classify_launch(False, want_read_only=True) == ("read_only", False)
    assert launcher.classify_launch(False, answer="r") == ("read_only", False)
    assert launcher.classify_launch(False, answer="readonly") == ("read_only", False)


# 功能：验证交互式 t/n 回答分别进入信任与放弃，且无任何输入时默认放弃
# 设计：直接测纯函数，避免依赖 stdin；n/no/None 都应收敛到 abort
def test_classify_launch_interactive_and_abort() -> None:
    assert launcher.classify_launch(False, answer="t") == ("trust", True)
    assert launcher.classify_launch(False, answer="trust") == ("trust", True)
    assert launcher.classify_launch(False, answer="n") == ("abort", False)
    assert launcher.classify_launch(False, answer="no") == ("abort", False)
    assert launcher.classify_launch(False) == ("abort", False)


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
