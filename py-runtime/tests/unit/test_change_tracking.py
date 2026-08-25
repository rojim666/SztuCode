from __future__ import annotations

from pathlib import Path

import pytest

from sztu_code.core.changes import (
    WorkspaceChangeTracker,
    active_manifest_changes,
    load_manifest,
    revert_manifest_changes,
)


def test_tracker_reverts_only_the_agent_run_boundary(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "src" / "example.py"
    target.parent.mkdir()
    target.write_text("before\n", encoding="utf-8")
    run_path = tmp_path / "run"

    tracker = WorkspaceChangeTracker(workspace, run_path, "run-1")
    target.write_text("after\n", encoding="utf-8")
    created = workspace / "new.py"
    created.write_text("new\n", encoding="utf-8")
    records = tracker.finalize()

    assert [record["path"] for record in records] == ["new.py", "src/example.py"]
    reverted, blocked = revert_manifest_changes(
        tracker.manifest_path, workspace, ["src/example.py", "new.py"]
    )

    assert reverted == ["new.py", "src/example.py"]
    assert blocked == {}
    assert target.read_text(encoding="utf-8") == "before\n"
    assert not created.exists()


def test_revert_refuses_to_overwrite_a_file_changed_after_run(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "example.txt"
    target.write_text("before", encoding="utf-8")
    tracker = WorkspaceChangeTracker(workspace, tmp_path / "run", "run-2")
    target.write_text("agent", encoding="utf-8")
    tracker.finalize()
    target.write_text("human", encoding="utf-8")

    reverted, blocked = revert_manifest_changes(
        tracker.manifest_path, workspace, ["example.txt"]
    )

    assert reverted == []
    assert blocked["example.txt"] == "file changed since this Agent run; nothing was overwritten"
    assert target.read_text(encoding="utf-8") == "human"


def test_revert_requires_an_explicit_owned_path(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tracker = WorkspaceChangeTracker(workspace, tmp_path / "run", "run-3")
    (workspace / "agent.txt").write_text("agent", encoding="utf-8")
    tracker.finalize()

    with pytest.raises(ValueError, match="owned by this run"):
        revert_manifest_changes(tracker.manifest_path, workspace, ["other.txt"])


def test_active_changes_disappear_after_a_successful_revert(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "agent.txt"
    tracker = WorkspaceChangeTracker(workspace, tmp_path / "run", "run-4")
    target.write_text("agent", encoding="utf-8")
    tracker.finalize()
    manifest = load_manifest(tracker.manifest_path)
    assert manifest is not None
    assert [change["path"] for change in active_manifest_changes(manifest, workspace)] == ["agent.txt"]

    revert_manifest_changes(tracker.manifest_path, workspace, ["agent.txt"])

    assert active_manifest_changes(manifest, workspace) == []


def test_tracker_ignores_cache_files_but_keeps_business_cache_modules(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tracker = WorkspaceChangeTracker(workspace, tmp_path / "run", "run-cache")
    module = workspace / "src" / "cache.py"
    cache_file = workspace / ".pytest_cache" / "state.json"
    bytecode = workspace / "src" / "__pycache__" / "cache.pyc"
    module.parent.mkdir()
    cache_file.parent.mkdir()
    bytecode.parent.mkdir()
    module.write_text("VALUE = 1\n", encoding="utf-8")
    cache_file.write_text("{}\n", encoding="utf-8")
    bytecode.write_bytes(b"compiled")

    records = tracker.finalize()

    assert [record["path"] for record in records] == ["src/cache.py"]
