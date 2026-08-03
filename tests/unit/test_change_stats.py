from __future__ import annotations

import subprocess
from pathlib import Path

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
