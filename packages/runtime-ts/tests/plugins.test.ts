import assert from "node:assert/strict";
import test from "node:test";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { PluginManager } from "../src/plugins.js";
import { SkillLoader } from "../src/skills.js";

async function createBuiltinPlugin(root: string, name: string, skillName: string, skillBody = "Demo body."): Promise<string> {
  const pluginRoot = path.join(root, name);
  const skillDir = path.join(pluginRoot, "skills", skillName);
  await mkdir(skillDir, { recursive: true });
  await writeFile(path.join(pluginRoot, "plugin.json"), `${JSON.stringify({ name, description: `${name} plugin`, version: "0.9.0", skills: "skills", interface: { displayName: name.toUpperCase(), brandColor: "#123456" } }, null, 2)}\n`, "utf8");
  await writeFile(path.join(skillDir, "SKILL.md"), `---\nname: ${skillName}\ndescription: ${skillName} skill\n---\n${skillBody}\n`, "utf8");
  return pluginRoot;
}

test("PluginManager discovers builtin plugins with builtin source and brand metadata", async () => {
  const projectRoot = await mkdtemp(path.join(os.tmpdir(), "sztu-plugin-project-"));
  const configRoot = await mkdtemp(path.join(os.tmpdir(), "sztu-plugin-config-"));
  const builtinRoot = await mkdtemp(path.join(os.tmpdir(), "sztu-plugin-builtin-"));
  try {
    await createBuiltinPlugin(builtinRoot, "demo", "hello");
    const manager = new PluginManager(projectRoot, configRoot, builtinRoot);
    const plugins = await manager.list();
    assert.equal(plugins.length, 1);
    const demo = plugins[0];
    assert.equal(demo.id, "builtin:demo");
    assert.equal(demo.source, "builtin");
    assert.equal(demo.display_name, "DEMO");
    assert.equal(demo.brand_color, "#123456");
    assert.deepEqual(demo.skills, ["hello"]);
    assert.equal(demo.enabled, true);
  } finally {
    await Promise.all([projectRoot, configRoot, builtinRoot].map((dir) => rm(dir, { recursive: true, force: true })));
  }
});

test("builtin plugins can be disabled but never uninstalled", async () => {
  const projectRoot = await mkdtemp(path.join(os.tmpdir(), "sztu-plugin-project-"));
  const configRoot = await mkdtemp(path.join(os.tmpdir(), "sztu-plugin-config-"));
  const builtinRoot = await mkdtemp(path.join(os.tmpdir(), "sztu-plugin-builtin-"));
  try {
    await createBuiltinPlugin(builtinRoot, "demo", "hello");
    const manager = new PluginManager(projectRoot, configRoot, builtinRoot);
    await assert.rejects(manager.uninstall("builtin:demo"), /builtin plugins cannot be uninstalled/);

    const disabled = await manager.setEnabled("builtin:demo", false);
    assert.equal(disabled.enabled, false);
    assert.equal((await manager.list())[0].enabled, false);
    assert.equal((await manager.skillRoots()).length, 0); // 禁用插件的技能根不再参与解析

    const enabled = await manager.setEnabled("builtin:demo", true);
    assert.equal(enabled.enabled, true);
    assert.equal((await manager.skillRoots()).length, 1);
  } finally {
    await Promise.all([projectRoot, configRoot, builtinRoot].map((dir) => rm(dir, { recursive: true, force: true })));
  }
});

test("SkillLoader exposes builtin plugin skills with system scope and priority over flat builtin", async () => {
  const projectRoot = await mkdtemp(path.join(os.tmpdir(), "sztu-plugin-project-"));
  const configRoot = await mkdtemp(path.join(os.tmpdir(), "sztu-plugin-config-"));
  const builtinRoot = await mkdtemp(path.join(os.tmpdir(), "sztu-plugin-builtin-"));
  const builtinPluginsRoot = await mkdtemp(path.join(os.tmpdir(), "sztu-plugin-builtin-plugins-"));
  const previousPluginsRoot = process.env.SZTU_BUILTIN_PLUGINS;
  process.env.SZTU_BUILTIN_PLUGINS = builtinPluginsRoot;
  try {
    // 同名技能：内建平铺版本（builtin）应被内置插件版本（builtin-plugin）覆盖
    await mkdir(path.join(builtinRoot, "hello"), { recursive: true });
    await writeFile(path.join(builtinRoot, "hello", "SKILL.md"), "---\nname: hello\ndescription: flat builtin\n---\nFlat body.\n", "utf8");
    await createBuiltinPlugin(builtinPluginsRoot, "demo", "hello", "Plugin body.");

    const loader = new SkillLoader(projectRoot, configRoot, builtinRoot);
    const skills = await loader.list();
    const hellos = skills.filter((skill) => skill.name === "hello");
    assert.equal(hellos.length, 1); // 同名技能按来源优先级去重
    assert.equal(hellos[0].source, "builtin-plugin:demo");
    assert.equal(hellos[0].scope, "system");
    assert.equal(hellos[0].plugin, "demo");
    assert.equal(hellos[0].system_prompt_template, "Plugin body.");

    // 用户技能目录中的同名技能优先级高于内置插件
    await mkdir(path.join(configRoot, "skills", "hello"), { recursive: true });
    await writeFile(path.join(configRoot, "skills", "hello", "SKILL.md"), "---\nname: hello\ndescription: user override\n---\nUser body.\n", "utf8");
    const merged = await new SkillLoader(projectRoot, configRoot, builtinRoot).list();
    const overridden = merged.filter((skill) => skill.name === "hello");
    assert.equal(overridden.length, 1);
    assert.equal(overridden[0].source, "user");
    assert.equal(overridden[0].plugin, null);
  } finally {
    if (previousPluginsRoot === undefined) delete process.env.SZTU_BUILTIN_PLUGINS;
    else process.env.SZTU_BUILTIN_PLUGINS = previousPluginsRoot;
    await Promise.all([projectRoot, configRoot, builtinRoot, builtinPluginsRoot].map((dir) => rm(dir, { recursive: true, force: true })));
  }
});
