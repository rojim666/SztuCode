from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_MAX_FILE_BYTES = 1_000_000
_MAX_SNAPSHOT_BYTES = 32 * 1024 * 1024
_IGNORED_PARTS = {".git", ".sztu", "__pycache__", "node_modules", ".venv"}
_MANIFEST_NAME = "changes.json"


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@dataclass(frozen=True)
class _FileState:
    content: bytes
    digest: str


class WorkspaceChangeTracker:
    """Records a bounded workspace snapshot so a run can be reverted without Git reset."""

    def __init__(self, workspace_root: Path, run_path: Path, run_id: str) -> None:
        self._root = workspace_root.resolve()
        self._run_path = run_path
        self._run_id = run_id
        self._before = self._snapshot()

    @property
    def manifest_path(self) -> Path:
        return self._run_path / _MANIFEST_NAME

    def finalize(self) -> list[dict[str, Any]]:
        after = self._snapshot()
        records: list[dict[str, Any]] = []
        snapshots = self._run_path / "change-snapshots"
        for index, path in enumerate(sorted(set(self._before) | set(after))):
            before = self._before.get(path)
            current = after.get(path)
            if before is not None and current is not None and before.digest == current.digest:
                continue
            snapshot_name: str | None = None
            if before is not None:
                snapshots.mkdir(parents=True, exist_ok=True)
                snapshot_name = f"{index:04d}.bin"
                (snapshots / snapshot_name).write_bytes(before.content)
            records.append(
                {
                    "path": path,
                    "before_exists": before is not None,
                    "before_digest": before.digest if before else None,
                    "after_exists": current is not None,
                    "after_digest": current.digest if current else None,
                    "before_snapshot": snapshot_name,
                    "revertible": True,
                }
            )
        self._run_path.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "run_id": self._run_id,
                    "workspace_path": str(self._root),
                    "changes": records,
                },
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        return records

    def _snapshot(self) -> dict[str, _FileState]:
        states: dict[str, _FileState] = {}
        total_bytes = 0
        for path in sorted(self._root.rglob("*"), key=lambda item: item.as_posix().lower()):
            if not path.is_file() or any(part in _IGNORED_PARTS for part in path.parts):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > _MAX_FILE_BYTES or total_bytes + size > _MAX_SNAPSHOT_BYTES:
                continue
            try:
                content = path.read_bytes()
            except OSError:
                continue
            total_bytes += len(content)
            relative = path.relative_to(self._root).as_posix()
            states[relative] = _FileState(content=content, digest=_digest(content))
        return states


def load_manifest(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def active_manifest_changes(manifest: dict[str, Any], workspace_root: Path) -> list[dict[str, Any]]:
    """Return only records whose on-disk state is still the exact post-run state."""
    root = workspace_root.resolve()
    if manifest.get("workspace_path") != str(root):
        return []
    changes = manifest.get("changes")
    if not isinstance(changes, list):
        return []
    active: list[dict[str, Any]] = []
    for change in changes:
        if not isinstance(change, dict) or not isinstance(change.get("path"), str):
            continue
        target = (root / change["path"]).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            continue
        expected_exists = bool(change.get("after_exists"))
        if target.exists() != expected_exists:
            continue
        if not expected_exists:
            active.append(change)
            continue
        try:
            if _digest(target.read_bytes()) == change.get("after_digest"):
                active.append(change)
        except OSError:
            continue
    return active


def revert_manifest_changes(
    manifest_path: Path,
    workspace_root: Path,
    paths: list[str],
) -> tuple[list[str], dict[str, str]]:
    """Restore exact pre-run bytes only when the file still matches the recorded post-run state."""
    manifest = load_manifest(manifest_path)
    if manifest is None or manifest.get("workspace_path") != str(workspace_root.resolve()):
        raise ValueError("agent change record not found for this workspace")
    requested = set(paths)
    changes = manifest.get("changes")
    if not requested or not isinstance(changes, list):
        raise ValueError("select one or more agent-owned files to revert")
    known = {str(change.get("path")): change for change in changes if isinstance(change, dict)}
    unknown = requested - known.keys()
    if unknown:
        raise ValueError(f"paths are not owned by this run: {', '.join(sorted(unknown))}")

    root = workspace_root.resolve()
    reverted: list[str] = []
    blocked: dict[str, str] = {}
    for relative in sorted(requested):
        change = known[relative]
        target = (root / relative).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            blocked[relative] = "invalid recorded path"
            continue
        expected_exists = bool(change.get("after_exists"))
        if target.exists() != expected_exists:
            blocked[relative] = "file changed since this Agent run; nothing was overwritten"
            continue
        if expected_exists:
            try:
                current_digest = _digest(target.read_bytes())
            except OSError:
                blocked[relative] = "cannot read current file"
                continue
            if current_digest != change.get("after_digest"):
                blocked[relative] = "file changed since this Agent run; nothing was overwritten"
                continue
        if bool(change.get("before_exists")):
            snapshot_name = change.get("before_snapshot")
            if not isinstance(snapshot_name, str):
                blocked[relative] = "missing pre-run snapshot"
                continue
            snapshot = manifest_path.parent / "change-snapshots" / snapshot_name
            try:
                content = snapshot.read_bytes()
            except OSError:
                blocked[relative] = "missing pre-run snapshot"
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        elif target.exists():
            # This can only remove a file created during this run after the digest guard above.
            target.unlink()
        reverted.append(relative)
    return reverted, blocked
