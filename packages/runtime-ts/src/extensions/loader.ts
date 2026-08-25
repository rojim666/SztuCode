import { pathToFileURL } from "node:url";
import path from "node:path";
import type { ExtensionDefinition, ExtensionScope } from "./types.js";
import { ExtensionRegistry } from "./registry.js";

export async function loadExtensionModule(registry: ExtensionRegistry, modulePath: string, scope: ExtensionScope, workspaceRoot: string): Promise<boolean> {
  const root = path.resolve(workspaceRoot); const id = path.basename(modulePath).replace(/\.[^.]+$/, "");
  try {
    const module = await import(pathToFileURL(path.resolve(modulePath)).href) as { default?: unknown; activate?: unknown; extension?: unknown };
    const candidate = module.default ?? module.extension ?? (typeof module.activate === "function" ? { activate: module.activate } : undefined);
    const definition = typeof candidate === "function" ? { id, scope, root, activate: candidate as ExtensionDefinition["activate"] } : candidate as ExtensionDefinition | undefined;
    if (!definition || typeof definition.activate !== "function") throw new Error("Extension module must export default activate(api) or an ExtensionDefinition");
    return await registry.load({ ...definition, id: definition.id ?? id, scope: definition.scope ?? scope, root: definition.root ?? root });
  } catch (error) {
    registry.recordLoad(id, root, scope, error);
    return false;
  }
}
