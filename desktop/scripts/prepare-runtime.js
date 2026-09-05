import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { chmod, cp, mkdir, readdir, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { prepareSkillAssets } from "../../scripts/prepare-skill-assets.js";

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(desktopRoot, "..");
const output = path.join(desktopRoot, "src-tauri", "resources", "runtime", "main.js");
const runtimeRoot = path.dirname(output);
const lockPath = path.join(path.dirname(runtimeRoot), ".runtime-prep.lock");

async function acquireLock() {
  // resources 目录被 .gitignore 忽略，干净 CI 中可能尚不存在。
  await mkdir(path.dirname(lockPath), { recursive: true });
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
const esbuildArgs = [path.join(repositoryRoot, "packages", "runtime-ts", "src", "main.ts"), "--bundle", "--platform=node", "--format=esm", "--loader:.node=file", `--outfile=${output}`,
  // ESM 产物中 CJS 依赖的动态 require 会落入 esbuild 抛错 shim，注入真实 require
  `--banner:js=import { createRequire } from 'node:module'; const require = createRequire(import.meta.url);`];
const nativeEsbuild = process.platform === "win32"
  ? path.join(repositoryRoot, "node_modules", "@esbuild", `win32-${process.arch === "ia32" ? "ia32" : process.arch === "arm64" ? "arm64" : "x64"}`, "esbuild.exe")
  : esbuild;
const esbuildCommand = await import("node:fs").then(({ existsSync }) => existsSync(nativeEsbuild) ? nativeEsbuild : esbuild);
const esbuildIsScript = esbuildCommand === esbuild && readFileSync(esbuild).subarray(0, 2).toString() === "#!/";
const result = spawnSync(esbuildIsScript ? process.execPath : esbuildCommand, esbuildIsScript ? [esbuildCommand, ...esbuildArgs] : esbuildArgs, { cwd: repositoryRoot, stdio: "inherit", windowsHide: true });
if (result.status !== 0) throw new Error(`Failed to bundle the TypeScript runtime (exit code ${result.status ?? 1})`);
// esbuild 的 file loader 只把 .node 拷进产物目录，不会带它们的运行时动态库；
// 缺失时 linuxdeploy 直接报 "Could not find dependency: libonnxruntime.so.x / libvips-cpp.so.42"，
// 安装版 daemon 也无法加载（Linux 走 $ORIGIN rpath，Windows 走 node.exe 同目录搜索）。
const onnxBin = path.join(repositoryRoot, "node_modules", "onnxruntime-node", "bin");
for (const napiVersion of await readdir(onnxBin).catch(() => [])) {
  const nativeDir = path.join(onnxBin, napiVersion, process.platform, process.arch);
  for (const file of await readdir(nativeDir).catch(() => [])) {
    if (!file.endsWith(".node")) await cp(path.join(nativeDir, file), path.join(runtimeRoot, file));
  }
}
const sharpVendor = path.join(repositoryRoot, "node_modules", "sharp", "vendor");
for (const vipsVersion of await readdir(sharpVendor).catch(() => [])) {
  const libDir = path.join(sharpVendor, vipsVersion, `${process.platform}-${process.arch}`, "lib");
  for (const file of await readdir(libDir).catch(() => [])) {
    if (/\.(so(\.\d+)*|dll)$/.test(file)) await cp(path.join(libDir, file), path.join(runtimeRoot, file));
  }
}
// sharp 的预编译 .node 写死了指向原 vendor 相对路径的 RPATH，被 esbuild 拷到产物目录后失效
//（linuxdeploy 与 dlopen 都按 RPATH 找依赖，库就在同目录也会报 Could not find dependency）；
// 统一改成 $ORIGIN，让同目录的原生库可解析
if (process.platform === "linux") {
  for (const file of await readdir(runtimeRoot)) {
    if (file.endsWith(".node")) {
      const nativePath = path.join(runtimeRoot, file);
      // .node 只是扩展名；只有 ELF 原生模块才能由 patchelf 修改 RPATH。
      const header = readFileSync(nativePath).subarray(0, 4);
      if (header.length < 4 || header[0] !== 0x7f || header[1] !== 0x45 || header[2] !== 0x4c || header[3] !== 0x46) continue;
      const patched = spawnSync("patchelf", ["--set-rpath", "$ORIGIN", nativePath], { stdio: "inherit" });
      if (patched.status !== 0) throw new Error(`patchelf failed for ${file}`);
    }
  }
}
// esbuild 以 --format=esm 输出 .js，而 Node 对 .js 默认按 CommonJS 解析；
// 必须在 runtime 目录声明 "type": "module"，否则安装版 daemon 启动即报
// "Cannot use import statement outside a module"（issue #152）
await writeFile(path.join(runtimeRoot, "package.json"), `${JSON.stringify({ type: "module" }, null, 2)}\n`);
await prepareSkillAssets(path.join(repositoryRoot, "packages", "runtime-ts", "skills"), path.join(runtimeRoot, "skills"), repositoryRoot);
for (const directory of ["prompts", "agents"]) await cp(path.join(repositoryRoot, "packages", "runtime-ts", directory), path.join(runtimeRoot, directory), { recursive: true });
} finally {
  await rm(lockPath, { recursive: true, force: true });
}
