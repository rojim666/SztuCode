from __future__ import annotations

import json
import platform
import re
from functools import cache
from pathlib import Path
from typing import Any, cast

from jinja2 import ChainableUndefined
from jinja2.sandbox import SandboxedEnvironment

RESOURCE_ROOT = Path(__file__).parent / "workbuddy"
_ENGINE = SandboxedEnvironment(autoescape=False, undefined=ChainableUndefined)
_ALIASES = dict(
    zip(
        ("Read Write Edit Glob Grep LS Bash PowerShell Agent Skill AskUserQuestion "
         "TaskCreate TaskGet TaskUpdate TaskList TaskOutput TaskStop BashOutput KillShell").split(),
        ("read_file write_file edit_file glob_search grep_search list_dir bash bash spawn_agent "
         "skill ask_user_question task_create task_get task_update task_list agent_result "
         "task_stop bash_output bash_kill").split(),
        strict=True,
    )
)


@cache
def manifest() -> dict[str, Any]:
    value = json.loads((RESOURCE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("version") != 1 or not all(
        isinstance(value.get(k), list) for k in ("files", "skills", "agents", "commands")
    ):
        raise ValueError("Invalid WorkBuddy resource manifest")
    return cast(dict[str, Any], value)


def resource_path(relative: str) -> Path:
    if Path(relative).is_absolute():
        raise ValueError("Resource path must be bundle-relative")
    candidate = (RESOURCE_ROOT / relative).resolve()
    if candidate == RESOURCE_ROOT.resolve() or RESOURCE_ROOT.resolve() not in candidate.parents:
        raise ValueError("Resource path escapes the WorkBuddy bundle")
    return candidate


def adapt_text(text: str) -> str:
    def normalize(match: re.Match[str]) -> str:
        expr = re.sub(r"==\s*undefined", "is undefined", match[0].replace("===", "=="))
        expr = re.sub(r"([A-Za-z_][\w.]*)\.length", r"(\1 | length)", expr)
        return re.sub(r"([A-Za-z_][\w.]*)\.join\(([^)]*)\)", r"(\1 | join(\2))", expr)

    text = re.sub(r"({{[\s\S]*?}}|{%[\s\S]*?%})", normalize, text)
    text = re.sub(r"\b(CodeBuddy Code|CodeBuddy|WorkBuddy)\b", "SztuCode", text)
    text = text.replace("CODEBUDDY.md", "SZTUCODE.md")
    text = re.sub(r"\b(" + "|".join(_ALIASES) + r")\b", lambda m: _ALIASES[m[0]], text)
    return text.replace(
        "All tasks described below are already completed.",
        "Record completed work and pending work separately. Never mark unfinished work completed.",
    ).replace(
        "**DO NOT re-run, re-do or re-execute any of the tasks mentioned!**",
        "**Do not repeat completed work. Preserve pending tasks "
        "and the next action for continuation.**",
    )


@cache
def _template(text: str) -> Any:
    return _ENGINE.from_string(adapt_text(text))


def render_text(text: str, variables: dict[str, Any] | None = None) -> str:
    windows = platform.system() == "Windows"
    values: dict[str, Any] = {
        "productName": "SztuCode",
        "dataFolderName": ".sztu",
        "modelName": "the configured model",
        "modelId": "the configured model",
        "ResponseLanguage": "Follow the user's preferred language; default to Chinese.",
        "IsWindows": windows,
        "platform": "win32" if windows else "linux",
        "defaultShell": "Git Bash" if windows else "bash",
        "bashDefaultTimeoutMs": 30000,
        "bashMaxTimeoutMs": 120000,
        "cliDocsDir": "docs",
        "productFeatures": {"DisableMultimodalGeneration": True},
        "LocalSkillsMemoryEnabled": False,
        "ExpertManagementEnabled": False,
        "forkSubagentDisabled": True,
        "teamEnabled": False,
        "settings": {"includeCoAuthoredBy": False},
        "skills": [],
        "agents": [],
        "userMemory": [],
        "projectMemory": [],
        "localMemory": [],
        "additionalDirs": [],
        "customCommands": [],
        "truncatedCustomCommands": [],
        "ArtifactDirectoryPath": ".sztu/artifacts",
        "planFilePath": ".sztu/plan.md",
    }
    values.update(variables or {})
    return str(_template(text).render(values)).strip()


def load_resource(relative: str, variables: dict[str, Any] | None = None) -> str:
    return render_text(resource_path(relative).read_text(encoding="utf-8"), variables)


def runtime_contract() -> str:
    return resource_path("runtime-contract.md").read_text(encoding="utf-8").strip()


def build_base() -> str:
    # Keep the initial injection small. Product workflows and skills are loaded on demand.
    return "\n\n".join([load_resource("main/sztucode-core.tpl"), runtime_contract()])


def mode_prompt(mode: str) -> str:
    if mode not in {"ask", "craft", "plan", "expert"}:
        raise ValueError(f"Unknown interaction mode: {mode}")
    parts = [
        load_resource(f["path"])
        for f in manifest()["files"]
        if f["path"].startswith(f"modes/{mode}/fragments/")
        and not f["path"].endswith("interaction.md")
    ]
    if mode == "plan":
        parts.append(
            "Plan mode is active. Only inspect and plan. Do not modify project files "
            "or execute commands until the runtime exits plan mode."
        )
    return "\n\n".join([*filter(None, parts), runtime_contract()])


def imported_agent(name: str) -> dict[str, Any] | None:
    agent = next((agent for agent in manifest()["agents"] if agent["name"] == name), None)
    if agent is None:
        return None
    tools = list(agent["tools"])
    if "read_file" in tools or "skill" in tools:
        tools.append("prompt_resource")
    return {**agent, "tools": list(dict.fromkeys(tools))}


def imported_skills() -> list[dict[str, Any]]:
    return [*manifest()["skills"], *manifest()["commands"]]


def imported_plugins() -> list[dict[str, Any]]:
    names = sorted({s["plugin"] for s in manifest()["skills"] if s["plugin"]})
    return [
        {
            "name": name,
            "path": resource_path(f"skills/_builtin-plugins/{name}"),
            "skills": [s["name"] for s in manifest()["skills"] if s["plugin"] == name],
        }
        for name in names
    ]


def read_resource(relative: str = "", offset: int = 0, limit: int = 200) -> str:
    if offset < 0 or not 1 <= limit <= 1000:
        raise ValueError("Invalid resource pagination")
    if Path(relative).is_absolute() or ".." in re.split(r"[\\/]", relative):
        raise ValueError("Resource path must be bundle-relative without traversal")
    if not relative or relative.endswith("/"):
        files = [f["path"] for f in manifest()["files"] if f["path"].startswith(relative)]
        return json.dumps(
            {
                "path": relative,
                "total_files": len(files),
                "files": files[offset : offset + limit],
                "next_offset": offset + limit if offset + limit < len(files) else None,
                "limitations": manifest()["limitations"],
            },
            ensure_ascii=False,
        )
    content = (
        adapt_text(resource_path(relative).read_text(encoding="utf-8"))
        if relative.startswith("skills/")
        else load_resource(relative)
    )
    lines = content.splitlines()
    return json.dumps(
        {
            "path": relative,
            "offset": offset,
            "total_lines": len(lines),
            "text": "\n".join(lines[offset : offset + limit]),
            "next_offset": offset + limit if offset + limit < len(lines) else None,
        },
        ensure_ascii=False,
    )
