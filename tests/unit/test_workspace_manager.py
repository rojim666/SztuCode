from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from sztu_code.core.workspace import WorkspaceManager


# 功能：验证打开工作区后可持久化最近目录、读取受限文件树并进行文本搜索。
# 设计：使用临时目录构造嵌套源码与被忽略目录，重建 manager 验证磁盘恢复，同时断言 tree/search 只暴露工作区内可读内容。
def test_workspace_open_persists_tree_and_search(tmp_path: Path) -> None:
    root = tmp_path / "project"
    source = root / "src"
    source.mkdir(parents=True)
    (source / "main.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")
    (root / "README.md").write_text("hello workspace\n", encoding="utf-8")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("hidden", encoding="utf-8")

    recent_file = tmp_path / "state" / "workspaces.json"
    manager = WorkspaceManager(recent_file)
    workspace = manager.open(str(root))

    tree = manager.tree(workspace.id, max_depth=2)
    assert {node["name"] for node in tree} == {"README.md", "src"}
    assert manager.read_file(workspace.id, "src/main.py").content.startswith("def hello")
    assert manager.search(workspace.id, "hello") == [
        {"path": "README.md", "line": 1, "preview": "hello workspace"},
        {"path": "src/main.py", "line": 1, "preview": "def hello():"},
    ]

    restored = WorkspaceManager(recent_file)
    assert restored.list_recent() == [workspace]

def test_workspace_archive_resume_persists(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    recent_file = tmp_path / "state" / "workspaces.json"

    manager = WorkspaceManager(recent_file)
    active = manager.open(str(first))
    archived = manager.open(str(second))

    archived = manager.archive(archived.id)

    assert archived.archived is True
    assert [item.id for item in manager.list_recent(include_archived=False)] == [active.id]

    restored = WorkspaceManager(recent_file)
    assert restored.get(archived.id).archived is True

    resumed = restored.resume(archived.id)
    assert resumed.archived is False
    assert [item.id for item in restored.list_recent(include_archived=False)] == [
        active.id,
        archived.id,
    ]


# 功能：验证工作区文件读取拒绝目录穿越及不存在目录，避免客户端借 IPC 读取任意本地文件。
# 设计：对已打开临时工作区传入 ../ 路径和无效 open 路径，分别断言 ValueError，覆盖路径边界与输入验证。
def test_workspace_rejects_paths_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    manager = WorkspaceManager(tmp_path / "workspaces.json")
    workspace = manager.open(str(root))

    with pytest.raises(ValueError, match="escapes workspace"):
        manager.read_file(workspace.id, "../outside.txt")
    with pytest.raises(ValueError, match="existing directory"):
        manager.open(str(tmp_path / "missing"))


def test_workspace_tree_keeps_root_files_visible_when_a_directory_is_large(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    large = root / "aaa"
    cache = root / ".mypy_cache"
    large.mkdir(parents=True)
    cache.mkdir()
    for index in range(40):
        (large / f"file-{index}.txt").write_text("data", encoding="utf-8")
    (cache / "hidden.json").write_text("{}", encoding="utf-8")
    (root / "main.py").write_text("print('visible')", encoding="utf-8")
    manager = WorkspaceManager(tmp_path / "workspaces.json")
    workspace = manager.open(str(root))

    tree = manager.tree(workspace.id, max_depth=3, max_entries=10)

    assert [node["name"] for node in tree] == ["aaa", "main.py"]
    assert ".mypy_cache" not in {node["name"] for node in tree}


@pytest.mark.parametrize(
    ("name", "payload", "encoding"),
    [
        ("utf8.txt", "你好 UTF-8".encode(), "UTF-8"),
        ("utf8-bom.txt", b"\xef\xbb\xbf" + "你好 BOM".encode(), "UTF-8 BOM"),
        ("utf16.txt", "你好 UTF-16".encode("utf-16"), "UTF-16 LE"),
        ("gbk.txt", "你好 GB18030".encode("gb18030"), "GB18030"),
    ],
)
def test_workspace_detects_common_text_encodings(
    tmp_path: Path, name: str, payload: bytes, encoding: str
) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / name).write_bytes(payload)
    manager = WorkspaceManager(tmp_path / "workspaces.json")
    workspace = manager.open(str(root))

    result = manager.read_file(workspace.id, name)

    assert "你好" in result.content
    assert result.encoding == encoding
    assert result.binary is False


def test_workspace_reports_binary_and_replaces_unknown_text_bytes(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "image.bin").write_bytes(b"\x89PNG\r\n\x1a\n\x00data")
    (root / "broken.txt").write_bytes(b"plain text \xff")
    manager = WorkspaceManager(tmp_path / "workspaces.json")
    workspace = manager.open(str(root))

    binary = manager.read_file(workspace.id, "image.bin")
    broken = manager.read_file(workspace.id, "broken.txt")

    assert binary.binary is True
    assert binary.content == ""
    assert broken.binary is False
    assert broken.content.startswith("plain text")


def test_workspace_returns_image_data_for_binary_previews(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "pixel.png").write_bytes(
        bytes.fromhex("89504e470d0a1a0a0000000d49484452")
    )
    manager = WorkspaceManager(tmp_path / "workspaces.json")
    workspace = manager.open(str(root))

    result = manager.read_file(workspace.id, "pixel.png")

    assert result.binary is True
    assert result.mime_type == "image/png"
    assert result.media_base64


def test_workspace_diff_reads_staged_and_untracked_files(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    manager = WorkspaceManager(tmp_path / "workspaces.json")
    workspace = manager.open(str(root))
    import subprocess

    subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
    tracked = root / "tracked.py"
    tracked.write_text("print('staged')\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "tracked.py"], check=True)
    untracked = root / "new.py"
    untracked.write_text("print('new')\n", encoding="utf-8")

    staged_diff = manager.diff(workspace.id, "tracked.py")
    untracked_diff = manager.diff(workspace.id, "new.py")

    assert "print('staged')" in staged_diff
    assert "print('new')" in untracked_diff


# 功能：验证变更清单返回可直接用于加载 Diff 的特殊字符文件路径。
# 策略：创建包含中文和空格的未跟踪文件，并把清单路径原样传给 diff。
def test_workspace_change_paths_round_trip_to_diff(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    manager = WorkspaceManager(tmp_path / "workspaces.json")
    workspace = manager.open(str(root))
    import subprocess

    subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
    changed = root / "中文 file.py"
    changed.write_text("print('details')\n", encoding="utf-8")

    changes = manager.list_changes(workspace.id)

    assert [change["path"] for change in changes] == ["中文 file.py"]
    assert "print('details')" in manager.diff(workspace.id, changes[0]["path"])


def test_workspace_changes_and_diff_ignore_cache_files(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    manager = WorkspaceManager(tmp_path / "workspaces.json")
    workspace = manager.open(str(root))
    import subprocess

    subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
    source = root / "src" / "cache.py"
    cached = root / ".pytest_cache" / "state.json"
    bytecode = root / "src" / "__pycache__" / "cache.cpython-313.pyc"
    source.parent.mkdir()
    cached.parent.mkdir()
    bytecode.parent.mkdir()
    source.write_text("VALUE = 'before'\n", encoding="utf-8")
    cached.write_text('{"state": "before"}\n', encoding="utf-8")
    bytecode.write_bytes(b"before")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )

    source.write_text("VALUE = 'after'\n", encoding="utf-8")
    cached.write_text('{"state": "after"}\n', encoding="utf-8")
    bytecode.write_bytes(b"after")
    (root / ".mypy_cache").mkdir()
    (root / ".mypy_cache" / "new.json").write_text("{}\n", encoding="utf-8")

    assert [change["path"] for change in manager.list_changes(workspace.id)] == ["src/cache.py"]
    assert manager.status(workspace.id)["changed_file_count"] == 1
    assert "VALUE = 'after'" in manager.diff(workspace.id)
    assert "pytest_cache" not in manager.diff(workspace.id)
    assert manager.diff(workspace.id, ".pytest_cache/state.json") == ""
    assert manager.diff_numstat(
        workspace.id,
        ["src/cache.py", ".pytest_cache/state.json", "src/__pycache__/cache.cpython-313.pyc"],
    ) == {"src/cache.py": (1, 1)}


def test_workspace_git_stage_unstage_discard_and_commit(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    tracked = root / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Sztu Test"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-m", "initial"], check=True, capture_output=True)

    manager = WorkspaceManager(tmp_path / "workspaces.json")
    workspace = manager.open(str(root))
    tracked.write_text("after\n", encoding="utf-8")

    assert manager.stage(workspace.id, ["tracked.txt"]) == ["tracked.txt"]
    assert manager.list_changes(workspace.id)[0]["index_status"] == "M"
    assert manager.unstage(workspace.id, ["tracked.txt"]) == ["tracked.txt"]
    assert manager.list_changes(workspace.id)[0]["worktree_status"] == "M"

    untracked = root / "new.txt"
    untracked.write_text("keep me\n", encoding="utf-8")
    assert manager.discard(workspace.id, ["tracked.txt", "new.txt"]) == ["tracked.txt", "new.txt"]
    assert tracked.read_text(encoding="utf-8") == "before\n"
    assert untracked.read_text(encoding="utf-8") == "keep me\n"
    assert manager.list_changes(workspace.id) == [{"path": "new.txt", "index_status": "?", "worktree_status": "?", "additions": 1, "deletions": 0}]

    tracked.write_text("committed\n", encoding="utf-8")
    manager.stage(workspace.id, ["tracked.txt"])
    commit_hash = manager.commit(workspace.id, "update tracked file")
    assert len(commit_hash) == 7
    assert manager.list_changes(workspace.id) == [{"path": "new.txt", "index_status": "?", "worktree_status": "?", "additions": 1, "deletions": 0}]


def test_workspace_git_history_returns_head_and_parent_relationship(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    tracked = root / "tracked.txt"
    subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Sztu Test"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
    tracked.write_text("first\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-m", "initial"], check=True, capture_output=True)
    tracked.write_text("second\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "commit", "-am", "second"], check=True, capture_output=True)

    manager = WorkspaceManager(tmp_path / "workspaces.json")
    workspace = manager.open(str(root))
    history = manager.history(workspace.id)
    branch = subprocess.run(
        ["git", "-C", str(root), "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert [commit["subject"] for commit in history] == ["second", "initial"]
    assert history[0]["parents"] == [history[1]["hash"]]
    assert history[0]["is_head"] is True
    assert history[1]["is_head"] is False
    assert len(str(history[0]["short_hash"])) >= 7
    assert history[0]["is_outgoing"] is False
    assert {item["name"] for item in history[0]["refs"]} == {branch}
    assert [commit["subject"] for commit in manager.history(workspace.id, 1, 1)] == ["initial"]


def test_git_output_uses_replacement_decoding(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> SimpleNamespace:
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="diff with replacement \ufffd")

    monkeypatch.setattr("sztu_code.core.workspace.manager.subprocess.run", fake_run)

    result = WorkspaceManager._git(Path("."), ["diff"])

    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"
    assert "\ufffd" in result


# \u529f\u80fd\uff1a\u9a8c\u8bc1\u5220\u9664\u5de5\u4f5c\u533a\u53ea\u4ece\u5217\u8868\u79fb\u9664\u767b\u8bb0\u8bb0\u5f55\uff0c\u78c1\u76d8\u6587\u4ef6\u4fdd\u7559
# \u8bbe\u8ba1\uff1a\u6253\u5f00\u4e34\u65f6\u9879\u76ee\u540e delete\uff0c\u65ad\u8a00\u5217\u8868\u4e3a\u7a7a\u3001\u78c1\u76d8\u76ee\u5f55\u4e0e\u6587\u4ef6\u4ecd\u5728\u3001\u91cd\u5efa manager \u540e\u8bb0\u5f55\u4e5f\u4e3a\u7a7a
def test_workspace_delete_removes_list_but_keeps_directory(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "file.txt").write_text("x", encoding="utf-8")
    recent_file = tmp_path / "state" / "workspaces.json"
    manager = WorkspaceManager(recent_file)
    workspace = manager.open(str(root))

    manager.delete(workspace.id)

    assert root.exists()
    assert (root / "file.txt").read_text(encoding="utf-8") == "x"
    assert manager.list_recent() == []
    restored = WorkspaceManager(recent_file)
    assert restored.list_recent() == []


# \u529f\u80fd\uff1a\u9a8c\u8bc1\u5220\u9664\u672a\u767b\u8bb0\u7684\u5de5\u4f5c\u533a\u629b\u51fa ValueError \u4e14\u4e0d\u4ea7\u751f\u526f\u4f5c\u7528
# \u8bbe\u8ba1\uff1a\u76f4\u63a5 delete \u4e00\u4e2a\u4e0d\u5b58\u5728\u7684 id\uff0c\u65ad\u8a00\u629b\u9519\uff0c\u6700\u8fd1\u5217\u8868\u4fdd\u6301\u4e3a\u7a7a
def test_workspace_delete_missing_raises(tmp_path: Path) -> None:
    recent_file = tmp_path / "state" / "workspaces.json"
    manager = WorkspaceManager(recent_file)

    with pytest.raises(ValueError):
        manager.delete("ws-nonexistent")

    assert manager.list_recent() == []


# \u529f\u80fd\uff1a\u9a8c\u8bc1\u76ee\u5f55\u5df2\u4e0d\u5b58\u5728\u7684\u5de5\u4f5c\u533a\u88ab\u81ea\u52a8\u8fc7\u6ee4\uff0c\u4e0d\u663e\u793a\u60ac\u6302\u9879\u76ee\u6761\u76ee
# \u8bbe\u8ba1\uff1a\u6253\u5f00\u4e34\u65f6\u76ee\u5f55\u540e\u5220\u9664\u76ee\u5f55\uff0c\u65ad\u8a00 list_recent \u4e0d\u518d\u8fd4\u56de\u8be5\u5de5\u4f5c\u533a\uff0c\u9632\u6b62\u6765\u8def\u4e0d\u660e\u7684\u65e0\u6548\u9879\u76ee
def test_list_recent_filters_missing_directory_workspaces(tmp_path: Path) -> None:
    recent_file = tmp_path / "state" / "workspaces.json"
    manager = WorkspaceManager(recent_file)
    root = tmp_path / "gone"
    root.mkdir()
    manager.open(str(root))
    assert len(manager.list_recent()) == 1

    root.rmdir()

    assert manager.list_recent() == []
