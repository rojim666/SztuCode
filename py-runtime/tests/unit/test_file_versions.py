import asyncio
from pathlib import Path

import pytest

from sztu_code.core.file_versions import FileVersions, digest
from sztu_code.core.tools.builtin.edit_file import EditFileTool


def test_local_edit_preserves_bytes_and_restore_survives_restart(tmp_path: Path) -> None:
    target = tmp_path / "page.html"
    before = b'\xef\xbb\xbf<h1>Title</h1>\r\n<p>Keep</p>\r\n'
    target.write_bytes(before)
    result = asyncio.run(EditFileTool(tmp_path).invoke({"path": "page.html", "old_string": "Title", "new_string": "Updated", "expected_hash": digest(before)}))
    assert not result.is_error
    after = before.replace(b"Title", b"Updated")
    assert target.read_bytes() == after
    store = FileVersions(tmp_path)
    assert len(store.list("page.html")) == 1
    store.restore("page.html", digest(before), digest(after))
    assert target.read_bytes() == before
    assert len(store.list("page.html")) == 2
    store.restore("page.html", digest(after), digest(before))
    assert target.read_bytes() == after


def test_restore_refuses_stale_state_and_corrupt_snapshot(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_bytes(b"before")
    store = FileVersions(tmp_path)
    store.write("notes.txt", b"after", digest(b"before"))
    target.write_bytes(b"manual edit")
    with pytest.raises(ValueError, match="changed since selection"):
        store.restore("notes.txt", digest(b"before"), digest(b"after"))
    assert target.read_bytes() == b"manual edit"
    snapshot = next((tmp_path / ".sztu/file-versions").rglob(f"{digest(b'before')}.bin"))
    snapshot.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="integrity"):
        store.restore("notes.txt", digest(b"before"), digest(b"manual edit"))
    with pytest.raises(PermissionError):
        store.write("../outside.txt", b"x", digest(b""))


def test_empty_selection_cannot_rewrite_every_character(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_bytes(b"keep")
    result = asyncio.run(EditFileTool(tmp_path).invoke({"path": "notes.txt", "old_string": "", "new_string": "x", "replace_all": True}))
    assert result.is_error
    assert target.read_bytes() == b"keep"
