from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

SkillScope = Literal["system", "personal", "workspace"]


@dataclass
class Skill:
    name: str
    description: str
    system_prompt_template: str
    allowed_tools: list[str] = field(default_factory=list)
    source: str = "builtin"
    path: Path | None = None
    scope: SkillScope = "system"
    plugin: str | None = None
    enabled: bool = True
    display_name: str = ""
    short_description: str = ""
    icon: str | None = None
    brand_color: str | None = None
    allow_implicit_invocation: bool = True

    @property
    # 生成跨刷新稳定的技能标识，供运行时协议和启停设置使用
    def id(self) -> str:
        return f"{self.source}:{self.name}"


@dataclass(frozen=True)
class Plugin:
    id: str
    name: str
    description: str
    version: str
    source: Literal["personal", "workspace"]
    path: Path
    manifest_path: Path
    skills: tuple[str, ...] = ()
    display_name: str = ""
    brand_color: str | None = None
    enabled: bool = True


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


# 将受控的 YAML 标量转换为字符串，避免为少量界面元数据引入完整解析依赖
def _yaml_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        if value[0] == '"':
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, str) else value[1:-1]
            except ValueError:
                return value[1:-1]
        return value[1:-1].replace("''", "'")
    return value


# 读取 agents/openai.yaml 中供目录界面使用的扁平元数据字段
def _read_openai_metadata(skill_path: Path) -> dict[str, str | bool]:
    if skill_path.name.lower() != "skill.md":
        return {}
    metadata_path = skill_path.parent / "agents" / "openai.yaml"
    if not metadata_path.is_file():
        return {}
    try:
        lines = metadata_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    section = ""
    result: dict[str, str | bool] = {}
    accepted = {
        "interface": {
            "display_name",
            "short_description",
            "icon_small",
            "icon_large",
            "brand_color",
            "default_prompt",
        },
        "policy": {"allow_implicit_invocation"},
    }
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith((" ", "\t")) and stripped.endswith(":"):
            section = stripped[:-1]
            continue
        if section not in accepted or ":" not in stripped:
            continue
        key, raw = stripped.split(":", 1)
        if key not in accepted[section]:
            continue
        value = _yaml_scalar(raw)
        if key == "allow_implicit_invocation":
            result[key] = value.lower() != "false"
        else:
            result[key] = value
    return result


# 根据技能来源计算其界面作用域和所属插件
def _source_metadata(source: str) -> tuple[SkillScope, str | None]:
    if source == "builtin":
        return "system", None
    if source == "user":
        return "personal", None
    if source == "project":
        return "workspace", None
    if source.startswith("user-plugin:"):
        return "personal", source.split(":", 1)[1]
    if source.startswith("project-plugin:"):
        return "workspace", source.split(":", 1)[1]
    return "system", None


# 解析 Markdown 技能文件，并按需延迟加载正文以实现渐进式披露
def _parse_skill_file(
    path: Path,
    *,
    source: str = "builtin",
    include_body: bool = True,
) -> Skill:
    text = path.read_text(encoding="utf-8")
    name = path.parent.name if path.name.lower() == "skill.md" else path.stem
    description = ""
    allowed_tools: list[str] = []
    body = text

    match = _FRONTMATTER_RE.match(text)
    if match:
        front = match.group(1)
        body = text[match.end():]
        lines = front.splitlines()
        index = 0
        reading_allowed_tools = False
        while index < len(lines):
            line = lines[index]
            stripped = line.strip()
            if stripped.startswith("name:"):
                reading_allowed_tools = False
                name = _yaml_scalar(stripped[len("name:"):])
            elif stripped.startswith("description:"):
                reading_allowed_tools = False
                value = stripped[len("description:"):].strip()
                if value in (">", "|"):
                    fold = value == ">"
                    parts: list[str] = []
                    index += 1
                    while index < len(lines) and lines[index].startswith((" ", "\t")):
                        parts.append(lines[index].strip())
                        index += 1
                    description = (" ".join(parts) if fold else "\n".join(parts)).strip()
                    continue
                description = _yaml_scalar(value)
            elif stripped.startswith("allowed_tools:"):
                reading_allowed_tools = True
            elif reading_allowed_tools and stripped.startswith("- "):
                allowed_tools.append(_yaml_scalar(stripped[2:]))
            elif stripped and not line.startswith((" ", "\t")):
                reading_allowed_tools = False
            index += 1

    metadata = _read_openai_metadata(path)
    scope, plugin = _source_metadata(source)
    display_name = str(metadata.get("display_name", ""))
    short_description = str(metadata.get("short_description", ""))
    icon_value = metadata.get("icon_small") or metadata.get("icon_large")
    icon = str(icon_value) if icon_value else None
    brand_value = str(metadata.get("brand_color", ""))
    brand_color = brand_value if _HEX_COLOR_RE.fullmatch(brand_value) else None
    return Skill(
        name=name,
        description=description,
        system_prompt_template=body.strip() if include_body else "",
        allowed_tools=allowed_tools if include_body else [],
        source=source,
        path=path,
        scope=scope,
        plugin=plugin,
        display_name=display_name,
        short_description=short_description,
        icon=icon,
        brand_color=brand_color,
        allow_implicit_invocation=bool(metadata.get("allow_implicit_invocation", True)),
    )


class SkillLoader:
    _BUILTIN_DIR = Path(__file__).parent / "builtin"
    _CACHE_TTL = 5.0

    # 初始化绑定工作区和个人配置根目录的技能目录加载器
    def __init__(
        self,
        project_root: Path | None = None,
        config_root: Path | None = None,
    ) -> None:
        self._project_root = (project_root or Path.cwd()).expanduser().resolve()
        self._config_root = (config_root or Path("~/.sztu")).expanduser().resolve()
        self._cache: list[Skill] | None = None
        self._cache_ts = 0.0

    # 按内建、个人、个人插件、工作区、工作区插件顺序返回技能根目录
    def _roots(self) -> list[tuple[Path, str]]:
        roots = [
            (self._BUILTIN_DIR, "builtin"),
            (self._config_root / "skills", "user"),
        ]
        roots.extend(self._plugin_skill_roots(self._config_root / "plugins", "user-plugin"))
        roots.append((self._project_root / ".sztu" / "skills", "project"))
        roots.extend(
            self._plugin_skill_roots(
                self._project_root / ".sztu" / "plugins", "project-plugin"
            )
        )
        return roots

    # 查找兼容 SztuCode 与 Codex 目录约定的插件清单文件
    @staticmethod
    def _plugin_manifest_paths(plugin_parent: Path) -> list[tuple[Path, Path]]:
        if not plugin_parent.is_dir():
            return []
        found: dict[Path, Path] = {}
        for plugin_dir in sorted(path for path in plugin_parent.iterdir() if path.is_dir()):
            direct = plugin_dir / "plugin.json"
            codex = plugin_dir / ".codex-plugin" / "plugin.json"
            if codex.is_file():
                found[plugin_dir.resolve()] = codex
            elif direct.is_file():
                found[plugin_dir.resolve()] = direct
        return list(found.items())

    # 读取插件清单声明的技能目录，并限制目录不能越出插件根目录
    @classmethod
    def _plugin_skill_roots(cls, plugin_parent: Path, scope: str) -> list[tuple[Path, str]]:
        roots: list[tuple[Path, str]] = []
        for plugin_root, manifest in cls._plugin_manifest_paths(plugin_parent):
            try:
                value = json.loads(manifest.read_text(encoding="utf-8"))
                declared = value.get("skills", "skills")
                entries = [declared] if isinstance(declared, str) else declared
                if not isinstance(entries, list):
                    continue
                plugin_name = str(value.get("name") or plugin_root.name)
                for entry in entries:
                    if not isinstance(entry, str) or not entry.strip():
                        continue
                    candidate = (plugin_root / entry).resolve()
                    if candidate != plugin_root and plugin_root not in candidate.parents:
                        continue
                    if candidate.is_dir():
                        roots.append((candidate, f"{scope}:{plugin_name}"))
            except (OSError, ValueError, TypeError):
                continue
        return roots

    # 返回个人与工作区插件的结构化清单，并附上当前可见的技能名称
    def list_plugins(self) -> list[Plugin]:
        skills_by_plugin: dict[tuple[SkillScope, str], list[str]] = {}
        for skill in self.list_all_skills(include_disabled=True):
            if skill.plugin:
                skills_by_plugin.setdefault((skill.scope, skill.plugin), []).append(skill.name)
        result: list[Plugin] = []
        enabled_overrides = self._plugin_enabled_overrides()
        locations: list[tuple[Path, Literal["personal", "workspace"]]] = [
            (self._config_root / "plugins", "personal"),
            (self._project_root / ".sztu" / "plugins", "workspace"),
        ]
        for parent, source in locations:
            for plugin_root, manifest in self._plugin_manifest_paths(parent):
                try:
                    value = json.loads(manifest.read_text(encoding="utf-8"))
                except (OSError, ValueError, TypeError):
                    continue
                name = str(value.get("name") or plugin_root.name)
                description = str(value.get("description") or "")
                version = str(value.get("version") or "")
                interface = value.get("interface", {})
                display_name = (
                    str(interface.get("displayName") or name)
                    if isinstance(interface, dict)
                    else name
                )
                brand_value = (
                    str(interface.get("brandColor") or "")
                    if isinstance(interface, dict)
                    else ""
                )
                brand_color = brand_value if _HEX_COLOR_RE.fullmatch(brand_value) else None
                scope: SkillScope = "personal" if source == "personal" else "workspace"
                plugin_id = f"{source}:{name}"
                result.append(
                    Plugin(
                        id=plugin_id,
                        name=name,
                        description=description,
                        version=version,
                        source=source,
                        path=plugin_root,
                        manifest_path=manifest,
                        skills=tuple(sorted(skills_by_plugin.get((scope, name), []))),
                        display_name=display_name,
                        brand_color=brand_color,
                        enabled=enabled_overrides.get(plugin_id, True),
                    )
                )
        return result

    # 返回插件启停状态文件，作用域规则与插件安装目录保持一致
    def _plugin_settings_paths(self) -> list[Path]:
        return [
            self._config_root / "plugin-settings.json",
            self._project_root / ".sztu" / "plugin-settings.json",
        ]

    # 合并个人和工作区插件启停覆盖项
    def _plugin_enabled_overrides(self) -> dict[str, bool]:
        result: dict[str, bool] = {}
        for path in self._plugin_settings_paths():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                values = payload.get("plugins", {})
                if isinstance(values, dict):
                    result.update(
                        {
                            str(key): value
                            for key, value in values.items()
                            if isinstance(value, bool)
                        }
                    )
            except (OSError, ValueError, TypeError):
                continue
        return result

    # 判断插件技能来源当前是否允许参与解析
    def _plugin_source_enabled(self, source: str) -> bool:
        if source.startswith("user-plugin:"):
            plugin_id = f"personal:{source.split(':', 1)[1]}"
        elif source.startswith("project-plugin:"):
            plugin_id = f"workspace:{source.split(':', 1)[1]}"
        else:
            return True
        return self._plugin_enabled_overrides().get(plugin_id, True)

    # 返回技能启停状态文件，工作区设置可覆盖个人设置
    def _settings_paths(self) -> list[Path]:
        return [
            self._config_root / "skill-settings.json",
            self._project_root / ".sztu" / "skill-settings.json",
        ]

    # 合并有效的技能启停覆盖项，损坏的设置文件会被安全忽略
    def _enabled_overrides(self) -> dict[str, bool]:
        result: dict[str, bool] = {}
        for path in self._settings_paths():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                values = payload.get("skills", {})
                if isinstance(values, dict):
                    result.update(
                        {
                            str(key): value
                            for key, value in values.items()
                            if isinstance(value, bool)
                        }
                    )
            except (OSError, ValueError, TypeError):
                continue
        return result

    # 将启停覆盖写入对应作用域并使用原子替换避免部分写入
    @staticmethod
    def _write_enabled_override(path: Path, skill_id: str, enabled: bool) -> None:
        payload: dict[str, Any] = {"skills": {}}
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(current, dict):
                payload = current
        except (OSError, ValueError, TypeError):
            pass
        values = payload.get("skills")
        if not isinstance(values, dict):
            values = {}
            payload["skills"] = values
        values[skill_id] = enabled
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(path)

    # 修改已发现技能的启停状态并立即失效当前目录缓存
    def set_enabled(self, skill_id: str, enabled: bool) -> Skill:
        skill = next(
            (item for item in self.list_all_skills(include_disabled=True) if item.id == skill_id),
            None,
        )
        if skill is None:
            raise ValueError(f"skill not found: {skill_id}")
        settings_path = (
            self._project_root / ".sztu" / "skill-settings.json"
            if skill.scope == "workspace"
            else self._config_root / "skill-settings.json"
        )
        self._write_enabled_override(settings_path, skill.id, enabled)
        self.invalidate()
        updated = next(
            item
            for item in self.list_all_skills(include_disabled=True)
            if item.id == skill_id
        )
        return updated

    # 修改插件启停状态；禁用后其捆绑技能立即停止参与运行时解析
    def set_plugin_enabled(self, plugin_id: str, enabled: bool) -> Plugin:
        plugin = next((item for item in self.list_plugins() if item.id == plugin_id), None)
        if plugin is None:
            raise ValueError(f"plugin not found: {plugin_id}")
        settings_path = (
            self._project_root / ".sztu" / "plugin-settings.json"
            if plugin.source == "workspace"
            else self._config_root / "plugin-settings.json"
        )
        self._write_named_override(settings_path, "plugins", plugin.id, enabled)
        self.invalidate()
        return next(item for item in self.list_plugins() if item.id == plugin_id)

    # 按优先级查找技能文件；禁用的高优先级技能不会回退到同名低优先级版本
    def resolve(self, name: str) -> Skill | None:
        overrides = self._enabled_overrides()
        for path, source in self._search_paths(name):
            if path.exists():
                try:
                    skill = _parse_skill_file(path, source=source)
                    skill.enabled = overrides.get(skill.id, True) and self._plugin_source_enabled(
                        source
                    )
                    return skill if skill.enabled else None
                except (OSError, UnicodeError, ValueError):
                    return None
        return None

    # 返回扁平文件和目录式技能的候选路径，较高优先级来源排在前面
    def _search_paths(self, name: str) -> list[tuple[Path, str]]:
        paths: list[tuple[Path, str]] = []
        for directory, source in reversed(self._roots()):
            paths.append((directory / f"{name}.md", source))
            paths.append((directory / name / "SKILL.md", source))
        return paths

    # 列出当前启用且经过同名覆盖后的技能名称
    def list_all(self) -> list[str]:
        return [skill.name for skill in self.list_all_skills()]

    # 扫描技能目录并只加载目录元数据，完整正文留到 resolve 时再读取
    def list_all_skills(self, *, include_disabled: bool = False) -> list[Skill]:
        now = time.monotonic()
        if self._cache is None or now - self._cache_ts >= self._CACHE_TTL:
            overrides = self._enabled_overrides()
            seen: dict[str, Skill] = {}
            for directory, source in self._roots():
                if not directory.exists():
                    continue
                files = [*sorted(directory.glob("*.md")), *sorted(directory.glob("*/SKILL.md"))]
                for path in files:
                    try:
                        skill = _parse_skill_file(path, source=source, include_body=False)
                        skill.enabled = overrides.get(
                            skill.id, True
                        ) and self._plugin_source_enabled(source)
                        seen[skill.name] = skill
                    except (OSError, UnicodeError, ValueError):
                        continue
            self._cache = list(seen.values())
            self._cache_ts = time.monotonic()
        result = list(self._cache)
        return result if include_disabled else [skill for skill in result if skill.enabled]

    # 从本地文件或目录安装技能到个人或工作区技能目录，且不覆盖已有内容
    def install_skill(self, source_path: Path, scope: Literal["personal", "workspace"]) -> Skill:
        source = source_path.expanduser().resolve()
        if source.is_dir():
            skill_file = source / "SKILL.md"
            if not skill_file.is_file():
                raise ValueError("skill directory must contain SKILL.md")
            destination_root = self._install_root(scope, "skills")
            destination = destination_root / source.name
            copied_skill = destination / "SKILL.md"
        elif source.is_file() and source.suffix.lower() == ".md":
            skill_file = source
            destination_root = self._install_root(scope, "skills")
            destination = destination_root / source.name
            copied_skill = destination
        else:
            raise ValueError(
                "skill source must be a Markdown file or a directory containing SKILL.md"
            )
        _parse_skill_file(skill_file, include_body=False)
        self._copy_install_source(source, destination)
        installed_source = "user" if scope == "personal" else "project"
        self.invalidate()
        return _parse_skill_file(copied_skill, source=installed_source, include_body=False)

    # 从本地插件目录安装兼容清单到个人或工作区插件目录，且不覆盖已有内容
    def install_plugin(
        self,
        source_path: Path,
        scope: Literal["personal", "workspace"],
        *,
        install_name: str | None = None,
    ) -> Plugin:
        source = source_path.expanduser().resolve()
        if not source.is_dir():
            raise ValueError("plugin source must be a directory")
        direct = source / "plugin.json"
        codex = source / ".codex-plugin" / "plugin.json"
        manifest = codex if codex.is_file() else direct
        if not manifest.is_file():
            raise ValueError(
                "plugin directory must contain .codex-plugin/plugin.json or plugin.json"
            )
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as error:
            raise ValueError("plugin manifest must be valid JSON") from error
        if not isinstance(payload, dict):
            raise ValueError("plugin manifest must be a JSON object")
        destination_name = install_name or source.name
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", destination_name):
            raise ValueError(
                "plugin install name must use letters, numbers, dots, dashes, or underscores"
            )
        destination = self._install_root(scope, "plugins") / destination_name
        self._copy_install_source(source, destination)
        self.invalidate()
        installed = next(
            (
                plugin
                for plugin in self.list_plugins()
                if plugin.path.resolve() == destination.resolve()
            ),
            None,
        )
        if installed is None:
            raise ValueError("installed plugin could not be loaded")
        return installed

    # 卸载个人或工作区插件，仅允许删除受控插件根目录的直接子项
    def uninstall_plugin(self, plugin_id: str) -> None:
        plugin = next((item for item in self.list_plugins() if item.id == plugin_id), None)
        if plugin is None:
            raise ValueError(f"plugin not found: {plugin_id}")
        parent = self._install_root(plugin.source, "plugins").resolve()
        target = plugin.path.resolve()
        if target.parent != parent or target == parent:
            raise ValueError("refusing to remove a plugin outside the managed plugin root")
        shutil.rmtree(target)
        self.invalidate()

    # 返回所选安装作用域的受控目标目录
    def _install_root(
        self,
        scope: Literal["personal", "workspace"],
        kind: Literal["skills", "plugins"],
    ) -> Path:
        if scope == "personal":
            return self._config_root / kind
        if scope == "workspace":
            return self._project_root / ".sztu" / kind
        raise ValueError(f"unsupported install scope: {scope}")

    # 复制经过验证的本地来源，并拒绝覆盖或递归复制到来源内部
    @staticmethod
    def _copy_install_source(source: Path, destination: Path) -> None:
        if destination.exists():
            raise ValueError(f"install target already exists: {destination.name}")
        if source == destination or source in destination.parents:
            raise ValueError("install target cannot be inside the source directory")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)

    # 清除目录缓存，使安装和启停操作能在下一次读取时立即生效
    def invalidate(self) -> None:
        self._cache = None
        self._cache_ts = 0.0

    # 写入任意命名布尔覆盖区段，供插件状态复用技能设置的原子写入方式
    @staticmethod
    def _write_named_override(
        path: Path,
        section: str,
        item_id: str,
        enabled: bool,
    ) -> None:
        payload: dict[str, Any] = {section: {}}
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(current, dict):
                payload = current
        except (OSError, ValueError, TypeError):
            pass
        values = payload.get(section)
        if not isinstance(values, dict):
            values = {}
            payload[section] = values
        values[item_id] = enabled
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(path)

    # 将技能模板中的参数占位符替换为用户提供的调用参数
    def render_prompt(self, skill: Skill, arguments: str) -> str:
        return skill.system_prompt_template.replace("$ARGUMENTS", arguments)
