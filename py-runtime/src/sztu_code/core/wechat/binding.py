"""Read the desktop-authored WeChat session binding.

The desktop connection panel lets the user pick the session a WeChat
conversation should land in. That choice is persisted next to the other
desktop state files (``~/.sztu/wechat-bridge.json``) because the desktop is the
only writer; the ACP bridge is the reader, so an incoming WeChat turn reuses
the bound SztuCode session instead of creating an empty one.

The reader is intentionally forgiving: a missing, unreadable, or malformed file
must degrade to "no binding" rather than break the ACP handshake.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Shared with desktop/src-tauri/src/wechat_bridge.rs; keep both in sync.
BINDING_RELATIVE_PATH = ".sztu/wechat-bridge.json"
BOUND_SESSION_KEY = "boundSessionId"


def binding_path() -> Path:
    """Absolute location of the binding file shared with the desktop."""
    return Path("~").expanduser() / BINDING_RELATIVE_PATH


def read_bound_session_id(path: Path | None = None) -> str | None:
    """Return the bound daemon session id, or ``None`` when unset/unreadable."""
    target = path or binding_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.debug("ignoring unreadable WeChat binding at %s: %s", target, exc)
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get(BOUND_SESSION_KEY)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None
