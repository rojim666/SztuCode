import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";
import { prepareSkillAssets } from "../../../scripts/prepare-skill-assets.js";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(packageRoot, "../..");
await prepareSkillAssets(resolve(repositoryRoot, "packages/runtime-ts/skills"), resolve(packageRoot, "skills"), repositoryRoot);
const sources = [
  [resolve(repositoryRoot, "packages/runtime-ts/prompts"), resolve(packageRoot, "prompts")],
  [resolve(repositoryRoot, "packages/runtime-ts/agents"), resolve(packageRoot, "agents")],
];
for (const [source, target] of sources) {
  if (!existsSync(source)) throw new Error(`Missing build output: ${source}`);
  rmSync(target, { recursive: true, force: true });
  cpSync(source, target, { recursive: true });
}
const cliSource = resolve(repositoryRoot, "packages/cli/src/main.ts"); const cliTarget = resolve(packageRoot, "cli");
rmSync(cliTarget, { recursive: true, force: true }); mkdirSync(cliTarget, { recursive: true });
const runtimeTarget = resolve(packageRoot, "runtime"); rmSync(runtimeTarget, { recursive: true, force: true }); mkdirSync(runtimeTarget, { recursive: true });
const runtimeSource = resolve(repositoryRoot, "packages/runtime-ts/src/main.ts");
await build({ entryPoints: [cliSource], bundle: true, platform: "node", format: "esm", outfile: resolve(cliTarget, "main.js") });
await build({ entryPoints: [runtimeSource], bundle: true, platform: "node", format: "esm", outfile: resolve(runtimeTarget, "main.js") });
console.log("Bundled the TypeScript runtime and CLI for npm publishing.");
