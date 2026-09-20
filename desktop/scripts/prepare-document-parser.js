import { spawnSync } from "node:child_process";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

// Exercise the frozen executable, not the development Python environment:
// a successful PyInstaller build does not guarantee imports work at runtime.
async function verifyDocumentParser(runtimeRoot) {
  const executable = path.join(runtimeRoot, "document-parser", process.platform === "win32" ? "document-parser.exe" : "document-parser");
  const workspace = await mkdtemp(path.join(os.tmpdir(), "sztu-parser-check-"));
  function invoke(tool, params) {
    const result = spawnSync(executable, ["--office"], {
      input: JSON.stringify({ tool, workspace, params }), encoding: "utf8",
      windowsHide: true, timeout: 60_000, maxBuffer: 1024 * 1024,
    });
    if (result.error || result.status !== 0) throw new Error(`Document parser smoke test failed: ${result.error?.message ?? result.stderr}`);
    const response = JSON.parse(result.stdout);
    if (response.error || !response.result) throw new Error(`Document parser smoke test failed: ${response.error ?? "missing result"}`);
    return response.result;
  }
  try {
    const marker = "办公解析验证";
    for (const [format, content] of [
      ["docx", { blocks: [{ kind: "paragraph", text: marker }] }],
      ["pptx", { slides: [{ title: marker, notes: "演讲备注" }] }],
      ["xlsx", { sheets: [{ name: "资料", rows: [[marker]] }] }],
    ]) {
      const file = `资料.${format}`;
      invoke("create_document", { path: file, ...content });
      const read = invoke("read_document", { path: file });
      if (!JSON.stringify(read.blocks).includes(marker)) throw new Error(`Document parser did not extract ${format} content`);
    }
  } finally {
    await rm(workspace, { recursive: true, force: true });
  }
}

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
  await verifyDocumentParser(runtimeRoot);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await prepareDocumentParser(path.join(root, "desktop", "src-tauri", "resources", "runtime"));
}
