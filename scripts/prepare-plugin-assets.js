import { cp, mkdir, readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { prepareSkillAssets } from "./prepare-skill-assets.js";

// Only distribute the skill roots explicitly selected by each built-in manifest.
// Legacy research copies are retained in the checkout, never shipped to clients.
export async function preparePluginAssets(source, target, repositoryRoot) {
  await mkdir(target, { recursive: true });
  for (const entry of await readdir(source, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue;
    const root = path.join(source, entry.name);
    const manifest = JSON.parse(await readFile(path.join(root, "plugin.json"), "utf8"));
    const output = path.join(target, entry.name);
    await mkdir(output, { recursive: true });
    for (const file of await readdir(root, { withFileTypes: true })) {
      if (file.isFile()) await cp(path.join(root, file.name), path.join(output, file.name));
    }
    for (const directory of Array.isArray(manifest.skills) ? manifest.skills : [manifest.skills ?? "skills"]) {
      const resolved = path.resolve(root, directory);
      const relative = path.relative(root, resolved);
      if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) throw new Error(`Invalid bundled skill root: ${directory}`);
      await prepareSkillAssets(resolved, path.join(output, relative), repositoryRoot);
    }
  }
}
