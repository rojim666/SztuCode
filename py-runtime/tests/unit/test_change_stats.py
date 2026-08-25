from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from sztu_code.core.changes import manifest_file_diff
from sztu_code.core.workspace import WorkspaceManager


# 在临时目录执行 git 命令
def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


# 初始化一个带提交历史的最小 git 仓库
def _make_git_repo(root: Path) -> None:
    root.mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "a.txt").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "init")


# 功能：验证 diff_numstat 统计跟踪文件的增减行数与未跟踪文件的新增行数
# 设计：临时 git 仓库里改一个已提交文件（+2/-1）、新增一个未跟踪文件（+3），断言各自统计
def test_diff_numstat_counts_tracked_and_untracked(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _make_git_repo(root)
    (root / "a.txt").write_text("one\nTWO\nthree\nfour\n", encoding="utf-8")  # two→TWO：+1/-1
    (root / "new.txt").write_text("x\ny\nz\n", encoding="utf-8")  # 未跟踪：3 行全算新增
    manager = WorkspaceManager(tmp_path / "state" / "workspaces.json")
    workspace = manager.open(str(root))

    stats = manager.diff_numstat(workspace.id, ["a.txt", "new.txt"])

    assert stats["a.txt"] == (1, 1)
    assert stats["new.txt"] == (3, 0)
    changes = {change["path"]: change for change in manager.list_changes(workspace.id)}
    assert changes["a.txt"]["additions"] == 1
    assert changes["a.txt"]["deletions"] == 1
    assert changes["new.txt"]["additions"] == 3
    assert changes["new.txt"]["deletions"] == 0


# 功能：验证 diff_numstat 对不存在的文件返回 0/0，且路径越界被拒绝
# 设计：不存在的文件无 diff 且非文件 → (0,0)；../ 越界路径抛 ValueError（复用工作区守卫）
def test_diff_numstat_missing_and_escape(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _make_git_repo(root)
    manager = WorkspaceManager(tmp_path / "state" / "workspaces.json")
    workspace = manager.open(str(root))

    assert manager.diff_numstat(workspace.id, ["nope.txt"]) == {"nope.txt": (0, 0)}
    try:
        manager.diff_numstat(workspace.id, ["../escape.txt"])
    except ValueError:
        pass
    else:
        raise AssertionError("path escape should be rejected")


# 功能：验证 stage 把文件加入 git 暂存区（审核"接受" = 暂存待提交）
# 设计：修改已提交文件后 stage，断言 git status --porcelain 索引列为 M
def test_stage_adds_to_git_index(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _make_git_repo(root)
    (root / "a.txt").write_text("one\nTWO\nthree\nfour\n", encoding="utf-8")
    manager = WorkspaceManager(tmp_path / "state" / "workspaces.json")
    workspace = manager.open(str(root))

    manager.stage(workspace.id, ["a.txt"])

    status = _git(root, "status", "--porcelain").stdout
    assert any(line.startswith("M ") for line in status.splitlines())


def test_diff_numstat_counts_staged_changes_against_head(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _make_git_repo(root)
    (root / "a.txt").write_text("one\nTWO\nthree\nfour\nFIVE\n", encoding="utf-8")
    manager = WorkspaceManager(tmp_path / "state" / "workspaces.json")
    workspace = manager.open(str(root))

    manager.stage(workspace.id, ["a.txt"])

    assert manager.diff_numstat(workspace.id, ["a.txt"]) == {"a.txt": (2, 1)}


# 构造一个带 before 快照的 changes.json 清单，返回 manifest 路径
def _make_manifest(run_dir: Path, workspace_path: str, records: list[dict]) -> Path:
    snapshots = run_dir / "change-snapshots"
    snapshots.mkdir(parents=True)
    for record in records:
        snapshot_name = record.get("before_snapshot")
        if snapshot_name:
            (snapshots / snapshot_name).write_bytes(record["before_bytes"])
    manifest_path = run_dir / "changes.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "run_id": "run-test",
                "workspace_path": str(Path(workspace_path).resolve()),
                "changes": [
                    {key: value for key, value in record.items() if not key.startswith("before_bytes")}
                    for record in records
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return manifest_path


def _record(path: str, before: bytes | None, after: bytes | None, snapshot: str | None = None) -> dict:
    return {
        "path": path,
        "before_exists": before is not None,
        "before_digest": hashlib.sha256(before).hexdigest() if before else None,
        "after_exists": after is not None,
        "after_digest": hashlib.sha256(after).hexdigest() if after else None,
        "before_snapshot": snapshot,
        "before_bytes": before,
        "revertible": True,
    }


# 功能：即使 run 改动已提交（磁盘仍为 after 内容），也能基于快照生成 before→当前 的 diff
# 设计：临时目录写入 before 快照与 after 内容，断言 diff 含 -two/+TWO 且含 ---/+++/@@ 头
def test_manifest_file_diff_committed_file(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    before = b"one\ntwo\nthree\n"
    after = b"one\nTWO\nthree\n"
    (root / "a.txt").write_bytes(after)  # 磁盘仍是 run 结束后的内容（模拟已提交）
    manifest_path = _make_manifest(
        tmp_path / "run",
        str(root),
        [_record("a.txt", before, after, snapshot="0000.bin")],
    )
    diff = manifest_file_diff(manifest_path, root, "a.txt")
    assert diff is not None
    assert "-two" in diff
    assert "+TWO" in diff
    assert diff.startswith("--- a.txt")
    assert "@@" in diff


# 功能：run 期间新建的文件按"空→当前"生成全新增 diff
def test_manifest_file_diff_new_file(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    after = b"x\ny\n"
    (root / "new.txt").write_bytes(after)
    manifest_path = _make_manifest(
        tmp_path / "run",
        str(root),
        [_record("new.txt", None, after)],
    )
    diff = manifest_file_diff(manifest_path, root, "new.txt")
    assert diff is not None
    assert "+x" in diff
    assert diff.count("+") >= 2


# 功能：run 期间删除的文件生成全删除 diff（before→空）
def test_manifest_file_diff_deleted_file(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    before = b"a\nb\n"
    manifest_path = _make_manifest(
        tmp_path / "run",
        str(root),
        [_record("gone.txt", before, None, snapshot="0000.bin")],
    )
    diff = manifest_file_diff(manifest_path, root, "gone.txt")
    assert diff is not None
    assert "-a" in diff
    assert [line for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")] == []


# 功能：清单中不存在的路径返回 None，调用方回退 Git diff
def test_manifest_file_diff_unknown_path_returns_none(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "a.txt").write_bytes(b"x")
    manifest_path = _make_manifest(
        tmp_path / "run",
        str(root),
        [_record("a.txt", b"x", b"y", snapshot="0000.bin")],
    )
    assert manifest_file_diff(manifest_path, root, "missing.txt") is None


# 功能：manifest 记录的工作区路径与当前不一致时拒绝生成，防止跨目录读快照
def test_manifest_file_diff_wrong_workspace_returns_none(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / "a.txt").write_bytes(b"y")
    other = tmp_path / "other"
    other.mkdir()
    manifest_path = _make_manifest(
        tmp_path / "run",
        str(other),
        [_record("a.txt", b"x", b"y", snapshot="0000.bin")],
    )
    assert manifest_file_diff(manifest_path, root, "a.txt") is None
