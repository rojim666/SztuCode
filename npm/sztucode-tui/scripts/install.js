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
// ESM 产物中 CJS 依赖（如 mammoth/xlsx）的 require("fs") 会落入 esbuild 的抛错 shim；
// 注入 createRequire 提供真实 require，保证捆绑的 Node 内置模块解析正常
const requireBanner = { js: "import { createRequire } from 'node:module'; const require = createRequire(import.meta.url);" };
// transformers.js 会在运行时加载平台相关的 ONNX 原生模块，不能把所有平台的 .node 文件捆进单一产物。
// 将它保留为外部依赖，由发布包在目标平台安装对应版本。
const sharedBuildOptions = {
  bundle: true,
  platform: "node",
  format: "esm",
  absWorkingDir: repositoryRoot,
  banner: requireBanner,
  external: ["@xenova/transformers"],
};
await build({ ...sharedBuildOptions, entryPoints: [cliSource], outfile: resolve(cliTarget, "main.js") });
await build({ ...sharedBuildOptions, entryPoints: [runtimeSource], outfile: resolve(runtimeTarget, "main.js") });
console.log("Bundled the TypeScript runtime and CLI for npm publishing.");
