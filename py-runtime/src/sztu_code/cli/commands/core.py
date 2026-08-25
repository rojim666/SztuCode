from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path

from sztu_code.core.config import SztuConfig

_PID_FILE = Path.home() / ".sztu" / "sztu-code.pid"


# 尝试连接 daemon，成功则正常返回，失败则抛出 ConnectionRefusedError/OSError
async def _ping_check(config: SztuConfig) -> None:
    _r, w = await asyncio.open_connection(config.host, config.port)
    w.close()
    await w.wait_closed()


# Windows 上 os.kill(pid,0) 对活进程也可能抛错（权限/完整性级别差异），改用 tasklist 判断存活
def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True
        )
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# 读取 PID 文件并确认进程存活，进程已消失则删除文件并返回 None
def _running_pid() -> int | None:
    if not _PID_FILE.exists():
        return None
    try:
        pid = int(_PID_FILE.read_text().strip())
    except ValueError:
        _PID_FILE.unlink(missing_ok=True)
        return None
    if _pid_alive(pid):
        return pid
    _PID_FILE.unlink(missing_ok=True)
    return None


# 打印 daemon 当前状态（running / not running）
def cmd_core_status(config: SztuConfig) -> None:
    try:
        asyncio.run(_ping_check(config))
        print(f"running  ({config.host}:{config.port})")
    except (ConnectionRefusedError, OSError):
        print("not running")


# 在后台启动 daemon，若已在运行则提示并退出
def cmd_core_start(config: SztuConfig) -> None:
    try:
        asyncio.run(_ping_check(config))
        print(f"already running  ({config.host}:{config.port})")
        return
    except (ConnectionRefusedError, OSError):
        pass

    proc = subprocess.Popen(
        [sys.executable, "-m", "sztu_code.core"],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PID_FILE.write_text(str(proc.pid))
    print(f"started  pid={proc.pid}  ({config.host}:{config.port})")


# 向 daemon 发送 SIGTERM 停止进程，若未运行则提示
def cmd_core_stop(config: SztuConfig) -> None:
    pid = _running_pid()
    if pid is None:
        print("not running")
        return
    os.kill(pid, signal.SIGTERM)
    _PID_FILE.unlink(missing_ok=True)
    print(f"stopped  pid={pid}")
