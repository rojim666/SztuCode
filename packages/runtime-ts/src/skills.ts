import fsSync from "node:fs";
import fsPromises from "node:fs/promises";
import path from "node:path";
import { PluginManager } from "./plugins.js";
import { fileURLToPath } from "node:url";

export type SkillScope = "system" | "personal" | "workspace";
export type Skill = { id: string; name: string; display_name: string; description: string; short_description: string; source: string; scope: SkillScope; path: string; enabled: boolean; system_prompt_template: string; allowed_tools: string[]; plugin: string | null; icon: string | null; brand_color: string | null; allow_implicit_invocation: boolean };

const frontmatter = /^---\s*\r?\n([\s\S]*?)\r?\n---\s*\r?\n/;
const scalar = (value: string) => value.trim().replace(/^(["'])(.*)\1$/, "$2");
const FRONTMATTER_SCAN_LIMIT = 65536; // frontmatter 只可能出现在文件开头，超过该长度按解析失败处理
type ParsedSkillFile = { name: string; description: string; tools: string[]; body: string };
// 模块级缓存：key 为 SKILL.md 绝对路径，值为完整解析结果，供 get()/list() 复用，避免重复读全文
const skillFileCache = new Map<string, ParsedSkillFile>();
function parseHeader(header: string): { values: Map<string, string>; tools: string[] } { const values = new Map<string, string>(); const tools: string[] = []; let list = ""; for (const raw of header.split(/\r?\n/)) { const line = raw.trim(); if (line.startsWith("- ") && list === "allowed_tools") tools.push(scalar(line.slice(2))); else if (line.includes(":")) { const [key, ...rest] = line.split(":"); list = key; values.set(key, scalar(rest.join(":"))); } } return { values, tools }; }
function parseSkillText(text: string): ParsedSkillFile { const match = frontmatter.exec(text); const header = match?.[1] ?? ""; const body = match ? text.slice(match[0].length) : text; const { values, tools } = parseHeader(header); return { name: values.get("name") ?? "", description: values.get("description") ?? "", tools, body: body.trim() }; }
// 只分块读取文件开头的 frontmatter，不加载正文，避免每次 list() 都付出全文 IO 代价
async function readFrontmatterHeader(filePath: string): Promise<string | null> { try { const handle = await fsPromises.open(filePath, "r"); try { let text = ""; const buffer = Buffer.alloc(8192); for (;;) { const { bytesRead } = await handle.read(buffer, 0, buffer.length, null); if (!bytesRead) break; text += buffer.toString("utf8", 0, bytesRead); const match = frontmatter.exec(text); if (match) return match[1]; if (text.length > FRONTMATTER_SCAN_LIMIT) break; } return null; } finally { await handle.close(); } } catch { return null; } }
// 全文解析仅在 get()/install() 按需触发，结果写入模块级缓存
async function parseSkillFile(filePath: string): Promise<ParsedSkillFile> { const cached = skillFileCache.get(filePath); if (cached) return cached; const parsed = parseSkillText(await fsPromises.readFile(filePath, "utf8")); skillFileCache.set(filePath, parsed); return parsed; }
// 惰性正文：调用方真正访问 system_prompt_template 时才读取（优先走缓存），保证 list() 本身不读正文
function lazyBody(filePath: string): string { const cached = skillFileCache.get(filePath); if (cached) return cached.body; try { const parsed = parseSkillText(fsSync.readFileSync(filePath, "utf8")); skillFileCache.set(filePath, parsed); return parsed.body; } catch { return ""; } }
function buildSkill(filePath: string, source: string, scope: SkillScope, parsed: ParsedSkillFile, enabled: boolean): Skill { const name = parsed.name || path.basename(path.dirname(filePath)); return { id: `${source}:${name}`, name, display_name: name, description: parsed.description, short_description: parsed.description, source, scope, path: filePath, enabled, system_prompt_template: parsed.body, allowed_tools: parsed.tools, plugin: null, icon: null, brand_color: null, allow_implicit_invocation: true }; }

export class SkillLoader {
  constructor(private readonly projectRoot: string, private readonly configRoot = path.join(process.env.USERPROFILE ?? process.env.HOME ?? process.cwd(), ".sztu"), private readonly builtinRoot = resolveBuiltinRoot()) {}
  async list(): Promise<Skill[]> {
    const roots: Array<[string, string, SkillScope]> = [[this.builtinRoot, "builtin", "system"], [path.join(this.configRoot, "skills"), "user", "personal"], [path.join(this.projectRoot, ".sztu", "skills"), "project", "workspace"]];
    for (const plugin of await new PluginManager(this.projectRoot, this.configRoot).skillRoots()) roots.push([plugin.root, plugin.source, plugin.scope]);
    const enabled = await this.enabledOverrides(); const result: Skill[] = [];
    // 轻量路径：只读 frontmatter 拿 name/description/allowed_tools；正文延迟到属性被访问或 get() 时加载
    for (const [root, source, scope] of roots) { try { for (const entry of await fsPromises.readdir(root, { withFileTypes: true })) { const candidate = entry.isDirectory() ? path.join(root, entry.name, "SKILL.md") : entry.name.toLowerCase().endsWith(".md") ? path.join(root, entry.name) : ""; if (!candidate) continue; const header = await readFrontmatterHeader(candidate); if (header === null) continue; /* 无 frontmatter 或解析失败：跳过且不抛错 */ const { values, tools } = parseHeader(header); const name = values.get("name") || path.basename(path.dirname(candidate)); const id = `${source}:${name}`; result.push({ id, name, display_name: name, description: values.get("description") ?? "", short_description: values.get("description") ?? "", source, scope, path: candidate, enabled: enabled[id] ?? true, get system_prompt_template(): string { return lazyBody(candidate); }, allowed_tools: tools, plugin: null, icon: null, brand_color: null, allow_implicit_invocation: true }); } } catch { /* optional root */ } }
    return result;
  }
  async setEnabled(id: string, enabled: boolean): Promise<Skill> { const all = await this.list(); const skill = all.find((item) => item.id === id); if (!skill) throw new Error(`Unknown skill: ${id}`); const values = await this.enabledOverrides(); values[id] = enabled; const file = path.join(this.configRoot, "skill-settings.json"); await fsPromises.mkdir(path.dirname(file), { recursive: true }); await fsPromises.writeFile(file, `${JSON.stringify({ skills: values }, null, 2)}\n`, "utf8"); return { id: skill.id, name: skill.name, display_name: skill.display_name, description: skill.description, short_description: skill.short_description, source: skill.source, scope: skill.scope, path: skill.path, enabled, get system_prompt_template(): string { return lazyBody(skill.path); }, allowed_tools: skill.allowed_tools, plugin: skill.plugin, icon: skill.icon, brand_color: skill.brand_color, allow_implicit_invocation: skill.allow_implicit_invocation }; }
  async install(sourcePath: string, scope: "personal" | "workspace"): Promise<Skill> { const source = path.resolve(sourcePath); const info = await fsPromises.stat(source); const skillFile = info.isDirectory() ? path.join(source, "SKILL.md") : source; const parsed = await parseSkillFile(skillFile); const parent = scope === "personal" ? path.join(this.configRoot, "skills") : path.join(this.projectRoot, ".sztu", "skills"); const destination = path.join(parent, parsed.name || path.basename(path.dirname(skillFile))); await fsPromises.mkdir(parent, { recursive: true }); if (info.isDirectory()) await fsPromises.cp(source, destination, { recursive: true, force: true }); else { await fsPromises.mkdir(destination, { recursive: true }); await fsPromises.cp(source, path.join(destination, "SKILL.md"), { force: true }); } const installedFile = path.join(destination, "SKILL.md"); skillFileCache.delete(installedFile); /* 覆盖安装后让旧缓存失效 */ return buildSkill(installedFile, scope === "personal" ? "user" : "project", scope, await parseSkillFile(installedFile), true); }
  async get(name: string): Promise<Skill> { const skill = (await this.list()).find((item) => item.enabled && item.name === name); if (!skill) throw new Error(`Unknown or disabled skill: ${name}`); const parsed = await parseSkillFile(skill.path); return { ...skill, system_prompt_template: parsed.body, allowed_tools: parsed.tools }; }
  invalidateCache(): void { skillFileCache.clear(); }
  private async enabledOverrides(): Promise<Record<string, boolean>> { try { return (JSON.parse(await fsPromises.readFile(path.join(this.configRoot, "skill-settings.json"), "utf8")) as { skills?: Record<string, boolean> }).skills ?? {}; } catch { return {}; } }
}

function resolveBuiltinRoot(): string {
  if (process.env.SZTU_BUILTIN_SKILLS) return path.resolve(process.env.SZTU_BUILTIN_SKILLS);
  const moduleDirectory = path.dirname(fileURLToPath(import.meta.url));
  // The package-owned assets are the product source of truth. The repository fallback
  // is retained only for old development layouts and must not be needed by releases.
  return fsSync.existsSync(path.join(moduleDirectory, "skills"))
    ? path.join(moduleDirectory, "skills")
    : path.resolve(moduleDirectory, "../skills");
}
