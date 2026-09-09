"""Immutable file snapshots for exact edits and conflict-checked restoration."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path

from sztu_code.core.tools.workspace import resolve_workspace_path

_LOCK = threading.RLock()
_LIMIT = 32 * 1024 * 1024


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class FileVersions:
    def __init__(self, root: Path | None) -> None:
        self.root = (root or Path.cwd()).resolve()

    def _target(self, relative: str) -> Path:
        target = resolve_workspace_path(self.root, relative)
        if ".sztu" in target.relative_to(self.root).parts:
            raise ValueError("Versioned edits cannot modify internal .sztu files")
        return target

    def _directory(self, target: Path) -> Path:
        key = digest(target.relative_to(self.root).as_posix().encode())
        directory = resolve_workspace_path(self.root, f".sztu/file-versions/{key}")
        return directory

    def _snapshot(self, directory: Path, data: bytes) -> str:
        version = digest(data)
        snapshot = directory / f"{version}.bin"
        try:
            with snapshot.open("xb") as stream:
                stream.write(data)
        except FileExistsError:
            if snapshot.is_symlink() or digest(snapshot.read_bytes()) != version:
                raise ValueError("Stored version failed integrity verification")
        return version

    def list(self, relative: str) -> list[dict[str, object]]:
        directory = self._directory(self._target(relative))
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.json"))]

    def write(self, relative: str, data: bytes, expected_hash: str) -> dict[str, str]:
        if len(data) > _LIMIT:
            raise ValueError("Versioned edit exceeds 32 MB")
        with _LOCK:
            target = self._target(relative)
            before = target.read_bytes()
            if len(before) > _LIMIT:
                raise ValueError("Source exceeds 32 MB")
            if digest(before) != expected_hash:
                raise ValueError("File changed since selection; select the current content again")
            directory = self._directory(target)
            directory.mkdir(parents=True, exist_ok=True)
            old_hash = self._snapshot(directory, before)
            new_hash = self._snapshot(directory, data)
            record = {"before": old_hash, "after": new_hash, "path": relative}
            # Both versions are durable before the editable file is replaced.
            record_path = directory / f"{time.time_ns()}-{uuid.uuid4().hex}.json"
            record_path.write_text(json.dumps(record), encoding="utf-8")
            temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
            try:
                with temporary.open("xb") as stream:
                    stream.write(data)
                os.chmod(temporary, target.stat().st_mode)
                if digest(target.read_bytes()) != old_hash:
                    raise ValueError("File changed while preparing edit; nothing overwritten")
                os.replace(temporary, target)
            except BaseException:
                record_path.unlink(missing_ok=True)
                raise
            finally:
                temporary.unlink(missing_ok=True)
            return record

    def restore(self, relative: str, version: str, expected_hash: str) -> dict[str, str]:
        with _LOCK:
            records = self.list(relative)
            if not any(version in (r["before"], r["after"]) for r in records):
                raise ValueError("Unknown version for this file")
            if len(version) != 64 or any(c not in "0123456789abcdef" for c in version):
                raise ValueError("Invalid version hash")
            snapshot = self._directory(self._target(relative)) / f"{version}.bin"
            if snapshot.is_symlink():
                raise ValueError("Invalid version snapshot")
            data = snapshot.read_bytes()
            if digest(data) != version:
                raise ValueError("Stored version failed integrity verification")
            return self.write(relative, data, expected_hash)
