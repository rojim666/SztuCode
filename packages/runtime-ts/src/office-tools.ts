// Desktop compatibility bridge. All office behavior and validation live in Python.
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Tool, ToolContext } from "./tools.js";
import { officeToolContracts } from "./office-contract.js";

function parserCommand(): { executable: string; args: string[] } {
  const directory = path.dirname(fileURLToPath(import.meta.url));
  const name = process.platform === "win32" ? "document-parser.exe" : "document-parser";
  const bundled = path.join(directory, "document-parser", name);
  if (existsSync(bundled)) return { executable: bundled, args: ["--office"] };
  const repository = path.resolve(directory, "../../..");
  const prepared = path.join(repository, "desktop/src-tauri/resources/runtime/document-parser", name);
  if (existsSync(prepared)) return { executable: prepared, args: ["--office"] };
  const project = path.join(repository, "py-runtime");
  const python = path.join(project, process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python");
  if (existsSync(python)) return { executable: python, args: [path.join(project, "src/sztu_code/core/documents.py"), "--office"] };
  throw new Error("内置办公解析器未准备，请运行 node desktop/scripts/prepare-document-parser.js 或安装完整客户端");
}

export async function invokeOffice(name: string, params: Record<string, unknown>, context: ToolContext): Promise<Record<string, unknown>> {
  const command = parserCommand();
  const input = JSON.stringify({ tool: name, params, workspace: context.workspace.root });
  if (Buffer.byteLength(input) > 1024 * 1024) throw new Error("办公请求超过 1MB 限制");
  if (context.signal?.aborted) throw new Error("办公操作已取消");
  return await new Promise((resolve, reject) => {
    const child = spawn(command.executable, command.args, { stdio: ["pipe", "pipe", "pipe"], windowsHide: true });
    let output = "";
    let settled = false;
    const finish = (error?: Error, result?: Record<string, unknown>) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      context.signal?.removeEventListener("abort", abort);
      if (error) reject(error); else resolve(result!);
    };
    const abort = () => { child.kill(); finish(new Error("办公操作已取消；若为写操作，请先检查目标文件再重试")); };
    const timer = setTimeout(() => { child.kill(); finish(new Error("办公操作超时；请检查目标文件或拆分资料")); }, 60_000);
    context.signal?.addEventListener("abort", abort, { once: true });
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => {
      output += chunk;
      if (output.length > 1024 * 1024) { child.kill(); finish(new Error("办公工具输出超限")); }
    });
    child.stderr.resume();
    child.on("error", (error) => finish(error));
    child.stdin.on("error", (error) => finish(error));
    child.on("close", (code) => {
      if (code !== 0) return finish(new Error(`办公解析器异常退出 (${code})`));
      try {
        const response = JSON.parse(output);
        if (response.error) return finish(new Error(String(response.error)));
        if (!response.result || typeof response.result !== "object") return finish(new Error("办公解析器返回无效结果"));
        finish(undefined, response.result);
      } catch (error) { finish(error instanceof Error ? error : new Error(String(error))); }
    });
    child.stdin.end(input);
  });
}

export function createOfficeTools(): Tool[] {
  return officeToolContracts.map((contract): Tool => ({
    ...contract,
    permission: contract.permission as Tool["permission"],
    timeoutMs: 65_000,
    retryable: false,
    async invoke(params, context) {
      try {
        const result = await invokeOffice(contract.name, params, context);
        if (contract.permission !== "read_only" && typeof result.path === "string") context.onFileChanged?.(result.path);
        return { ok: true, output: JSON.stringify(result) };
      } catch (error) { return { ok: false, output: "", error: error instanceof Error ? error.message : String(error) }; }
    },
  }));
}
