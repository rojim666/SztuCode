export type SlashMenuItem = {
  id: string;
  name: string;
  description: string;
  group: "command" | "skill";
};

export const BUILT_IN_SLASH_COMMANDS: SlashMenuItem[] = [
  { id: "command-plan", name: "plan", description: "先分析并制定执行计划，不修改项目文件", group: "command" },
  { id: "command-edits", name: "edits", description: "允许编辑项目文件，其他敏感操作仍需确认", group: "command" },
  { id: "command-auto", name: "auto", description: "允许直接执行所有操作，提交前仍可调整权限", group: "command" },
];

export const BUILT_IN_SKILLS: Array<{ name: string; description: string }> = [
  { name: "frontend-design", description: "设计并实现高质量、可交付的前端界面与交互" },
  { name: "find-skills", description: "发现适合当前任务的技能并提供安装路径" },
  { name: "review-agent", description: "以缺陷和回归风险为优先进行代码审查" },
  { name: "documents", description: "创建、编辑并检查 Word 文档" },
  { name: "presentations", description: "创建或编辑演示文稿与幻灯片" },
  { name: "spreadsheets", description: "创建、编辑和分析电子表格文件" },
  { name: "pdf", description: "读取、创建、渲染并检查 PDF 文件" },
  { name: "imagegen", description: "生成或编辑图片、纹理与视觉素材" },
  { name: "visualize", description: "创建图表、可视化和交互式探索工具" },
  { name: "openai-docs", description: "查询 OpenAI 产品与 API 的官方资料" },
  { name: "skill-creator", description: "创建或更新可复用的 Agent 技能" },
  { name: "plugin-creator", description: "创建和维护 SztuCode 插件结构" },
];

export function slashMenuItems(
  query: string,
  skills: Array<{ name: string; description: string }>,
): SlashMenuItem[] {
  const normalized = query.trim().toLocaleLowerCase();
  const matches = (item: SlashMenuItem) => !normalized || `${item.name} ${item.description}`.toLocaleLowerCase().includes(normalized);
  const commands = BUILT_IN_SLASH_COMMANDS.filter(matches);
  const mergedSkills = new Map(BUILT_IN_SKILLS.map((skill) => [skill.name.toLocaleLowerCase(), skill]));
  for (const skill of skills) mergedSkills.set(skill.name.toLocaleLowerCase(), skill);
  const runtimeSkills = [...mergedSkills.values()]
    .map((skill) => ({ id: `skill-${skill.name}`, name: skill.name, description: skill.description, group: "skill" as const }))
    .filter(matches)
    .slice(0, 18);
  return [...commands, ...runtimeSkills];
}
