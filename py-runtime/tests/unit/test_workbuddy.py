from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sztu_code.core.agents.loader import AgentProfileLoader
from sztu_code.core.prompts.workbuddy import (
    RESOURCE_ROOT, build_base, imported_skills, load_resource, manifest,
    mode_prompt, read_resource, render_text, resource_path,
)
from sztu_code.core.skills.loader import SkillLoader
from sztu_code.core.tools.builtin.prompt_resource import PromptResourceTool, SkillTool


def test_bundle_integrity_and_runtime_parity() -> None:
    inventory = manifest()
    assert len(inventory["files"]) == 485
    assert len(inventory["skills"]) == 48
    assert len(inventory["agents"]) == 19
    ts_root = Path(__file__).resolve().parents[3] / "packages/runtime-ts/prompts/workbuddy"
    for file in inventory["files"]:
        data = resource_path(file["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == file["sha256"], file["path"]
        assert (ts_root / file["path"]).read_bytes() == data
        if file["path"].endswith(".tpl") or file["path"].startswith("modes/") and file["path"].endswith(".md"):
            rendered = load_resource(file["path"])
            assert "{{" not in rendered and "{%" not in rendered, file["path"]
    for mode in ("ask", "craft", "plan", "expert"):
        assert mode_prompt(mode)
    assert render_text("{{productName}} {{values.join(',')}} {% if values.length === 2 %}yes{% endif %}", {"values": ["a", "b"]}) == "SztuCode a,b yes"
    assert "{{" not in build_base()


def test_resource_reader_pagination_and_boundaries() -> None:
    page = json.loads(read_resource("product/", 0, 3))
    assert page["total_files"] == 118
    assert len(page["files"]) == 3
    assert page["next_offset"] == 3
    excerpt = json.loads(read_resource("product/command-commit-prompt.tpl", 2, 4))
    assert len(excerpt["text"].splitlines()) == 4
    assert excerpt["next_offset"] == 6
    for value in ("../content/main/index.json", "../../", str(RESOURCE_ROOT / "manifest.json")):
        with pytest.raises(ValueError):
            read_resource(value)
    with pytest.raises(ValueError, match="pagination"):
        read_resource("", limit=1001)


def test_skills_plugins_commands_and_overrides(tmp_path: Path) -> None:
    loader = SkillLoader(tmp_path, tmp_path / "config")
    for item in imported_skills():
        skill = loader.resolve(item["name"])
        assert skill is not None
        assert skill.source == "workbuddy"
        assert "# SztuCode runtime contract" in skill.system_prompt_template
        assert "Skill directory:" in skill.system_prompt_template
    nested = next(s for s in loader.list_all_skills() if s.source == "workbuddy" and s.plugin)
    loader.set_plugin_enabled(f"builtin:{nested.plugin}", False)
    assert loader.resolve(nested.name) is None
    loader.set_plugin_enabled(f"builtin:{nested.plugin}", True)
    assert loader.resolve(nested.name) is not None
    local = tmp_path / ".sztu/skills" / nested.name
    local.mkdir(parents=True)
    (local / "SKILL.md").write_text(f"---\nname: {nested.name}\nworkbuddy: true\ndescription: Local\n---\nKeep {{{{ literal }}}} in examples.\n", encoding="utf-8")
    loader.invalidate()
    override = loader.resolve(nested.name)
    assert override is not None and override.source == "project"
    assert "{{ literal }}" in override.system_prompt_template


def test_all_imported_agents_resolve_templates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    for agent in manifest()["agents"]:
        profile = AgentProfileLoader().load(agent["name"])
        assert profile is not None
        assert profile.restrict_tools
        assert "# SztuCode runtime contract" in profile.system_prompt
        assert "{{" not in profile.system_prompt and "{%" not in profile.system_prompt
        if not agent["tools"]:
            assert profile.allowed_tools == []
        if agent["name"] in {"Plan", "Explore"}:
            assert profile.permission_mode == "plan"


async def test_registered_skill_and_resource_tools(tmp_path: Path) -> None:
    item = manifest()["skills"][0]
    result = await SkillTool(tmp_path).invoke({"name": item["name"]})
    assert not result.is_error
    assert json.loads(result.content)["instructions"]
    result = await PromptResourceTool().invoke({"path": "product/", "limit": 2})
    assert not result.is_error
    assert len(json.loads(result.content)["files"]) == 2
    result = await PromptResourceTool().invoke({"path": "../outside"})
    assert result.is_error
