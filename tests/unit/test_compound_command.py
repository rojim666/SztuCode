from __future__ import annotations

import pytest

from sztu_code.core.permissions.policy import (
    PermissionDecision,
    ToolPolicy,
    _any_segment_matches_deny,
    _any_segment_matches_outside_cwd,
    evaluate,
    matches_outside_cwd,
    split_compound_command,
)

# ── split_compound_command ─────────────────────────────────────────────────────

# 功能：验证纯单命令不拆分
# 设计：无分隔符的命令返回包含原命令的单元素列表
def test_simple_command_not_split() -> None:
    result = split_compound_command("echo hello")
    assert result == ["echo hello"]


# 功能：验证 && 正确拆分复合命令
# 设计：cmd1 && cmd2 → 两个独立段
def test_and_and_splits() -> None:
    result = split_compound_command("cd /tmp && ls -la")
    assert result == ["cd /tmp", "ls -la"]


# 功能：验证 || 正确拆分
# 设计：cmd1 || cmd2 → 两个独立段
def test_or_or_splits() -> None:
    result = split_compound_command("false || echo fallback")
    assert result == ["false", "echo fallback"]


# 功能：验证管道 | 正确拆分
# 设计：cmd1 | cmd2 → 两个独立段
def test_pipe_splits() -> None:
    result = split_compound_command("cat file | grep pattern")
    assert result == ["cat file", "grep pattern"]


# 功能：验证分号 ; 正确拆分
# 设计：cmd1; cmd2 → 两个独立段
def test_semicolon_splits() -> None:
    result = split_compound_command("echo a; echo b")
    assert result == ["echo a", "echo b"]


# 功能：验证引号内的分隔符被保留不拆分
# 设计：echo "a && b" 中 && 在双引号内，不应拆分
def test_quoted_separator_preserved() -> None:
    result = split_compound_command('echo "a && b"')
    assert result == ['echo "a && b"']


# 功能：验证单引号内的分隔符被保留
# 设计：echo 'a || b' 中 || 在单引号内，不应拆分
def test_single_quoted_separator_preserved() -> None:
    result = split_compound_command("echo 'a || b'")
    assert result == ["echo 'a || b'"]


# 功能：验证多段复合命令正确拆分
# 设计：三段用 && 连接
def test_three_segment_split() -> None:
    result = split_compound_command("mkdir dir && cd dir && touch file")
    assert result == ["mkdir dir", "cd dir", "touch file"]


# ── 复合命令 deny_patterns 检查 ────────────────────────────────────────────────

# 功能：验证复合命令第二段命中 deny → 整体 DENY
# 设计：第一段安全但第二段含 rm -rf，应整体拒绝
def test_deny_in_second_segment_blocked() -> None:
    policy = ToolPolicy(
        default=PermissionDecision.ASK,
        deny_patterns=[r"\brm\b"],
    )
    result = evaluate("bash", {"command": "echo safe && rm -rf /tmp"}, policy)
    assert result == PermissionDecision.DENY


# 功能：验证 deny_patterns 在第一段命中同样生效
# 设计：第一段就含 rm，第一段检测即拒绝
def test_deny_in_first_segment_blocked() -> None:
    policy = ToolPolicy(
        default=PermissionDecision.ASK,
        deny_patterns=[r"\brm\b"],
    )
    result = evaluate("bash", {"command": "rm -rf /tmp && echo done"}, policy)
    assert result == PermissionDecision.DENY


# ── 复合命令 OUTSIDE_CWD 检查 ──────────────────────────────────────────────────

# 功能：验证复合命令任一段命中 OUTSIDE_CWD → 强制 ASK
# 设计：第一段安全（echo），第二段含绝对路径 → 整体 ASK
def test_outside_cwd_in_any_segment_forces_ask() -> None:
    policy = ToolPolicy(default=PermissionDecision.ALLOW)  # 即使默认 ALLOW
    result = evaluate("bash", {"command": "echo safe && cat /etc/passwd"}, policy)
    assert result == PermissionDecision.ASK


# 功能：验证所有段都在 cwd 内时不触发 OUTSIDE_CWD
# 设计：两段都是安全本地操作，应走 allow_patterns 或 default
def test_all_segments_safe_no_outside_cwd() -> None:
    policy = ToolPolicy(default=PermissionDecision.ASK, allow_patterns=[r"^echo\b"])
    result = evaluate("bash", {"command": "echo hello && echo world"}, policy)
    assert result == PermissionDecision.ALLOW


# ── 新增 OUTSIDE_CWD 规则测试 ──────────────────────────────────────────────────

# 功能：验证 sudo 命令触发 OUTSIDE_CWD 强制 ASK
# 设计：sudo 提权操作必须确认
def test_sudo_forces_ask() -> None:
    assert matches_outside_cwd("sudo apt install pkg")


# 功能：验证 builtin cd 触发 OUTSIDE_CWD 强制 ASK
# 设计：builtin cd 绕过常规 cd 检测，但新规则应捕获
def test_builtin_cd_forces_ask() -> None:
    assert matches_outside_cwd("builtin cd /tmp")


# 功能：验证 command cd 触发 OUTSIDE_CWD 强制 ASK
# 设计：command cd 是另一种 cd 绕过方式
def test_command_cd_forces_ask() -> None:
    assert matches_outside_cwd("command cd /etc")


# 功能：验证 source 外部文件触发 OUTSIDE_CWD
# 设计：source /some/path 加载外部脚本，存在风险
def test_source_outside_forces_ask() -> None:
    assert matches_outside_cwd("source ~/env.sh")


# 功能：验证 LD_PRELOAD 触发 OUTSIDE_CWD
# 设计：LD_PRELOAD 可劫持任何进程，必须确认
def test_ld_preload_forces_ask() -> None:
    assert matches_outside_cwd("LD_PRELOAD=/evil.so ./app")


# 功能：验证 LD_LIBRARY_PATH 触发 OUTSIDE_CWD
# 设计：库路径劫持同样危险
def test_ld_library_path_forces_ask() -> None:
    assert matches_outside_cwd("LD_LIBRARY_PATH=/evil ./app")


# 功能：验证安全的本地命令不触发新规则误报
# 设计：常规 git 操作不应被 sudo 规则误匹配
def test_safe_commands_not_misdetected() -> None:
    assert not matches_outside_cwd("git status")
    assert not matches_outside_cwd("npm install")
    assert not matches_outside_cwd("python -m pytest")


# ── _any_segment 辅助函数 ──────────────────────────────────────────────────────

# 功能：验证 _any_segment_matches_deny 正确检测复合命令的 deny 段
# 设计：传入 deny_patterns 列表和复合命令，确认返回 True
def test_any_segment_matches_deny_detects() -> None:
    assert _any_segment_matches_deny(
        "ls && rm -rf /", [r"\brm\b"]
    ) is True


# 功能：验证 _any_segment_matches_deny 在无命中时返回 False
# 设计：安全复合命令不应触发 deny
def test_any_segment_matches_deny_no_match() -> None:
    assert _any_segment_matches_deny(
        "ls && echo done", [r"\brm\b"]
    ) is False


# 功能：验证 _any_segment_matches_outside_cwd 检测复合命令的越界段
# 设计：含绝对路径段时返回 True
def test_any_segment_matches_outside_cwd_detects() -> None:
    assert _any_segment_matches_outside_cwd(
        "echo ok && cat /etc/hosts"
    ) is True


# 功能：验证 _any_segment_matches_outside_cwd 在安全时返回 False
# 设计：全程本地操作不触发
def test_any_segment_matches_outside_cwd_no_match() -> None:
    assert _any_segment_matches_outside_cwd(
        "echo hello && ls src/"
    ) is False
