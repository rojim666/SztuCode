from __future__ import annotations

import asyncio
import ctypes
import functools
import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from sztu_code.core.tools.base import (
    BaseTool,
    ToolExecutionState,
    ToolPermission,
    ToolResult,
)

_MAX_OUTPUT_BYTES = 64 * 1024  # 64 KB
_DEFAULT_TIMEOUT = 30
_DEFAULT_GIT_TIMEOUT = 20
_PROCESS_CLEANUP_TIMEOUT = 1.0
_WINDOWS_CREATE_SUSPENDED = 0x00000004
_WINDOWS_SNAPSHOT_THREAD = 0x00000004
_WINDOWS_THREAD_SUSPEND_RESUME = 0x0002
_WINDOWS_PROCESS_SET_QUOTA = 0x0100
_WINDOWS_PROCESS_TERMINATE = 0x0001
_WINDOWS_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


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


def _process_group_options() -> dict[str, Any]:
    if os.name == "nt":
        return {
            # Suspend first so the Job Object is attached before the shell can
            # create descendants; _resume_windows_process releases the gate.
            "creationflags": (
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | _WINDOWS_CREATE_SUSPENDED
            ),
        }
    return {"start_new_session": True}


def _windows_kernel32() -> Any | None:
    if os.name != "nt":
        return None
    win_dll = getattr(ctypes, "WinDLL", None)
    if win_dll is None:
        return None
    try:
        return win_dll("kernel32", use_last_error=True)
    except OSError:
        return None


def _native_handle_value(handle: Any) -> int | None:
    if isinstance(handle, int):
        return handle or None
    value = getattr(handle, "value", None)
    return int(value) if value else None


def _create_windows_job(proc: asyncio.subprocess.Process) -> int | None:
    """Attach the process to a Job so descendants survive parent exit only to cleanup."""
    kernel32 = _windows_kernel32()
    if kernel32 is None:
        return None

    handle_type = ctypes.c_void_p
    kernel32.CreateJobObjectW.restype = handle_type
    kernel32.OpenProcess.restype = handle_type
    kernel32.AssignProcessToJobObject.restype = ctypes.c_int
    kernel32.CloseHandle.restype = ctypes.c_int

    job = kernel32.CreateJobObjectW(None, None)
    job_value = _native_handle_value(job)
    if not job_value:
        return None

    keep_job = False
    try:
        process_handle = kernel32.OpenProcess(
            _WINDOWS_PROCESS_SET_QUOTA
            | _WINDOWS_PROCESS_TERMINATE
            | _WINDOWS_PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            proc.pid,
        )
        process_value = _native_handle_value(process_handle)
        if not process_value:
            return None

        try:
            assigned = kernel32.AssignProcessToJobObject(
                handle_type(job_value), handle_type(process_value)
            )
        finally:
            kernel32.CloseHandle(handle_type(process_value))

        if not assigned:
            return None
        keep_job = True
        return int(job_value)
    except Exception:
        return None
    finally:
        if not keep_job:
            kernel32.CloseHandle(handle_type(job_value))


def _resume_windows_process(pid: int) -> None:
    """Resume a suspended process after its Job Object has been attached."""
    if os.name != "nt":
        return
    kernel32 = _windows_kernel32()
    if kernel32 is None:
        raise RuntimeError("Windows process control is unavailable")

    class _ThreadEntry32(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.c_uint32),
            ("cntUsage", ctypes.c_uint32),
            ("th32ThreadID", ctypes.c_uint32),
            ("th32OwnerProcessID", ctypes.c_uint32),
            ("tpBasePri", ctypes.c_int32),
            ("tpDeltaPri", ctypes.c_int32),
            ("dwFlags", ctypes.c_uint32),
        ]

    handle_type = ctypes.c_void_p
    kernel32.CreateToolhelp32Snapshot.restype = handle_type
    kernel32.Thread32First.restype = ctypes.c_int
    kernel32.Thread32Next.restype = ctypes.c_int
    kernel32.OpenThread.restype = handle_type
    kernel32.ResumeThread.restype = ctypes.c_uint32
    kernel32.CloseHandle.restype = ctypes.c_int

    snapshot = kernel32.CreateToolhelp32Snapshot(_WINDOWS_SNAPSHOT_THREAD, 0)
    snapshot_value = _native_handle_value(snapshot)
    if not snapshot_value:
        raise RuntimeError("Unable to enumerate Windows process threads")

    entry = _ThreadEntry32(dwSize=ctypes.sizeof(_ThreadEntry32))
    resumed = False
    try:
        has_entry = kernel32.Thread32First(
            handle_type(snapshot_value), ctypes.byref(entry)
        )
        while has_entry:
            if entry.th32OwnerProcessID == pid:
                thread = kernel32.OpenThread(
                    _WINDOWS_THREAD_SUSPEND_RESUME,
                    False,
                    entry.th32ThreadID,
                )
                thread_value = _native_handle_value(thread)
                if thread_value:
                    try:
                        if kernel32.ResumeThread(handle_type(thread_value)) == 0xFFFFFFFF:
                            raise RuntimeError("Unable to resume Windows process thread")
                        resumed = True
                    finally:
                        kernel32.CloseHandle(handle_type(thread_value))
            has_entry = kernel32.Thread32Next(
                handle_type(snapshot_value), ctypes.byref(entry)
            )
    finally:
        kernel32.CloseHandle(handle_type(snapshot_value))

    if not resumed:
        raise RuntimeError("Windows process primary thread was not found")


def _close_windows_job(job_handle: int | None) -> None:
    if job_handle is None:
        return
    kernel32 = _windows_kernel32()
    if kernel32 is not None:
        kernel32.CloseHandle(ctypes.c_void_p(job_handle))


async def _terminate_process_tree(
    proc: asyncio.subprocess.Process, job_handle: int | None = None
) -> None:
    """Stop the shell and its descendants before the pipe is reaped."""
    if os.name == "nt":
        kernel32 = _windows_kernel32()
        if kernel32 is not None and job_handle is not None:
            kernel32.TerminateJobObject.restype = ctypes.c_int
            kernel32.TerminateJobObject(ctypes.c_void_p(job_handle), 1)
        try:
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(proc.pid),
                "/T",
                "/F",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await asyncio.wait_for(
                killer.communicate(), timeout=_PROCESS_CLEANUP_TIMEOUT
            )
        except Exception:
            # Fall back to killing the shell handle if taskkill is unavailable.
            pass
    else:
        killpg = getattr(os, "killpg", None)
        if killpg is not None:
            try:
                killpg(proc.pid, getattr(signal, "SIGKILL", signal.SIGTERM))
            except (PermissionError, ProcessLookupError):
                pass

    try:
        proc.kill()
    except ProcessLookupError:
        pass


async def _reap_process(proc: asyncio.subprocess.Process) -> None:
    """Reap a terminated process without letting pipe cleanup hang forever."""
    try:
        await asyncio.wait_for(
            proc.communicate(), timeout=_PROCESS_CLEANUP_TIMEOUT
        )
    except TimeoutError:
        # Keep the timeout result UNKNOWN when the process cannot be confirmed
        # reaped within the bounded cleanup window.
        pass


async def _cleanup_process(
    proc: asyncio.subprocess.Process, job_handle: int | None
) -> str | None:
    """Attempt tree termination and reaping, preserving cleanup failures."""
    errors: list[str] = []
    try:
        await _terminate_process_tree(proc, job_handle)
    except Exception as exc:
        errors.append(f"terminate: {exc}")
    try:
        await _reap_process(proc)
    except Exception as exc:
        errors.append(f"reap: {exc}")
    return "; ".join(errors) if errors else None


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
        # 评测场景（Terminal-Bench 等 bench harness）任务本身常要求安装依赖，
        # 由 SZTU_EVAL_ALLOW_INSTALL=1 显式放开
        if _BLOCKED_INSTALL_RE.search(command) and not os.environ.get("SZTU_EVAL_ALLOW_INSTALL"):
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
        proc: asyncio.subprocess.Process | None = None
        job_handle: int | None = None
        try:
            if bash:
                proc = await asyncio.create_subprocess_exec(
                    bash, "--login", "-c", command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=str(self._workspace_root) if self._workspace_root is not None else None,
                    **_process_group_options(),
                )
            else:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=str(self._workspace_root) if self._workspace_root is not None else None,
                    **_process_group_options(),
                )
            job_handle = _create_windows_job(proc)
            _resume_windows_process(proc.pid)
            try:
                stdout_bytes, _ = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except TimeoutError:
                cleanup_error = await _cleanup_process(proc, job_handle)
                cleanup_suffix = f"; cleanup failed: {cleanup_error}" if cleanup_error else ""
                return ToolResult(
                    content=f"[timeout after {timeout}s]{cleanup_suffix}",
                    is_error=True,
                    error_type="timeout",
                    execution_state=ToolExecutionState.UNKNOWN,
                )
            except asyncio.CancelledError:
                # Parent Run cancellation must not leave the child process
                # alive; preserve cancellation after best-effort reaping.
                try:
                    await _terminate_process_tree(proc, job_handle)
                    await _reap_process(proc)
                except Exception:
                    pass
                raise
            finally:
                _close_windows_job(job_handle)
        except Exception as exc:
            cleanup_error = (
                await _cleanup_process(proc, job_handle) if proc is not None else None
            )
            cleanup_suffix = f"; cleanup failed: {cleanup_error}" if cleanup_error else ""
            return ToolResult(
                content=f"{exc}{cleanup_suffix}",
                is_error=True,
                error_type="runtime_error",
                execution_state=(
                    ToolExecutionState.UNKNOWN
                    if proc is not None
                    else ToolExecutionState.COMPLETED
                ),
            )

        output = stdout_bytes.decode("utf-8", errors="replace")
        truncated = len(stdout_bytes) > _MAX_OUTPUT_BYTES
        if truncated:
            output = output[:_MAX_OUTPUT_BYTES] + "\n[truncated]"

        assert proc is not None
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
