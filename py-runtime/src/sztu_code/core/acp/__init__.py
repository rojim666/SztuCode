"""ACP (Agent Client Protocol) agent server for SztuCode.

Exposes SztuCode to ACP clients over stdio. The primary consumer is the
OpenClaw WeChat channel plugin ecosystem, which routes WeChat messages to an
ACP backend (see ``docs/guides/wechat-openclaw-acp.md``).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from sztu_code.core.acp.backend import AgentBackend, DaemonBackend, DaemonUnavailableError
from sztu_code.core.acp.bridge import AcpBridge, ClientLink
from sztu_code.core.acp.stdio import StdioLink, serve

__all__ = [
    "AcpBridge",
    "AgentBackend",
    "ClientLink",
    "DaemonBackend",
    "DaemonUnavailableError",
    "StdioLink",
    "agent_version",
    "serve",
]


def agent_version() -> str:
    """Best-effort installed SztuCode version, used in the ACP ``initialize``."""
    try:
        return version("SztuCode")
    except PackageNotFoundError:  # pragma: no cover - depends on install layout
        return "0.0.1"
