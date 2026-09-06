import { spawnSync } from "node:child_process";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

export async function prepareDocumentParser(runtimeRoot) {
  const project = path.join(root, "py-runtime");
  const scratch = path.join(root, ".sztu", "document-parser-build");
  await mkdir(scratch, { recursive: true });
  const result = spawnSync("uv", [
    "run", "--project", project, "--frozen", "--group", "desktop",
    "--cache-dir", path.join(root, ".sztu", "uv-cache"),
    "python", "-m", "PyInstaller", "--noconfirm", "--onedir",
    "--name", "document-parser", "--distpath", runtimeRoot,
    "--workpath", path.join(scratch, "build"), "--specpath", scratch,
    "--paths", path.join(project, "src"),
    path.join(project, "src", "sztu_code", "core", "documents.py"),
  ], { cwd: root, stdio: "inherit", windowsHide: true });
  if (result.error || result.status !== 0) {
    throw new Error(`Failed to bundle document parser: ${result.error?.message ?? result.status}. Install uv and retry.`);
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await prepareDocumentParser(path.join(root, "desktop", "src-tauri", "resources", "runtime"));
}
