import { createApp } from "vue";
import SkillCenter from "../../../src/components/Skills/SkillCenter.vue";
import { i18n } from "../../../src/i18n";
import { IpcClient } from "../../../src/lib/ipc";
import "../../../src/sztu.css";
import "../../../src/skill-center.css";
import "../../../src/appearance.css";

const skills: Array<Record<string, unknown>> = [
  { id: "skill-frontend-design", name: "frontend-design", display_name: "frontend-design", description: "设计并实现高质量、可交付的前端界面与交互", short_description: "前端界面设计与实现", source: "user", scope: "personal", path: "", enabled: true, allow_implicit_invocation: false },
  { id: "skill-find-skills", name: "find-skills", display_name: "find-skills", description: "发现适合当前任务的技能并提供安装路径", short_description: "技能发现与安装", source: "user", scope: "personal", path: "", enabled: true, allow_implicit_invocation: false },
  { id: "skill-review-agent", name: "review-agent", display_name: "review-agent", description: "以缺陷和回归风险为优先进行代码审查", short_description: "缺陷优先的代码审查", source: "user", scope: "personal", path: "", enabled: true, allow_implicit_invocation: false },
];

IpcClient.prototype.request = async function request(
  method: string,
  params: Record<string, unknown> = {},
): Promise<Record<string, unknown>> {
  if (method === "skill.list") return { skills };
  if (method === "skill.install") {
    const added = { id: "skill-release-notes", name: "release-notes", display_name: "release-notes", description: "从提交历史生成发布说明", short_description: "发布说明生成", source: "user", scope: "personal", path: String(params.source_path ?? ""), enabled: true, allow_implicit_invocation: false };
    skills.push(added);
    return { skill: added };
  }
  if (method === "skill.uninstall") {
    const index = skills.findIndex((skill) => skill.id === params.skill_id);
    if (index >= 0) skills.splice(index, 1);
    return { removed: true };
  }
  if (method === "plugin.list") return { plugins: [] };
  if (method === "plugin.catalog") return { marketplaces: [], plugins: [], supported: true };
  return {};
};

document.documentElement.dataset.theme = "light";
createApp(SkillCenter, { connected: true }).use(i18n).mount("#app");
