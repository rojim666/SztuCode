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
