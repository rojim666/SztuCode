import { spawnSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
if (process.platform === "win32") {
  const root = fileURLToPath(new URL("../src-tauri/", import.meta.url));
  mkdirSync(`${root}/target/installer`, { recursive: true });
  const result = spawnSync("rustc", ["--edition=2021", "-O", "-C", "target-feature=+crt-static",
    `${root}/installer/stop-runtime.rs`, "-o", `${root}/target/installer/stop-runtime.exe`], { stdio: "inherit", windowsHide: true });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}
