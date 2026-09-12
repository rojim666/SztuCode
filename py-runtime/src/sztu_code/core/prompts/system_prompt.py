from __future__ import annotations

import platform
import subprocess
from pathlib import Path

from sztu_code.core.prompts.catalog import (
    DEFAULT_PROMPT_CATALOG,
    PromptCatalog,
)
from sztu_code.core.prompts.catalog import PromptIndexError as PromptIndexError
from sztu_code.core.prompts.Sztubuddy import build_base

# 静态/动态段分界哨兵，供 /system-prompt 定位动态上下文起点
DYNAMIC_BOUNDARY = "__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__"

# 预算常量
MAX_INSTRUCTION_FILE_CHARS = 4_000
MAX_TOTAL_INSTRUCTION_CHARS = 12_000
MAX_GIT_DIFF_CHARS = 50_000
_MAX_PARENT_SCAN_DEPTH = 6

# 候选指令文件名与 scope 标识
_INSTRUCTION_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("CLAUDE.md", "claude_md"),
    ("SZTUCODE.md", "sztucode_md"),
    ("CLAW.md", "claw_md"),
    ("AGENTS.md", "agents_md"),
    (".claude/CLAUDE.md", "claude_claude_md"),
)


# 按分组索引声明的顺序加载原子提示词及其稳定 ID
def load_prompt_entries(
    group: str, *, prompt_root: Path | None = None
) -> tuple[tuple[str, str], ...]:
    catalog = DEFAULT_PROMPT_CATALOG if prompt_root is None else PromptCatalog(prompt_root)
    return tuple((entry.prompt_id, entry.content) for entry in catalog.entries(group))


# 仅返回 Markdown 正文，供静态系统提示词按索引顺序拼接
def load_prompt_sections(group: str, *, prompt_root: Path | None = None) -> tuple[str, ...]:
    return tuple(
        content for _section_id, content in load_prompt_entries(group, prompt_root=prompt_root)
    )


# 常驻基座只保留身份、安全和最小执行约束；详细规则由 Harness 按场景注入
def _static_sections() -> tuple[str, ...]:
    return (build_base(),)


# 在指定目录执行 git 命令，失败或非 git 目录返回空字符串
def _git(root: Path, *args: str) -> str:
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
    return result.stdout


# 拼接静态脚手架段，供主代理和子代理继承
def build_static_base() -> str:
    return "\n\n".join(_static_sections())


# 渲染环境上下文段：模型家族、工作目录、平台
# 注意：日期不在这里——它每天变化，写进 system 会击穿前缀缓存；
# 改由 runner 注入到消息尾部。
def _environment_section(*, cwd: str, model_family: str, os_name: str, os_version: str) -> str:
    return (
        "# Environment context\n"
        f" - Model family: {model_family}\n"
        f" - Working directory: {cwd}\n"
        f" - Platform: {os_name} {os_version}"
    )


# 渲染 git 快照：分支、最近提交、变更文件、diff（超预算截断）；非 git 目录返回 None
def render_git_snapshot(workspace_root: Path) -> str | None:
    branch = _git(workspace_root, "branch", "--show-current").strip()
    status = _git(workspace_root, "status", "--short", "--branch").strip()
    if not branch and not status:
        return None
    commits = _git(workspace_root, "log", "-5", "--pretty=format:%h %s").strip()
    diff = _git(workspace_root, "diff", "--no-ext-diff")
    if len(diff) > MAX_GIT_DIFF_CHARS:
        diff = diff[:MAX_GIT_DIFF_CHARS] + "\n... [diff truncated — too large for system prompt]"
    lines = [f"Git branch: {branch or '(detached)'}"]
    if status:
        lines.append("\nGit status snapshot:\n" + status)
    if commits:
        lines.append("\nRecent commits (last 5):\n" + commits)
    if diff:
        lines.append("\nGit diff snapshot:\n" + diff)
    return "\n".join(lines)


# 归一化文本：折叠连续空行并 trim，用于去重与预算
def _normalize(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if line.strip()).strip()


# 从工作区根向上发现指令文件（CLAUDE.md、SZTUCODE.md 等），去重并受预算限制
def discover_instruction_files(root: Path) -> list[tuple[str, str]]:
    seen: set[str] = set()
    entries: list[tuple[str, str]] = []
    budget = MAX_TOTAL_INSTRUCTION_CHARS
    current = root.expanduser().resolve()
    for _depth in range(_MAX_PARENT_SCAN_DEPTH):
        for candidate, scope in _INSTRUCTION_CANDIDATES:
            path = current / candidate
            if not path.is_file():
                continue
            try:
                content = _normalize(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            if not content:
                continue
            digest = f"{scope}:{content}"
            if digest in seen:
                continue
            seen.add(digest)
            if len(content) > MAX_INSTRUCTION_FILE_CHARS:
                content = content[:MAX_INSTRUCTION_FILE_CHARS] + "\n[truncated]"
            if len(content) > budget:
                content = content[:budget] + "\n[truncated]"
                budget = 0
            else:
                budget -= len(content)
            label = (
                candidate
                if candidate in {"CLAUDE.md", "SZTUCODE.md"}
                else f"{current.name}/{candidate}"
            )
            entries.append((label, content))
            if budget <= 0:
                return entries
        if current.parent == current:
            break
        current = current.parent
    return entries


# 渲染项目上下文与项目指令段。
# 注意：git 快照不在这里渲染——它随文件改动每轮变化，写进 system prompt 会击穿
# 前缀缓存（system 是缓存锚点，一旦变化整段缓存失效）；改由 runner 通过
# render_git_snapshot 注入到消息尾部。
def _project_sections(
    *,
    cwd: str,
    instruction_entries: list[tuple[str, str]],
) -> list[str]:
    sections: list[str] = [
        "# Project context\n"
        f" - Working directory: {cwd}\n"
        f" - Project instruction files discovered: {len(instruction_entries)}."
    ]
    if instruction_entries:
        parts = ["# Project instructions"]
        for label, content in instruction_entries:
            parts.append(f"## {label}\n{content}")
        sections.append("\n".join(parts))
    return sections


# 组装完整分层系统提示词
def build_system_prompt(
    *,
    workspace_root: Path | None = None,
    model_family: str = "an AI assistant",
    platform_name: str | None = None,
    platform_version: str | None = None,
) -> str:
    cwd = str((workspace_root or Path.cwd()).resolve())
    os_name = platform_name or platform.system()
    os_version = platform_version or platform.release()

    instruction_entries: list[tuple[str, str]] = []
    if workspace_root is not None:
        instruction_entries = discover_instruction_files(workspace_root)

    sections: list[str] = list(_static_sections())
    sections.append(DYNAMIC_BOUNDARY)
    sections.append(
        _environment_section(
            cwd=cwd,
            model_family=model_family,
            os_name=os_name,
            os_version=os_version,
        )
    )
    sections.extend(
        _project_sections(
            cwd=cwd,
            instruction_entries=instruction_entries,
        )
    )
    return "\n\n".join(sections)
