from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

from sztu_code.core.skills.loader import SkillLoader


def test_six_bundled_plugins_have_real_skills_and_provenance(tmp_path: Path) -> None:
    loader = SkillLoader(project_root=tmp_path, config_root=tmp_path / "config")
    plugins = {p.name: p for p in loader.list_plugins() if p.source == "builtin"}
    expected = {
        "pdf-monster": {"pdf-monster"}, "word": {"doc"},
        "excel": {"spreadsheet"}, "jingmei-ppt": {"jingmei-ppt", "slides"},
        "frontend-design": {"frontend-design", "uicraft"},
        "github": {"github", "gh-address-comments", "gh-fix-ci"},
    }
    assert set(plugins) == set(expected)
    for name, names in expected.items():
        plugin = plugins[name]
        assert set(plugin.skills) == names
        assert plugin.publisher and plugin.homepage and plugin.license
        assert (plugin.path / "SOURCE.md").is_file()
        for skill_name in names:
            skill = loader.resolve(skill_name)
            assert skill and skill.plugin == name and skill.source == f"builtin-plugin:{name}"
        loader.set_plugin_enabled(plugin.id, False)
        for skill_name in names:
            assert loader.resolve(skill_name) is None
        visible = {s.name: s for s in loader.list_all_skills(include_disabled=True)}
        assert all(not visible[n].enabled for n in names)
        loader.set_plugin_enabled(plugin.id, True)


def test_python_and_desktop_plugin_manifests_match() -> None:
    root = Path(__file__).resolve().parents[3]
    for path in SkillLoader._BUILTIN_PLUGINS_DIR.glob("*/plugin.json"):
        desktop = root / "packages/runtime-ts/plugins" / path.parent.name / "plugin.json"
        assert json.loads(path.read_text(encoding="utf-8")) == json.loads(desktop.read_text(encoding="utf-8"))


def test_pdf_artifacts_do_not_pollute_working_directory(tmp_path: Path, monkeypatch) -> None:
    path = SkillLoader._BUILTIN_PLUGINS_DIR / "pdf-monster/skills/pdf-monster/scripts/analyze_pdf.py"
    spec = importlib.util.spec_from_file_location("pdf_monster_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.chdir(tmp_path)
    store = module.ArtifactStore(None)
    artifact = store.path("pages", "page-1.png")
    try:
        assert not list(tmp_path.iterdir())
        assert not artifact.is_relative_to(tmp_path)
        assert store.policy == "temporary"
        assert ("Remove-Item -LiteralPath" if os.name == "nt" else "rm -rf --") in store.cleanup_command()
    finally:
        import shutil
        shutil.rmtree(store.root)
    persistent = module.ArtifactStore(tmp_path / "requested-output")
    persistent.ensure()
    assert persistent.cleanup_command() is None
