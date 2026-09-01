#!/usr/bin/env node
// Cleans up leftover Tauri/desktop dev processes that can block the next build:
//   - the running desktop app binary (sztucode-desktop)
//   - cargo run (tauri dev)
//   - the Tauri CLI dev process
//   - desktop Vite dev servers
//   - the Node runtime bundled into the desktop bundle
//
// Default mode is a dry run. Pass --apply to actually terminate the processes.

import { execFileSync, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const apply = process.argv.includes("--apply");
const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const desktopRoot = path.join(repositoryRoot, "desktop");
const repoPath = repositoryRoot.toLowerCase();
const desktopPath = desktopRoot.toLowerCase();

function isDesktopResidual(name, command) {
  const n = String(name ?? "").toLowerCase();
  const c = String(command ?? "").toLowerCase();

  // 1. The desktop app binary produced by `tauri dev` / `cargo run`.
  if (n.includes("sztucode") || n.includes("sztucode-desktop")) return true;

  // 2. `tauri dev` launches cargo run with --no-default-features.
  if (n === "cargo" || n === "cargo.exe") {
    return c.includes("--no-default-features") || c.includes(repoPath) || c.includes("tauri");
  }

  // 3. The Tauri CLI (dev/build) invoked through its JS launcher or native binary.
  if (c.includes("@tauri-apps") || c.includes("tauri.js") || c.includes("tauri.exe")) {
    return c.includes(repoPath) || c.includes("tauri");
  }

  // 4. A Vite dev server rooted in desktop/ (port 5173 or the per-instance ports).
  if (c.includes("vite") && c.includes(desktopPath)) return true;

  // 5. The Node runtime bundled into the desktop build resources.
  if (c.includes(desktopPath) && c.includes("resources") && c.includes("runtime")) return true;

  return false;
}

function resolvePowerShell() {
  // Some toolchains (IDE terminals, CI wrappers) strip System32\WindowsPowerShell
  // from PATH, so resolve the absolute path before spawning.
  const systemRoot = process.env.SystemRoot || "C:\\Windows";
  const fullPath = path.join(systemRoot, "System32", "WindowsPowerShell", "v1.0", "powershell.exe");
  try {
    if (existsSync(fullPath)) return fullPath;
  } catch {
    // Fall through to the bare command and let the OS resolve it.
  }
  return "powershell";
}

function listProcesses() {
  const rows = [];
  if (process.platform === "win32") {
    const out = execFileSync(
      resolvePowerShell(),
      [
        "-NoProfile",
        "-Command",
        "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Compress",
      ],
      { encoding: "utf8", windowsHide: true, maxBuffer: 16 * 1024 * 1024 },
    );
    const parsed = JSON.parse(out);
    const items = Array.isArray(parsed) ? parsed : [parsed];
    for (const item of items) {
      rows.push({ pid: item.ProcessId, ppid: item.ParentProcessId, name: item.Name, command: item.CommandLine ?? "" });
    }
  } else {
    const out = execFileSync("ps", ["-eo", "pid=,ppid=,comm=,args="], {
      encoding: "utf8",
      maxBuffer: 16 * 1024 * 1024,
    });
    for (const line of out.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      const fields = trimmed.split(/\s+/);
      const pid = Number.parseInt(fields[0], 10);
      const ppid = Number.parseInt(fields[1], 10);
      const name = fields[2] ?? "";
      const command = fields.slice(3).join(" ");
      rows.push({ pid, ppid, name, command });
    }
  }
  return rows;
}

const selfPid = process.pid;
const processes = listProcesses();
const processByPid = new Map(processes.map((p) => [p.pid, p]));
const protectedPids = new Set([selfPid]);
// `predev` and `prebuild` run as children of the active Tauri CLI. Never
// terminate that command while it is waiting for this lifecycle hook.
for (let pid = process.ppid; pid && !protectedPids.has(pid); ) {
  protectedPids.add(pid);
  pid = processByPid.get(pid)?.ppid;
}
const targets = listProcesses().filter(
  (p) => !protectedPids.has(p.pid) && isDesktopResidual(p.name, p.command),
);

if (targets.length === 0) {
  console.log("No leftover desktop/Tauri processes found.");
  process.exit(0);
}

console.log(`${apply ? "Terminating" : "Found"} ${targets.length} leftover desktop/Tauri process(es):`);
for (const p of targets) {
  console.log(`  [${p.pid}] ${p.name} ${p.command}`);
}

if (!apply) {
  console.log("\nDry run. Re-run with --apply to terminate these processes.");
  process.exit(0);
}

let failures = 0;
for (const p of targets) {
  const result =
    process.platform === "win32"
      ? spawnSync("taskkill", ["/PID", String(p.pid), "/T", "/F"], { stdio: "ignore", windowsHide: true })
      : spawnSync("kill", ["-9", String(p.pid)], { stdio: "ignore" });
  if (result.status !== 0) {
    failures += 1;
  }
}

// Windows may keep an executable handle alive briefly after taskkill returns.
// Wait for the process tree to disappear before prepare-runtime replaces files.
const targetPids = new Set(targets.map((p) => p.pid));
const deadline = Date.now() + 2_000;
while (Date.now() < deadline) {
  const remaining = listProcesses().some((p) => targetPids.has(p.pid));
  if (!remaining) break;
  await new Promise((resolve) => setTimeout(resolve, 100));
}

if (failures > 0) {
  console.log(`\n${failures} process(es) already exited or could not be terminated.`);
} else {
  console.log("\nCleanup complete.");
}
