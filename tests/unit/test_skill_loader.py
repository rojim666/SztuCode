from __future__ import annotations

from pathlib import Path

import pytest

from sztu_code.core.skills.loader import Skill, SkillLoader


# 功能：内建 review skill 应能被 SkillLoader 查找到
# 设计：直接调用 resolve("review")，不依赖文件系统之外的任何状态
def test_builtin_skill_found() -> None:
    loader = SkillLoader()
    skill = loader.resolve("review")
    assert skill is not None
    assert skill.name == "review"
    assert "审查" in skill.description or "review" in skill.description.lower()
    assert skill.system_prompt_template != ""


# 功能：内建 init / summarize / orchestrate skill 均可找到
# 设计：列举所有内建 skill 名，断言均能解析
@pytest.mark.parametrize("name", ["init", "review", "summarize", "orchestrate"])
def test_all_builtin_skills_found(name: str) -> None:
    loader = SkillLoader()
    skill = loader.resolve(name)
    assert skill is not None, f"builtin skill '{name}' not found"


# 功能：不存在的 skill 名应返回 None
# 设计：查找一个不存在的名称，断言 resolve 返回 None 而非抛异常
def test_unknown_skill_returns_none() -> None:
    loader = SkillLoader()
    result = loader.resolve("nonexistent_skill_xyz")
    assert result is None


# 功能：render_prompt 应将 $ARGUMENTS 替换为传入的参数字符串
# 设计：构造含 $ARGUMENTS 的 skill，验证 render_prompt 结果不含 "$ARGUMENTS" 且含参数值
def test_arguments_substituted() -> None:
    loader = SkillLoader()
    skill = Skill(
        name="test",
        description="test skill",
        system_prompt_template="Review this: $ARGUMENTS\nPlease be thorough.",
        allowed_tools=[],
    )
    rendered = loader.render_prompt(skill, "src/foo.py")
    assert "$ARGUMENTS" not in rendered
    assert "src/foo.py" in rendered


# 功能：frontmatter 中的 allowed_tools 列表应被正确解析
# 设计：构造含 allowed_tools 的 Markdown 文件，通过 _parse_skill_file 解析并验证结果
def test_frontmatter_parsed(tmp_path: Path) -> None:
    from sztu_code.core.skills.loader import _parse_skill_file

    content = """\
---
name: custom
description: 自定义 skill 测试
allowed_tools:
  - read_file
  - bash
---
你是一个测试助手，目标：$ARGUMENTS
"""
    p = tmp_path / "custom.md"
    p.write_text(content, encoding="utf-8")
    skill = _parse_skill_file(p)
    assert skill.name == "custom"
    assert skill.description == "自定义 skill 测试"
    assert "read_file" in skill.allowed_tools
    assert "bash" in skill.allowed_tools
    assert "$ARGUMENTS" in skill.system_prompt_template


# 功能：无 frontmatter 的 Markdown 文件仍可加载，allowed_tools 为空列表
# 设计：写入纯正文 Markdown，断言解析成功且 allowed_tools=[]
def test_no_frontmatter(tmp_path: Path) -> None:
    from sztu_code.core.skills.loader import _parse_skill_file

    content = "你是助手，请帮助用户完成任务：$ARGUMENTS\n"
    p = tmp_path / "plain.md"
    p.write_text(content, encoding="utf-8")
    skill = _parse_skill_file(p)
    assert skill.name == "plain"
    assert skill.allowed_tools == []
    assert "你是助手" in skill.system_prompt_template


# 功能：项目本地 skill 应覆盖内建同名 skill
# 设计：在 .sztu/skills/ 中写入同名文件，用 monkeypatch 修改 cwd，断言加载到的是本地版本
def test_project_overrides_global(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    local_skills = tmp_path / ".sztu" / "skills"
    local_skills.mkdir(parents=True)
    (local_skills / "review.md").write_text(
        "---\nname: review\ndescription: local override\n---\nlocal system prompt $ARGUMENTS\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    loader = SkillLoader()
    skill = loader.resolve("review")
    assert skill is not None
    assert skill.description == "local override"
    assert "local system prompt" in skill.system_prompt_template


# 功能：指定工作区根目录时应发现该工作区内的项目技能
# 设计：不切换进程 cwd，验证会话绑定的工作区而不是 daemon 启动目录决定技能发现。
def test_project_root_is_used_for_skill_discovery(tmp_path: Path) -> None:
    skills = tmp_path / ".sztu" / "skills"
    skills.mkdir(parents=True)
    (skills / "release.md").write_text(
        "---\nname: release\ndescription: workspace skill\n---\nrelease $ARGUMENTS\n",
        encoding="utf-8",
    )
    skill = SkillLoader(project_root=tmp_path).resolve("release")
    assert skill is not None
    assert skill.source == "project"
    assert skill.path == skills / "release.md"


# 功能：只解析 allowed_tools 键下的列表项，避免误授予其他 frontmatter 列表内容
# 设计：在无关 tags 列表后加入 tool 名称，断言该名称不会进入工具白名单。
def test_only_allowed_tools_list_is_parsed(tmp_path: Path) -> None:
    from sztu_code.core.skills.loader import _parse_skill_file

    path = tmp_path / "safe.md"
    path.write_text(
        "---\nname: safe\nallowed_tools:\n  - read_file\ntags:\n  - bash\n---\nSafe skill\n",
        encoding="utf-8",
    )
    assert _parse_skill_file(path).allowed_tools == ["read_file"]


# 功能：项目插件清单声明的 skills 目录应参与技能发现
# 设计：使用插件相对目录并通过公开 resolve 验证，不依赖插件内部实现细节。
def test_project_plugin_declares_skill_root(tmp_path: Path) -> None:
    plugin = tmp_path / ".sztu" / "plugins" / "release-tools"
    skill_dir = plugin / "workflows" / "release"
    skill_dir.mkdir(parents=True)
    (plugin / "plugin.json").write_text(
        '{"name":"release-tools","skills":["workflows"]}', encoding="utf-8"
    )
    (skill_dir / "SKILL.md").write_text(
        "---\nname: release\ndescription: Release workflow\n---\nShip $ARGUMENTS\n",
        encoding="utf-8",
    )
    skill = SkillLoader(project_root=tmp_path).resolve("release")
    assert skill is not None
    assert skill.source == "project-plugin:release-tools"


# 功能：技能目录应读取 openai.yaml 展示元数据并延迟加载正文
# 设计：分别通过目录列表与 resolve 断言目录对象无正文、解析对象包含完整正文。
def test_catalog_uses_openai_metadata_with_progressive_disclosure(tmp_path: Path) -> None:
    skill_dir = tmp_path / ".sztu" / "skills" / "reports"
    (skill_dir / "agents").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: reports\ndescription: Full description\n---\nCreate $ARGUMENTS\n",
        encoding="utf-8",
    )
    (skill_dir / "agents" / "openai.yaml").write_text(
        'interface:\n  display_name: "Reports"\n  short_description: "Build concise reports"\n'
        '  brand_color: "#2563EB"\npolicy:\n  allow_implicit_invocation: false\n',
        encoding="utf-8",
    )
    loader = SkillLoader(project_root=tmp_path, config_root=tmp_path / "profile")
    catalog_skill = next(skill for skill in loader.list_all_skills() if skill.name == "reports")
    assert catalog_skill.system_prompt_template == ""
    assert catalog_skill.display_name == "Reports"
    assert catalog_skill.short_description == "Build concise reports"
    assert catalog_skill.brand_color == "#2563EB"
    assert catalog_skill.allow_implicit_invocation is False
    resolved = loader.resolve("reports")
    assert resolved is not None
    assert "Create $ARGUMENTS" in resolved.system_prompt_template


# 功能：禁用技能后目录仍保留条目，但显式调用不再解析该技能
# 设计：通过公开 set_enabled 写入工作区状态，再新建加载器验证持久化结果。
def test_skill_enabled_state_is_persisted_without_deletion(tmp_path: Path) -> None:
    skill_dir = tmp_path / ".sztu" / "skills" / "release"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: release\ndescription: Release\n---\nShip $ARGUMENTS\n",
        encoding="utf-8",
    )
    config_root = tmp_path / "profile"
    loader = SkillLoader(project_root=tmp_path, config_root=config_root)
    skill = next(item for item in loader.list_all_skills() if item.name == "release")
    updated = loader.set_enabled(skill.id, False)
    assert updated.enabled is False
    reloaded = SkillLoader(project_root=tmp_path, config_root=config_root)
    assert reloaded.resolve("release") is None
    disabled = next(
        item for item in reloaded.list_all_skills(include_disabled=True) if item.name == "release"
    )
    assert disabled.enabled is False
    assert (skill_dir / "SKILL.md").is_file()


# 功能：本地技能目录应真实复制到个人技能根目录并立即参与解析
# 设计：使用隔离配置根执行安装，并验证目标文件、来源和重复安装保护。
def test_install_local_skill_directory(tmp_path: Path) -> None:
    source = tmp_path / "source" / "writer"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: writer\ndescription: Writer\n---\nWrite $ARGUMENTS\n",
        encoding="utf-8",
    )
    config_root = tmp_path / "profile"
    loader = SkillLoader(project_root=tmp_path / "workspace", config_root=config_root)
    installed = loader.install_skill(source, "personal")
    assert installed.source == "user"
    assert installed.path == config_root / "skills" / "writer" / "SKILL.md"
    assert loader.resolve("writer") is not None
    with pytest.raises(ValueError, match="already exists"):
        loader.install_skill(source, "personal")


# 功能：Codex 的 .codex-plugin/plugin.json 目录约定应可发现插件及其技能
# 设计：创建最小兼容插件，断言插件摘要和插件技能来源保持关联。
def test_codex_plugin_manifest_is_supported(tmp_path: Path) -> None:
    plugin = tmp_path / ".sztu" / "plugins" / "quality-suite"
    (plugin / ".codex-plugin").mkdir(parents=True)
    skill_dir = plugin / "skills" / "audit"
    skill_dir.mkdir(parents=True)
    (plugin / ".codex-plugin" / "plugin.json").write_text(
        '{"name":"quality-suite","description":"Quality workflows","version":"1.2.0"}',
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text(
        "---\nname: audit\ndescription: Audit changes\n---\nAudit $ARGUMENTS\n",
        encoding="utf-8",
    )
    loader = SkillLoader(project_root=tmp_path, config_root=tmp_path / "profile")
    found = loader.resolve("audit")
    assert found is not None
    assert found.source == "project-plugin:quality-suite"
    summary = next(plugin for plugin in loader.list_plugins() if plugin.name == "quality-suite")
    assert summary.source == "workspace"
    assert summary.skills == ("audit",)


# 功能：插件启停状态应同时控制其捆绑技能是否可被运行时解析
# 设计：在隔离个人插件目录切换状态，验证插件仍保留但技能解析随之变化。
def test_plugin_enabled_state_controls_bundled_skills(tmp_path: Path) -> None:
    config_root = tmp_path / "profile"
    plugin = config_root / "plugins" / "quality-suite"
    (plugin / ".codex-plugin").mkdir(parents=True)
    skill_dir = plugin / "skills" / "audit"
    skill_dir.mkdir(parents=True)
    (plugin / ".codex-plugin" / "plugin.json").write_text(
        '{"name":"quality-suite","skills":"./skills"}', encoding="utf-8"
    )
    (skill_dir / "SKILL.md").write_text(
        "---\nname: audit\ndescription: Audit\n---\nAudit $ARGUMENTS\n",
        encoding="utf-8",
    )
    loader = SkillLoader(project_root=tmp_path / "workspace", config_root=config_root)
    installed = next(item for item in loader.list_plugins() if item.name == "quality-suite")

    disabled = loader.set_plugin_enabled(installed.id, False)
    assert disabled.enabled is False
    assert loader.resolve("audit") is None
    assert loader.list_plugins()[0].skills == ("audit",)

    enabled = loader.set_plugin_enabled(installed.id, True)
    assert enabled.enabled is True
    assert loader.resolve("audit") is not None


# 功能：卸载插件仅删除受控插件目录并立即移出插件目录
# 设计：安装隔离插件后调用 uninstall_plugin，断言目标消失且配置根仍完整存在。
def test_uninstall_plugin_removes_only_managed_plugin_directory(tmp_path: Path) -> None:
    config_root = tmp_path / "profile"
    plugin = config_root / "plugins" / "removable"
    (plugin / ".codex-plugin").mkdir(parents=True)
    (plugin / ".codex-plugin" / "plugin.json").write_text(
        '{"name":"removable","version":"1.0.0"}', encoding="utf-8"
    )
    loader = SkillLoader(project_root=tmp_path / "workspace", config_root=config_root)
    installed = next(item for item in loader.list_plugins() if item.name == "removable")

    loader.uninstall_plugin(installed.id)

    assert not plugin.exists()
    assert (config_root / "plugins").is_dir()
    assert loader.list_plugins() == []
