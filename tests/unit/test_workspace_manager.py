from __future__ import annotations

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
