import { cp, mkdir, readFile, readdir, rm, stat, writeFile } from "node:fs/promises";
import fsSync from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SztubuddyPlugins } from "./workbuddy-resources.js";

export type PluginScope = "personal" | "workspace";
export type PluginSource = PluginScope | "builtin";
export type PluginSummary = { id: string; name: string; description: string; version: string; source: PluginSource; path: string; skills: string[]; installed: boolean; display_name: string; brand_color: string | null; enabled: boolean; publisher: string; homepage: string; license: string };

type Manifest = { publisher?: string; homepage?: string; license?: string; name?: string; description?: string; version?: string; skills?: string | string[]; interface?: { displayName?: string; brandColor?: string } };

// 内置插件目录随包分发：源码布局在 packages/runtime-ts/plugins，打包产物在 main.js 同级 plugins。
function resolveBuiltinPluginsRoot(): string {
  if (process.env.SZTU_BUILTIN_PLUGINS) return path.resolve(process.env.SZTU_BUILTIN_PLUGINS);
  const moduleDirectory = path.dirname(fileURLToPath(import.meta.url));
  // The package-owned assets are the product source of truth. The repository fallback
  // is retained only for old development layouts and must not be needed by releases.
  return fsSync.existsSync(path.join(moduleDirectory, "plugins"))
    ? path.join(moduleDirectory, "plugins")
    : path.resolve(moduleDirectory, "../plugins");
}

export class PluginManager {
  constructor(
    private readonly projectRoot: string,
    private readonly configRoot = path.join(process.env.USERPROFILE ?? process.env.HOME ?? process.cwd(), ".sztu"),
    private readonly builtinRoot = resolveBuiltinPluginsRoot(),
  ) {}
  private parent(scope: PluginScope): string { return scope === "personal" ? path.join(this.configRoot, "plugins") : path.join(this.projectRoot, ".sztu", "plugins"); }
  async list(): Promise<PluginSummary[]> {
    const enabled = await this.enabledOverrides();
    const output: PluginSummary[] = [];
    // 内置插件排在个人/工作区之前；同名插件以用户安装版本为准（列表后写覆盖前写）。
    for (const source of ["builtin", "personal", "workspace"] as const) {
      const parent = source === "builtin" ? this.builtinRoot : this.parent(source);
      try {
        for (const entry of await readdir(parent, { withFileTypes: true })) {
          if (!entry.isDirectory()) continue;
          const root = path.join(parent, entry.name);
          const manifest = await this.readManifest(root);
          if (!manifest) continue;
          const name = manifest.name || entry.name;
          const id = `${source}:${name}`;
          const skillDirs = Array.isArray(manifest.skills) ? manifest.skills : [manifest.skills ?? "skills"];
          const skills: string[] = [];
          for (const directory of skillDirs) {
            try {
              for (const item of await readdir(path.resolve(root, directory), { withFileTypes: true }))
                if (item.isDirectory()) skills.push(item.name);
            } catch { /* optional skills */ }
          }
          output.push({
            id, name, description: manifest.description ?? "", version: manifest.version ?? "", source,
            path: root, skills: skills.sort(), installed: true,
            display_name: manifest.interface?.displayName ?? name,
            brand_color: /^#[0-9a-f]{6}$/i.test(manifest.interface?.brandColor ?? "") ? manifest.interface!.brandColor! : null,
            enabled: enabled[id] ?? true, publisher: manifest.publisher ?? "", homepage: manifest.homepage ?? "", license: manifest.license ?? "",
          });
        }
      } catch { /* optional root */ }
    }
    for (const plugin of SztubuddyPlugins()) {
      const id = `builtin:${plugin.name}`;
      output.push({ ...plugin, id, source: "builtin", version: "", description: "Imported Sztubuddy skill collection; external services require configured connectors.", installed: true, display_name: plugin.name, brand_color: null, enabled: enabled[id] ?? true, publisher: "", homepage: "", license: "" });
    }
    return output;
  }
  async install(sourcePath: string, scope: PluginScope): Promise<PluginSummary> { const source = path.resolve(sourcePath); if (!(await stat(source)).isDirectory()) throw new Error("plugin source must be a directory"); const manifest = await this.readManifest(source); if (!manifest) throw new Error("plugin.json or .codex-plugin/plugin.json is required"); const name = manifest.name || path.basename(source); if (!/^[A-Za-z0-9_.-]+$/.test(name)) throw new Error("invalid plugin name"); const destination = path.join(this.parent(scope), name); await mkdir(path.dirname(destination), { recursive: true }); await rm(destination, { recursive: true, force: true }); await cp(source, destination, { recursive: true }); const plugin = (await this.list()).find((item) => item.id === `${scope}:${name}`); if (!plugin) throw new Error("installed plugin could not be loaded"); return plugin; }
  async setEnabled(id: string, enabled: boolean): Promise<PluginSummary> { const plugin = (await this.list()).find((item) => item.id === id); if (!plugin) throw new Error(`Unknown plugin: ${id}`); const values = await this.enabledOverrides(); values[id] = enabled; await mkdir(this.configRoot, { recursive: true }); await writeFile(path.join(this.configRoot, "plugin-settings.json"), `${JSON.stringify({ plugins: values }, null, 2)}\n`, "utf8"); return { ...plugin, enabled }; }
  async uninstall(id: string): Promise<void> { const plugin = (await this.list()).find((item) => item.id === id); if (!plugin) throw new Error(`Unknown plugin: ${id}`); if (plugin.source === "builtin") throw new Error("builtin plugins cannot be uninstalled"); await rm(plugin.path, { recursive: true, force: true }); }
  async skillRoots(includeDisabled = false): Promise<Array<{ root: string; source: string; scope: "system" | "personal" | "workspace"; enabled: boolean }>> {
    const result: Array<{ root: string; source: string; scope: "system" | "personal" | "workspace"; enabled: boolean }> = [];
    for (const plugin of await this.list()) {
      if (SztubuddyPlugins().some(item => item.path === plugin.path)) continue;
      if (!plugin.enabled && !includeDisabled) continue;
      const manifest = await this.readManifest(plugin.path);
      const directories = Array.isArray(manifest?.skills) ? manifest!.skills : [manifest?.skills ?? "skills"];
      for (const directory of directories) {
        const root = path.resolve(plugin.path, directory);
        const relative = path.relative(plugin.path, root);
        if (relative.startsWith("..") || path.isAbsolute(relative)) continue;
        const prefix = plugin.source === "builtin" ? "builtin-plugin" : plugin.source === "personal" ? "user-plugin" : "project-plugin";
        const scope = plugin.source === "builtin" ? "system" : plugin.source;
        result.push({ root, source: `${prefix}:${plugin.name}`, scope, enabled: plugin.enabled });
      }
    }
    return result;
  }
  private async readManifest(root: string): Promise<Manifest | null> { for (const candidate of [path.join(root, ".codex-plugin", "plugin.json"), path.join(root, "plugin.json")]) { try { return JSON.parse(await readFile(candidate, "utf8")) as Manifest; } catch { /* next */ } } return null; }
  private async enabledOverrides(): Promise<Record<string, boolean>> { try { return (JSON.parse(await readFile(path.join(this.configRoot, "plugin-settings.json"), "utf8")) as { plugins?: Record<string, boolean> }).plugins ?? {}; } catch { return {}; } }
}
