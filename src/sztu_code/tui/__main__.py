from __future__ import annotations

import argparse

from sztu_code.core.config import get_config
from sztu_code.tui.app import KamaTuiApp
from sztu_code.tui.launcher import _setup_logging


# sztu-tui 入口：解析 --replay 参数后启动 TUI 应用
def main() -> None:
    parser = argparse.ArgumentParser(prog="sztu-tui", description="SztuCode TUI")
    parser.add_argument(
        "--replay",
        metavar="RUN_ID",
        help="Replay events from a past run on connect",
    )
    args = parser.parse_args()

    config = get_config()
    _setup_logging(config.logging.level)
    app = KamaTuiApp(config.host, config.port, replay_run_id=args.replay)
    app.run(inline=True, inline_no_clear=True)


if __name__ == "__main__":
    main()
