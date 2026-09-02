from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from sztu_code.core.prompts import build_system_prompt
from sztu_code.core.prompts.system_prompt import (
    DYNAMIC_BOUNDARY,
    MAX_INSTRUCTION_FILE_CHARS,
    PromptIndexError,
    build_static_base,
    discover_instruction_files,
    load_prompt_sections,
    render_git_snapshot,
)


# 在临时目录执行 git 命令
def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


# 功能：验证静态基础段同时包含已索引章节和尚未迁移的后续章节
# 设计：直接拼 build_static_base，断言常驻身份、安全和最小任务约束存在，详细规则不常驻
def test_static_base_contains_indexed_main_and_existing_sections() -> None:
    base = build_static_base()
    assert "交互式智能体" in base
    assert "不要对你没有阅读过的代码提出更改建议" in base
    assert "# 谨慎执行操作" not in base
    assert "用户选择的权限模式下执行" in base
    assert "授权的安全测试" in base


# 功能：验证第一章主系统提示词完全由有序索引加载
# 设计：断言三个原子内容均存在，并按照身份、权限、安全审查的索引顺序拼接
def test_main_prompt_sections_are_loaded_in_index_order() -> None:
    sections = load_prompt_sections("main")

    assert len(sections) == 3
    assert sections[0].startswith("你是 SztuCode")
    assert sections[1].startswith("工具在用户选择的权限模式下执行")
    assert sections[2].startswith("重要提示：可以协助进行授权的安全测试")


# 功能：验证第二章任务执行指令按 2.1 至 2.13 的索引顺序完整加载
# 设计：检查原子数量、首尾内容和关键中间规则，并确认静态提示词没有重复注入
def test_doing_tasks_sections_are_loaded_once_in_index_order() -> None:
    sections = load_prompt_sections("doing-tasks")
    base = build_static_base()

    assert len(sections) == 13
    assert sections[0].startswith("用户主要会要求你执行软件工程任务")
    assert sections[1].startswith("一般来说，不要对你没有阅读过的代码提出更改建议")
    assert sections[2].startswith("注意不要引入安全漏洞")
    assert sections[9].startswith("避免给出任务所需时间的估计")
    assert "使用 SztuCode 的帮助" in sections[10]
    assert "github.com/rojim666/SztuCode/issues" in sections[10]
    assert sections[-1].startswith("如果你的方法受阻")
    assert sum(section in base for section in sections) == 4


# 功能：验证第三章谨慎执行操作由完整原子提示词加载且仅注入一次
# 设计：检查高风险操作、确认边界和受阻后的处理规则，避免退回旧的精简版本
def test_executing_actions_with_care_section_is_loaded_once() -> None:
    sections = load_prompt_sections("executing-actions-with-care")
    base = build_static_base()

    assert len(sections) == 1
    section = sections[0]
    assert section.startswith("# 谨慎执行操作")
    assert "用户一次批准某个操作（如 git push）并不意味着他们在所有上下文中都批准该操作" in section
    assert "破坏性操作：删除文件/分支" in section
    assert "不要使用破坏性操作作为让问题消失的捷径" in section
    assert base.count(section) == 0


# 功能：验证第四章输出效率由完整原子提示词加载且仅注入一次
# 设计：检查简洁输出、状态更新和错误报告等关键约束，并确保不重复注入
def test_output_efficiency_section_is_loaded_once() -> None:
    sections = load_prompt_sections("output-efficiency")
    base = build_static_base()

    assert len(sections) == 1
    section = sections[0]
    assert section.startswith("# 输出效率")
    assert "直奔主题" in section
    assert "在自然里程碑处的高层级状态更新" in section
    assert "这不适用于代码或工具调用" in section
    assert base.count(section) == 1


# 功能：验证第五章语气与风格的三个原子按顺序加载且仅注入一次
# 设计：检查代码引用、工具调用前标点和简洁输出约束，避免重复注入相同指令
def test_tone_and_style_sections_are_loaded_once_in_index_order() -> None:
    sections = load_prompt_sections("tone-and-style")
    base = build_static_base()

    assert len(sections) == 3
    assert sections[0].startswith("在引用特定函数或代码片段时")
    assert "file_path:line_number" in sections[0]
    assert sections[1].startswith("仅当用户明确要求时才使用表情符号")
    assert "在工具调用前不要使用冒号" in sections[1]
    assert sections[2] == "你的回复应简短精炼。"
    assert base.count(sections[0]) == 0
    assert base.count(sections[1]) == 0
    assert sections[2] in base


# 功能：验证第六章工具使用策略按顺序加载并使用 SztuCode 的真实工具名
# 设计：覆盖六项专用工具规则，以及探索、并行、任务管理、运行环境原子
def test_tool_usage_policy_sections_are_loaded_once_in_index_order() -> None:
    sections = load_prompt_sections("tool-usage-policy")
    base = build_static_base()

    assert len(sections) == 10
    assert sections[0].startswith("# 工具使用策略")
    assert "`read_file`" in sections[0]
    assert "`edit_file`" in sections[1]
    assert "`write_file`" in sections[2]
    assert "`glob_search`" in sections[3] and "`list_dir`" in sections[3]
    assert "`grep_search`" in sections[4]
    assert "将 `bash` 保留用于" in sections[5]
    assert "`spawn_agent`" in sections[6]
    assert '`subagent_type="explore"`' in sections[6]
    assert "不会继承父对话历史" in sections[6]
    assert "并行执行所有独立的工具调用" in sections[7]
    assert "按顺序调用它们" in sections[7]
    assert all(
        tool_name in sections[8]
        for tool_name in ("`task_create`", "`task_update`", "`task_list`", "`task_get`")
    )
    assert "使用 Git Bash 而不是 cmd" in sections[9]
    assert "ensurepip 安装包" in sections[9]
    assert all(base.count(section) == 0 for section in sections)


# 功能：验证主系统提示词的章节分组顺序稳定
# 设计：第一至六章顺序稳定，第六章必须先于尚未迁移的工作协议
def test_static_prompt_group_order() -> None:
    base = build_static_base()

    assert base.index("你是 SztuCode") < base.index("用户主要会要求你执行软件工程任务")
    assert base.index("用户主要会要求你执行软件工程任务") < base.index("# 输出效率")
    assert base.index("# 输出效率") < base.index("你的回复应简短精炼")
    assert base.index("你的回复应简短精炼") < base.index("# Work protocol")


# 功能：验证索引中的非法路径不会越过提示词分组目录
# 设计：使用临时索引指向父目录，断言加载器在读取文件前即拒绝
def test_prompt_index_rejects_non_atomic_markdown_path(tmp_path: Path) -> None:
    group_root = tmp_path / "main"
    group_root.mkdir()
    (group_root / "index.json").write_text(
        json.dumps(
            {
                "version": 1,
                "sections": [
                    {"id": "escape", "file": "../outside.md", "source": "test"}
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(PromptIndexError, match="invalid file"):
        load_prompt_sections("main", prompt_root=tmp_path)


# 功能：验证完整提示词含动态边界、环境与项目段
# 设计：无 workspace 时断言 boundary 与 Environment 段存在，且不含指令段
def test_build_system_prompt_has_boundary_and_environment() -> None:
    prompt = build_system_prompt(workspace_root=None)
    assert DYNAMIC_BOUNDARY in prompt
    assert "# Environment context" in prompt
    assert "# Project context" in prompt
    assert "# Project instructions" not in prompt


# 功能：验证从工作区发现 CLAUDE.md 并注入指令段
# 设计：临时目录放一份 CLAUDE.md，build 后断言其内容与文件名出现
def test_discover_and_inject_claude_md(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text("项目规则：先写测试再实现\n", encoding="utf-8")

    entries = discover_instruction_files(tmp_path)
    assert len(entries) == 1
    assert entries[0][0] == "CLAUDE.md"
    assert "先写测试再实现" in entries[0][1]

    prompt = build_system_prompt(workspace_root=tmp_path)
    assert "## CLAUDE.md" in prompt
    assert "先写测试再实现" in prompt


# 功能：验证 SztuCode 原生项目指令文件与 CLAUDE.md 使用同一套发现和注入机制
# 设计：临时目录放置 SZTUCODE.md，分别检查发现结果和完整系统提示词
def test_discover_and_inject_sztucode_md(tmp_path: Path) -> None:
    (tmp_path / "SZTUCODE.md").write_text(
        "SztuCode 项目规则：先运行测试\n", encoding="utf-8"
    )

    entries = discover_instruction_files(tmp_path)
    assert len(entries) == 1
    assert entries[0][0] == "SZTUCODE.md"
    assert "先运行测试" in entries[0][1]

    prompt = build_system_prompt(workspace_root=tmp_path)
    assert "## SZTUCODE.md" in prompt
    assert "SztuCode 项目规则：先运行测试" in prompt


# 功能：验证超大指令文件被按预算截断
# 设计：写入远超单文件上限的 CLAUDE.md，断言内容被截断且含 [truncated]
def test_instruction_file_budget_truncation(tmp_path: Path) -> None:
    big = "x" * (MAX_INSTRUCTION_FILE_CHARS + 200)
    (tmp_path / "CLAUDE.md").write_text(big, encoding="utf-8")

    entries = discover_instruction_files(tmp_path)

    assert len(entries) == 1
    assert len(entries[0][1]) <= MAX_INSTRUCTION_FILE_CHARS + len("\n[truncated]")
    assert entries[0][1].endswith("[truncated]")


# 功能：验证 git 快照渲染分支、提交与 diff
# 设计：临时 git 仓库提交后修改文件，断言 branch/commit/diff 出现在快照里
def test_git_snapshot_renders(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "T")
    (tmp_path / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "init")
    _git(tmp_path, "branch", "-M", "main")
    (tmp_path / "a.txt").write_text("one\nTWO\n", encoding="utf-8")

    snapshot = render_git_snapshot(tmp_path)

    assert snapshot is not None
    assert "Git branch: main" in snapshot
    assert "Recent commits" in snapshot
    assert "Git diff snapshot" in snapshot


# 功能：验证系统提示包含工作协议段（禁止安装/先验证后停）
# 设计：检查静态基座是否包含 Work protocol 段及关键约束短语
def test_static_base_contains_work_protocol() -> None:
    base = build_static_base()
    assert "# Work protocol" in base
    assert "install/update commands are blocked" in base
    assert "verify" in base
