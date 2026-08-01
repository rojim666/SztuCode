from __future__ import annotations

import hashlib
import json
import base64
import mimetypes
import os
import subprocess
from codecs import BOM_UTF8, BOM_UTF16_BE, BOM_UTF16_LE
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    id: str
    path: str
    name: str


@dataclass(frozen=True)
class FileContent:
    content: str
    encoding: str
    binary: bool = False
    truncated: bool = False
    media_base64: str | None = None
    mime_type: str | None = None


class WorkspaceManager:
    _TREE_IGNORED_NAMES = {
        ".git",
        ".idea",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        ".vscode",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
    }

    # 初始化本地工作区管理器，并加载最近打开目录记录
    def __init__(self, recent_file: Path) -> None:
        self._recent_file = recent_file.expanduser()
        self._workspaces: dict[str, Workspace] = {}
        self._load_recent()

    # 打开本地目录并将其加入最近工作区列表
    def open(self, path: str) -> Workspace:
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_dir():
            raise ValueError("workspace path must be an existing directory")
        workspace = self._make_workspace(resolved)
        self._workspaces[workspace.id] = workspace
        self._save_recent()
        return workspace

    # 返回最近工作区，最近打开的目录排在最前面
    def list_recent(self) -> list[Workspace]:
        return list(self._workspaces.values())

    # 返回工作区的 Git 分支和未提交文件摘要
    def status(self, workspace_id: str) -> dict[str, object]:
        workspace = self.get(workspace_id)
        root = Path(workspace.path)
        branch = self._git(root, ["branch", "--show-current"]).strip()
        changes = self._git(root, ["status", "--short"])
        changed_files = [line for line in changes.splitlines() if line]
        return {
            "workspace": workspace,
            "branch": branch or None,
            "is_git_repository": bool(branch or self._is_git_repository(root)),
            "changed_file_count": len(changed_files),
        }

    # 构建受深度和条目数限制的目录树，供客户端文件面板展示
    def tree(
        self,
        workspace_id: str,
        relative_path: str = "",
        *,
        max_depth: int = 2,
        max_entries: int = 300,
    ) -> list[dict[str, object]]:
        root = self._resolve_in_workspace(workspace_id, relative_path)
        if not root.is_dir():
            raise ValueError("workspace tree path must be a directory")
        count = 0

        # 先收集当前层，再递归展开，避免大型目录耗尽配额后隐藏同级文件。
        def build(path: Path, depth: int) -> list[dict[str, object]]:
            nonlocal count
            nodes: list[dict[str, object]] = []
            if depth > max_depth:
                return nodes
            try:
                entries = sorted(
                    (
                        entry for entry in path.iterdir()
                        if entry.name not in self._TREE_IGNORED_NAMES
                    ),
                    key=lambda item: (not item.is_dir(), item.name.lower()),
                )
            except OSError:
                return nodes
            for entry in entries:
                if count >= max_entries:
                    break
                count += 1
                node: dict[str, object] = {
                    "path": entry.relative_to(Path(self.get(workspace_id).path)).as_posix(),
                    "name": entry.name,
                    "kind": "directory" if entry.is_dir() else "file",
                }
                nodes.append(node)
            if depth < max_depth:
                for node, entry in zip(nodes, entries, strict=False):
                    if count >= max_entries:
                        break
                    if entry.is_dir():
                        node["children"] = build(entry, depth + 1)
            return nodes

        return build(root, 0)

    # 读取工作区内 UTF-8 文本文件，拒绝目录穿越与超大文件
    def read_file(
        self,
        workspace_id: str,
        relative_path: str,
        *,
        max_bytes: int = 1_000_000,
    ) -> FileContent:
        path = self._resolve_in_workspace(workspace_id, relative_path)
        if not path.is_file():
            raise ValueError("file path must point to an existing file")
        size = path.stat().st_size
        mime_type, _ = mimetypes.guess_type(path.name)
        image_limit = 5_000_000
        read_limit = image_limit if mime_type and mime_type.startswith("image/") else max_bytes
        with path.open("rb") as stream:
            data = stream.read(read_limit)
        content, encoding, binary = self._decode_text(data)
        media_base64 = None
        if binary and mime_type and mime_type.startswith("image/") and size <= image_limit:
            media_base64 = base64.b64encode(data).decode("ascii")
        return FileContent(
            content=content,
            encoding=encoding,
            binary=binary,
            truncated=size > read_limit,
            media_base64=media_base64,
            mime_type=mime_type if media_base64 else None,
        )

    # 在工作区文本文件中搜索字面量，并返回有限的路径、行号与内容片段
    def search(
        self,
        workspace_id: str,
        query: str,
        *,
        max_results: int = 100,
    ) -> list[dict[str, object]]:
        if not query:
            raise ValueError("search query must not be empty")
        workspace = self.get(workspace_id)
        root = Path(workspace.path)
        matches: list[dict[str, object]] = []
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().lower()):
            if len(matches) >= max_results:
                break
            is_ignored = any(
                part in {".git", "__pycache__", "node_modules"} for part in path.parts
            )
            if not path.is_file() or is_ignored:
                continue
            try:
                if path.stat().st_size > 1_000_000:
                    continue
                data = path.read_bytes()
                content, _encoding, binary = self._decode_text(data)
                if binary:
                    continue
                lines = content.splitlines()
            except OSError:
                continue
            for line_number, line in enumerate(lines, start=1):
                if query in line:
                    matches.append({
                        "path": path.relative_to(root).as_posix(),
                        "line": line_number,
                        "preview": line[:300],
                    })
                    if len(matches) >= max_results:
                        break
        return matches

    # 返回 Git 工作区中未提交文件的状态摘要，供变更审阅面板展示
    def list_changes(self, workspace_id: str) -> list[dict[str, str]]:
        workspace = self.get(workspace_id)
        raw = self._git(Path(workspace.path), ["status", "--porcelain"])
        changes: list[dict[str, str]] = []
        for line in raw.splitlines():
            if len(line) < 4:
                continue
            index_status, worktree_status, path = line[0], line[1], line[3:]
            changes.append({
                "path": path,
                "index_status": index_status,
                "worktree_status": worktree_status,
            })
        return changes

    # 返回工作区或指定文件的未提交 Git diff，不执行任何修改操作
    def diff(self, workspace_id: str, relative_path: str | None = None) -> str:
        workspace = self.get(workspace_id)
        root = Path(workspace.path)
        args = ["diff", "--no-ext-diff"]
        if relative_path is not None:
            self._resolve_in_workspace(workspace_id, relative_path)
            args.extend(["--", relative_path])
        diff = self._git(root, args)
        if relative_path is not None and not diff:
            diff = self._git(root, ["diff", "--cached", "--no-ext-diff", "--", relative_path])
        if relative_path is not None and not diff:
            untracked = self._git(
                root, ["ls-files", "--others", "--exclude-standard", "--", relative_path]
            ).strip()
            if untracked:
                diff = self._git(
                    root,
                    ["diff", "--no-index", "--no-ext-diff", os.devnull, relative_path],
                    success_codes=(0, 1),
                )
        return diff

    # 根据稳定 workspace_id 取回已登记的工作区，不存在时拒绝请求
    def get(self, workspace_id: str) -> Workspace:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise ValueError("workspace not found")
        return workspace

    # 将相对路径限制在指定工作区根目录内，防止读取任意本地文件
    def _resolve_in_workspace(self, workspace_id: str, relative_path: str) -> Path:
        root = Path(self.get(workspace_id).path)
        candidate = (root / relative_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            raise ValueError("path escapes workspace") from None
        return candidate

    # 从最近记录文件恢复仍然存在的目录
    def _load_recent(self) -> None:
        if not self._recent_file.exists():
            return
        try:
            paths = json.loads(self._recent_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return
        if not isinstance(paths, list):
            return
        for value in paths:
            if not isinstance(value, str):
                continue
            path = Path(value).expanduser()
            if path.is_dir():
                workspace = self._make_workspace(path.resolve())
                self._workspaces[workspace.id] = workspace

    # 将当前工作区目录写入最近记录文件
    def _save_recent(self) -> None:
        self._recent_file.parent.mkdir(parents=True, exist_ok=True)
        paths = [workspace.path for workspace in self._workspaces.values()]
        self._recent_file.write_text(
            json.dumps(paths, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    # 从目录绝对路径生成稳定且不可歧义的工作区标识
    @staticmethod
    def _make_workspace(path: Path) -> Workspace:
        workspace_id = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
        return Workspace(id=f"ws-{workspace_id}", path=str(path), name=path.name or str(path))

    # 执行只读 Git 命令；非 Git 目录或 Git 不存在时返回空字符串
    @staticmethod
    def _git(
        root: Path,
        args: list[str],
        *,
        success_codes: tuple[int, ...] = (0,),
    ) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(root), *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        return result.stdout if result.returncode in success_codes else ""

    @staticmethod
    def _decode_text(data: bytes) -> tuple[str, str, bool]:
        if not data:
            return "", "UTF-8", False
        if data.startswith(BOM_UTF8):
            return data.decode("utf-8-sig"), "UTF-8 BOM", False
        if data.startswith(BOM_UTF16_LE):
            return data.decode("utf-16"), "UTF-16 LE", False
        if data.startswith(BOM_UTF16_BE):
            return data.decode("utf-16"), "UTF-16 BE", False

        sample = data[:4096]
        even_nuls = sample[0::2].count(0)
        odd_nuls = sample[1::2].count(0)
        pairs = max(1, len(sample) // 2)
        if odd_nuls / pairs > 0.4:
            return data.decode("utf-16-le", errors="replace"), "UTF-16 LE", False
        if even_nuls / pairs > 0.4:
            return data.decode("utf-16-be", errors="replace"), "UTF-16 BE", False

        control_count = sum(byte < 9 or 13 < byte < 32 for byte in sample)
        if b"\x00" in sample or control_count / len(sample) > 0.08:
            return "", "Binary", True
        try:
            return data.decode("utf-8"), "UTF-8", False
        except UnicodeDecodeError:
            pass
        try:
            return data.decode("gb18030"), "GB18030", False
        except UnicodeDecodeError:
            return data.decode("utf-8", errors="replace"), "UTF-8 (replacement)", False

    # 检查目录是否属于 Git 仓库，即使仓库尚未创建分支也能正确识别
    def _is_git_repository(self, root: Path) -> bool:
        return self._git(root, ["rev-parse", "--is-inside-work-tree"]).strip() == "true"
