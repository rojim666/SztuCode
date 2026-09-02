// 启动带 CDP 调试端口的 Chrome，供路线 2（attached 模式）连接
// 默认使用持久 agent profile（登录一次后登录态跨会话保留，且不与日常 Chrome 冲突）
// 用法：npm run browser:launch           —— 持久 agent profile
//       npm run browser:launch:system   —— 系统真实 profile（需先完全退出日常 Chrome）
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import http from "node:http";
import path from "node:path";
import { dataRoot } from "../src/server-helpers.js";

const port = Number(process.env.SZTU_CHROME_DEBUG_PORT ?? 9222);
const useSystemProfile = process.argv.includes("--system");
const profileDir = path.join(dataRoot(), "chrome-agent-profile");

const chromeCandidates = (): string[] => {
  if (process.env.CHROME_PATH) return [process.env.CHROME_PATH];
  if (process.platform === "win32") {
    const programFiles = [process.env["PROGRAMFILES"], process.env["PROGRAMFILES(X86)"], process.env.LOCALAPPDATA].filter((v): v is string => !!v);
    return programFiles.map((base) => path.join(base, "Google", "Chrome", "Application", "chrome.exe"));
  }
  if (process.platform === "darwin") return ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"];
  return ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"];
};

const executable = chromeCandidates().find((candidate) => existsSync(candidate));
if (!executable) {
  console.error("未找到 Chrome，请设置 CHROME_PATH 指向 chrome.exe");
  process.exit(1);
}

const getJson = (url: string): Promise<Record<string, unknown> | null> => new Promise((resolve) => {
  const request = http.get(url, (response) => {
    let body = "";
    response.setEncoding("utf8");
    response.on("data", (chunk) => { body += chunk; });
    response.on("end", () => { try { resolve(JSON.parse(body) as Record<string, unknown>); } catch { resolve(null); } });
  });
  request.on("error", () => resolve(null));
  request.setTimeout(1000, () => { request.destroy(); resolve(null); });
});

const versionUrl = `http://127.0.0.1:${port}/json/version`;
const existing = await getJson(versionUrl);
if (existing) {
  console.log(`CDP 端口 ${port} 已有 Chrome 在运行（${String(existing.Browser ?? "unknown")}），直接复用`);
} else {
  const args = [`--remote-debugging-port=${port}`, "--no-first-run", "--no-default-browser-check", "about:blank"];
  if (useSystemProfile) {
    console.log("使用系统真实 profile：若日常 Chrome 未完全退出，调试端口不会生效");
  } else {
    args.push(`--user-data-dir=${profileDir}`);
    console.log(`使用持久 agent profile：${profileDir}`);
  }
  spawn(executable, args, { detached: true, stdio: "ignore" }).unref();
  const deadline = Date.now() + 15_000;
  let ready = false;
  while (Date.now() < deadline) {
    if (await getJson(versionUrl)) { ready = true; break; }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  if (!ready) {
    console.error(`Chrome 已启动但 CDP 端口 ${port} 未就绪（若用了系统 profile，请先完全退出日常 Chrome 再试）`);
    process.exit(1);
  }
  console.log(`Chrome 已启动，CDP 就绪：${versionUrl}`);
}

console.log(`\n下一步：设置 SZTU_MCP_CONFIG 指向 mcp.chrome-devtools.attached.json 后启动 runtime，或运行：`);
console.log(`  npm run verify:browser-mcp:attached`);
