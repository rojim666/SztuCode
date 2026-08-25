from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import dataclass, field
from enum import StrEnum
from itertools import islice
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

_MAX_SCAN_DEPTH = 6
_MAX_SCAN_ENTRIES = 8_000
_MAX_MANIFEST_CHARS = 128_000
_MAX_CONTEXT_PROJECTS = 8
_MAX_CONTEXT_COMMANDS = 8
_MAX_CONTEXT_CHARS = 4_000
_IGNORED_DIRECTORY_NAMES = {
    ".git",
    ".gradle",
    ".hg",
    ".idea",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    ".vscode",
    "__pycache__",
    "build",
    "cmakefiles",
    "coverage",
    "dist",
    "node_modules",
    "out",
    "target",
    "venv",
}
_COMPONENT_MARKER_NAMES = {
    "build.gradle",
    "build.gradle.kts",
    "cmakelists.txt",
    "compile_commands.json",
    "conanfile.py",
    "conanfile.txt",
    "configure.ac",
    "makefile",
    "meson.build",
    "package.json",
    "pipfile",
    "pipfile.lock",
    "pdm.lock",
    "pnpm-workspace.yaml",
    "poetry.lock",
    "pom.xml",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "settings.gradle",
    "settings.gradle.kts",
    "uv.lock",
    "vcpkg.json",
}
_CPP_SUFFIXES = {".cc", ".cpp", ".cxx", ".c++", ".hpp", ".hh", ".hxx", ".h++"}
_PYTHON_PACKAGING_TOOL_TABLES = {
    "flit",
    "hatch",
    "pdm",
    "poetry",
    "setuptools",
    "uv",
}
_PYTHON_CHECK_TOOL_TABLES = {
    "black",
    "mypy",
    "pytest",
    "ruff",
}
_NODE_PACKAGE_MANAGER_CANDIDATES = (
    ("pnpm", "pnpm-lock.yaml", "pnpm lockfile"),
    ("yarn", "yarn.lock", "Yarn lockfile"),
    ("bun", "bun.lockb", "Bun lockfile"),
    ("bun", "bun.lock", "Bun lockfile"),
    ("npm", "package-lock.json", "npm lockfile"),
)
_NODE_WORKSPACE_MARKERS = ("pnpm-workspace.yaml", "lerna.json", "nx.json", "turbo.json")


class EvidenceStrength(StrEnum):
    CONFIRMED = "confirmed"
    SUPPORTING = "supporting"
    WEAK = "weak"


class ValidationCategory(StrEnum):
    FORMAT = "format"
    STATIC_CHECK = "static_check"
    UNIT_TEST = "unit_test"
    INTEGRATION_TEST = "integration_test"
    BUILD = "build"


class DetectionEvidence(BaseModel):
    """描述一项检测结论的本地证据。"""

    model_config = ConfigDict(frozen=True)

    path: str
    rule: str
    detail: str | None = None
    strength: EvidenceStrength = EvidenceStrength.SUPPORTING


class TechnologyFinding(BaseModel):
    """描述语言、框架、包管理器或构建工具结论。"""

    model_config = ConfigDict(frozen=True)

    name: str
    confidence: Literal["confirmed", "likely"] = "confirmed"
    evidence: list[DetectionEvidence] = Field(default_factory=list)


class ValidationCommand(BaseModel):
    """描述一条仅供参考的验证命令。"""

    model_config = ConfigDict(frozen=True)

    category: ValidationCategory
    command: str
    working_directory: str
    reason: str
    evidence: list[DetectionEvidence] = Field(default_factory=list)
    recommendation_only: Literal[True] = True


class ProjectComponent(BaseModel):
    """描述工作区内一个独立项目边界的技术画像。"""

    model_config = ConfigDict(frozen=True)

    path: str
    languages: list[TechnologyFinding] = Field(default_factory=list)
    frameworks: list[TechnologyFinding] = Field(default_factory=list)
    package_managers: list[TechnologyFinding] = Field(default_factory=list)
    build_tools: list[TechnologyFinding] = Field(default_factory=list)
    evidence: list[DetectionEvidence] = Field(default_factory=list)
    validation_plan: list[ValidationCommand] = Field(default_factory=list)


class ProjectProfile(BaseModel):
    """描述整个工作区的项目画像，路径均相对工作区根目录。"""

    model_config = ConfigDict(frozen=True)

    root_path: str = "."
    monorepo: bool = False
    projects: list[ProjectComponent] = Field(default_factory=list)
    scan_limited: bool = False


@dataclass(frozen=True)
class _WorkspaceScan:
    candidate_roots: tuple[Path, ...]
    files: tuple[Path, ...]
    scan_limited: bool


@dataclass
class _ComponentSignals:
    languages: list[TechnologyFinding] = field(default_factory=list)
    frameworks: list[TechnologyFinding] = field(default_factory=list)
    package_managers: list[TechnologyFinding] = field(default_factory=list)
    build_tools: list[TechnologyFinding] = field(default_factory=list)
    evidence: list[DetectionEvidence] = field(default_factory=list)
    validation_plan: list[ValidationCommand] = field(default_factory=list)


# 读取工作区并返回稳定排序的候选项目与普通文件清单。
def detect_project_profile(root: Path) -> ProjectProfile:
    workspace_root = root.expanduser().resolve()
    if not workspace_root.is_dir():
        raise ValueError("project profile root must be an existing directory")
    scan = _scan_workspace(workspace_root)
    projects: list[ProjectComponent] = []
    for component_root in scan.candidate_roots:
        component = _detect_component(
            workspace_root,
            component_root,
            scan.files,
            scan.candidate_roots,
        )
        if component is not None:
            projects.append(component)
    return ProjectProfile(
        monorepo=_is_monorepo(workspace_root, projects),
        projects=projects,
        scan_limited=scan.scan_limited,
    )


# 将路径和命令中的控制字符清理为单行文本，避免工程文件名破坏上下文格式。
def _context_value(value: str) -> str:
    return "".join("'" if char == "`" else char if char.isprintable() else " " for char in value)


# 把结构化画像压缩成适合 Agent system prompt 的说明，不复制原始清单内容。
def render_project_profile_context(profile: ProjectProfile) -> str:
    if not profile.projects:
        return ""
    lines = [
        "## Detected Project Profile",
        "Generated locally from project structure. Recommended verification commands are advisory "
        "only and are not executed automatically; any execution still requires the normal tool "
        "permission and approval flow.",
        f"Workspace layout: {'monorepo' if profile.monorepo else 'single project'}.",
    ]
    for project in profile.projects[:_MAX_CONTEXT_PROJECTS]:
        languages = _context_value(_finding_names(project.languages) or "unknown")
        frameworks = _context_value(_finding_names(project.frameworks))
        package_managers = _context_value(_finding_names(project.package_managers))
        build_tools = _context_value(_finding_names(project.build_tools))
        project_path = _context_value(project.path)
        summary = f"- {project_path}: languages={languages}"
        if frameworks:
            summary += f"; frameworks={frameworks}"
        if package_managers:
            summary += f"; package managers={package_managers}"
        if build_tools:
            summary += f"; build tools={build_tools}"
        evidence_paths = ", ".join(_context_value(item.path) for item in project.evidence[:4])
        if evidence_paths:
            summary += f"; evidence={evidence_paths}"
        lines.append(summary)
        for command in project.validation_plan[:_MAX_CONTEXT_COMMANDS]:
            lines.append(
                f"  - {command.category.value}: `{_context_value(command.command)}` "
                f"(run from `{_context_value(command.working_directory)}`; advisory)"
            )
    remaining = len(profile.projects) - _MAX_CONTEXT_PROJECTS
    if remaining > 0:
        lines.append(
            f"- {remaining} additional detected project(s) are available in the workspace UI."
        )
    return "\n".join(lines)[:_MAX_CONTEXT_CHARS].rstrip()


# 受深度和数量上限约束地遍历目录，避免扫描依赖、缓存和构建产物。
def _scan_workspace(root: Path) -> _WorkspaceScan:
    pending: list[tuple[Path, int]] = [(root, 0)]
    candidate_roots: set[Path] = set()
    files: list[Path] = []
    entry_count = 0
    scan_limited = False
    while pending:
        current, depth = pending.pop()
        remaining_entries = _MAX_SCAN_ENTRIES - entry_count
        try:
            with os.scandir(current) as iterator:
                entries = list(islice(iterator, remaining_entries + 1))
        except OSError:
            continue
        if len(entries) > remaining_entries:
            entries.pop()
            scan_limited = True
            pending.clear()
        for scanned_entry in sorted(entries, key=lambda item: item.name.lower()):
            entry = Path(scanned_entry.path)
            entry_count += 1
            if entry.is_symlink():
                continue
            try:
                if entry.is_dir():
                    if entry.name.lower() in _IGNORED_DIRECTORY_NAMES:
                        continue
                    if depth < _MAX_SCAN_DEPTH:
                        pending.append((entry, depth + 1))
                    else:
                        scan_limited = True
                    continue
                if not entry.is_file():
                    continue
            except OSError:
                continue
            files.append(entry)
            if _is_component_marker(entry.name):
                candidate_roots.add(current)
    ordered_roots = tuple(sorted(candidate_roots, key=lambda path: _component_sort_key(root, path)))
    return _WorkspaceScan(ordered_roots, tuple(files), scan_limited)


# 判断文件名是否能作为明确的项目边界候选信号。
def _is_component_marker(name: str) -> bool:
    lowered = name.lower()
    return lowered in _COMPONENT_MARKER_NAMES or (
        lowered.startswith("requirements") and lowered.endswith(".txt")
    )


# 为候选项目路径提供根目录优先、深度优先的稳定排序键。
def _component_sort_key(root: Path, component_root: Path) -> tuple[int, str]:
    relative = component_root.relative_to(root)
    return (len(relative.parts), relative.as_posix().lower())


# 在工作区文件清单中识别某一组件范围内的非嵌套文件。
def _component_files(
    component_root: Path,
    files: tuple[Path, ...],
    candidate_roots: tuple[Path, ...],
) -> list[Path]:
    nested_roots = [
        candidate
        for candidate in candidate_roots
        if candidate != component_root and _is_within(candidate, component_root)
    ]
    result: list[Path] = []
    for path in files:
        if not _is_within(path, component_root):
            continue
        if any(_is_within(path, nested_root) for nested_root in nested_roots):
            continue
        result.append(path)
    return result


# 判断路径是否在给定父目录内，避免字符串前缀造成路径边界误判。
def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


# 检测候选目录中的所有支持语言，并组合为一个项目组件。
def _detect_component(
    workspace_root: Path,
    component_root: Path,
    files: tuple[Path, ...],
    candidate_roots: tuple[Path, ...],
) -> ProjectComponent | None:
    component_files = _component_files(component_root, files, candidate_roots)
    direct_files = _direct_files(component_root, component_files)
    relative_path = _relative_path(workspace_root, component_root)
    signals = _ComponentSignals()
    _detect_python(
        workspace_root, component_root, relative_path, direct_files, component_files, signals
    )
    _detect_node(workspace_root, component_root, relative_path, direct_files, signals)
    _detect_java(
        workspace_root,
        component_root,
        relative_path,
        direct_files,
        component_files,
        signals,
    )
    _detect_c_family(
        workspace_root, component_root, relative_path, direct_files, component_files, signals
    )
    if not signals.languages:
        return None
    return ProjectComponent(
        path=relative_path,
        languages=signals.languages,
        frameworks=signals.frameworks,
        package_managers=signals.package_managers,
        build_tools=signals.build_tools,
        evidence=_unique_evidence(signals.evidence),
        validation_plan=signals.validation_plan,
    )


# 获取组件根目录下直接存在的文件，键统一为小写以兼容不同文件系统。
def _direct_files(component_root: Path, files: list[Path]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in files:
        if path.parent == component_root:
            result.setdefault(path.name.lower(), path)
    return result


# 将绝对路径转换为工作区内相对路径，根目录固定以 . 表示。
def _relative_path(root: Path, path: Path) -> str:
    relative = path.relative_to(root)
    return relative.as_posix() if relative.parts else "."


# 安全读取有限长度的 UTF-8 工程清单，读取失败时作为无信号处理。
def _read_text(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            return stream.read(_MAX_MANIFEST_CHARS)
    except OSError:
        return ""


# 安全解析 pyproject.toml，只有结构化 Python 字段才会作为语言识别信号。
def _read_toml(path: Path) -> dict[str, Any]:
    try:
        parsed = tomllib.loads(_read_text(path))
    except tomllib.TOMLDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


# 安全解析 package.json，只接受对象根节点以避免弱信号误报。
def _read_package_json(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(_read_text(path))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


# 构造相对于工作区的可解释证据对象。
def _evidence(
    workspace_root: Path,
    path: Path,
    rule: str,
    *,
    detail: str | None = None,
    strength: EvidenceStrength = EvidenceStrength.SUPPORTING,
) -> DetectionEvidence:
    return DetectionEvidence(
        path=_relative_path(workspace_root, path),
        rule=rule,
        detail=detail,
        strength=strength,
    )


# 向技术结论列表追加名称唯一的结论，保留首次出现的最直接证据。
def _add_finding(
    target: list[TechnologyFinding],
    name: str,
    evidence: list[DetectionEvidence],
    *,
    confidence: Literal["confirmed", "likely"] = "confirmed",
) -> None:
    if any(item.name == name for item in target):
        return
    target.append(
        TechnologyFinding(name=name, confidence=confidence, evidence=_unique_evidence(evidence))
    )


# 向验证计划追加去重后的建议命令，所有命令显式标记为仅建议。
def _add_command(
    target: list[ValidationCommand],
    category: ValidationCategory,
    command: str,
    working_directory: str,
    reason: str,
    evidence: list[DetectionEvidence],
) -> None:
    if any(item.category == category and item.command == command for item in target):
        return
    target.append(
        ValidationCommand(
            category=category,
            command=command,
            working_directory=working_directory,
            reason=reason,
            evidence=_unique_evidence(evidence),
        )
    )


# 去重证据以保持 IPC 结果与上下文渲染稳定、紧凑。
def _unique_evidence(items: list[DetectionEvidence]) -> list[DetectionEvidence]:
    result: list[DetectionEvidence] = []
    seen: set[tuple[str, str, str | None, EvidenceStrength]] = set()
    for item in items:
        key = (item.path, item.rule, item.detail, item.strength)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


# 汇总技术结论的名称，用于紧凑上下文而不暴露完整配置。
def _finding_names(items: list[TechnologyFinding]) -> str:
    return ", ".join(item.name for item in items)


# 判断组件范围内是否存在指定后缀的源码文件，源码仅作为清单之外的辅助信号。
def _has_source_suffix(files: list[Path], suffixes: set[str]) -> bool:
    return any(path.suffix.lower() in suffixes for path in files)


# 返回组件范围内第一个指定后缀的源码文件，作为工程清单之外的辅助证据。
def _first_source_with_suffix(files: list[Path], suffixes: set[str]) -> Path | None:
    sources = sorted(
        (path for path in files if path.suffix.lower() in suffixes),
        key=lambda path: path.as_posix().lower(),
    )
    return sources[0] if sources else None


# 返回组件范围内第一个稳定排序的 C/C++ 源码路径，供建议命令提供具体输入。
def _first_c_family_source(component_root: Path, files: list[Path]) -> str | None:
    sources = sorted(
        (
            path
            for path in files
            if path.suffix.lower() == ".c" or path.suffix.lower() in _CPP_SUFFIXES
        ),
        key=lambda path: path.as_posix().lower(),
    )
    if not sources:
        return None
    return sources[0].relative_to(component_root).as_posix()


# 从 Python 清单和源码目录综合识别项目、依赖框架、包管理器与验证建议。
def _detect_python(
    workspace_root: Path,
    component_root: Path,
    relative_path: str,
    direct_files: dict[str, Path],
    component_files: list[Path],
    signals: _ComponentSignals,
) -> None:
    pyproject = direct_files.get("pyproject.toml")
    setup_py = direct_files.get("setup.py")
    setup_cfg = direct_files.get("setup.cfg")
    requirements = [
        path
        for name, path in direct_files.items()
        if name.startswith("requirements") and name.endswith(".txt")
    ]
    pyproject_data = _read_toml(pyproject) if pyproject is not None else {}
    pyproject_text = _read_text(pyproject).lower() if pyproject is not None else ""
    setup_py_text = _read_text(setup_py).lower() if setup_py is not None else ""
    setup_cfg_text = _read_text(setup_cfg).lower() if setup_cfg is not None else ""
    setup_text = "\n".join((setup_py_text, setup_cfg_text))
    requirements_text = "\n".join(_read_text(path).lower() for path in requirements)
    pyproject_project = pyproject_data.get("project")
    pyproject_build_system = pyproject_data.get("build-system")
    pyproject_tools = pyproject_data.get("tool")
    has_pyproject_metadata = isinstance(pyproject_project, dict) or isinstance(
        pyproject_build_system, dict
    )
    tool_names = set(pyproject_tools) if isinstance(pyproject_tools, dict) else set()
    has_python_packaging_tool_config = bool(tool_names & _PYTHON_PACKAGING_TOOL_TABLES)
    has_python_check_tool_config = bool(tool_names & _PYTHON_CHECK_TOOL_TABLES)
    has_setup_py_metadata = setup_py is not None and (
        "setuptools" in setup_py_text
        or "distutils" in setup_py_text
        or bool(re.search(r"\bsetup\s*\(", setup_py_text))
    )
    has_setup_cfg_metadata = setup_cfg is not None and (
        "[metadata]" in setup_cfg_text or "[options]" in setup_cfg_text
    )
    python_source = _first_source_with_suffix(component_files, {".py"})
    has_python_lock = any(
        name in direct_files
        for name in ("uv.lock", "poetry.lock", "pdm.lock", "pipfile.lock", "pipfile")
    )
    has_requirements_project = bool(requirements) and python_source is not None
    has_python_tool_project = has_python_packaging_tool_config or (
        has_python_check_tool_config
        and (python_source is not None or bool(requirements) or has_python_lock)
    )
    has_lock_project = has_python_lock and (
        python_source is not None
        or bool(requirements)
        or has_pyproject_metadata
        or has_python_tool_project
    )
    has_python_manifest = (
        has_pyproject_metadata
        or has_python_tool_project
        or has_setup_py_metadata
        or has_setup_cfg_metadata
    )
    if not has_python_manifest and not has_requirements_project and not has_lock_project:
        return
    evidence: list[DetectionEvidence] = []
    if pyproject is not None and (has_pyproject_metadata or has_python_tool_project):
        evidence.append(
            _evidence(
                workspace_root,
                pyproject,
                "Structured Python project metadata or tool configuration in pyproject.toml",
                strength=(
                    EvidenceStrength.CONFIRMED
                    if has_pyproject_metadata
                    else EvidenceStrength.SUPPORTING
                ),
            )
        )
    if setup_py is not None and has_setup_py_metadata:
        evidence.append(
            _evidence(
                workspace_root,
                setup_py,
                "Python setuptools entry point",
                strength=EvidenceStrength.CONFIRMED,
            )
        )
    if setup_cfg is not None and has_setup_cfg_metadata:
        evidence.append(
            _evidence(
                workspace_root,
                setup_cfg,
                "Python setup configuration",
                strength=EvidenceStrength.CONFIRMED,
            )
        )
    for requirement in requirements:
        evidence.append(
            _evidence(
                workspace_root,
                requirement,
                "Python dependency requirements",
                strength=EvidenceStrength.SUPPORTING,
            )
        )
    if python_source is not None:
        evidence.append(
            _evidence(
                workspace_root,
                python_source,
                "Python source file accompanies project metadata or dependencies",
                strength=EvidenceStrength.SUPPORTING,
            )
        )
    _add_finding(
        signals.languages,
        "Python",
        evidence,
        confidence=(
            "confirmed"
            if has_pyproject_metadata
            or has_python_packaging_tool_config
            or has_setup_py_metadata
            or has_setup_cfg_metadata
            else "likely"
        ),
    )
    signals.evidence.extend(evidence)
    combined_text = "\n".join((pyproject_text, setup_text, requirements_text))
    framework_source = pyproject or (requirements[0] if requirements else setup_py or setup_cfg)
    if framework_source is not None:
        _add_python_frameworks(
            workspace_root,
            framework_source,
            combined_text,
            signals,
            evidence,
        )
    package_managers = _add_python_package_managers(
        workspace_root,
        direct_files,
        pyproject_text,
        signals,
        evidence,
    )
    _add_python_build_tools(
        workspace_root,
        pyproject,
        setup_py,
        setup_cfg,
        pyproject_text,
        signals,
        evidence,
    )
    runner = _python_runner(package_managers)
    tool_evidence = evidence[:1]
    if "ruff" in combined_text:
        _add_command(
            signals.validation_plan,
            ValidationCategory.FORMAT,
            f"{runner} ruff format --check .",
            relative_path,
            "Ruff is declared by the Python project",
            tool_evidence,
        )
        _add_command(
            signals.validation_plan,
            ValidationCategory.STATIC_CHECK,
            f"{runner} ruff check .",
            relative_path,
            "Ruff is declared by the Python project",
            tool_evidence,
        )
    if "black" in combined_text:
        _add_command(
            signals.validation_plan,
            ValidationCategory.FORMAT,
            f"{runner} black --check .",
            relative_path,
            "Black is declared by the Python project",
            tool_evidence,
        )
    if "mypy" in combined_text:
        _add_command(
            signals.validation_plan,
            ValidationCategory.STATIC_CHECK,
            f"{runner} mypy .",
            relative_path,
            "mypy is declared by the Python project",
            tool_evidence,
        )
    has_tests = "pytest" in combined_text or (component_root / "tests").is_dir()
    if has_tests:
        _add_command(
            signals.validation_plan,
            ValidationCategory.UNIT_TEST,
            f"{runner} pytest",
            relative_path,
            "pytest configuration or tests directory detected",
            tool_evidence,
        )
    if (component_root / "tests" / "integration").is_dir() or "integration" in combined_text:
        _add_command(
            signals.validation_plan,
            ValidationCategory.INTEGRATION_TEST,
            f"{runner} pytest tests/integration",
            relative_path,
            "Python integration-test directory or marker detected",
            tool_evidence,
        )
    if (
        has_pyproject_metadata
        or has_python_packaging_tool_config
        or has_setup_py_metadata
        or has_setup_cfg_metadata
    ):
        _add_command(
            signals.validation_plan,
            ValidationCategory.BUILD,
            _python_build_command(package_managers),
            relative_path,
            "Python package metadata detected",
            tool_evidence,
        )


# 从依赖文本中记录常见 Python Web 框架，避免根据单个源码扩展名猜测。
def _add_python_frameworks(
    workspace_root: Path,
    evidence_path: Path,
    combined_text: str,
    signals: _ComponentSignals,
    evidence: list[DetectionEvidence],
) -> None:
    framework_evidence = [
        _evidence(
            workspace_root,
            evidence_path,
            "Python dependency or tool configuration names the framework",
            strength=EvidenceStrength.SUPPORTING,
        )
    ]
    for marker, name in (("fastapi", "FastAPI"), ("django", "Django"), ("flask", "Flask")):
        if marker in combined_text:
            _add_finding(signals.frameworks, name, framework_evidence)
            signals.evidence.extend(framework_evidence)
    del evidence


# 根据锁文件和工具配置选择 Python 包管理器，并返回名称供命令前缀使用。
def _add_python_package_managers(
    workspace_root: Path,
    direct_files: dict[str, Path],
    pyproject_text: str,
    signals: _ComponentSignals,
    fallback_evidence: list[DetectionEvidence],
) -> list[str]:
    result: list[str] = []
    candidates = (
        ("uv.lock", "uv", "uv lockfile"),
        ("poetry.lock", "Poetry", "Poetry lockfile"),
        ("pdm.lock", "PDM", "PDM lockfile"),
        ("pipfile.lock", "Pipenv", "Pipenv lockfile"),
        ("pipfile", "Pipenv", "Pipenv manifest"),
    )
    for filename, name, rule in candidates:
        path = direct_files.get(filename)
        if path is None:
            continue
        item_evidence = [_evidence(workspace_root, path, rule, strength=EvidenceStrength.CONFIRMED)]
        _add_finding(signals.package_managers, name, item_evidence)
        signals.evidence.extend(item_evidence)
        result.append(name)
    if "[tool.uv" in pyproject_text and "uv" not in result:
        _add_finding(signals.package_managers, "uv", fallback_evidence, confidence="likely")
        result.append("uv")
    if "[tool.poetry" in pyproject_text and "Poetry" not in result:
        _add_finding(signals.package_managers, "Poetry", fallback_evidence, confidence="likely")
        result.append("Poetry")
    if "[tool.pdm" in pyproject_text and "PDM" not in result:
        _add_finding(signals.package_managers, "PDM", fallback_evidence, confidence="likely")
        result.append("PDM")
    if not result:
        _add_finding(signals.package_managers, "pip", fallback_evidence, confidence="likely")
        result.append("pip")
    return result


# 根据 build backend 与工具配置记录 Python 构建工具结论。
def _add_python_build_tools(
    workspace_root: Path,
    pyproject: Path | None,
    setup_py: Path | None,
    setup_cfg: Path | None,
    pyproject_text: str,
    signals: _ComponentSignals,
    fallback_evidence: list[DetectionEvidence],
) -> None:
    if pyproject is None:
        setuptools_path = setup_py or setup_cfg
        if setuptools_path is not None:
            setuptools_evidence = [
                _evidence(
                    workspace_root,
                    setuptools_path,
                    "Python setuptools entry point or configuration",
                    strength=EvidenceStrength.CONFIRMED,
                )
            ]
            _add_finding(signals.build_tools, "Setuptools", setuptools_evidence)
            signals.evidence.extend(setuptools_evidence)
        return
    build_evidence = [
        _evidence(
            workspace_root,
            pyproject,
            "Python build backend declared in pyproject.toml",
            strength=EvidenceStrength.SUPPORTING,
        )
    ]
    tool_names = (
        ("hatchling", "Hatchling"),
        ("setuptools", "Setuptools"),
        ("poetry-core", "Poetry"),
        ("flit", "Flit"),
        ("pdm.backend", "PDM"),
    )
    for marker, name in tool_names:
        if marker in pyproject_text:
            _add_finding(signals.build_tools, name, build_evidence)
            signals.evidence.extend(build_evidence)
    if not signals.build_tools:
        _add_finding(signals.build_tools, "PEP 517", fallback_evidence, confidence="likely")


# 选择 Python 验证命令的安全运行器前缀，不执行或安装任何依赖。
def _python_runner(package_managers: list[str]) -> str:
    if "uv" in package_managers:
        return "uv run"
    if "Poetry" in package_managers:
        return "poetry run"
    if "PDM" in package_managers:
        return "pdm run"
    if "Pipenv" in package_managers:
        return "pipenv run"
    return "python -m"


# 根据已识别的 Python 包管理器生成构建建议，而非直接尝试构建。
def _python_build_command(package_managers: list[str]) -> str:
    if "uv" in package_managers:
        return "uv build"
    if "Poetry" in package_managers:
        return "poetry build"
    if "PDM" in package_managers:
        return "pdm build"
    return "python -m build"


# 从 package.json、锁文件和 scripts 识别 Node.js 项目及其建议命令。
def _detect_node(
    workspace_root: Path,
    component_root: Path,
    relative_path: str,
    direct_files: dict[str, Path],
    signals: _ComponentSignals,
) -> None:
    package_json = direct_files.get("package.json")
    if package_json is None:
        return
    package_data = _read_package_json(package_json)
    scripts = _string_mapping(package_data.get("scripts"))
    dependencies = _dependency_names(package_data)
    has_node_manifest = bool(
        package_data.get("name")
        or scripts
        or dependencies
        or package_data.get("workspaces")
        or package_data.get("packageManager")
        or package_data.get("private")
    )
    if not has_node_manifest:
        return
    manifest_evidence = [
        _evidence(
            workspace_root,
            package_json,
            "Node.js package manifest with metadata, dependencies, or scripts",
            strength=EvidenceStrength.CONFIRMED,
        )
    ]
    _add_finding(signals.languages, "Node.js", manifest_evidence)
    signals.evidence.extend(manifest_evidence)
    manager = _add_node_package_manager(
        workspace_root,
        component_root,
        package_json,
        package_data,
        direct_files,
        signals,
        manifest_evidence,
    )
    _add_node_frameworks_and_build_tools(dependencies, signals, manifest_evidence)
    _add_node_validation_commands(scripts, manager, relative_path, signals, manifest_evidence)


# 从 JSON 映射提取字符串键值，忽略非字符串脚本和异常配置。
def _string_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items() if isinstance(item, str)}


# 从 package.json 的依赖区块汇总规范化包名。
def _dependency_names(package_data: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for field_name in (
        "dependencies",
        "devDependencies",
        "peerDependencies",
        "optionalDependencies",
    ):
        value = package_data.get(field_name)
        if isinstance(value, dict):
            names.update(str(name).lower() for name in value)
    return names


# 返回直接目录中优先级最高的 Node.js 锁文件包管理器信号。
def _node_lockfile_manager(direct_files: dict[str, Path]) -> tuple[str, Path, str] | None:
    for name, filename, rule in _NODE_PACKAGE_MANAGER_CANDIDATES:
        path = direct_files.get(filename)
        if path is not None:
            return name, path, rule
    return None


# 规范化 packageManager 字段中声明的 Node.js 包管理器名称。
def _declared_node_package_manager(package_data: dict[str, Any]) -> str | None:
    package_manager_field = str(package_data.get("packageManager", "")).lower()
    return next(
        (name for name in ("pnpm", "yarn", "bun", "npm") if package_manager_field.startswith(name)),
        None,
    )


# 仅探测已知 Node.js 清单和锁文件，避免为继承工作区信号遍历大型父目录。
def _directory_direct_files(directory: Path) -> dict[str, Path]:
    names = {
        "package.json",
        *_NODE_WORKSPACE_MARKERS,
        *(filename for _, filename, _ in _NODE_PACKAGE_MANAGER_CANDIDATES),
    }
    direct_files: dict[str, Path] = {}
    for name in names:
        candidate = directory / name
        try:
            if not candidate.is_symlink() and candidate.is_file():
                direct_files[name.lower()] = candidate
        except OSError:
            continue
    return direct_files


# 查找组件自身或祖先项目中的 Maven/Gradle wrapper，并生成相对组件目录可执行的路径。
def _java_wrapper_executable(
    workspace_root: Path,
    component_root: Path,
    wrapper_names: tuple[str, ...],
    fallback: str,
) -> tuple[str, Path | None]:
    current = component_root
    while _is_within(current, workspace_root):
        for wrapper_name in wrapper_names:
            candidate = current / wrapper_name
            try:
                if not candidate.is_symlink() and candidate.is_file():
                    relative = os.path.relpath(candidate, component_root).replace(os.sep, "/")
                    executable = relative if relative.startswith(".") else f"./{relative}"
                    return executable, candidate
            except OSError:
                continue
        if current == workspace_root:
            break
        current = current.parent
    return fallback, None


# 查找最近的显式 Node.js 工作区根，避免把任意父项目的包管理器错误继承给子项目。
def _node_workspace_source(
    workspace_root: Path,
    component_root: Path,
) -> tuple[dict[str, Any], dict[str, Path]] | None:
    if component_root == workspace_root:
        return None
    current = component_root.parent
    while _is_within(current, workspace_root):
        direct_files = _directory_direct_files(current)
        package_json = direct_files.get("package.json")
        package_data = _read_package_json(package_json) if package_json is not None else {}
        has_workspaces = isinstance(package_data.get("workspaces"), (list, dict))
        if has_workspaces or any(name in direct_files for name in _NODE_WORKSPACE_MARKERS):
            return package_data, direct_files
        if current == workspace_root:
            break
        current = current.parent
    return None


# 使用本地或工作区级 packageManager 字段和锁文件确定 Node.js 包管理器，默认 npm 仅作为保守回退。
def _add_node_package_manager(
    workspace_root: Path,
    component_root: Path,
    package_json: Path,
    package_data: dict[str, Any],
    direct_files: dict[str, Path],
    signals: _ComponentSignals,
    fallback_evidence: list[DetectionEvidence],
) -> str:
    lockfile = _node_lockfile_manager(direct_files)
    if lockfile is not None:
        name, path, rule = lockfile
        item_evidence = [_evidence(workspace_root, path, rule, strength=EvidenceStrength.CONFIRMED)]
        _add_finding(signals.package_managers, name, item_evidence)
        signals.evidence.extend(item_evidence)
        return name
    declared_manager = _declared_node_package_manager(package_data)
    if declared_manager is not None:
        item_evidence = [
            _evidence(
                workspace_root,
                package_json,
                f"packageManager field declares {declared_manager}",
                strength=EvidenceStrength.SUPPORTING,
            )
        ]
        _add_finding(
            signals.package_managers,
            declared_manager,
            item_evidence,
            confidence="likely",
        )
        signals.evidence.extend(item_evidence)
        return declared_manager
    workspace_source = _node_workspace_source(workspace_root, component_root)
    if workspace_source is not None:
        workspace_data, workspace_files = workspace_source
        workspace_lockfile = _node_lockfile_manager(workspace_files)
        if workspace_lockfile is not None:
            name, path, rule = workspace_lockfile
            item_evidence = [
                _evidence(
                    workspace_root,
                    path,
                    f"{rule} inherited from the workspace root",
                    strength=EvidenceStrength.CONFIRMED,
                )
            ]
            _add_finding(signals.package_managers, name, item_evidence)
            signals.evidence.extend(item_evidence)
            return name
        workspace_declared_manager = _declared_node_package_manager(workspace_data)
        if workspace_declared_manager is not None:
            workspace_package_json = workspace_files.get("package.json")
            if workspace_package_json is not None:
                item_evidence = [
                    _evidence(
                        workspace_root,
                        workspace_package_json,
                        f"workspace packageManager field declares {workspace_declared_manager}",
                        strength=EvidenceStrength.SUPPORTING,
                    )
                ]
                _add_finding(
                    signals.package_managers,
                    workspace_declared_manager,
                    item_evidence,
                    confidence="likely",
                )
                signals.evidence.extend(item_evidence)
                return workspace_declared_manager
    _add_finding(signals.package_managers, "npm", fallback_evidence, confidence="likely")
    return "npm"


# 从依赖名称提取常见前端、后端框架和构建工具结论。
def _add_node_frameworks_and_build_tools(
    dependencies: set[str],
    signals: _ComponentSignals,
    evidence: list[DetectionEvidence],
) -> None:
    for package_name, display_name in (
        ("react", "React"),
        ("next", "Next.js"),
        ("vue", "Vue"),
        ("nuxt", "Nuxt"),
        ("@angular/core", "Angular"),
        ("svelte", "Svelte"),
        ("express", "Express"),
        ("@nestjs/core", "NestJS"),
    ):
        if package_name in dependencies:
            _add_finding(signals.frameworks, display_name, evidence)
    for package_name, display_name in (
        ("vite", "Vite"),
        ("webpack", "Webpack"),
        ("turbo", "Turborepo"),
        ("nx", "Nx"),
        ("tsup", "tsup"),
    ):
        if package_name in dependencies:
            _add_finding(signals.build_tools, display_name, evidence)


# 按 package scripts 的名称分类 Node.js 验证建议，绝不拼接或执行脚本正文。
def _add_node_validation_commands(
    scripts: dict[str, str],
    package_manager: str,
    relative_path: str,
    signals: _ComponentSignals,
    evidence: list[DetectionEvidence],
) -> None:
    for category, names, reason in (
        (
            ValidationCategory.FORMAT,
            ("format", "format:check", "prettier:check"),
            "format script declared",
        ),
        (
            ValidationCategory.STATIC_CHECK,
            ("lint", "typecheck", "check"),
            "static-check script declared",
        ),
        (ValidationCategory.UNIT_TEST, ("test:unit", "unit", "test"), "unit-test script declared"),
        (
            ValidationCategory.INTEGRATION_TEST,
            ("test:integration", "integration", "test:e2e", "e2e"),
            "integration-test script declared",
        ),
        (ValidationCategory.BUILD, ("build", "compile", "bundle"), "build script declared"),
    ):
        script = _first_matching_script(scripts, names)
        if script is not None:
            _add_command(
                signals.validation_plan,
                category,
                f"{package_manager} run {script}",
                relative_path,
                reason,
                evidence,
            )


# 按优先级返回第一个声明的脚本名，保持建议的确定性。
def _first_matching_script(scripts: dict[str, str], names: tuple[str, ...]) -> str | None:
    for name in names:
        if name in scripts:
            return name
    return None


# 从 Maven 或 Gradle 清单及源码目录识别 Java 项目和验证工具。
def _detect_java(
    workspace_root: Path,
    component_root: Path,
    relative_path: str,
    direct_files: dict[str, Path],
    component_files: list[Path],
    signals: _ComponentSignals,
) -> None:
    pom = direct_files.get("pom.xml")
    gradle = direct_files.get("build.gradle") or direct_files.get("build.gradle.kts")
    pom_text = _read_text(pom).lower() if pom is not None else ""
    gradle_text = _read_text(gradle).lower() if gradle is not None else ""
    has_maven = pom is not None and "<project" in pom_text
    has_gradle = gradle is not None and bool(gradle_text.strip())
    if not has_maven and not has_gradle:
        return
    combined_text = "\n".join((pom_text, gradle_text))
    java_source = _first_source_with_suffix(component_files, {".java"})
    has_java_build_signal = any(
        marker in combined_text
        for marker in (
            "maven-compiler-plugin",
            "maven.compiler.",
            "spring-boot",
            "quarkus",
            "micronaut",
            "id 'java'",
            'id("java")',
            "java-library",
            "sourcecompatibility",
            "targetcompatibility",
        )
    )
    if java_source is None and not has_java_build_signal:
        return
    evidence: list[DetectionEvidence] = []
    if has_maven and pom is not None:
        evidence.append(
            _evidence(
                workspace_root, pom, "Maven project descriptor", strength=EvidenceStrength.CONFIRMED
            )
        )
    if has_gradle and gradle is not None:
        evidence.append(
            _evidence(
                workspace_root,
                gradle,
                "Gradle build descriptor",
                strength=EvidenceStrength.CONFIRMED,
            )
        )
    if java_source is not None:
        evidence.append(
            _evidence(
                workspace_root,
                java_source,
                "Java source file accompanies build descriptor",
                strength=EvidenceStrength.SUPPORTING,
            )
        )
    source_dir = component_root / "src" / "main" / "java"
    if source_dir.is_dir():
        evidence.append(
            DetectionEvidence(
                path=_relative_path(workspace_root, source_dir),
                rule="Java conventional source directory",
                strength=EvidenceStrength.SUPPORTING,
            )
        )
    if has_java_build_signal:
        descriptor = pom if has_maven else gradle
        if descriptor is not None:
            evidence.append(
                _evidence(
                    workspace_root,
                    descriptor,
                    "Java compiler, plugin, or framework configuration",
                    strength=EvidenceStrength.SUPPORTING,
                )
            )
    _add_finding(signals.languages, "Java", evidence)
    framework_evidence = evidence[:1]
    for marker, name in (
        ("spring-boot", "Spring Boot"),
        ("quarkus", "Quarkus"),
        ("micronaut", "Micronaut"),
    ):
        if marker in combined_text:
            _add_finding(signals.frameworks, name, framework_evidence)
    if has_maven:
        _add_finding(signals.package_managers, "Maven", evidence)
        _add_finding(signals.build_tools, "Maven", evidence)
        executable, wrapper = _java_wrapper_executable(
            workspace_root,
            component_root,
            ("mvnw.cmd", "mvnw") if os.name == "nt" else ("mvnw", "mvnw.cmd"),
            "mvn",
        )
        if wrapper is not None:
            wrapper_rule = (
                "Maven wrapper"
                if wrapper.parent == component_root
                else "Inherited Maven wrapper"
            )
            evidence.append(
                _evidence(
                    workspace_root,
                    wrapper,
                    wrapper_rule,
                    strength=EvidenceStrength.SUPPORTING,
                )
            )
        _add_java_commands(executable, "maven", combined_text, relative_path, signals, evidence)
    if has_gradle:
        _add_finding(signals.package_managers, "Gradle", evidence)
        _add_finding(signals.build_tools, "Gradle", evidence)
        executable, wrapper = _java_wrapper_executable(
            workspace_root,
            component_root,
            ("gradlew.bat", "gradlew") if os.name == "nt" else ("gradlew", "gradlew.bat"),
            "gradle",
        )
        if wrapper is not None:
            wrapper_rule = (
                "Gradle wrapper"
                if wrapper.parent == component_root
                else "Inherited Gradle wrapper"
            )
            evidence.append(
                _evidence(
                    workspace_root,
                    wrapper,
                    wrapper_rule,
                    strength=EvidenceStrength.SUPPORTING,
                )
            )
        _add_java_commands(executable, "gradle", combined_text, relative_path, signals, evidence)
    signals.evidence.extend(evidence)


# 按 Maven 或 Gradle 的已声明插件与目录生成 Java 验证建议。
def _add_java_commands(
    executable: str,
    build_system: Literal["maven", "gradle"],
    combined_text: str,
    relative_path: str,
    signals: _ComponentSignals,
    evidence: list[DetectionEvidence],
) -> None:
    if build_system == "maven":
        if "spotless" in combined_text:
            _add_command(
                signals.validation_plan,
                ValidationCategory.FORMAT,
                f"{executable} spotless:check",
                relative_path,
                "Spotless Maven plugin detected",
                evidence,
            )
        if "checkstyle" in combined_text:
            _add_command(
                signals.validation_plan,
                ValidationCategory.STATIC_CHECK,
                f"{executable} checkstyle:check",
                relative_path,
                "Checkstyle Maven plugin detected",
                evidence,
            )
        _add_command(
            signals.validation_plan,
            ValidationCategory.UNIT_TEST,
            f"{executable} test",
            relative_path,
            "Maven project descriptor detected",
            evidence,
        )
        if "failsafe" in combined_text or "integration" in combined_text:
            _add_command(
                signals.validation_plan,
                ValidationCategory.INTEGRATION_TEST,
                f"{executable} verify",
                relative_path,
                "Maven integration-test configuration detected",
                evidence,
            )
        _add_command(
            signals.validation_plan,
            ValidationCategory.BUILD,
            f"{executable} package",
            relative_path,
            "Maven project descriptor detected",
            evidence,
        )
        return
    if "spotless" in combined_text:
        _add_command(
            signals.validation_plan,
            ValidationCategory.FORMAT,
            f"{executable} spotlessCheck",
            relative_path,
            "Spotless Gradle plugin detected",
            evidence,
        )
    if "checkstyle" in combined_text:
        _add_command(
            signals.validation_plan,
            ValidationCategory.STATIC_CHECK,
            f"{executable} checkstyleMain",
            relative_path,
            "Checkstyle Gradle plugin detected",
            evidence,
        )
    _add_command(
        signals.validation_plan,
        ValidationCategory.UNIT_TEST,
        f"{executable} test",
        relative_path,
        "Gradle build descriptor detected",
        evidence,
    )
    if "integrationtest" in combined_text or "integration" in combined_text:
        _add_command(
            signals.validation_plan,
            ValidationCategory.INTEGRATION_TEST,
            f"{executable} integrationTest",
            relative_path,
            "Gradle integration-test configuration detected",
            evidence,
        )
    _add_command(
        signals.validation_plan,
        ValidationCategory.BUILD,
        f"{executable} build",
        relative_path,
        "Gradle build descriptor detected",
        evidence,
    )


# 从 CMake、Meson 或 Make 清单和源码信号识别 C/C++ 项目。
def _detect_c_family(
    workspace_root: Path,
    component_root: Path,
    relative_path: str,
    direct_files: dict[str, Path],
    component_files: list[Path],
    signals: _ComponentSignals,
) -> None:
    cmake = direct_files.get("cmakelists.txt")
    meson = direct_files.get("meson.build")
    makefile = direct_files.get("makefile")
    cmake_text = _read_text(cmake).lower() if cmake is not None else ""
    meson_text = _read_text(meson).lower() if meson is not None else ""
    make_text = _read_text(makefile).lower() if makefile is not None else ""
    has_sources = _has_source_suffix(component_files, {".c", *_CPP_SUFFIXES})
    cmake_declares_c = bool(re.search(r"\blanguages\b[^)]*\bc\b", cmake_text))
    cmake_declares_cpp = "cxx" in cmake_text or bool(re.search(r"\b(?:cpp|c\+\+)\b", cmake_text))
    meson_declares_c = bool(re.search(r"project\s*\([^)]*['\"]c['\"]", meson_text))
    meson_declares_cpp = bool(re.search(r"project\s*\([^)]*['\"](?:cpp|c\+\+)['\"]", meson_text))
    cmake_mentions_c_source = bool(re.search(r"\.c\b", cmake_text))
    cmake_mentions_cpp_source = bool(re.search(r"\.(?:cc|cpp|cxx|c\+\+)\b", cmake_text))
    meson_mentions_c_source = bool(re.search(r"\.c\b", meson_text))
    meson_mentions_cpp_source = bool(re.search(r"\.(?:cc|cpp|cxx|c\+\+)\b", meson_text))
    has_cmake = cmake is not None and (
        has_sources
        or cmake_declares_c
        or cmake_declares_cpp
        or cmake_mentions_c_source
        or cmake_mentions_cpp_source
    )
    has_meson = meson is not None and (
        has_sources
        or meson_declares_c
        or meson_declares_cpp
        or meson_mentions_c_source
        or meson_mentions_cpp_source
    )
    has_make = makefile is not None and has_sources and bool(make_text.strip())
    if not has_cmake and not has_meson and not has_make:
        return
    evidence: list[DetectionEvidence] = []
    if has_cmake and cmake is not None:
        evidence.append(
            _evidence(
                workspace_root, cmake, "CMake build descriptor", strength=EvidenceStrength.CONFIRMED
            )
        )
    if has_meson and meson is not None:
        evidence.append(
            _evidence(
                workspace_root, meson, "Meson build descriptor", strength=EvidenceStrength.CONFIRMED
            )
        )
    if has_make and makefile is not None:
        evidence.append(
            _evidence(
                workspace_root,
                makefile,
                "Make build descriptor with C/C++ sources",
                strength=EvidenceStrength.CONFIRMED,
            )
        )
    c_or_cpp_source = _first_source_with_suffix(component_files, {".c", *_CPP_SUFFIXES})
    if c_or_cpp_source is not None:
        evidence.append(
            _evidence(
                workspace_root,
                c_or_cpp_source,
                "C/C++ source file accompanies build descriptor",
                strength=EvidenceStrength.SUPPORTING,
            )
        )
    has_c = _has_source_suffix(component_files, {".c"}) or (
        cmake_declares_c or meson_declares_c or cmake_mentions_c_source or meson_mentions_c_source
    )
    has_cpp = _has_source_suffix(component_files, _CPP_SUFFIXES) or (
        cmake_declares_cpp
        or meson_declares_cpp
        or cmake_mentions_cpp_source
        or meson_mentions_cpp_source
    )
    if has_c:
        _add_finding(signals.languages, "C", evidence)
    if has_cpp:
        _add_finding(signals.languages, "C++", evidence)
    signals.evidence.extend(evidence)
    combined_text = "\n".join((cmake_text, meson_text, make_text))
    for marker, name in (("gtest", "GoogleTest"), ("catch2", "Catch2"), ("find_package(qt", "Qt")):
        if marker in combined_text:
            _add_finding(signals.frameworks, name, evidence)
    _add_c_family_package_managers(workspace_root, direct_files, signals, evidence)
    if has_cmake:
        _add_finding(signals.build_tools, "CMake", evidence)
        _add_cmake_commands(
            component_root,
            relative_path,
            direct_files,
            component_files,
            combined_text,
            signals,
            evidence,
        )
    if has_meson:
        _add_finding(signals.build_tools, "Meson", evidence)
        _add_meson_commands(relative_path, combined_text, signals, evidence)
    if has_make:
        _add_finding(signals.build_tools, "Make", evidence)
        _add_make_commands(relative_path, make_text, signals, evidence)


# 记录 C/C++ 项目使用的 Conan 或 vcpkg 包管理器。
def _add_c_family_package_managers(
    workspace_root: Path,
    direct_files: dict[str, Path],
    signals: _ComponentSignals,
    fallback_evidence: list[DetectionEvidence],
) -> None:
    for filename, name, rule in (
        ("conanfile.py", "Conan", "Conan dependency manifest"),
        ("conanfile.txt", "Conan", "Conan dependency manifest"),
        ("vcpkg.json", "vcpkg", "vcpkg dependency manifest"),
    ):
        path = direct_files.get(filename)
        if path is not None:
            item_evidence = [
                _evidence(workspace_root, path, rule, strength=EvidenceStrength.CONFIRMED)
            ]
            _add_finding(signals.package_managers, name, item_evidence)
            signals.evidence.extend(item_evidence)
    del fallback_evidence


# 基于 CMake 的测试、clang 配置和源码信号生成 C/C++ 验证建议。
def _add_cmake_commands(
    component_root: Path,
    relative_path: str,
    direct_files: dict[str, Path],
    component_files: list[Path],
    combined_text: str,
    signals: _ComponentSignals,
    evidence: list[DetectionEvidence],
) -> None:
    source = _first_c_family_source(component_root, component_files)
    if source is not None and (".clang-format" in direct_files or "clang-format" in combined_text):
        _add_command(
            signals.validation_plan,
            ValidationCategory.FORMAT,
            f"clang-format --dry-run --Werror {source}",
            relative_path,
            "clang-format configuration detected",
            evidence,
        )
    if source is not None and (".clang-tidy" in direct_files or "clang-tidy" in combined_text):
        _add_command(
            signals.validation_plan,
            ValidationCategory.STATIC_CHECK,
            f"clang-tidy {source}",
            relative_path,
            "clang-tidy configuration detected",
            evidence,
        )
    has_tests = any(
        marker in combined_text for marker in ("enable_testing", "add_test", "gtest", "catch2")
    )
    if has_tests:
        _add_command(
            signals.validation_plan,
            ValidationCategory.UNIT_TEST,
            "ctest --test-dir build --output-on-failure",
            relative_path,
            "CTest or C/C++ test framework configuration detected",
            evidence,
        )
    if "integration" in combined_text:
        _add_command(
            signals.validation_plan,
            ValidationCategory.INTEGRATION_TEST,
            "ctest --test-dir build --output-on-failure -L integration",
            relative_path,
            "CMake integration-test signal detected",
            evidence,
        )
    _add_command(
        signals.validation_plan,
        ValidationCategory.BUILD,
        "cmake -S . -B build && cmake --build build",
        relative_path,
        "CMake build descriptor detected",
        evidence,
    )


# 为 Meson 项目生成保持在建议层的构建和测试命令。
def _add_meson_commands(
    relative_path: str,
    combined_text: str,
    signals: _ComponentSignals,
    evidence: list[DetectionEvidence],
) -> None:
    if "test(" in combined_text:
        _add_command(
            signals.validation_plan,
            ValidationCategory.UNIT_TEST,
            "meson test -C build",
            relative_path,
            "Meson test declaration detected",
            evidence,
        )
    _add_command(
        signals.validation_plan,
        ValidationCategory.BUILD,
        "meson setup build && meson compile -C build",
        relative_path,
        "Meson build descriptor detected",
        evidence,
    )


# 为 Makefile 中明确声明的目标生成 C/C++ 验证建议。
def _add_make_commands(
    relative_path: str,
    make_text: str,
    signals: _ComponentSignals,
    evidence: list[DetectionEvidence],
) -> None:
    for category, target, reason in (
        (ValidationCategory.FORMAT, "format", "Makefile format target detected"),
        (ValidationCategory.STATIC_CHECK, "lint", "Makefile lint target detected"),
        (ValidationCategory.UNIT_TEST, "test", "Makefile test target detected"),
        (
            ValidationCategory.INTEGRATION_TEST,
            "integration-test",
            "Makefile integration target detected",
        ),
    ):
        if _make_target_exists(make_text, target):
            _add_command(
                signals.validation_plan,
                category,
                f"make {target}",
                relative_path,
                reason,
                evidence,
            )
    build_command = "make build" if _make_target_exists(make_text, "build") else "make"
    _add_command(
        signals.validation_plan,
        ValidationCategory.BUILD,
        build_command,
        relative_path,
        "Make build descriptor detected",
        evidence,
    )


# 用行首 target 语法识别 Makefile 目标，避免把普通文本误作为可运行命令。
def _make_target_exists(make_text: str, target: str) -> bool:
    return re.search(rf"^{re.escape(target)}\s*:", make_text, flags=re.MULTILINE) is not None


# 根据显式 workspace 配置或多个项目边界判断是否为 Monorepo。
def _is_monorepo(root: Path, projects: list[ProjectComponent]) -> bool:
    if len(projects) > 1:
        return True
    package_json = root / "package.json"
    if package_json.is_file() and isinstance(
        _read_package_json(package_json).get("workspaces"), (list, dict)
    ):
        return True
    return any(
        (root / name).is_file()
        for name in (*_NODE_WORKSPACE_MARKERS, "settings.gradle", "settings.gradle.kts")
    )
