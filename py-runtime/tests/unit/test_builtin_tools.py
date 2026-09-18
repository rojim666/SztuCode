from __future__ import annotations

import asyncio
import os
import shlex
import signal
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from sztu_code.core.tools.base import ToolExecutionState
from sztu_code.core.tools.builtin import bash as bash_module
from sztu_code.core.tools.builtin.bash import BashTool
from sztu_code.core.tools.builtin.list_dir import ListDirTool
from sztu_code.core.tools.builtin.write_file import WriteFileTool


def _process_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False

    if os.name != "nt":
        stat_path = Path(f"/proc/{pid}/stat")
        if stat_path.exists():
            try:
                return stat_path.read_text().split()[2] != "Z"
            except (OSError, IndexError):
                pass
    return True


async def _wait_for_file(path: Path, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not path.exists():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError(f"timed out waiting for {path}")
        await asyncio.sleep(0.01)


async def _wait_for_process_exit(pid: int, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while _process_is_running(pid):
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError(f"process {pid} is still running")
        await asyncio.sleep(0.01)


# ── bash ──────────────────────────────────────────────────────────────────────

# 功能：验证成功命令的 stdout 出现在 ToolResult.content 中，is_error 为 False
# 设计：用 echo 命令避免外部依赖，直接比较输出内容，无需 mock
@pytest.mark.asyncio
async def test_bash_success_stdout() -> None:
    result = await BashTool().invoke({"command": "echo hello"})
    assert not result.is_error
    assert "hello" in result.content


# 功能：验证非零退出码时 is_error=True 且 content 包含退出码标注
# 设计：`exit 2` 是最简单的非零退出；不依赖任何外部命令行为
@pytest.mark.asyncio
async def test_bash_nonzero_exit_is_error() -> None:
    result = await BashTool().invoke({"command": "exit 2"})
    assert result.is_error
    assert "[exit 2]" in result.content


# 功能：验证命令超时后 is_error=True，error_type 为 "timeout"
# 设计：固定关闭 git-bash 分支并 mock create_subprocess_shell，保证各平台都走同一条 shell 路径；
#       用受控假进程模拟 communicate 超时，避免依赖平台特定的 sleep 命令
@pytest.mark.asyncio
async def test_bash_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    process = Mock(returncode=None)
    process.pid = 123
    process.communicate = AsyncMock(side_effect=[TimeoutError, (b"", None)])
    process.kill = Mock()
    create_process = AsyncMock(return_value=process)
    killer = Mock()
    killer.communicate = AsyncMock(return_value=(b"", None))
    create_killer = AsyncMock(return_value=killer)
    monkeypatch.setattr("sztu_code.core.tools.builtin.bash._git_bash_path", lambda: None)
    monkeypatch.setattr(bash_module, "_create_windows_job", lambda proc: None)
    monkeypatch.setattr(bash_module, "_resume_windows_process", lambda pid: None)
    monkeypatch.setattr(asyncio, "create_subprocess_shell", create_process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_killer)

    result = await BashTool().invoke({"command": "long-running", "timeout": 1})

    assert result.is_error
    assert result.error_type == "timeout", result.content
    assert result.execution_state == ToolExecutionState.UNKNOWN
    process.kill.assert_called_once_with()
    assert process.communicate.await_count == 2


@pytest.mark.asyncio
async def test_windows_cleanup_kills_the_process_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    # A parent may have exited while a descendant still owns the pipe.
    process = Mock(returncode=0, pid=123)
    killer = Mock()
    killer.communicate = AsyncMock(return_value=(b"", None))
    create_killer = AsyncMock(return_value=killer)
    monkeypatch.setattr(bash_module.os, "name", "nt")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_killer)

    await bash_module._terminate_process_tree(process)  # type: ignore[arg-type]

    create_killer.assert_awaited_once_with(
        "taskkill",
        "/PID",
        "123",
        "/T",
        "/F",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    process.kill.assert_called_once_with()


@pytest.mark.asyncio
async def test_posix_cleanup_kills_the_process_group(monkeypatch: pytest.MonkeyPatch) -> None:
    process = Mock(returncode=None, pid=123)
    killpg = Mock()
    monkeypatch.setattr(bash_module.os, "name", "posix")
    monkeypatch.setattr(bash_module.os, "killpg", killpg, raising=False)

    await bash_module._terminate_process_tree(process)  # type: ignore[arg-type]

    killpg.assert_called_once_with(123, getattr(signal, "SIGKILL", signal.SIGTERM))
    process.kill.assert_called_once_with()


@pytest.mark.asyncio
async def test_bash_timeout_kills_a_real_child_process_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    child_code = (
        "import os,pathlib,time;"
        "pathlib.Path('child-pid.txt').write_text(str(os.getpid()));"
        "time.sleep(1.5);"
        "pathlib.Path('child-survived.txt').write_text('survived')"
    )
    parent_code = (
        "import subprocess,sys,time;"
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]);"
        "time.sleep(30)"
    )
    if bash_module.os.name == "nt":
        # Keep this process-tree test independent of Git Bash/WSL discovery;
        # the Windows shell path still exercises CREATE_NEW_PROCESS_GROUP and taskkill /T.
        monkeypatch.setattr(bash_module, "_git_bash_path", lambda: None)
        command = subprocess.list2cmdline(["python", "-c", parent_code])
    else:
        command = f"python -c {shlex.quote(parent_code)}"

    result = await BashTool(tmp_path).invoke({"command": command, "timeout": 1})

    assert result.is_error
    assert result.error_type == "timeout"
    assert result.execution_state == ToolExecutionState.UNKNOWN
    await _wait_for_file(tmp_path / "child-pid.txt")
    await _wait_for_process_exit(int((tmp_path / "child-pid.txt").read_text()))
    assert (tmp_path / "child-pid.txt").exists()
    assert not (tmp_path / "child-survived.txt").exists()


@pytest.mark.asyncio
async def test_bash_timeout_kills_descendant_after_parent_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    child_code = (
        "import os,pathlib,time;"
        "pathlib.Path('child-pid.txt').write_text(str(os.getpid()));"
        "time.sleep(2);"
        "pathlib.Path('child-survived.txt').write_text('survived')"
    )
    parent_code = (
        "import subprocess,sys,time;"
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]);"
        "time.sleep(0.2)"
    )
    if bash_module.os.name == "nt":
        monkeypatch.setattr(bash_module, "_git_bash_path", lambda: None)
        command = subprocess.list2cmdline(["python", "-c", parent_code])
    else:
        command = f"python -c {shlex.quote(parent_code)}"

    result = await BashTool(tmp_path).invoke({"command": command, "timeout": 1})

    assert result.is_error
    assert result.error_type == "timeout"
    assert result.execution_state == ToolExecutionState.UNKNOWN
    await _wait_for_file(tmp_path / "child-pid.txt")
    await _wait_for_process_exit(int((tmp_path / "child-pid.txt").read_text()))
    assert not (tmp_path / "child-survived.txt").exists()


@pytest.mark.asyncio
async def test_bash_parent_cancellation_kills_and_reaps_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = Mock(returncode=None)
    process.pid = 123
    process.communicate = AsyncMock(side_effect=[asyncio.CancelledError, (b"", None)])
    process.kill = Mock()
    create_process = AsyncMock(return_value=process)
    killer = Mock()
    killer.communicate = AsyncMock(return_value=(b"", None))
    create_killer = AsyncMock(return_value=killer)
    monkeypatch.setattr("sztu_code.core.tools.builtin.bash._git_bash_path", lambda: None)
    monkeypatch.setattr(bash_module, "_create_windows_job", lambda proc: None)
    monkeypatch.setattr(bash_module, "_resume_windows_process", lambda pid: None)
    monkeypatch.setattr(asyncio, "create_subprocess_shell", create_process)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_killer)

    with pytest.raises(asyncio.CancelledError):
        await BashTool().invoke({"command": "long-running", "timeout": 1})

    process.kill.assert_called_once_with()
    assert process.communicate.await_count == 2


@pytest.mark.asyncio
async def test_bash_cleanup_failure_keeps_timeout_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = Mock(returncode=None, pid=123)
    process.communicate = AsyncMock(side_effect=TimeoutError)
    process.kill = Mock()
    create_process = AsyncMock(return_value=process)
    monkeypatch.setattr(bash_module, "_git_bash_path", lambda: None)
    monkeypatch.setattr(bash_module, "_create_windows_job", lambda proc: None)
    monkeypatch.setattr(bash_module, "_resume_windows_process", lambda pid: None)
    monkeypatch.setattr(asyncio, "create_subprocess_shell", create_process)

    async def failed_cleanup(
        proc: asyncio.subprocess.Process, job_handle: int | None
    ) -> str:
        del proc, job_handle
        return "reap: pipe closed"

    monkeypatch.setattr(bash_module, "_cleanup_process", failed_cleanup)

    result = await BashTool().invoke({"command": "long-running", "timeout": 1})

    assert result.is_error
    assert result.error_type == "timeout"
    assert result.execution_state == ToolExecutionState.UNKNOWN
    assert "cleanup failed: reap: pipe closed" in result.content


# 功能：验证 stderr 被合并到 stdout 输出中
# 设计：只写 stderr 的命令（>&2 echo），输出应该出现在合并后的 content 里
@pytest.mark.asyncio
async def test_bash_stderr_merged() -> None:
    result = await BashTool().invoke({"command": "echo err >&2"})
    assert not result.is_error
    assert "err" in result.content


# ── write_file ────────────────────────────────────────────────────────────────

# 功能：验证 write_file 写入文件后内容可以被读取，返回字节数
# 设计：写入临时目录，断言文件存在且内容一致；用 tmp_path fixture 自动清理
@pytest.mark.asyncio
async def test_write_file_creates_and_returns_size(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    result = await WriteFileTool(tmp_path).invoke(
        {"path": "out.txt", "content": "hello world"}
    )
    assert not result.is_error
    assert "11" in result.content  # "hello world" = 11 bytes
    assert target.read_text() == "hello world"


# 功能：验证 write_file 自动创建不存在的父目录
# 设计：路径包含两层不存在的子目录，确认写入后目录结构被创建
@pytest.mark.asyncio
async def test_write_file_creates_parent_dirs(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "file.txt"
    result = await WriteFileTool(tmp_path).invoke(
        {"path": "a/b/file.txt", "content": "x"}
    )
    assert not result.is_error
    assert target.exists()


# 功能：验证 write_file 拒绝包含 .. 的路径并抛出 PermissionError
# 设计：.. 路径遍历与 read_file 遵循相同规则，用相同的断言模式保持一致性
@pytest.mark.asyncio
async def test_write_file_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(PermissionError):
        await WriteFileTool(tmp_path).invoke(
            {"path": "../secret.txt", "content": "x"}
        )


# ── list_dir ──────────────────────────────────────────────────────────────────

# 功能：验证 list_dir 输出包含目录中的文件名
# 设计：在 tmp_path 创建已知结构，断言文件名出现在 content 中；不约束格式细节
@pytest.mark.asyncio
async def test_list_dir_shows_files(tmp_path: Path) -> None:
    (tmp_path / "foo.py").write_text("x")
    (tmp_path / "bar.md").write_text("y")
    result = await ListDirTool(tmp_path).invoke({"path": "."})
    assert not result.is_error
    assert "foo.py" in result.content
    assert "bar.md" in result.content


# 功能：验证 list_dir 按 max_depth 限制递归深度（depth=1 时不展示孙级目录内容）
# 设计：创建 parent/child/grandchild 三层，depth=1 时 grandchild 不应出现在输出中
@pytest.mark.asyncio
async def test_list_dir_respects_max_depth(tmp_path: Path) -> None:
    child = tmp_path / "child"
    child.mkdir()
    grandchild = child / "grandchild"
    grandchild.mkdir()
    (grandchild / "deep.txt").write_text("x")

    result = await ListDirTool(tmp_path).invoke({"path": ".", "max_depth": 1})
    assert not result.is_error
    assert "child" in result.content
    assert "deep.txt" not in result.content


# 功能：验证对不存在的路径 list_dir 抛出 FileNotFoundError
# 设计：直接传入不存在的路径字符串，预期抛出标准异常（invocation.py 捕获后返回 error ToolResult）
@pytest.mark.asyncio
async def test_list_dir_missing_path_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        await ListDirTool(tmp_path).invoke({"path": "missing"})


# 功能：验证 list_dir 拒绝包含 .. 的路径
# 设计：与 read_file 和 write_file 保持一致的安全规则
@pytest.mark.asyncio
async def test_list_dir_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(PermissionError):
        await ListDirTool(tmp_path).invoke({"path": "../"})
