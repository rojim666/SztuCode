from __future__ import annotations

import json
from pathlib import Path

from sztu_code.core.wechat.binding import BOUND_SESSION_KEY, read_bound_session_id


def test_reads_bound_session_id(tmp_path: Path) -> None:
    path = tmp_path / "wechat-bridge.json"
    path.write_text(json.dumps({BOUND_SESSION_KEY: "sess-42"}), encoding="utf-8")
    assert read_bound_session_id(path) == "sess-42"


def test_missing_file_means_no_binding(tmp_path: Path) -> None:
    assert read_bound_session_id(tmp_path / "absent.json") is None


def test_malformed_file_degrades_to_no_binding(tmp_path: Path) -> None:
    path = tmp_path / "wechat-bridge.json"
    path.write_text("{not json", encoding="utf-8")
    assert read_bound_session_id(path) is None


def test_blank_or_non_string_binding_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "wechat-bridge.json"
    for payload in ({BOUND_SESSION_KEY: "   "}, {BOUND_SESSION_KEY: 7}, {"other": "x"}, []):
        path.write_text(json.dumps(payload), encoding="utf-8")
        assert read_bound_session_id(path) is None
