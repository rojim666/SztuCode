from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import subprocess
from codecs import BOM_UTF8, BOM_UTF16_BE, BOM_UTF16_LE
from dataclasses import dataclass, replace
from pathlib import Path

from sztu_code.core.workspace.project_profile import ProjectProfile, detect_project_profile


@dataclass(frozen=True)
class Workspace:
    id: str
    path: str
    name: str
    archived: bool = False
    pinned: bool = False


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
    _CHANGE_IGNORED_PARTS = {
        ".cache",
        ".git",
        ".hypothesis",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".sztu",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
    }
    _CHANGE_IGNORED_SUFFIXES = (".pyc", ".pyo")

    # 初始化本地工作区管理器，并加载最近打开目录记录
    def __init__(self, recent_file: Path) -> None:
        self._recent_file = recent_file.expanduser()
        self._workspaces: dict[str, Workspace] = {}
        self._profiles: dict[str, ProjectProfile] = {}
        self._load_recent()

    # 打开本地目录并将其加入最近工作区列表
    def open(self, path: str) -> Workspace:
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_dir():
            raise ValueError("workspace path must be an existing directory")
        workspace = self._make_workspace(resolved, archived=False)
        self._workspaces[workspace.id] = workspace
        self._profiles.pop(workspace.id, None)
        self._save_recent()
        return workspace

    # 返回最近工作区，最近打开的目录排在最前面；目录已不存在的悬挂条目自动过滤
    def list_recent(self, *, include_archived: bool = True) -> list[Workspace]:
        return [
            workspace
            for workspace in self._workspaces.values()
            if (include_archived or not workspace.archived)
            and Path(workspace.path).is_dir()
        ]

    def archive(self, workspace_id: str) -> Workspace:
        return self._set_archived(workspace_id, True)

    def resume(self, workspace_id: str) -> Workspace:
        return self._set_archived(workspace_id, False)

    def pin(self, workspace_id: str, pinned: bool) -> Workspace:
        current = self.get(workspace_id)
        if current.pinned == pinned:
            return current
        updated = replace(current, pinned=pinned)
        self._workspaces[workspace_id] = updated
        self._save_recent()
        return updated

    def rename(self, workspace_id: str, name: str) -> Workspace:
        current = self.get(workspace_id)
        normalized = name.strip()
        if not normalized:
            raise ValueError("workspace name is required")
        updated = replace(current, name=normalized[:120])
        self._workspaces[workspace_id] = updated
        self._save_recent()
        return updated

    def _set_archived(self, workspace_id: str, archived: bool) -> Workspace:
        current = self.get(workspace_id)
        if current.archived == archived:
            return current
        updated = replace(current, archived=archived)
        self._workspaces[workspace_id] = updated
        self._save_recent()
        return updated

    # 从项目列表删除工作区（保留磁盘文件），仅移除登记记录
    def delete(self, workspace_id: str) -> None:
        self.get(workspace_id)  # 不存在时抛错
        del self._workspaces[workspace_id]
        self._profiles.pop(workspace_id, None)
        self._save_recent()

    # 返回工作区的 Git 分支和未提交文件摘要
    def status(self, workspace_id: str) -> dict[str, object]:
        workspace = self.get(workspace_id)
        root = Path(workspace.path)
        branch = self._git(root, ["branch", "--show-current"]).strip()
        changes = self._git(root, ["status", "--short"])
        changed_files = [
            line
            for line in changes.splitlines()
            if line and not self._is_ignored_status_line(line)
        ]
        return {
            "workspace": workspace,
            "branch": branch or None,
            "is_git_repository": bool(branch or self._is_git_repository(root)),
            "changed_file_count": len(changed_files),
        }

    # 返回工作区的离线项目画像；默认复用缓存，显式刷新时重新扫描磁盘。
    def profile(self, workspace_id: str, *, refresh: bool = False) -> ProjectProfile:
        if not refresh and (cached := self._profiles.get(workspace_id)) is not None:
            return cached
        workspace = self.get(workspace_id)
        profile = detect_project_profile(Path(workspace.path))
        self._profiles[workspace_id] = profile
        return profile

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
    def list_changes(self, workspace_id: str) -> list[dict[str, object]]:
        workspace = self.get(workspace_id)
        raw = self._git(Path(workspace.path), ["status", "--porcelain=v1", "-z"])
        changes: list[dict[str, str]] = []
        records = raw.split("\0")
        index = 0
        while index < len(records):
            record = records[index]
            index += 1
            if len(record) < 4:
                continue
            index_status, worktree_status, path = record[0], record[1], record[3:]
            renamed_from: str | None = None
            if index_status in {"R", "C"} or worktree_status in {"R", "C"}:
                if index < len(records):
                    renamed_from = records[index]
                    index += 1
            if self._is_ignored_change_path(path) or (
                renamed_from is not None and self._is_ignored_change_path(renamed_from)
            ):
                continue
            changes.append({
                "path": path,
                "index_status": index_status,
                "worktree_status": worktree_status,
            })
        numstat = self.diff_numstat(workspace_id, [str(change["path"]) for change in changes])
        return [
            {
                **change,
                "additions": numstat.get(str(change["path"]), (0, 0))[0],
                "deletions": numstat.get(str(change["path"]), (0, 0))[1],
            }
            for change in changes
        ]

    # 返回工作区或指定文件的未提交 Git diff，不执行任何修改操作
    def diff(self, workspace_id: str, relative_path: str | None = None) -> str:
        workspace = self.get(workspace_id)
        root = Path(workspace.path)
        args = ["diff", "--no-ext-diff"]
        if relative_path is not None:
            self._resolve_in_workspace(workspace_id, relative_path)
            if self._is_ignored_change_path(relative_path):
                return ""
            args.extend(["--", relative_path])
        else:
            args.extend(["--", ".", *self._change_exclude_pathspecs()])
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

    # 将指定文件加入 git 暂存区（审核"接受" = 暂存待提交）
    def stage(self, workspace_id: str, paths: list[str]) -> list[str]:
        workspace = self.get(workspace_id)
        root = Path(workspace.path)
        git_paths: list[str] = []
        for relative_path in paths:
            self._resolve_in_workspace(workspace_id, relative_path)
            git_paths.append(relative_path.replace("\\", "/"))
        self._git(root, ["add", "--", *git_paths])
        return paths

    # 将指定文件移出暂存区，保留工作区内容
    def unstage(self, workspace_id: str, paths: list[str]) -> list[str]:
        workspace = self.get(workspace_id)
        root = Path(workspace.path)
        git_paths = [self._git_relative_path(workspace_id, path) for path in paths]
        self._git(root, ["reset", "--", *git_paths])
        return paths

    # 丢弃已跟踪文件的暂存区与工作区改动；未跟踪文件不会被删除
    def discard(self, workspace_id: str, paths: list[str]) -> list[str]:
        workspace = self.get(workspace_id)
        root = Path(workspace.path)
        git_paths = [self._git_relative_path(workspace_id, path) for path in paths]
        tracked = [path for path in git_paths if self._git(root, ["ls-files", "--error-unmatch", "--", path]).strip()]
        if tracked:
            self._git(root, ["restore", "--source=HEAD", "--staged", "--worktree", "--", *tracked])
        return paths

    # 创建 Git 提交并返回提交哈希
    def commit(self, workspace_id: str, message: str) -> str:
        if not message.strip():
            raise ValueError("commit message must not be empty")
        workspace = self.get(workspace_id)
        root = Path(workspace.path)
        result = self._git_result(root, ["commit", "-m", message])
        if result[0] != 0:
            raise ValueError(result[2].strip() or result[1].strip() or "git commit failed")
        commit_hash = self._git(root, ["rev-parse", "--short", "HEAD"]).strip()
        return commit_hash

    # 返回提交历史和父提交关系，供源代码管理图谱绘制提交节点与分支线。
    def history(
        self, workspace_id: str, limit: int = 100, skip: int = 0
    ) -> list[dict[str, object]]:
        workspace = self.get(workspace_id)
        root = Path(workspace.path)
        head_hash = self._git(root, ["rev-parse", "HEAD"]).strip()
        upstream = self._git(
            root,
            ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        ).strip()
        outgoing_hashes = set(
            self._git(root, ["rev-list", f"{upstream}..HEAD"]).splitlines()
        ) if upstream else set()
        refs_by_hash: dict[str, list[dict[str, str]]] = {}
        for line in self._git(root, ["show-ref", "--dereference"]).splitlines():
            try:
                object_hash, full_name = line.split(" ", 1)
            except ValueError:
                continue
            peeled = full_name.endswith("^{}")
            full_name = full_name.removesuffix("^{}")
            if full_name.startswith("refs/heads/"):
                kind, name = "head", full_name.removeprefix("refs/heads/")
            elif full_name.startswith("refs/remotes/"):
                kind, name = "remote", full_name.removeprefix("refs/remotes/")
            elif full_name.startswith("refs/tags/"):
                kind, name = "tag", full_name.removeprefix("refs/tags/")
            else:
                continue
            item = {"name": name, "kind": kind}
            if peeled:
                for values in refs_by_hash.values():
                    if item in values:
                        values.remove(item)
            if item not in refs_by_hash.setdefault(object_hash, []):
                refs_by_hash[object_hash].append(item)
        raw = self._git(
            root,
            [
                "log", "--all", "--topo-order", "--date=iso-strict",
                f"--skip={skip}", f"-n{limit}",
                "--pretty=format:%H%x00%h%x00%P%x00%an%x00%ad%x00%s%x1e",
            ],
        )
        commits: list[dict[str, object]] = []
        for record in raw.split("\x1e"):
            fields = record.strip("\x00\n").split("\x00")
            if len(fields) != 6 or not fields[0]:
                continue
            commits.append({
                "hash": fields[0],
                "short_hash": fields[1],
                "parents": fields[2].split() if fields[2] else [],
                "author": fields[3],
                "date": fields[4],
                "subject": fields[5],
                "is_head": fields[0] == head_hash,
                "is_outgoing": fields[0] in outgoing_hashes,
                "refs": refs_by_hash.get(fields[0], []),
            })
        return commits

    def _git_relative_path(self, workspace_id: str, relative_path: str) -> str:
        self._resolve_in_workspace(workspace_id, relative_path)
        return relative_path.replace("\\", "/")

    # 统计相对 HEAD 的新增/删除行数；未跟踪文件没有 HEAD 对照时按文本行计为新增。
    def diff_numstat(self, workspace_id: str, paths: list[str]) -> dict[str, tuple[int, int]]:
        workspace = self.get(workspace_id)
        root = Path(workspace.path)
        stats: dict[str, tuple[int, int]] = {}
        for relative_path in paths:
            self._resolve_in_workspace(workspace_id, relative_path)
            if self._is_ignored_change_path(relative_path):
                continue
            git_path = relative_path.replace("\\", "/")
            # HEAD diff 同时包含暂存区和工作区改动，避免暂存后只统计当前文件总行数。
            raw = self._git(root, ["diff", "HEAD", "--numstat", "--", git_path]).strip()
            if not raw:
                raw = self._git(root, ["diff", "--cached", "--numstat", "--", git_path]).strip()
            if not raw:
                raw = self._git(root, ["diff", "--numstat", "--", git_path]).strip()
            if raw:
                parts = raw.split(None, 2)
                if len(parts) >= 2 and parts[0] != "-" and parts[1] != "-":
                    try:
                        stats[relative_path] = (int(parts[0]), int(parts[1]))
                        continue
                    except ValueError:
                        pass
                # Git uses -/- for binary files; binary content has no line count.
                if len(parts) >= 2 and parts[0] == "-" and parts[1] == "-":
                    stats[relative_path] = (0, 0)
                    continue
            file_path = root / relative_path
            if file_path.is_file():
                try:
                    data = file_path.read_bytes()
                    _content, _encoding, binary = self._decode_text(data)
                    line_count = 0 if binary else len(data.decode("utf-8", errors="replace").splitlines())
                except OSError:
                    line_count = 0
                stats[relative_path] = (line_count, 0)
            else:
                stats[relative_path] = (0, 0)
        return stats

    @classmethod
    def _is_ignored_change_path(cls, relative_path: str) -> bool:
        normalized = relative_path.replace("\\", "/").strip().strip('"')
        parts = [part for part in normalized.split("/") if part and part != "."]
        if any(part in cls._CHANGE_IGNORED_PARTS for part in parts):
            return True
        return any(normalized.lower().endswith(suffix) for suffix in cls._CHANGE_IGNORED_SUFFIXES)

    @classmethod
    def _is_ignored_status_line(cls, line: str) -> bool:
        path = line[3:] if len(line) >= 4 else ""
        # Git reports renames as "old -> new"; either side being ignored is
        # enough to keep generated/cache files out of the review surface.
        return any(cls._is_ignored_change_path(part.strip()) for part in path.split(" -> "))

    @classmethod
    def _change_exclude_pathspecs(cls) -> list[str]:
        directory_patterns = [
            pattern
            for part in sorted(cls._CHANGE_IGNORED_PARTS)
            for pattern in (f":(exclude){part}/**", f":(exclude)**/{part}/**")
        ]
        suffix_patterns = [
            f":(exclude)**/*{suffix}" for suffix in cls._CHANGE_IGNORED_SUFFIXES
        ]
        return [*directory_patterns, *suffix_patterns]

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
                if isinstance(value, dict) and isinstance(value.get("path"), str):
                    path = Path(value["path"]).expanduser()
                    archived = bool(value.get("archived", False))
                    pinned = bool(value.get("pinned", False))
                else:
                    continue
            else:
                path = Path(value).expanduser()
                archived = False
                pinned = False
            if path.is_dir():
                workspace = self._make_workspace(path.resolve(), archived=archived, pinned=pinned)
                self._workspaces[workspace.id] = workspace

    # 将当前工作区目录写入最近记录文件
    def _save_recent(self) -> None:
        self._recent_file.parent.mkdir(parents=True, exist_ok=True)
        paths = [
            {"path": workspace.path, "archived": workspace.archived, "pinned": workspace.pinned}
            for workspace in self._workspaces.values()
        ]
        self._recent_file.write_text(
            json.dumps(paths, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    # 从目录绝对路径生成稳定且不可歧义的工作区标识
    @staticmethod
    def _make_workspace(path: Path, *, archived: bool = False, pinned: bool = False) -> Workspace:
        workspace_id = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
        return Workspace(
            id=f"ws-{workspace_id}",
            path=str(path),
            name=path.name or str(path),
            archived=archived,
            pinned=pinned,
        )

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
    def _git_result(root: Path, args: list[str]) -> tuple[int, str, str]:
        try:
            result = subprocess.run(
                ["git", "-C", str(root), *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return 1, "", str(error)
        return result.returncode, result.stdout, result.stderr

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
