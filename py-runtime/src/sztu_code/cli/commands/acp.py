from __future__ import annotations

import asyncio
import sys

from sztu_code.core.acp import agent_version, serve
from sztu_code.core.acp.backend import DaemonBackend
from sztu_code.core.config import SztuConfig


# 以 ACP agent 身份运行：由编辑器/微信接入插件通过 stdio 驱动本进程
def cmd_acp(config: SztuConfig) -> None:
    backend = DaemonBackend(config)
    try:
        exit_code = asyncio.run(serve(backend, version=agent_version()))
    except KeyboardInterrupt:
        sys.exit(130)
    sys.exit(exit_code)
