# 桌面 GUI 入口：解析命令行参数并启动 SztuCodeDestkop 主窗口
from __future__ import annotations

import argparse

from sztu_code.desktop.app import run_desktop
from sztu_code.core.config import get_config


def main() -> None:
    parser = argparse.ArgumentParser(prog="sztu-desktop", description="SztuCode Desktop GUI")
    parser.add_argument("--host", default=None, help="Daemon host (default: from config)")
    parser.add_argument("--port", type=int, default=None, help="Daemon port (default: from config)")
    args = parser.parse_args()

    config = get_config()
    host = args.host or config.host
    port = args.port or config.port

    run_desktop(host, port)
