import fsSync from "node:fs";
import fsPromises from "node:fs/promises";
import path from "node:path";
import { PluginManager } from "./plugins.js";
import { fileURLToPath } from "node:url";
import { adaptSztubuddyText, loadSztubuddyResource, renderSztubuddyText, resourcePath, SztubuddyContract, SztubuddySkills, SztubuddyRoot } from "./Sztubuddy-resources.js";

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
function renderBuiltin(filePath: string, parsed: ParsedSkillFile): ParsedSkillFile {
  if (path.dirname(filePath) === resolveBuiltinRoot() && ["init.md", "review.md", "summarize.md", "orchestrate.md"].includes(path.basename(filePath))) return { ...parsed, body: renderSztubuddyText(parsed.body) };
  return parsed;
}
// 只分块读取文件开头的 frontmatter，不加载正文，避免每次 list() 都付出全文 IO 代价
async function readFrontmatterHeader(filePath: string): Promise<string | null> { try { const handle = await fsPromises.open(filePath, "r"); try { let text = ""; const buffer = Buffer.alloc(8192); for (;;) { const { bytesRead } = await handle.read(buffer, 0, buffer.length, null); if (!bytesRead) break; text += buffer.toString("utf8", 0, bytesRead); const match = frontmatter.exec(text); if (match) return match[1]; if (text.length > FRONTMATTER_SCAN_LIMIT) break; } return null; } finally { await handle.close(); } } catch { return null; } }
// 全文解析仅在 get()/install() 按需触发，结果写入模块级缓存
async function parseSkillFile(filePath: string): Promise<ParsedSkillFile> { const cached = skillFileCache.get(filePath); if (cached) return cached; const parsed = renderBuiltin(filePath, parseSkillText(await fsPromises.readFile(filePath, "utf8"))); skillFileCache.set(filePath, parsed); return parsed; }
// 惰性正文：调用方真正访问 system_prompt_template 时才读取（优先走缓存），保证 list() 本身不读正文
function lazyBody(filePath: string): string { const cached = skillFileCache.get(filePath); if (cached) return cached.body; try { const parsed = renderBuiltin(filePath, parseSkillText(fsSync.readFileSync(filePath, "utf8"))); skillFileCache.set(filePath, parsed); return parsed.body; } catch { return ""; } }
function buildSkill(filePath: string, source: string, scope: SkillScope, parsed: ParsedSkillFile, enabled: boolean): Skill { const name = parsed.name || path.basename(path.dirname(filePath)); return { id: `${source}:${name}`, name, display_name: name, description: parsed.description, short_description: parsed.description, source, scope, path: filePath, enabled, system_prompt_template: parsed.body, allowed_tools: parsed.tools, plugin: null, icon: null, brand_color: null, allow_implicit_invocation: true }; }

export class SkillLoader {
  constructor(private readonly projectRoot: string, private readonly configRoot = path.join(process.env.USERPROFILE ?? process.env.HOME ?? process.cwd(), ".sztu"), private readonly builtinRoot = resolveBuiltinRoot()) {}
  async list(): Promise<Skill[]> {
    // 优先级与 Python 端一致：builtin < builtin-plugin < user < user-plugin < project < project-plugin
    const pluginRoots = await new PluginManager(this.projectRoot, this.configRoot).skillRoots(true);
    const plugins = await new PluginManager(this.projectRoot, this.configRoot).list();
    const roots: Array<[string, string, SkillScope]> = [
      [this.builtinRoot, "builtin", "system"],
      ...pluginRoots.filter((item) => item.scope === "system").map((item) => [item.root, item.source, item.scope] as [string, string, SkillScope]),
      [path.join(SztubuddyRoot, "skills"), "Sztubuddy", "system"],
      [path.join(this.configRoot, "skills"), "user", "personal"],
      ...pluginRoots.filter((item) => item.scope === "personal").map((item) => [item.root, item.source, item.scope] as [string, string, SkillScope]),
      [path.join(this.projectRoot, ".sztu", "skills"), "project", "workspace"],
      ...pluginRoots.filter((item) => item.scope === "workspace").map((item) => [item.root, item.source, item.scope] as [string, string, SkillScope]),
    ];
    const enabled = await this.enabledOverrides();
    // 轻量路径：只读 frontmatter 拿 name/description/allowed_tools；正文延迟到属性被访问或 get() 时加载
    // 同名技能以高优先级来源为准（后写覆盖前写），与 Python 端 list_all_skills 的覆盖语义对齐。
    const seen = new Map<string, Skill>();
    for (const [root, source, scope] of roots) {
      if (source === "Sztubuddy") {
        for (const item of SztubuddySkills()) {
          const candidate = resourcePath(item.path);
          const id = `Sztubuddy:${item.name}`;
          seen.set(item.name, { id, name: item.name, display_name: item.name, description: item.description, short_description: item.description, source, scope, path: candidate, enabled: (enabled[id] ?? true) && (plugins.find(plugin => plugin.id === `builtin:${item.plugin}`)?.enabled ?? true), get system_prompt_template() { return importedSkillBody(candidate, item.path); }, allowed_tools: item.allowedTools, plugin: item.plugin, icon: null, brand_color: null, allow_implicit_invocation: !item.path.startsWith("product/") });
        }
        continue;
      }
      try {
        for (const entry of await fsPromises.readdir(root, { withFileTypes: true })) {
          const candidate = entry.isDirectory() ? path.join(root, entry.name, "SKILL.md") : entry.name.toLowerCase().endsWith(".md") ? path.join(root, entry.name) : "";
          if (!candidate) continue;
          const header = await readFrontmatterHeader(candidate);
          if (header === null) continue;
          const { values, tools } = parseHeader(header);
          const name = values.get("name") || path.basename(path.dirname(candidate));
          const id = `${source}:${name}`;
          const plugin = source.includes(":") ? source.slice(source.indexOf(":") + 1) : null;
          seen.set(name, { id, name, display_name: name, description: values.get("description") ?? "", short_description: values.get("description") ?? "", source, scope, path: candidate, enabled: (enabled[id] ?? true) && (pluginRoots.find((item) => item.source === source)?.enabled ?? true), get system_prompt_template(): string { return lazyBody(candidate); }, allowed_tools: tools, plugin, icon: null, brand_color: null, allow_implicit_invocation: true });
        }
      } catch { /* optional root */ }
    }
    return [...seen.values()];
  }
  async setEnabled(id: string, enabled: boolean): Promise<Skill> {
    const skill = (await this.list()).find(item => item.id === id);
    if (!skill) throw new Error(`Unknown skill: ${id}`);
    const values = await this.enabledOverrides(); values[id] = enabled;
    const file = path.join(this.configRoot, "skill-settings.json");
    await fsPromises.mkdir(path.dirname(file), { recursive: true });
    await fsPromises.writeFile(file, `${JSON.stringify({ skills: values }, null, 2)}\n`, "utf8");
    return (await this.list()).find(item => item.id === id)!;
  }
  async install(sourcePath: string, scope: "personal" | "workspace"): Promise<Skill> { const source = path.resolve(sourcePath); const info = await fsPromises.stat(source); const skillFile = info.isDirectory() ? path.join(source, "SKILL.md") : source; const parsed = await parseSkillFile(skillFile); const parent = scope === "personal" ? path.join(this.configRoot, "skills") : path.join(this.projectRoot, ".sztu", "skills"); const destination = path.join(parent, parsed.name || path.basename(path.dirname(skillFile))); await fsPromises.mkdir(parent, { recursive: true }); if (info.isDirectory()) await fsPromises.cp(source, destination, { recursive: true, force: true }); else { await fsPromises.mkdir(destination, { recursive: true }); await fsPromises.cp(source, path.join(destination, "SKILL.md"), { force: true }); } const installedFile = path.join(destination, "SKILL.md"); skillFileCache.delete(installedFile); /* 覆盖安装后让旧缓存失效 */ return buildSkill(installedFile, scope === "personal" ? "user" : "project", scope, await parseSkillFile(installedFile), true); }
  async uninstall(id: string): Promise<void> { const skill = (await this.list()).find((item) => item.id === id); if (!skill) throw new Error(`Unknown skill: ${id}`); if (skill.plugin || (skill.source !== "user" && skill.source !== "project")) throw new Error("Only directly installed personal or workspace skills can be uninstalled"); const root = path.resolve(skill.source === "user" ? path.join(this.configRoot, "skills") : path.join(this.projectRoot, ".sztu", "skills")); const skillPath = path.resolve(skill.path); const target = path.basename(skillPath).toLowerCase() === "skill.md" ? path.dirname(skillPath) : skillPath; const relative = path.relative(root, target); if (!relative || relative.startsWith(`..${path.sep}`) || relative === ".." || path.isAbsolute(relative)) throw new Error("Refusing to uninstall a skill outside its installation root"); await fsPromises.rm(target, { recursive: true, force: false }); skillFileCache.delete(skillPath); }
  async get(name: string): Promise<Skill> { const skill = (await this.list()).find((item) => item.enabled && item.name === name); if (!skill) throw new Error(`Unknown or disabled skill: ${name}`); if (skill.source === "Sztubuddy") return { ...skill }; const parsed = await parseSkillFile(skill.path); return { ...skill, system_prompt_template: parsed.body, allowed_tools: parsed.tools }; }
  invalidateCache(): void { skillFileCache.clear(); }
  private async enabledOverrides(): Promise<Record<string, boolean>> { try { return (JSON.parse(await fsPromises.readFile(path.join(this.configRoot, "skill-settings.json"), "utf8")) as { skills?: Record<string, boolean> }).skills ?? {}; } catch { return {}; } }
}

function importedSkillBody(candidate: string, relative: string): string {
  const body = relative.startsWith("product/") ? loadSztubuddyResource(relative) : adaptSztubuddyText(lazyBody(candidate));
  return `Skill directory: ${path.posix.dirname(relative)} (use prompt_resource for relative references).\n\n${body}\n\n${SztubuddyContract()}`;
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
