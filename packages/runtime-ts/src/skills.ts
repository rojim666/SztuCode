import { existsSync } from "node:fs";
import { cp, mkdir, readFile, readdir, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { PluginManager } from "./plugins.js";
import { fileURLToPath } from "node:url";

export type SkillScope = "system" | "personal" | "workspace";
export type Skill = { id: string; name: string; display_name: string; description: string; short_description: string; source: string; scope: SkillScope; path: string; enabled: boolean; system_prompt_template: string; allowed_tools: string[]; plugin: string | null; icon: string | null; brand_color: string | null; allow_implicit_invocation: boolean };

const frontmatter = /^---\s*\r?\n([\s\S]*?)\r?\n---\s*\r?\n/;
const scalar = (value: string) => value.trim().replace(/^(["'])(.*)\1$/, "$2");
async function parseSkill(filePath: string, source: string, scope: SkillScope): Promise<Skill> {
  const text = await readFile(filePath, "utf8"); const match = frontmatter.exec(text); const header = match?.[1] ?? ""; const body = match ? text.slice(match[0].length) : text; const values = new Map<string, string>(); const tools: string[] = []; let list = "";
  for (const raw of header.split(/\r?\n/)) { const line = raw.trim(); if (line.startsWith("- ") && list === "allowed_tools") tools.push(scalar(line.slice(2))); else if (line.includes(":")) { const [key, ...rest] = line.split(":"); list = key; values.set(key, scalar(rest.join(":"))); } }
  const name = values.get("name") || path.basename(path.dirname(filePath));
  return { id: `${source}:${name}`, name, display_name: name, description: values.get("description") ?? "", short_description: values.get("description") ?? "", source, scope, path: filePath, enabled: true, system_prompt_template: body.trim(), allowed_tools: tools, plugin: null, icon: null, brand_color: null, allow_implicit_invocation: true };
}

export class SkillLoader {
  constructor(private readonly projectRoot: string, private readonly configRoot = path.join(process.env.USERPROFILE ?? process.env.HOME ?? process.cwd(), ".sztu"), private readonly builtinRoot = resolveBuiltinRoot()) {}
  async list(): Promise<Skill[]> {
    const roots: Array<[string, string, SkillScope]> = [[this.builtinRoot, "builtin", "system"], [path.join(this.configRoot, "skills"), "user", "personal"], [path.join(this.projectRoot, ".sztu", "skills"), "project", "workspace"]];
    for (const plugin of await new PluginManager(this.projectRoot, this.configRoot).skillRoots()) roots.push([plugin.root, plugin.source, plugin.scope]);
    const result: Skill[] = [];
    for (const [root, source, scope] of roots) { try { for (const entry of await readdir(root, { withFileTypes: true })) { const candidate = entry.isDirectory() ? path.join(root, entry.name, "SKILL.md") : entry.name.toLowerCase().endsWith(".md") ? path.join(root, entry.name) : ""; if (!candidate) continue; try { result.push(await parseSkill(candidate, source, scope)); } catch { /* skip invalid skill */ } } } catch { /* optional root */ } }
    const enabled = await this.enabledOverrides(); return result.map((skill) => ({ ...skill, enabled: enabled[skill.id] ?? true }));
  }
  async setEnabled(id: string, enabled: boolean): Promise<Skill> { const all = await this.list(); const skill = all.find((item) => item.id === id); if (!skill) throw new Error(`Unknown skill: ${id}`); const values = await this.enabledOverrides(); values[id] = enabled; const file = path.join(this.configRoot, "skill-settings.json"); await mkdir(path.dirname(file), { recursive: true }); await writeFile(file, `${JSON.stringify({ skills: values }, null, 2)}\n`, "utf8"); return { ...skill, enabled }; }
  async install(sourcePath: string, scope: "personal" | "workspace"): Promise<Skill> { const source = path.resolve(sourcePath); const info = await stat(source); const skillFile = info.isDirectory() ? path.join(source, "SKILL.md") : source; const parsed = await parseSkill(skillFile, scope === "personal" ? "user" : "project", scope); const parent = scope === "personal" ? path.join(this.configRoot, "skills") : path.join(this.projectRoot, ".sztu", "skills"); const destination = path.join(parent, parsed.name); await mkdir(parent, { recursive: true }); if (info.isDirectory()) await cp(source, destination, { recursive: true, force: true }); else { await mkdir(destination, { recursive: true }); await cp(source, path.join(destination, "SKILL.md"), { force: true }); } return parseSkill(path.join(destination, "SKILL.md"), scope === "personal" ? "user" : "project", scope); }
  async get(name: string): Promise<Skill> { const skill = (await this.list()).find((item) => item.enabled && item.name === name); if (!skill) throw new Error(`Unknown or disabled skill: ${name}`); return skill; }
  private async enabledOverrides(): Promise<Record<string, boolean>> { try { return (JSON.parse(await readFile(path.join(this.configRoot, "skill-settings.json"), "utf8")) as { skills?: Record<string, boolean> }).skills ?? {}; } catch { return {}; } }
}

function resolveBuiltinRoot(): string {
  if (process.env.SZTU_BUILTIN_SKILLS) return path.resolve(process.env.SZTU_BUILTIN_SKILLS);
  const moduleDirectory = path.dirname(fileURLToPath(import.meta.url));
  // The package-owned assets are the product source of truth. The repository fallback
  // is retained only for old development layouts and must not be needed by releases.
  return existsSync(path.join(moduleDirectory, "skills"))
    ? path.join(moduleDirectory, "skills")
    : path.resolve(moduleDirectory, "../skills");
}
