# 功能：验证 BashTool 动态权限分级逻辑
# 设计：覆盖只读命令降级、危险路径维持高级别、未知命令等场景
from __future__ import annotations

from sztu_code.core.tools.base import ToolPermission
from sztu_code.core.tools.builtin.bash import BashTool, _extract_cmd_name, _has_dangerous_paths


def _classify(command: str) -> ToolPermission:
    return BashTool().classify_permission({"command": command})


# 功能：验证只读命令 + 安全路径降级为 workspace_write
# 设计：ls、cat、git status 等纯读取命令应返回较低的权限级别
def test_bash_read_only_commands_downgraded() -> None:
    assert _classify("ls -la") == ToolPermission.WORKSPACE_WRITE
    assert _classify("cat file.txt") == ToolPermission.WORKSPACE_WRITE
    assert _classify("git status") == ToolPermission.WORKSPACE_WRITE
    assert _classify("grep -r pattern .") == ToolPermission.WORKSPACE_WRITE
    assert _classify("echo hello") == ToolPermission.WORKSPACE_WRITE
    assert _classify("wc -l file.txt") == ToolPermission.WORKSPACE_WRITE


# 功能：验证包含绝对路径的只读命令维持 danger_full_access
# 设计：即使命令是只读的，访问 /etc 等绝对路径应升级权限
def test_bash_read_only_with_dangerous_path_keeps_high() -> None:
    assert _classify("cat /etc/passwd") == ToolPermission.DANGER_FULL_ACCESS
    assert _classify("ls /root") == ToolPermission.DANGER_FULL_ACCESS


# 功能：验证包含 .. 的命令维持 danger_full_access
# 设计：父目录穿越即使配合只读命令也是危险的
def test_bash_parent_traversal_is_dangerous() -> None:
    assert _classify("cat ../../secret.txt") == ToolPermission.DANGER_FULL_ACCESS
    assert _classify("ls ../..") == ToolPermission.DANGER_FULL_ACCESS


# 功能：验证包含 sudo 的命令维持 danger_full_access
# 设计：任何包含 sudo 的命令都应是最危险的级别
def test_bash_sudo_is_dangerous() -> None:
    assert _classify("sudo ls") == ToolPermission.DANGER_FULL_ACCESS
    assert _classify("sudo cat /etc/shadow") == ToolPermission.DANGER_FULL_ACCESS


# 功能：验证非只读命令默认 danger_full_access
# 设计：rm、mv、curl 等修改系统状态的命令保持最高权限
def test_bash_write_commands_are_dangerous() -> None:
    assert _classify("rm -rf /tmp/test") == ToolPermission.DANGER_FULL_ACCESS
    assert _classify("curl http://example.com") == ToolPermission.DANGER_FULL_ACCESS
    assert _classify("pip install requests") == ToolPermission.DANGER_FULL_ACCESS
    assert _classify("npm install") == ToolPermission.DANGER_FULL_ACCESS


# 功能：验证空命令返回 danger_full_access
# 设计：空字符串或无命令应保守地返回最高级别
def test_bash_empty_command() -> None:
    assert _classify("") == ToolPermission.DANGER_FULL_ACCESS


# 功能：验证 _extract_cmd_name 从各种格式中正确提取命令名
# 设计：覆盖路径前缀、赋值前缀、引号等场景
def test_extract_cmd_name() -> None:
    assert _extract_cmd_name("ls -la") == "ls"
    assert _extract_cmd_name("  git status  ") == "git"
    assert _extract_cmd_name("./script.sh") == "script.sh"
    assert _extract_cmd_name("/usr/bin/python") == "python"
    assert _extract_cmd_name("VAR=val cmd") == "cmd"


# 功能：验证 Bash 默认超时和 Git 专用默认超时
# 设计：未显式设置时普通命令为 30 秒、Git 为 20 秒，显式 timeout 始终优先
def test_bash_effective_timeout_defaults() -> None:
    from sztu_code.core.tools.builtin.bash import BashParams, _effective_timeout

    assert _effective_timeout(BashParams(command="python -V"), "python -V") == 30
    assert _effective_timeout(BashParams(command="git status"), "git status") == 20
    assert _effective_timeout(BashParams(command="git status", timeout=7), "git status") == 7


# 功能：验证 _has_dangerous_paths 检测危险模式
# 设计：绝对路径、~、..、$HOME、sudo 等应被检出
def test_dangerous_path_detection() -> None:
    assert _has_dangerous_paths("cat /etc/hosts")
    assert _has_dangerous_paths("ls ~/Documents")
    assert _has_dangerous_paths("cd ../../../")
    assert _has_dangerous_paths("echo $HOME")
    assert _has_dangerous_paths("sudo reboot")
    assert not _has_dangerous_paths("ls -la")
    assert not _has_dangerous_paths("cat file.txt")
    assert not _has_dangerous_paths("git status")


# 功能：验证 Windows 风格命令被预处理为 git-bash 可用形式
# 设计：覆盖 cd /d、前导 dir、Windows 盘符路径三种常见误用（raw 字符串保证反斜杠字面量）
def test_preprocess_windows_commands() -> None:
    from sztu_code.core.tools.builtin.bash import _preprocess_command

    assert _preprocess_command(r"cd /d C:\repo\src && pwd") == "cd /c/repo/src && pwd"
    assert _preprocess_command("dir") == "ls"
    assert _preprocess_command(r"cd /d D:\data") == "cd /d/data"
    # 不含盘符的命令保持原样（避免破坏正则转义）
    assert _preprocess_command(r"grep '\d+' file") == r"grep '\d+' file"
    # cd 不带 /d 不受影响
    assert _preprocess_command("cd src && ls") == "cd src && ls"


# 功能：验证 cmd 风格命令（where/set/nul/%VAR%/type/cls）被转译为 git-bash 等价物
# 设计：逐条断言转换结果，并验证 bash 内建 type -p 等不误伤
def test_preprocess_cmd_isms_translated() -> None:
    from sztu_code.core.tools.builtin.bash import _preprocess_command

    assert _preprocess_command("where git") == "which git"
    assert _preprocess_command("dir 2>nul") == "ls 2>/dev/null"
    assert _preprocess_command("find . >nul") == "find . >/dev/null"
    assert (
        _preprocess_command("set PYTHONIOENCODING=utf-8 && python -V")
        == "export PYTHONIOENCODING=utf-8 && python -V"
    )
    assert _preprocess_command("cd %USERPROFILE%") == "cd $USERPROFILE"
    assert _preprocess_command("cls") == "clear"
    assert _preprocess_command("type config.py") == "cat config.py"
    # bash 内建 `type -p` 不应被误转为 cat
    assert _preprocess_command("type -p bash") == "type -p bash"
    assert _preprocess_command("del tmp.txt") == "rm tmp.txt"
    assert _preprocess_command("copy a.txt b.txt") == "cp a.txt b.txt"
    # dir 的 /s /b 标志映射到 ls 的 -R / -1
    assert _preprocess_command("dir /s /b src") == "ls -R src"
    assert _preprocess_command("dir /s src") == "ls -R src"
    assert _preprocess_command("dir /b src") == "ls -1 src"
    assert _preprocess_command("dir src") == "ls src"


# 功能：验证安装/更新依赖命令被 bash 工具直接拦截不执行
# 设计：pip/npm/apt/ensurepip 等命令应返回 is_error 且内容含 blocked，不触发子进程
async def test_install_commands_blocked() -> None:
    from sztu_code.core.tools.builtin.bash import _BLOCKED_INSTALL_RE, BashTool

    assert _BLOCKED_INSTALL_RE.search("pip install requests")
    assert _BLOCKED_INSTALL_RE.search("python -m pip install -e .")
    assert _BLOCKED_INSTALL_RE.search("npm install")
    assert _BLOCKED_INSTALL_RE.search("apt-get update && apt-get install curl")
    assert _BLOCKED_INSTALL_RE.search("ensurepip")
    assert _BLOCKED_INSTALL_RE.search("conda install numpy")
    assert not _BLOCKED_INSTALL_RE.search("git status")
    assert not _BLOCKED_INSTALL_RE.search("pytest tests/foo.py")
    assert not _BLOCKED_INSTALL_RE.search("echo hello world")

    result = await BashTool().invoke({"command": "pip install requests"})
    assert result.is_error
    assert "blocked" in result.content.lower()


# 功能：验证 Windows 上能找到可用的 git-bash，避免 cmd.exe 缺 Unix 工具
# 设计：标准安装路径或 PATH 中任一命中即视为可用；SZTU_BASH_PATH 可覆盖；未安装时回退 cmd 不算失败
def test_git_bash_path_detection() -> None:
    import sys

    from sztu_code.core.tools.builtin.bash import _git_bash_path

    found = _git_bash_path()
    if sys.platform != "win32":
        return
    if found is not None:
        from pathlib import Path

        assert Path(found).is_file()


# 功能：验证此前在 cmd.exe 下失败的命令（grep/pwd 等）经 git-bash 执行成功
# 设计：覆盖真实 bug 回归——Windows 且 git-bash 存在时断言非错误输出；无 git-bash 的环境跳过
async def test_bash_runs_unix_tools_on_windows() -> None:
    import sys

    from sztu_code.core.tools.builtin.bash import BashTool, _git_bash_path

    if sys.platform != "win32" or _git_bash_path() is None:
        return
    result = await BashTool().invoke({"command": "grep --version"})
    assert not result.is_error, result.content
    assert "grep" in result.content.lower()
    result = await BashTool().invoke({"command": "pwd"})
    assert not result.is_error, result.content
