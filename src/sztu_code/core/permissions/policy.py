from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class PermissionDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class PermissionMode(StrEnum):
    """权限模式：控制工具调用的审批行为"""
    NORMAL = "normal"           # 默认模式，走完整权限检查流程
    AUTO = "auto"               # 自动批准所有工具调用
    ACCEPT_EDITS = "accept_edits"  # 自动批准编辑操作，其他仍需审批
    PLAN = "plan"               # 只允许只读工具，拒绝所有写入/执行


# 编辑类工具（Accept Edits 模式下自动批准）
_EDIT_TOOLS: set[str] = {"write_file", "note_save"}

# 只读工具（Plan 模式下允许）
_READONLY_TOOLS: set[str] = {
    "read_file", "list_dir",
    "task_get", "task_list",
}

# 写入/执行类工具（Plan 模式下拒绝）
_WRITE_EXEC_TOOLS: set[str] = {
    "write_file", "bash", "note_save",
    "task_create", "task_update",
}


# 检查工具是否属于编辑类
def is_edit_tool(tool_name: str) -> bool:
    return tool_name in _EDIT_TOOLS


# 检查工具是否属于只读类
def is_readonly_tool(tool_name: str) -> bool:
    return tool_name in _READONLY_TOOLS


# 检查工具是否属于写入/执行类
def is_write_exec_tool(tool_name: str) -> bool:
    return tool_name in _WRITE_EXEC_TOOLS


# 检测 bash 命令是否操作 cwd 之外路径的正则规则列表（强制触发 ASK，不可被 allow_patterns 绕过）
OUTSIDE_CWD_HEURISTICS: list[str] = [
    r"(^|\s)/[^\s]",              # absolute path
    r"(^|\s)~",                   # tilde home
    r"(^|\s)\.\.(/|$|\s)",        # parent traversal
    r"\$\{?HOME\b",               # $HOME variable
    r"\$\{?PWD\b",                # $PWD variable
    r"(^|\s|;|&&|\|\|)cd(\s|$)",  # explicit cd
    # 以下为参考 Claude Code 的 AST 安全检测新增的启发式规则
    r"(^|\s|;|&&|\|\|)sudo\b",              # sudo 提权
    r"(^|\s|;|&&|\|\|)builtin\s+cd\b",      # builtin cd 绕过
    r"(^|\s|;|&&|\|\|)command\s+cd\b",      # command cd 绕过
    r"(^|\s|;|&&|\|\|)(source|\.)\s+[~/]",  # source 外部文件
    r"\bLD_PRELOAD\b",                        # 动态库注入劫持
    r"\bLD_LIBRARY_PATH\b",                   # 库路径劫持
]

_OUTSIDE_CWD_RE: list[re.Pattern[str]] = [re.compile(p) for p in OUTSIDE_CWD_HEURISTICS]


# 判断 bash 命令是否命中 outside-cwd 启发式规则
def matches_outside_cwd(command: str) -> bool:
    return any(pat.search(command) for pat in _OUTSIDE_CWD_RE)


# 将复合 bash 命令按 && || ; | 拆分为独立子命令，保留引号内的分隔符
def split_compound_command(command: str) -> list[str]:
    segments: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(command):
        ch = command[i]
        # 处理反斜杠转义
        if ch == "\\" and i + 1 < len(command):
            current.append(ch)
            current.append(command[i + 1])
            i += 2
            continue
        # 处理引号状态
        if ch == "'" and not in_double:
            in_single = not in_single
            current.append(ch)
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            current.append(ch)
            i += 1
            continue
        # 在引号内，直接追加
        if in_single or in_double:
            current.append(ch)
            i += 1
            continue
        # 检查分隔符 && || ; |
        if ch == "&" and i + 1 < len(command) and command[i + 1] == "&":
            segments.append("".join(current).strip())
            current = []
            i += 2
            continue
        if ch == "|" and i + 1 < len(command) and command[i + 1] == "|":
            segments.append("".join(current).strip())
            current = []
            i += 2
            continue
        if ch == "|":
            segments.append("".join(current).strip())
            current = []
            i += 1
            continue
        if ch == ";":
            segments.append("".join(current).strip())
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    remaining = "".join(current).strip()
    if remaining:
        segments.append(remaining)
    # 如果没有拆分出多段，返回原始命令的单元素列表
    return segments if len(segments) > 1 else [command.strip()]


# 对复合命令的每个子命令执行 deny_patterns 检查，任一段命中即返回 True
def _any_segment_matches_deny(command: str, deny_patterns: list[str]) -> bool:
    segments = split_compound_command(command)
    for seg in segments:
        for pat in deny_patterns:
            if re.search(pat, seg):
                return True
    return False


# 对复合命令的每个子命令执行 OUTSIDE_CWD 检查，任一段命中即返回 True
def _any_segment_matches_outside_cwd(command: str) -> bool:
    segments = split_compound_command(command)
    for seg in segments:
        if matches_outside_cwd(seg):
            return True
    return False


@dataclass
class ToolPolicy:
    default: PermissionDecision
    allow_patterns: list[str] = field(default_factory=list)
    deny_patterns: list[str] = field(default_factory=list)


DEFAULT_POLICIES: dict[str, ToolPolicy] = {
    "bash":       ToolPolicy(default=PermissionDecision.ASK),
    "write_file": ToolPolicy(default=PermissionDecision.ASK),
    "read_file":  ToolPolicy(default=PermissionDecision.ALLOW),
    "list_dir":   ToolPolicy(default=PermissionDecision.ALLOW),
    "note_save":  ToolPolicy(default=PermissionDecision.ALLOW),
}

# 未在 DEFAULT_POLICIES 中登记的工具的兜底策略
_UNKNOWN_TOOL_DEFAULT = PermissionDecision.ASK

# bash 参数中展示用的关键字段映射
_PREVIEW_KEY: dict[str, str] = {
    "bash":       "command",
    "read_file":  "path",
    "write_file": "path",
    "list_dir":   "path",
    "note_save":  "content",
}
_PREVIEW_MAX = 60


# 为权限审批事件生成人类可读的参数摘要
def param_preview(tool_name: str, params: dict[str, Any]) -> str:
    key = _PREVIEW_KEY.get(tool_name)
    if key and key in params:
        val = str(params[key])
        if len(val) > _PREVIEW_MAX:
            val = val[:_PREVIEW_MAX] + "…"
        return f"{key}={val!r}"
    snippet = str(params)
    return snippet[:_PREVIEW_MAX] if len(snippet) > _PREVIEW_MAX else snippet


# 对工具 + 参数执行 4 层静态策略评估，返回 ALLOW/DENY/ASK
def evaluate(
    tool_name: str,
    params: dict[str, Any],
    policy: ToolPolicy | None = None,
) -> PermissionDecision:
    if policy is None:
        policy = DEFAULT_POLICIES.get(tool_name)

    if policy is None:
        return _UNKNOWN_TOOL_DEFAULT

    command = str(params.get("command", "")) if tool_name == "bash" else ""

    # Tier 1: deny_patterns (bash only) — 逐段检查复合命令
    if command and policy.deny_patterns:
        if _any_segment_matches_deny(command, policy.deny_patterns):
            return PermissionDecision.DENY

    # Tier 2: OUTSIDE_CWD_HEURISTICS — forced ASK, not bypassable — 逐段检查复合命令
    if command and _any_segment_matches_outside_cwd(command):
        return PermissionDecision.ASK

    # Tier 3: allow_patterns (bash only)
    if command:
        for pat in policy.allow_patterns:
            if re.search(pat, command):
                return PermissionDecision.ALLOW

    # Tier 4: tool default
    return policy.default
