import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { chmod, cp, mkdir, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { prepareSkillAssets } from "../../scripts/prepare-skill-assets.js";

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(desktopRoot, "..");
const output = path.join(desktopRoot, "src-tauri", "resources", "runtime", "main.js");
const runtimeRoot = path.dirname(output);
const lockPath = path.join(path.dirname(runtimeRoot), ".runtime-prep.lock");

async function acquireLock() {
  const deadline = Date.now() + 120_000;
  for (;;) {
    try {
      await mkdir(lockPath);
      await writeFile(path.join(lockPath, "owner"), `${process.pid}\n`, "utf8");
      return;
    } catch (error) {
      if (error?.code !== "EEXIST") throw error;
      try {
        const lockAge = Date.now() - (await stat(lockPath)).mtimeMs;
        if (lockAge > 120_000) {
          await rm(lockPath, { recursive: true, force: true });
          continue;
        }
      } catch {
        // The other preparation process may be replacing the lock directory.
      }
      if (Date.now() >= deadline) throw new Error("Timed out waiting for another desktop runtime preparation");
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }
}

await acquireLock();
try {
  await rm(runtimeRoot, { recursive: true, force: true }); await mkdir(runtimeRoot, { recursive: true });
// Ship Node with the desktop bundle so installed clients can start the local daemon.
const bundledNode = path.join(runtimeRoot, process.platform === "win32" ? "node.exe" : "node");
await cp(process.execPath, bundledNode);
if (process.platform !== "win32") await chmod(bundledNode, 0o755);
const esbuild = path.join(repositoryRoot, "node_modules", "esbuild", "bin", "esbuild");
const esbuildArgs = [path.join(repositoryRoot, "packages", "runtime-ts", "src", "main.ts"), "--bundle", "--platform=node", "--format=esm", `--outfile=${output}`,
  // ESM 产物中 CJS 依赖的动态 require 会落入 esbuild 抛错 shim，注入真实 require
  `--banner:js=import { createRequire } from 'node:module'; const require = createRequire(import.meta.url);`];
const nativeEsbuild = process.platform === "win32"
  ? path.join(repositoryRoot, "node_modules", "@esbuild", `win32-${process.arch === "ia32" ? "ia32" : process.arch === "arm64" ? "arm64" : "x64"}`, "esbuild.exe")
  : esbuild;
const esbuildCommand = await import("node:fs").then(({ existsSync }) => existsSync(nativeEsbuild) ? nativeEsbuild : esbuild);
const esbuildIsScript = esbuildCommand === esbuild && readFileSync(esbuild).subarray(0, 2).toString() === "#!/";
const result = spawnSync(esbuildIsScript ? process.execPath : esbuildCommand, esbuildIsScript ? [esbuildCommand, ...esbuildArgs] : esbuildArgs, { cwd: repositoryRoot, stdio: "inherit", windowsHide: true });
if (result.status !== 0) throw new Error(`Failed to bundle the TypeScript runtime (exit code ${result.status ?? 1})`);
await prepareSkillAssets(path.join(repositoryRoot, "packages", "runtime-ts", "skills"), path.join(runtimeRoot, "skills"), repositoryRoot);
for (const directory of ["prompts", "agents"]) await cp(path.join(repositoryRoot, "packages", "runtime-ts", directory), path.join(runtimeRoot, directory), { recursive: true });
} finally {
  await rm(lockPath, { recursive: true, force: true });
}
