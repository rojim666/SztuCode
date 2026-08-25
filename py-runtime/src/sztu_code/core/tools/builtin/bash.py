from __future__ import annotations

import asyncio
import functools
import os
import re
import shutil
import sys
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from sztu_code.core.tools.base import BaseTool, ToolPermission, ToolResult

_MAX_OUTPUT_BYTES = 64 * 1024  # 64 KB
_DEFAULT_TIMEOUT = 30
_DEFAULT_GIT_TIMEOUT = 20


class BashParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    command: str
    timeout: int = Field(default=_DEFAULT_TIMEOUT, ge=1, le=120)


# bash 只读命令白名单 — 仅读取信息不修改系统状态
_READ_ONLY_COMMANDS: set[str] = {
    "cat", "head", "tail", "less", "more", "ls", "dir",
    "grep", "rg", "awk", "sed", "wc", "file", "stat",
    "find", "which", "where", "whereis", "type", "echo", "printf",
    "date", "env", "printenv", "pwd", "whoami", "uname", "cls",
    "git", "python", "python3", "node",
}

# 危险路径模式 — 操作工作区外或提权的命令
_DANGEROUS_PATH_PATTERNS: list[str] = [
    r"(^|\s)/[^\s]",              # 绝对路径
    r"(^|\s)~",                   # tilde home
    r"(^|\s)\.\.(/|$|\s)",        # 父目录穿越
    r"\$\{?HOME\b",
    r"\$\{?PWD\b",
    r"\bLD_PRELOAD\b",
    r"\bLD_LIBRARY_PATH\b",
    r"(^|\s|;|&&|\|\|)sudo\b",
]
_DANGEROUS_RE: list[re.Pattern[str]] = [re.compile(p) for p in _DANGEROUS_PATH_PATTERNS]

# 环境安装命令——直接拦截：环境已就绪，安装必然失败且烧掉大量步骤
_BLOCKED_INSTALL_RE = re.compile(
    r"(^|;|&&|\|\|)\s*(?:"
    r"python(\d|3)?\s+-m\s+pip\s+install|"
    r"pip(\d|3)?\s+install|"
    r"uv\s+pip\s+install|"
    r"pipenv\s+install|"
    r"poetry\s+install|"
    r"npm\s+(?:install|i|add)\b|"
    r"yarn\s+(?:install|add)\b|"
    r"pnpm\s+(?:install|add)\b|"
    r"apt(-get)?\s+(?:install|update)|"
    r"brew\s+install|"
    r"conda\s+install|"
    r"python(\d|3)?\s+-m\s+ensurepip|"
    r"ensurepip"
    r")(?=\s|$)"
)


def _extract_cmd_name(command: str) -> str:
    """提取命令的第一个单词（去除路径前缀和引号）"""
    stripped = command.strip()
    # 跳过前导赋值 (VAR=val cmd)
    if "=" in stripped.split()[0] if stripped.split() else False:
        parts = stripped.split(None, 1)
        if len(parts) > 1:
            stripped = parts[1]
    # 提取命令名
    word = stripped.split()[0] if stripped.split() else ""
    # 去除 ./ 或路径前缀
    if "/" in word:
        word = word.rsplit("/", 1)[-1]
    return word


def _has_dangerous_paths(command: str) -> bool:
    """检测命令是否包含危险路径模式"""
    return any(pat.search(command) for pat in _DANGEROUS_RE)


# 根据命令类型和显式参数选择唯一一层子进程超时
def _effective_timeout(params: BashParams, command: str) -> int:
    if "timeout" not in params.model_fields_set and _extract_cmd_name(command) == "git":
        return _DEFAULT_GIT_TIMEOUT
    return params.timeout


# 返回 Windows 上可用的 git-bash 路径；未找到返回 None（缓存，可用 SZTU_BASH_PATH 覆盖）
@functools.lru_cache(maxsize=1)
def _git_bash_path() -> str | None:
    candidates = [
        os.environ.get("SZTU_BASH_PATH", ""),
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return shutil.which("bash")


# 预处理 agent 常见的 Windows/cmd 风格命令，让其在 git-bash 下可用
def _preprocess_command(command: str) -> str:
    # cmd 风格 `cd /d X` → `cd X`（/d 是 cmd 切换盘符的标志，bash 不认）
    cmd = re.sub(r"\bcd\s+/d\b", "cd", command)
    # cmd 的 `dir /s`（递归）/`/b`（裸名）标志 → ls 的 -R/-1
    cmd = re.sub(
        r"^\s*dir(\s+/[sb]){1,2}\b",
        lambda m: "ls -R" if "/s" in m.group(0).lower() else "ls -1",
        cmd,
        flags=re.IGNORECASE,
    )
    # 前导 `dir` → `ls`（git-bash 下无 dir 命令）
    cmd = re.sub(r"^\s*dir(?=\s|$)", "ls", cmd)
    # cmd 的 `where X` → git-bash `which X`
    cmd = re.sub(r"\bwhere\s+(?=[A-Za-z0-9_./\\-])", "which ", cmd)
    # cmd 的重定向到 NUL 设备 → /dev/null
    cmd = re.sub(r"(?<![\w.])2>nul\b", "2>/dev/null", cmd, flags=re.IGNORECASE)
    cmd = re.sub(r"(?<![\w.])>nul\b", ">/dev/null", cmd, flags=re.IGNORECASE)
    # cmd 的 `set VAR=val` → bash 环境变量导出
    cmd = re.sub(r"\bset\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)", r"export \1=\2", cmd)
    # cmd 的 `%VAR%` → bash `$VAR`
    cmd = re.sub(r"%([A-Za-z_][A-Za-z0-9_]*)%", r"$\1", cmd)
    # cmd 的 `cls` → `clear`
    cmd = re.sub(r"^\s*cls(?=\s|$)", "clear", cmd)
    # cmd 的 `type <文件>`（读文件）→ `cat`，仅当后跟疑似路径时转换，避免误伤 bash 内建 type
    cmd = re.sub(r"^\s*type\s+(?=[^\s;|&]*[./\\])", "cat ", cmd, flags=re.IGNORECASE)
    # cmd 的 del/copy/move/ren → bash 的 rm/cp/mv/mv（bash 无这些内建，转换安全）
    cmd = re.sub(r"^\s*del\s+", "rm ", cmd, flags=re.IGNORECASE)
    cmd = re.sub(r"^\s*copy\s+", "cp ", cmd, flags=re.IGNORECASE)
    cmd = re.sub(r"^\s*move\s+", "mv ", cmd, flags=re.IGNORECASE)
    cmd = re.sub(r"^\s*ren\s+", "mv ", cmd, flags=re.IGNORECASE)
    # 含 Windows 盘符路径（C:\a\b 或 C:/a/b）时转成 git-bash 风格 /c/a/b，并把反斜杠转正斜杠
    if re.search(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]", cmd):
        cmd = re.sub(
            r"(?<![A-Za-z0-9])([A-Za-z]):([\\/])",
            lambda m: f"/{m.group(1).lower()}/",
            cmd,
        )
        cmd = cmd.replace("\\", "/")
    return cmd


class BashTool(BaseTool):
    params_model = BashParams
    name = "bash"
    required_permission = ToolPermission.DANGER_FULL_ACCESS
    manages_timeout = True
    aliases: ClassVar[list[str]] = []
    description = (
        "Execute a shell command and return its output (stdout + stderr combined). "
        "Non-interactive only — commands requiring user input will hang and time out. "
        "Prefer short, focused commands. Output is truncated at 64 KB."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute.",
            },
            "timeout": {
                "type": "integer",
                "description": f"Maximum seconds to wait (default {_DEFAULT_TIMEOUT}, max 120).",
            },
        },
        "required": ["command"],
    }

    # 绑定可选工作区根目录，使 shell 命令以任务工作区作为 cwd 执行
    def __init__(self, workspace_root: Path | None = None) -> None:
        self._workspace_root = workspace_root

    # 在子进程中执行 shell 命令，合并 stdout/stderr，超时或非零退出码时返回错误
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = BashParams.model_validate(params)
        command = _preprocess_command(p.command)
        timeout = _effective_timeout(p, command)

        # 安装/更新依赖命令直接拦截，不执行：环境已就绪，安装必然失败并浪费步骤
        if _BLOCKED_INSTALL_RE.search(command):
            return ToolResult(
                content=(
                    "[blocked] Installing/updating packages is not allowed in this "
                    "environment — dependencies are already provisioned. Do not run "
                    "install/update commands; use the existing packages directly."
                ),
                is_error=True,
                error_type="runtime_error",
            )

        # Windows 下优先用 git-bash 执行，否则 cmd.exe 找不到 grep/sed/pwd 等 Unix 工具
        bash = _git_bash_path() if sys.platform == "win32" else None
        try:
            if bash:
                proc = await asyncio.create_subprocess_exec(
                    bash, "--login", "-c", command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=str(self._workspace_root) if self._workspace_root is not None else None,
                )
            else:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=str(self._workspace_root) if self._workspace_root is not None else None,
                )
            try:
                stdout_bytes, _ = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except TimeoutError:
                proc.kill()
                await proc.communicate()
                return ToolResult(
                    content=f"[timeout after {timeout}s]",
                    is_error=True,
                    error_type="timeout",
                )
        except Exception as exc:
            return ToolResult(content=str(exc), is_error=True, error_type="runtime_error")

        output = stdout_bytes.decode("utf-8", errors="replace")
        truncated = len(stdout_bytes) > _MAX_OUTPUT_BYTES
        if truncated:
            output = output[:_MAX_OUTPUT_BYTES] + "\n[truncated]"

        returncode = proc.returncode or 0
        if returncode != 0:
            return ToolResult(
                content=f"[exit {returncode}]\n{output}",
                is_error=True,
                error_type="runtime_error",
            )
        return ToolResult(content=output or "[no output]")

    # 动态权限分级：只读命令 + 无危险路径 → workspace_write；其余 → danger_full_access
    def classify_permission(self, params: dict[str, object]) -> ToolPermission:
        command = str(params.get("command", ""))
        if not command:
            return ToolPermission.DANGER_FULL_ACCESS
        cmd_name = _extract_cmd_name(command)
        if cmd_name in _READ_ONLY_COMMANDS and not _has_dangerous_paths(command):
            return ToolPermission.WORKSPACE_WRITE
        return ToolPermission.DANGER_FULL_ACCESS
