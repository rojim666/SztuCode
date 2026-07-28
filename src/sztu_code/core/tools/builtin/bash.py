from __future__ import annotations

import asyncio
import re
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from sztu_code.core.tools.base import BaseTool, ToolPermission, ToolResult

_MAX_OUTPUT_BYTES = 64 * 1024  # 64 KB
_DEFAULT_TIMEOUT = 60


class BashParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    command: str
    timeout: int = Field(default=_DEFAULT_TIMEOUT, ge=1, le=120)


# bash 只读命令白名单 — 仅读取信息不修改系统状态
_READ_ONLY_COMMANDS: set[str] = {
    "cat", "head", "tail", "less", "more", "ls", "dir",
    "grep", "rg", "awk", "sed", "wc", "file", "stat",
    "find", "which", "whereis", "type", "echo", "printf",
    "date", "env", "printenv", "pwd", "whoami", "uname",
    "git", "python", "python3", "node", "npm", "uv", "pip",
    "cargo", "rustc", "go", "javac", "java",
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


class BashTool(BaseTool):
    params_model = BashParams
    name = "bash"
    required_permission = ToolPermission.DANGER_FULL_ACCESS
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

    # 在子进程中执行 shell 命令，合并 stdout/stderr，超时或非零退出码时返回错误
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = BashParams.model_validate(params)
        command = p.command
        timeout = p.timeout

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
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
