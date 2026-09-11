import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import nunjucks from "nunjucks";

const here = path.dirname(fileURLToPath(import.meta.url));
const runtimeRoot = fs.existsSync(path.join(here, "prompts")) ? here : path.resolve(here, "..");
export const workbuddyRoot = path.join(runtimeRoot, "prompts", "workbuddy");
export type InteractionMode = "ask" | "craft" | "plan" | "expert";
export interface ImportedSkill { name: string; description: string; path: string; allowedTools: string[]; plugin: string | null }
export interface ImportedAgent { name: string; description: string; template: string; tools: string[] }
interface Manifest { version: number; files: { path: string; source: string; sha256: string }[]; skills: ImportedSkill[]; commands: ImportedSkill[]; agents: ImportedAgent[]; toolMapping: Record<string, string>; limitations: string[] }
let manifest: Manifest | undefined;
const engine = new nunjucks.Environment([], { autoescape: false, throwOnUndefined: false });
const templates = new Map<string, nunjucks.Template>();
const aliases: Record<string, string> = { Read: "read_file", Write: "write_file", Edit: "edit_file", Glob: "glob_search", Grep: "grep_search", LS: "list_dir", Bash: "bash", PowerShell: "bash", Agent: "spawn_agent", Skill: "skill", AskUserQuestion: "ask_user_question", TaskCreate: "task_create", TaskGet: "task_get", TaskUpdate: "task_update", TaskList: "task_list", TaskOutput: "subagent_result", TaskStop: "subagent_cancel", BashOutput: "bash_output", KillShell: "bash_kill" };

export function workbuddyManifest(): Manifest {
  if (!manifest) {
    const value = JSON.parse(fs.readFileSync(path.join(workbuddyRoot, "manifest.json"), "utf8")) as Manifest;
    if (value.version !== 1 || !Array.isArray(value.files) || !Array.isArray(value.skills) || !Array.isArray(value.agents)) throw new Error("Invalid WorkBuddy resource manifest");
    manifest = value;
  }
  return manifest;
}

export function resourcePath(relative: string): string {
  if (path.isAbsolute(relative)) throw new Error("Resource path must be bundle-relative");
  const candidate = path.resolve(workbuddyRoot, relative);
  const rel = path.relative(workbuddyRoot, candidate);
  if (!rel || rel.startsWith("..") || path.isAbsolute(rel)) throw new Error("Resource path escapes the WorkBuddy bundle");
  const real = fs.realpathSync(candidate);
  const realRel = path.relative(fs.realpathSync(workbuddyRoot), real);
  if (realRel.startsWith("..") || path.isAbsolute(realRel)) throw new Error("Resource symlink escapes the WorkBuddy bundle");
  return real;
}

export function adaptWorkbuddyText(text: string): string {
  return text.replace(/({{[\s\S]*?}}|{%[\s\S]*?%})/g, expr => expr.replace(/===/g, "==").replace(/==\s*undefined/g, "is undefined").replace(/([A-Za-z_][\w.]*)\.length/g, "($1 | length)").replace(/([A-Za-z_][\w.]*)\.join\(([^)]*)\)/g, "($1 | join($2))"))
    .replace(/\b(CodeBuddy Code|CodeBuddy|WorkBuddy)\b/g, "SztuCode")
    .replaceAll("CODEBUDDY.md", "SZTUCODE.md")
    .replace(/\bagent_result\b/g, "subagent_result")
    .replace(/\b(Read|Write|Edit|Glob|Grep|LS|Bash|PowerShell|Agent|Skill|AskUserQuestion|TaskCreate|TaskGet|TaskUpdate|TaskList|TaskOutput|TaskStop|BashOutput|KillShell)\b/g, value => aliases[value])
    .replaceAll("All tasks described below are already completed.", "Record completed work and pending work separately. Never mark unfinished work completed.")
    .replaceAll("**DO NOT re-run, re-do or re-execute any of the tasks mentioned!**", "**Do not repeat completed work. Preserve pending tasks and the next action for continuation.**");
}

export function renderWorkbuddyText(text: string, variables: Record<string, unknown> = {}): string {
  const source = adaptWorkbuddyText(text);
  const defaults = { productName: "SztuCode", dataFolderName: ".sztu", modelName: "the configured model", modelId: "the configured model", ResponseLanguage: "Follow the user's preferred language; default to Chinese.", IsWindows: process.platform === "win32", platform: process.platform, defaultShell: process.platform === "win32" ? "Git Bash" : "bash", bashDefaultTimeoutMs: 30_000, bashMaxTimeoutMs: 120_000, cliDocsDir: "docs", productFeatures: { DisableMultimodalGeneration: true }, LocalSkillsMemoryEnabled: false, ExpertManagementEnabled: false, forkSubagentDisabled: true, teamEnabled: false, settings: { includeCoAuthoredBy: false }, skills: [], agents: [], userMemory: [], projectMemory: [], localMemory: [], additionalDirs: [], customCommands: [], truncatedCustomCommands: [], ArtifactDirectoryPath: ".sztu/artifacts", planFilePath: ".sztu/plan.md", ...variables };
  let template = templates.get(source);
  if (!template) { template = nunjucks.compile(source, engine); templates.set(source, template); }
  return template.render(defaults).trim();
}

export function loadWorkbuddyResource(relative: string, variables: Record<string, unknown> = {}): string {
  return renderWorkbuddyText(fs.readFileSync(resourcePath(relative), "utf8"), variables);
}

export function workbuddyContract(): string { return fs.readFileSync(resourcePath("runtime-contract.md"), "utf8").trim(); }

export function workbuddySkills(): ImportedSkill[] { return [...workbuddyManifest().skills, ...workbuddyManifest().commands]; }

export function workbuddyPlugins(): { name: string; path: string; skills: string[] }[] {
  const names = [...new Set(workbuddyManifest().skills.map(skill => skill.plugin).filter((name): name is string => Boolean(name)))];
  return names.map(name => ({ name, path: resourcePath(`skills/_builtin-plugins/${name}`), skills: workbuddyManifest().skills.filter(skill => skill.plugin === name).map(skill => skill.name) }));
}

export function buildWorkbuddyBase(): string {
  // Keep the initial injection small. Product workflows and skills are loaded on demand.
  return [loadWorkbuddyResource("main/sztucode-core.tpl"), workbuddyContract()].filter(Boolean).join("\n\n");
}
export function workbuddyMode(mode: InteractionMode): string {
  if (!["ask", "craft", "plan", "expert"].includes(mode)) throw new Error(`Unknown interaction mode: ${mode}`);
  const files = workbuddyManifest().files.filter(file => file.path.startsWith(`modes/${mode}/fragments/`) && !file.path.endsWith("interaction.md"));
  return [...files.map(file => loadWorkbuddyResource(file.path)), ...(mode === "plan" ? ["Plan mode is active. Only inspect and plan. Do not modify project files or execute commands until the runtime exits plan mode."] : []), workbuddyContract()].filter(Boolean).join("\n\n");
}

export function importedAgent(name: string): ImportedAgent | undefined {
  const agent = workbuddyManifest().agents.find(agent => agent.name === name);
  if (!agent) return undefined;
  const tools = agent.tools.map(tool => tool === "agent_result" ? "subagent_result" : tool);
  if (tools.includes("read_file") || tools.includes("skill")) tools.push("prompt_resource");
  return { ...agent, tools: [...new Set(tools)] };
}
export function importedToolDescription(name: string): string | undefined {
  const upstream = workbuddyManifest().toolMapping[name === "subagent_result" ? "agent_result" : name];
  if (!upstream) return undefined;
  return loadWorkbuddyResource(`product/tool-${upstream}-description.tpl`) + "\n\n" + workbuddyContract();
}

export function readPromptResource(relative = "", offset = 0, limit = 200): string {
  if (!Number.isInteger(offset) || offset < 0 || !Number.isInteger(limit) || limit < 1 || limit > 1000) throw new Error("Invalid resource pagination");
  if (path.isAbsolute(relative) || relative.split(/[\\/]/).includes("..")) throw new Error("Resource path must be bundle-relative without traversal");
  if (!relative || relative.endsWith("/")) {
    const files = workbuddyManifest().files.filter(file => file.path.startsWith(relative)).map(file => file.path);
    return JSON.stringify({ path: relative, total_files: files.length, files: files.slice(offset, offset + limit), next_offset: offset + limit < files.length ? offset + limit : null, limitations: workbuddyManifest().limitations });
  }
  const content = relative.startsWith("skills/") ? adaptWorkbuddyText(fs.readFileSync(resourcePath(relative), "utf8")) : loadWorkbuddyResource(relative);
  const lines = content.split(/\r?\n/);
  return JSON.stringify({ path: relative, offset, total_lines: lines.length, text: lines.slice(offset, offset + limit).join("\n"), next_offset: offset + limit < lines.length ? offset + limit : null });
}
