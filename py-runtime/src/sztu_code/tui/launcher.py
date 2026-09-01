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
from sztu_code.tui.app import SztuTuiApp

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
    flags = int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) if os.name == "nt" else 0
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


# sztucode 入口：确保 daemon 运行并启动 TUI（信任确认在 TUI 内完成）
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

    config = get_config()
    _setup_logging(config.logging.level)
    if not ensure_daemon(config.host, config.port):
        print(
            "warning: daemon 未能启动，TUI 将保持重连；可手动运行 sztu-code",
            file=sys.stderr,
        )
    if args.trust and not is_trusted(target):
        add_trusted(target)
    app = SztuTuiApp(
        config.host,
        config.port,
        project_path=str(target),
        read_only=args.read_only,
        trust=args.trust,
        replay_run_id=args.replay,
        theme=config.tui.theme,
        wallpaper=config.tui.wallpaper,
    )
    app.run(inline=True, inline_no_clear=True)


if __name__ == "__main__":
    main()
