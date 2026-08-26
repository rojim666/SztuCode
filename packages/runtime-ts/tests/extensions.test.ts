import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { ExtensionRegistry } from "../src/extensions/registry.js";
import { loadExtensionModule } from "../src/extensions/loader.js";
import type { ExtensionDefinition } from "../src/extensions/types.js";
import type { Tool } from "../src/tools.js";

const tool = (name: string): Tool => ({ name, description: name, permission: "read_only", schema: { type: "object" }, async invoke() { return { ok: true, output: name }; } });
const definition = (id: string, scope: "global" | "workspace", root: string, activate: ExtensionDefinition["activate"], deactivate?: ExtensionDefinition["deactivate"]): ExtensionDefinition => ({ id, scope, root, activate, deactivate });

test("extensions load, register tools and unload cleanly", async () => {
  const registry = new ExtensionRegistry(); let deactivated = false;
  assert.equal(await registry.load(definition("one", "global", "/global", (api) => { api.registerTool(tool("one_tool")); api.registerSlashCommand({ name: "one", execute: () => "ok" }); api.registerResource({ name: "doc", content: "resource" }); }, () => { deactivated = true; })), true);
  assert.deepEqual(registry.toolsForWorkspace("/a").map((item) => item.name), ["one_tool"]);
  assert.equal(await registry.unload("one"), true); assert.equal(deactivated, true); assert.equal(registry.toolsForWorkspace("/a").length, 0);
});

test("global and workspace extensions are isolated by workspace root", async () => {
  const registry = new ExtensionRegistry();
  await registry.load(definition("global", "global", "/ignored", (api) => api.registerTool(tool("global_tool"))));
  await registry.load(definition("workspace-a", "workspace", "/workspace/a", (api) => api.registerTool(tool("a_tool"))));
  assert.deepEqual(registry.toolsForWorkspace("/workspace/a").map((item) => item.name).sort(), ["a_tool", "global_tool"]);
  assert.deepEqual(registry.toolsForWorkspace("/workspace/b").map((item) => item.name), ["global_tool"]);
});

test("tool conflicts are diagnosed without replacing existing tools", async () => {
  const registry = new ExtensionRegistry(); await registry.load(definition("conflict", "global", "/", (api) => api.registerTool(tool("read_file"))));
  const tools = registry.toolsForWorkspace("/", new Set(["read_file"])); assert.equal(tools.length, 0);
  assert.ok(registry.diagnostics().some((item) => item.message.includes("Tool name conflict")));
});

test("activation, deactivation and hook errors are diagnosed and isolated", async () => {
  const registry = new ExtensionRegistry(); let second = false; let events = 0;
  assert.equal(await registry.load(definition("bad", "global", "/", () => { throw new Error("activate failed"); })), false);
  await registry.load(definition("hooks", "global", "/", (api) => { api.on("agent_start", () => { throw new Error("hook failed"); }); api.on("agent_start", () => { events += 1; }); api.onSessionEvent(async () => { throw new Error("event failed"); }); }));
  await registry.load(definition("good", "global", "/", () => { second = true; })); assert.equal(second, true);
  await registry.dispatch("agent_start", { goal: "x" }, "/"); await registry.emitSessionEvent({ type: "core.started", listen_addr: "x", version: "x" }, "/");
  assert.equal(events, 1); assert.ok(registry.diagnostics().some((item) => item.phase === "activate")); assert.ok(registry.diagnostics().some((item) => item.phase === "hook"));
});

test("extension loader reports module failures and loads default activate modules", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-extension-test-")); const registry = new ExtensionRegistry();
  const modulePath = path.join(root, "fixture.mjs"); await writeFile(modulePath, "export default (api) => api.registerTool({name:'loaded_tool',description:'loaded',permission:'read_only',schema:{type:'object'},invoke:async()=>({ok:true,output:'ok'})});", "utf8");
  assert.equal(await loadExtensionModule(registry, modulePath, "workspace", root), true); assert.equal(registry.toolsForWorkspace(root).length, 1);
  assert.equal(await loadExtensionModule(registry, path.join(root, "missing.mjs"), "workspace", root), false); assert.ok(registry.diagnostics().some((item) => item.phase === "load"));
  await rm(root, { recursive: true, force: true });
});
