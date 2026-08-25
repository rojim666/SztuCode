from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from urllib.parse import urlsplit

MarketplaceKind = Literal["default", "git", "local"]


@dataclass(frozen=True)
class Marketplace:
    id: str
    name: str
    display_name: str
    source: str
    kind: MarketplaceKind
    root_path: Path
    manifest_path: Path
    ref: str = ""
    sparse_paths: tuple[str, ...] = ()
    plugin_count: int = 0
    updated_at: str = ""
    removable: bool = False
    updatable: bool = False


@dataclass(frozen=True)
class MarketplacePlugin:
    id: str
    marketplace_id: str
    marketplace_name: str
    name: str
    display_name: str
    description: str
    version: str
    category: str
    publisher: str
    source_type: str
    source_path: Path | None
    source_url: str
    source_ref: str
    source_sha: str
    relative_path: str
    installation: str
    authentication: str


@dataclass(frozen=True)
class MaterializedPlugin:
    path: Path
    temporary_root: Path | None = None


_GITHUB_SHORTHAND_RE = re.compile(
    r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:@(?P<ref>[^\s]+))?$"
)
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


# 返回当前 UTC 时间，供市场刷新状态稳定序列化
def _now() -> str:
    return datetime.now(UTC).isoformat()


# 将展示名称转换为安全的稳定路径片段
def _slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return normalized[:60] or "marketplace"


# 校验稀疏检出路径为仓库内的相对 POSIX 路径
def _normalize_sparse_path(value: str) -> str:
    normalized = value.strip().replace("\\", "/").removeprefix("./").rstrip("/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"invalid sparse path: {value}")
    return path.as_posix()


# 确保相对路径解析结果仍位于给定市场根目录之内
def _resolve_inside(root: Path, value: str) -> Path:
    normalized = value.strip().replace("\\", "/")
    if not normalized.startswith("./"):
        raise ValueError("marketplace plugin paths must start with ./")
    candidate = (root / normalized[2:]).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise ValueError("marketplace plugin path escapes its root")
    return candidate


class MarketplaceManager:
    # 初始化个人配置、工作区和官方兼容 .agents 根目录
    def __init__(
        self,
        project_root: Path | None = None,
        config_root: Path | None = None,
        agents_root: Path | None = None,
    ) -> None:
        self._project_root = (project_root or Path.cwd()).expanduser().resolve()
        self._config_root = (config_root or Path("~/.sztu")).expanduser().resolve()
        self._agents_root = (agents_root or Path("~/.agents")).expanduser().resolve()
        self._config_file = self._config_root / "plugin-marketplaces.json"
        self._cache_root = self._config_root / "marketplaces"

    # 添加 GitHub、Git URL 或本地目录市场，并在返回前验证 marketplace.json
    def add(
        self,
        source: str,
        *,
        ref: str = "",
        sparse_paths: list[str] | None = None,
    ) -> Marketplace:
        raw_source = source.strip()
        if not raw_source:
            raise ValueError("marketplace source is required")
        normalized_sparse = tuple(
            dict.fromkeys(_normalize_sparse_path(value) for value in (sparse_paths or []))
        )
        local = Path(raw_source).expanduser()
        if local.is_dir():
            if ref or normalized_sparse:
                raise ValueError("Git ref and sparse paths are only valid for Git sources")
            resolved = local.resolve()
            manifest = self._find_marketplace_manifest(resolved, normalized_sparse)
            marketplace_id = self._marketplace_id("local", str(resolved), "", ())
            entries = self._load_entries()
            if any(item.get("id") == marketplace_id for item in entries):
                raise ValueError("marketplace source is already configured")
            entries.append(
                {
                    "id": marketplace_id,
                    "kind": "local",
                    "source": str(resolved),
                    "ref": "",
                    "sparse_paths": [],
                    "updated_at": _now(),
                }
            )
            self._write_entries(entries)
            return self._marketplace_from_manifest(
                marketplace_id,
                resolved,
                manifest,
                source=str(resolved),
                kind="local",
                updated_at=entries[-1]["updated_at"],
                removable=True,
            )

        git_url, inline_ref, label = self._normalize_git_source(raw_source)
        selected_ref = ref.strip() or inline_ref
        marketplace_id = self._marketplace_id(
            "git", git_url, selected_ref, normalized_sparse
        )
        entries = self._load_entries()
        if any(item.get("id") == marketplace_id for item in entries):
            raise ValueError("marketplace source is already configured")
        destination = self._cache_root / f"{_slug(label)}-{marketplace_id[-12:]}"
        self._clone_marketplace(git_url, destination, selected_ref, normalized_sparse)
        try:
            manifest = self._find_marketplace_manifest(destination, normalized_sparse)
        except Exception:
            self._remove_owned_tree(destination)
            raise
        updated_at = _now()
        entries.append(
            {
                "id": marketplace_id,
                "kind": "git",
                "source": raw_source,
                "git_url": git_url,
                "cache_path": str(destination),
                "ref": selected_ref,
                "sparse_paths": list(normalized_sparse),
                "updated_at": updated_at,
            }
        )
        self._write_entries(entries)
        return self._marketplace_from_manifest(
            marketplace_id,
            destination,
            manifest,
            source=raw_source,
            kind="git",
            ref=selected_ref,
            sparse_paths=normalized_sparse,
            updated_at=updated_at,
            removable=True,
            updatable=True,
        )

    # 列出工作区、个人默认市场以及显式配置的市场源
    def list_marketplaces(self) -> list[Marketplace]:
        result: list[Marketplace] = []
        seen_manifests: set[Path] = set()
        defaults = [
            (
                self._project_root,
                self._project_root / ".agents" / "plugins" / "marketplace.json",
                "workspace",
            ),
            (
                self._project_root,
                self._project_root / ".claude-plugin" / "marketplace.json",
                "workspace-legacy",
            ),
            (
                self._agents_root,
                self._agents_root / "plugins" / "marketplace.json",
                "personal",
            ),
        ]
        for root, manifest, label in defaults:
            if not manifest.is_file():
                continue
            resolved_manifest = manifest.resolve()
            if resolved_manifest in seen_manifests:
                continue
            seen_manifests.add(resolved_manifest)
            try:
                result.append(
                    self._marketplace_from_manifest(
                        f"default:{label}",
                        root,
                        resolved_manifest,
                        source=str(resolved_manifest),
                        kind="default",
                    )
                )
            except ValueError:
                continue
        for entry in self._load_entries():
            try:
                kind = str(entry.get("kind", ""))
                marketplace_id = str(entry["id"])
                if kind == "git":
                    root = Path(str(entry["cache_path"])).expanduser().resolve()
                elif kind == "local":
                    root = Path(str(entry["source"])).expanduser().resolve()
                else:
                    continue
                sparse = tuple(str(value) for value in entry.get("sparse_paths", []))
                manifest = self._find_marketplace_manifest(root, sparse)
                result.append(
                    self._marketplace_from_manifest(
                        marketplace_id,
                        root,
                        manifest,
                        source=str(entry.get("source", "")),
                        kind=kind,  # type: ignore[arg-type]
                        ref=str(entry.get("ref", "")),
                        sparse_paths=sparse,
                        updated_at=str(entry.get("updated_at", "")),
                        removable=True,
                        updatable=kind == "git",
                    )
                )
            except (KeyError, OSError, TypeError, ValueError):
                continue
        return result

    # 合并所有有效市场中的插件条目，单个损坏条目不会阻断其他市场
    def list_plugins(self) -> list[MarketplacePlugin]:
        result: list[MarketplacePlugin] = []
        for marketplace in self.list_marketplaces():
            try:
                payload = json.loads(marketplace.manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                continue
            entries = payload.get("plugins", []) if isinstance(payload, dict) else []
            if not isinstance(entries, list):
                continue
            for entry in entries:
                try:
                    plugin = self._parse_plugin_entry(marketplace, entry)
                    if plugin is not None:
                        result.append(plugin)
                except (OSError, TypeError, ValueError):
                    continue
        return result

    # 刷新一个或全部 Git 市场，保留本地和默认市场原样
    def refresh(self, marketplace_id: str | None = None) -> list[Marketplace]:
        entries = self._load_entries()
        matched = False
        for entry in entries:
            if entry.get("kind") != "git":
                continue
            if marketplace_id is not None and entry.get("id") != marketplace_id:
                continue
            matched = True
            root = Path(str(entry.get("cache_path", ""))).expanduser().resolve()
            self._assert_owned_cache_path(root)
            ref = str(entry.get("ref", "")).strip()
            if ref:
                self._run_git(
                    ["-C", str(root), "fetch", "--depth", "1", "origin", ref],
                    timeout=120,
                )
                self._run_git(
                    ["-C", str(root), "checkout", "--detach", "FETCH_HEAD"],
                    timeout=60,
                )
            else:
                self._run_git(["-C", str(root), "pull", "--ff-only"], timeout=120)
            entry["updated_at"] = _now()
        if marketplace_id is not None and not matched:
            raise ValueError(f"updatable marketplace not found: {marketplace_id}")
        self._write_entries(entries)
        return self.list_marketplaces()

    # 从配置中移除市场源，并仅删除 SztuCode 自己创建的 Git 快照
    def remove(self, marketplace_id: str) -> None:
        entries = self._load_entries()
        target = next((item for item in entries if item.get("id") == marketplace_id), None)
        if target is None:
            raise ValueError(f"configured marketplace not found: {marketplace_id}")
        if target.get("kind") == "git":
            cache_path = Path(str(target.get("cache_path", ""))).expanduser().resolve()
            self._remove_owned_tree(cache_path)
        self._write_entries([item for item in entries if item.get("id") != marketplace_id])

    # 将市场插件解析为可安装本地目录，远程来源使用受控临时快照
    def materialize_plugin(self, plugin_id: str) -> MaterializedPlugin:
        plugin = next((item for item in self.list_plugins() if item.id == plugin_id), None)
        if plugin is None:
            raise ValueError(f"marketplace plugin not found: {plugin_id}")
        if plugin.source_path is not None:
            if not plugin.source_path.is_dir():
                raise ValueError(f"plugin source directory not found: {plugin.name}")
            return MaterializedPlugin(path=plugin.source_path)
        if not plugin.source_url:
            raise ValueError(f"plugin source is not installable: {plugin.name}")
        temporary = self._cache_root / ".tmp" / f"plugin-{uuid.uuid4().hex}"
        self._clone_marketplace(
            plugin.source_url,
            temporary,
            plugin.source_ref,
            (plugin.relative_path.removeprefix("./"),) if plugin.relative_path else (),
            sha=plugin.source_sha,
        )
        path = (
            _resolve_inside(temporary, plugin.relative_path)
            if plugin.relative_path
            else temporary
        )
        return MaterializedPlugin(path=path, temporary_root=temporary)

    # 清理 materialize_plugin 创建的受控临时目录
    def cleanup_materialized(self, materialized: MaterializedPlugin) -> None:
        if materialized.temporary_root is not None:
            self._remove_owned_tree(materialized.temporary_root, allow_temporary=True)

    # 将来源转换为 Git URL，并兼容 owner/repo@ref 简写
    @staticmethod
    def _normalize_git_source(source: str) -> tuple[str, str, str]:
        shorthand = _GITHUB_SHORTHAND_RE.fullmatch(source)
        if shorthand:
            owner = shorthand.group("owner")
            repo = shorthand.group("repo").removesuffix(".git")
            inline_ref = shorthand.group("ref") or ""
            return f"https://github.com/{owner}/{repo}.git", inline_ref, repo
        if source.startswith("git@"):
            repo = source.rsplit("/", 1)[-1].removesuffix(".git")
            return source, "", repo
        parsed = urlsplit(source)
        if parsed.scheme not in {"http", "https", "ssh"} or not parsed.hostname:
            raise ValueError(
                "marketplace source must be owner/repo, a Git URL, or a local directory"
            )
        has_disallowed_username = bool(parsed.username) and parsed.scheme != "ssh"
        if has_disallowed_username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError(
                "Git marketplace URLs cannot contain credentials, queries, or fragments"
            )
        repo = Path(parsed.path.rstrip("/")).name.removesuffix(".git")
        return source, "", repo or "marketplace"

    # 生成由来源、引用和稀疏路径共同决定的稳定市场标识
    @staticmethod
    def _marketplace_id(
        kind: str,
        source: str,
        ref: str,
        sparse_paths: tuple[str, ...],
    ) -> str:
        digest = hashlib.sha256(
            json.dumps([kind, source, ref, sparse_paths], ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:16]
        return f"configured:{digest}"

    # 使用参数数组执行 Git，避免 shell 插值并返回可读错误
    @staticmethod
    def _run_git(args: list[str], *, timeout: int) -> None:
        try:
            completed = subprocess.run(
                ["git", *args],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except FileNotFoundError as error:
            raise ValueError("Git is required to add this marketplace") from error
        except subprocess.TimeoutExpired as error:
            raise ValueError("Git marketplace operation timed out") from error
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or "Git command failed"
            raise ValueError(message[-1200:])

    # 克隆 Git 市场并按需应用引用、稀疏检出或固定提交
    def _clone_marketplace(
        self,
        git_url: str,
        destination: Path,
        ref: str,
        sparse_paths: tuple[str, ...],
        *,
        sha: str = "",
    ) -> None:
        if destination.exists():
            raise ValueError("marketplace cache target already exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        clone_args = ["clone", "--filter=blob:none", "--no-tags"]
        if not sha:
            clone_args.extend(["--depth", "1"])
        if sparse_paths:
            clone_args.append("--sparse")
        clone_args.extend([git_url, str(destination)])
        try:
            self._run_git(clone_args, timeout=180)
            selected_revision = sha or ref
            if selected_revision:
                self._run_git(
                    [
                        "-C",
                        str(destination),
                        "fetch",
                        "--depth",
                        "1",
                        "origin",
                        selected_revision,
                    ],
                    timeout=120,
                )
                self._run_git(
                    ["-C", str(destination), "checkout", "--detach", "FETCH_HEAD"],
                    timeout=60,
                )
            if sparse_paths:
                self._run_git(
                    ["-C", str(destination), "sparse-checkout", "set", "--no-cone", *sparse_paths],
                    timeout=60,
                )
        except Exception:
            self._remove_owned_tree(destination, allow_temporary=True)
            raise

    # 查找标准位置或稀疏目录内唯一的 marketplace.json
    @staticmethod
    def _find_marketplace_manifest(root: Path, sparse_paths: tuple[str, ...]) -> Path:
        if not root.is_dir():
            raise ValueError("marketplace root must be an existing directory")
        candidates = [
            root / "marketplace.json",
            root / ".agents" / "plugins" / "marketplace.json",
            root / ".claude-plugin" / "marketplace.json",
        ]
        for sparse in sparse_paths:
            sparse_root = root / sparse
            candidates.append(
                sparse_root
                if sparse_root.name == "marketplace.json"
                else sparse_root / "marketplace.json"
            )
        found = [path.resolve() for path in candidates if path.is_file()]
        if not found:
            found = [
                path.resolve()
                for path in root.rglob("marketplace.json")
                if ".git" not in path.parts
            ][:3]
        unique = list(dict.fromkeys(found))
        if not unique:
            raise ValueError("marketplace.json was not found in this source")
        if len(unique) > 1:
            raise ValueError("multiple marketplace.json files found; use a sparse path")
        try:
            payload = json.loads(unique[0].read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as error:
            raise ValueError("marketplace.json must contain valid JSON") from error
        if not isinstance(payload, dict) or not isinstance(payload.get("plugins", []), list):
            raise ValueError("marketplace.json must contain a plugins array")
        return unique[0]

    # 根据市场清单构建展示摘要
    @staticmethod
    def _marketplace_from_manifest(
        marketplace_id: str,
        root: Path,
        manifest: Path,
        *,
        source: str,
        kind: MarketplaceKind,
        ref: str = "",
        sparse_paths: tuple[str, ...] = (),
        updated_at: str = "",
        removable: bool = False,
        updatable: bool = False,
    ) -> Marketplace:
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as error:
            raise ValueError("marketplace.json must contain valid JSON") from error
        if not isinstance(payload, dict):
            raise ValueError("marketplace.json must contain an object")
        name = str(payload.get("name") or root.name)
        interface = payload.get("interface", {})
        display_name = (
            str(interface.get("displayName") or name)
            if isinstance(interface, dict)
            else name
        )
        plugins = payload.get("plugins", [])
        return Marketplace(
            id=marketplace_id,
            name=name,
            display_name=display_name,
            source=source,
            kind=kind,
            root_path=root.resolve(),
            manifest_path=manifest.resolve(),
            ref=ref,
            sparse_paths=sparse_paths,
            plugin_count=len(plugins) if isinstance(plugins, list) else 0,
            updated_at=updated_at,
            removable=removable,
            updatable=updatable,
        )

    # 将 marketplace.json 单个插件条目转换为规范目录对象
    @staticmethod
    def _parse_plugin_entry(
        marketplace: Marketplace,
        entry: Any,
    ) -> MarketplacePlugin | None:
        if not isinstance(entry, dict):
            return None
        name = str(entry.get("name") or "").strip()
        if not _SAFE_NAME_RE.fullmatch(name):
            return None
        source = entry.get("source")
        source_type = "local"
        relative_path = ""
        source_url = ""
        source_ref = ""
        source_sha = ""
        if isinstance(source, str):
            relative_path = source
        elif isinstance(source, dict):
            source_type = str(source.get("source") or "local")
            relative_path = str(source.get("path") or "")
            source_url = str(source.get("url") or "")
            source_ref = str(source.get("ref") or "")
            source_sha = str(source.get("sha") or "")
        else:
            return None
        source_path: Path | None = None
        if source_type == "local" or (not source_url and relative_path):
            source_path = _resolve_inside(marketplace.root_path, relative_path)
        elif source_type not in {"url", "git-subdir"}:
            return None
        policy = entry.get("policy", {})
        installation = (
            str(policy.get("installation") or "AVAILABLE")
            if isinstance(policy, dict)
            else "AVAILABLE"
        )
        authentication = (
            str(policy.get("authentication") or "ON_INSTALL")
            if isinstance(policy, dict)
            else "ON_INSTALL"
        )
        manifest_payload: dict[str, Any] = {}
        if source_path is not None:
            manifest = source_path / ".codex-plugin" / "plugin.json"
            if not manifest.is_file():
                manifest = source_path / "plugin.json"
            try:
                parsed = json.loads(manifest.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    manifest_payload = parsed
            except (OSError, ValueError, TypeError):
                pass
        interface = manifest_payload.get("interface", {})
        entry_interface = entry.get("interface", {})
        display_name = name
        for candidate in (entry_interface, interface):
            if isinstance(candidate, dict) and candidate.get("displayName"):
                display_name = str(candidate["displayName"])
                break
        description = str(
            entry.get("description")
            or manifest_payload.get("description")
            or (interface.get("shortDescription") if isinstance(interface, dict) else "")
            or ""
        )
        publisher_value = entry.get("publisher") or manifest_payload.get("author") or ""
        if isinstance(publisher_value, dict):
            publisher = str(publisher_value.get("name") or "")
        else:
            publisher = str(publisher_value)
        return MarketplacePlugin(
            id=f"{marketplace.id}:{name}",
            marketplace_id=marketplace.id,
            marketplace_name=marketplace.display_name,
            name=name,
            display_name=display_name,
            description=description,
            version=str(entry.get("version") or manifest_payload.get("version") or "local"),
            category=str(entry.get("category") or "Other"),
            publisher=publisher,
            source_type=source_type,
            source_path=source_path,
            source_url=source_url,
            source_ref=source_ref,
            source_sha=source_sha,
            relative_path=relative_path,
            installation=installation,
            authentication=authentication,
        )

    # 读取显式市场配置，损坏文件按空配置处理
    def _load_entries(self) -> list[dict[str, Any]]:
        try:
            payload = json.loads(self._config_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return []
        entries = payload.get("marketplaces", []) if isinstance(payload, dict) else []
        return [dict(item) for item in entries if isinstance(item, dict)]

    # 原子写入显式市场配置
    def _write_entries(self, entries: list[dict[str, Any]]) -> None:
        self._config_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._config_file.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps({"marketplaces": entries}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self._config_file)

    # 验证路径确实位于市场缓存根目录后再允许删除
    def _assert_owned_cache_path(self, path: Path, *, allow_temporary: bool = False) -> None:
        root = self._cache_root.resolve()
        resolved = path.resolve()
        if resolved == root or root not in resolved.parents:
            raise ValueError("refusing to modify a path outside the marketplace cache")
        if not allow_temporary and ".tmp" in resolved.parts:
            raise ValueError("unexpected temporary marketplace path")

    # 删除 SztuCode 拥有的市场快照或临时目录
    def _remove_owned_tree(self, path: Path, *, allow_temporary: bool = False) -> None:
        if not path.exists():
            return
        self._assert_owned_cache_path(path, allow_temporary=allow_temporary)
        shutil.rmtree(path)
