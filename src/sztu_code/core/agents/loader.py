from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentProfile:
    name: str
    description: str
    system_prompt: str
    # 可选的原子提示词 ID；内建角色通过它引用 prompts/content 下的 Markdown
    prompt_id: str = ""
    allowed_tools: list[str] = field(default_factory=list)
    model: str = ""
    # 子 agent 权限模式：normal/plan/accept_edits/auto
    permission_mode: str = "normal"
    # 可选：spawn 时应用的 Agent Skill 名称
    skill: str = ""
    # 角色步数上限；0=继承全局 agent.max_steps
    max_steps: int = 0


# 按两级优先级（项目本地 > 用户全局 > 内建）查找并解析角色配置
class AgentProfileLoader:
    _BUILTIN_DIR = Path(__file__).parent / "builtin"

    # 查找指定角色配置；未找到返回 None
    def load(self, name: str) -> AgentProfile | None:
        for path in self._search_paths(name):
            if path.exists():
                try:
                    return self._parse(path, name)
                except Exception:
                    return None
        return None

    # 返回 [项目本地, 用户全局, 内建] 路径；load() 返回第一个存在的，项目本地优先级最高
    def _search_paths(self, name: str) -> list[Path]:
        builtin = self._BUILTIN_DIR / f"{name}.toml"
        global_ = Path("~/.sztu/agents").expanduser() / f"{name}.toml"
        local = Path(".sztu/agents") / f"{name}.toml"
        return [local, global_, builtin]

    # 解析 TOML 角色配置文件
    def _parse(self, path: Path, name: str) -> AgentProfile:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        agent = data.get("agent", {})
        prompt_id = agent.get("prompt_id", "").strip()
        system_prompt = agent.get("system_prompt", "").strip()
        if prompt_id:
            from sztu_code.core.prompts.subagent_prompts import load_subagent_prompt

            system_prompt = load_subagent_prompt(prompt_id)
        return AgentProfile(
            name=name,
            description=agent.get("description", ""),
            system_prompt=system_prompt,
            prompt_id=prompt_id,
            allowed_tools=agent.get("allowed_tools", []),
            model=agent.get("model", ""),
            permission_mode=agent.get("permission_mode", "normal"),
            skill=agent.get("skill", ""),
            max_steps=agent.get("max_steps", 0),
        )
