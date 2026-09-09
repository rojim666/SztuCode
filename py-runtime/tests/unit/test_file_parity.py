from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from sztu_code.core.tools.builtin.glob_search import GlobSearchTool
from sztu_code.core.tools.builtin.grep_search import GrepSearchTool
from sztu_code.core.tools.builtin.read_file import ReadFileTool


async def test_shared_search_scenarios(tmp_path: Path) -> None:
    fixture_path = Path(__file__).resolve().parents[3] / "tests/fixtures/runtime-file-parity.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    for name, content in fixture["files"].items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    result = await GlobSearchTool(tmp_path).invoke({"pattern": fixture["glob"]["pattern"]})
    assert sorted(result.content.splitlines()) == fixture["glob"]["expected"]
    for scenario in fixture["grep"]:
        result = await GrepSearchTool(tmp_path).invoke(scenario)
        assert sorted(line.split(":")[0] for line in result.content.splitlines()) == scenario["expected"]


async def test_read_pages_past_legacy_byte_limit(tmp_path: Path) -> None:
    (tmp_path / "large.txt").write_text("a" * (512 * 1024) + "\nsecond\nthird\n", encoding="utf-8")
    tool = ReadFileTool(tmp_path)
    result = await tool.invoke({"path": "large.txt", "offset": 1, "limit": 1})
    assert result.content.startswith("     2\tsecond")
    assert "next offset=2" in result.content
    result = await tool.invoke({"path": "large.txt", "offset": 2, "limit": 1})
    assert result.content == "     3\tthird"


async def test_search_skips_symlink_files(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("SECRET", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    try:
        (workspace / "link.py").symlink_to(outside / "secret.py")
    except OSError:
        pytest.skip("Creating symlinks requires Windows developer mode or privileges")
    assert (await GlobSearchTool(workspace).invoke({"pattern": "**/*.py"})).content == "No files found."
    assert (await GrepSearchTool(workspace).invoke({"pattern": "SECRET"})).content == "No matches found."


async def test_read_page_crlf_and_eof(tmp_path: Path) -> None:
    (tmp_path / "sample.txt").write_bytes(b"one\r\ntwo\r\n")
    tool = ReadFileTool(tmp_path)
    assert (await tool.invoke({"path": "sample.txt", "offset": 1})).content == "     2\ttwo"
    assert (await tool.invoke({"path": "sample.txt", "offset": 3})).content == ""


@pytest.mark.parametrize("params", [{"offset": -1}, {"limit": 0}, {"limit": 2001}])
async def test_invalid_page_rejected(tmp_path: Path, params: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        await ReadFileTool(tmp_path).invoke({"path": "sample.txt", **params})
