from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from sztu_code.core.prompts.Sztubuddy import read_resource
from sztu_code.core.skills.loader import SkillLoader
from sztu_code.core.tools.base import BaseTool, ToolPermission, ToolResult


class ResourceParams(BaseModel):
    path: str = ""
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=200, ge=1, le=1000)


class PromptResourceTool(BaseTool):
    name = "prompt_resource"
    description = (
        "Read bundled product prompts, mode/style templates, agent definitions and skill "
        "reference documents. With no path, list the resource catalog. "
        "Paths are relative to the bundle; a category ending in / lists its resources."
    )
    required_permission = ToolPermission.READ_ONLY
    params_model = ResourceParams
    input_schema = ResourceParams.model_json_schema()

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = ResourceParams.model_validate(params)
        try:
            return ToolResult(content=read_resource(p.path, p.offset, p.limit))
        except (ValueError, OSError) as exc:
            return ToolResult(content=str(exc), is_error=True, error_type="runtime_error")


class SkillParams(BaseModel):
    name: str = Field(min_length=1)


class SkillTool(BaseTool):
    name = "skill"
    description = (
        "Load an enabled skill by name. Use the skill directory with prompt_resource "
        "to read its bundled references; follow the returned runtime contract."
    )
    required_permission = ToolPermission.READ_ONLY
    params_model = SkillParams
    input_schema = SkillParams.model_json_schema()

    def __init__(self, workspace_root: Path | None) -> None:
        self.loader = SkillLoader(project_root=workspace_root)

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = SkillParams.model_validate(params)
        skill = self.loader.resolve(p.name)
        if skill is None:
            return ToolResult(
                content=f"Unknown or disabled skill: {p.name}",
                is_error=True,
                error_type="schema_error",
            )
        return ToolResult(
            content=json.dumps(
                {
                    "name": skill.name,
                    "path": str(skill.path),
                    "instructions": skill.system_prompt_template,
                },
                ensure_ascii=False,
            )
        )
