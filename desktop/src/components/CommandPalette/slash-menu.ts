import { t as globalTranslate } from "../../i18n";

export type SlashMenuItem = {
  id: string;
  name: string;
  description: string;
  group: "command" | "skill";
};

/** 翻译函数：组件内传入 useI18n 的 t 以保持响应式；缺省回退到全局 t */
export type TranslateFn = (key: string) => string;

/** 内建斜杠命令：name 为数据标识（发送给后端），描述文案见 palette.command.* */
export const BUILT_IN_SLASH_COMMANDS: Array<{ id: string; name: string }> = [
  { id: "command-plan", name: "plan" },
  { id: "command-edits", name: "edits" },
  { id: "command-auto", name: "auto" },
];

/** 内建技能目录：name 为数据标识，描述文案见 palette.skill.* */
export const BUILT_IN_SKILLS: Array<{ name: string }> = [
  { name: "frontend-design" },
  { name: "find-skills" },
  { name: "review-agent" },
  { name: "documents" },
  { name: "presentations" },
  { name: "spreadsheets" },
  { name: "pdf" },
  { name: "imagegen" },
  { name: "visualize" },
  { name: "openai-docs" },
  { name: "skill-creator" },
  { name: "plugin-creator" },
];

/** 内建斜杠命令项（描述按当前语言解析） */
export function builtInSlashCommandItems(t: TranslateFn = globalTranslate): SlashMenuItem[] {
  return BUILT_IN_SLASH_COMMANDS.map((command) => ({
    id: command.id,
    name: command.name,
    description: t(`palette.command.${command.id}`),
    group: "command" as const,
  }));
}

/** 内建技能目录（描述按当前语言解析） */
export function builtInSkillItems(t: TranslateFn = globalTranslate): Array<{ name: string; description: string }> {
  return BUILT_IN_SKILLS.map((skill) => ({ name: skill.name, description: t(`palette.skill.${skill.name}`) }));
}

export function slashMenuItems(
  query: string,
  skills: Array<{ name: string; description: string }>,
  t: TranslateFn = globalTranslate,
): SlashMenuItem[] {
  const normalized = query.trim().toLocaleLowerCase();
  const matches = (item: SlashMenuItem) => !normalized || `${item.name} ${item.description}`.toLocaleLowerCase().includes(normalized);
  const commands = builtInSlashCommandItems(t).filter(matches);
  const mergedSkills = new Map(builtInSkillItems(t).map((skill) => [skill.name.toLocaleLowerCase(), skill]));
  for (const skill of skills) mergedSkills.set(skill.name.toLocaleLowerCase(), skill);
  const runtimeSkills = [...mergedSkills.values()]
    .map((skill) => ({ id: `skill-${skill.name}`, name: skill.name, description: skill.description, group: "skill" as const }))
    .filter(matches)
    .slice(0, 18);
  return [...commands, ...runtimeSkills];
}
