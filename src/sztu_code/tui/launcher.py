from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from sztu_code.core.config import get_config
from sztu_code.core.trust import add_trusted, is_trusted
from sztu_code.tui.app import KamaTuiApp

_DEFAULT_TUI_LOG = "~/.sztu/logs/tui.log"


# TUI 文件日志初始化：不写 stderr（避免干扰 Textual 渲染），只写滚动文件
def _setup_logging(level: str) -> None:
    log_path = Path(os.environ.get("SZTU_TUI_LOG_FILE", _DEFAULT_TUI_LOG)).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter(
            'level=%(levelname)s ts=%(asctime)s source=%(name)s msg="%(message)s"',
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.DEBUG))
    root.handlers.clear()
    root.addHandler(handler)


# 纯决策函数：根据信任状态与用户输入返回 (mode, 是否需要记录信任)
# mode ∈ {"trust", "read_only", "abort"}；read_only 不记录信任
def classify_launch(
    already_trusted: bool,
    *,
    want_trust: bool = False,
    want_read_only: bool = False,
    answer: str | None = None,
) -> tuple[str, bool]:
    if already_trusted or want_trust:
        return ("trust", want_trust and not already_trusted)
    if want_read_only:
        return ("read_only", False)
    if answer is not None:
        choice = answer.strip().lower()
        if choice in ("t", "y", "trust", "yes"):
            return ("trust", True)
        if choice in ("r", "read", "read_only", "readonly"):
            return ("read_only", False)
        if choice in ("n", "no", "abort"):
            return ("abort", False)
    return ("abort", False)


# 探测 daemon 端口是否可连接
def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# 后台拉起 daemon 进程，日志写入 daemon 的日志文件
def _spawn_daemon() -> None:
    config = get_config()
    log_path = Path(config.logging.file).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    with open(log_path, "ab") as log_file, open(os.devnull, "rb") as devnull:
        subprocess.Popen(
            [sys.executable, "-m", "sztu_code.core.app"],
            stdin=devnull,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            creationflags=flags,
        )


# 确保 daemon 可连接：已运行则直接返回，否则后台拉起并等待就绪
def ensure_daemon(host: str, port: int, *, timeout: float = 5.0) -> bool:
    if _port_open(host, port):
        return True
    _spawn_daemon()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_open(host, port):
            return True
        time.sleep(0.25)
    return False


# sztucode 入口：信任确认后确保 daemon 运行并启动 TUI
def main() -> None:
    parser = argparse.ArgumentParser(prog="sztucode", description="在项目目录打开 SztuCode TUI")
    parser.add_argument("dir", nargs="?", default=".", help="项目目录（默认当前目录）")
    parser.add_argument("--trust", action="store_true", help="信任该目录")
    parser.add_argument("--read-only", action="store_true", help="只读模式打开（不信任）")
    parser.add_argument("--replay", metavar="RUN_ID", help="回放一次历史运行")
    args = parser.parse_args()

    target = Path(args.dir).expanduser().resolve()
    if not target.is_dir():
        print(f"error: not a directory: {target}", file=sys.stderr)
        sys.exit(1)

    already_trusted = is_trusted(target)
    answer: str | None = None
    if not already_trusted and not args.trust and not args.read_only and sys.stdin.isatty():
        print(f"SztuCode 将打开: {target}")
        print("该文件夹尚未被信任，Agent 将可读取和修改其中的文件。")
        try:
            answer = input("[T]rust  [r]ead-only  [n]o: ").strip()
        except EOFError:
            answer = None

    mode, should_record = classify_launch(
        already_trusted,
        want_trust=args.trust,
        want_read_only=args.read_only,
        answer=answer,
    )
    if mode == "abort":
        if answer is None and not args.trust and not args.read_only:
            print(
                "error: 文件夹未受信任；请加 --trust 或 --read-only，或在交互式终端运行",
                file=sys.stderr,
            )
        else:
            print("已放弃：文件夹未受信任。", file=sys.stderr)
        sys.exit(1)
    if should_record:
        add_trusted(target)

    config = get_config()
    _setup_logging(config.logging.level)
    if not ensure_daemon(config.host, config.port):
        print(
            "warning: daemon 未能启动，TUI 将保持重连；可手动运行 sztu-code",
            file=sys.stderr,
        )
    app = KamaTuiApp(
        config.host,
        config.port,
        project_path=str(target),
        read_only=(mode == "read_only"),
        replay_run_id=args.replay,
    )
    app.run()


if __name__ == "__main__":
    main()
