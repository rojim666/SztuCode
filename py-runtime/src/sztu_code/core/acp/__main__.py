"""``python -m sztu_code.core.acp`` — run SztuCode as an ACP agent over stdio."""

from __future__ import annotations

import sys

from sztu_code.cli.commands.acp import cmd_acp
from sztu_code.core.config import get_config
from sztu_code.core.logging_setup import setup_logging


def main() -> None:
    config = get_config()
    setup_logging(config)
    cmd_acp(config)


if __name__ == "__main__":
    main()
    sys.exit(0)
