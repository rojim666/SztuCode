import assert from "node:assert/strict";
import { mkdtemp, readFile, access } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { preparePluginAssets } from "../../../scripts/prepare-plugin-assets.js";
import { PluginManager } from "../src/plugins.js";

test("desktop distribution contains six executable plugins plus imported prompt plugins", async () => {
  const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
  const temp = await mkdtemp(path.join(os.tmpdir(), "sztu-builtin-plugins-"));
  const target = path.join(temp, "plugins");
  await preparePluginAssets(path.join(repo, "packages/runtime-ts/plugins"), target, repo);
  const plugins = await new PluginManager(temp, path.join(temp, "config"), target).list();
  const executablePlugins = plugins.filter(plugin => path.dirname(plugin.path) === target);
  assert.equal(executablePlugins.length, 6);
  assert.equal(plugins.length, 11);
  for (const plugin of executablePlugins) {
    assert.ok(plugin.skills.length > 0);
    assert.ok(plugin.publisher && plugin.homepage && plugin.license);
    await access(path.join(plugin.path, "SOURCE.md"));
  }
  for (const plugin of ["word", "excel", "github"]) {
    await assert.rejects(access(path.join(target, plugin, "skills")));
    await access(path.join(target, plugin, "bundled-skills"));
  }
  assert.match(await readFile(path.join(target, "word/bundled-skills/doc/LICENSE.txt"), "utf8"), /Apache License/);
});
