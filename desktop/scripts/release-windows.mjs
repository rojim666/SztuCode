import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const desktop = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const config = JSON.parse(readFileSync(path.join(desktop, "src-tauri/tauri.conf.json"), "utf8"));
const version = config.version;
const releaseTag = process.env.SZTU_RELEASE_TAG || `v${version}`;
const packageVersion = JSON.parse(readFileSync(path.join(desktop, "package.json"), "utf8")).version;
const cargo = readFileSync(path.join(desktop, "src-tauri/Cargo.toml"), "utf8");
if (process.platform !== "win32" || process.arch !== "x64") {
  throw new Error("This release command builds Windows x64 installers only.");
}
if (packageVersion !== version || !cargo.includes(`version = "${version}"`)) {
  throw new Error("Desktop npm, Cargo and Tauri versions must match.");
}
const notes = readFileSync(path.join(desktop, `../docs/releases/v${version}.md`), "utf8");
const env = { ...process.env };
if (!env.TAURI_SIGNING_PRIVATE_KEY) {
  const keyPath = env.SZTU_UPDATER_KEY_PATH || path.join(process.env.LOCALAPPDATA, "SztuCode/release-keys/updater.key");
  try {
    env.TAURI_SIGNING_PRIVATE_KEY = readFileSync(keyPath, "utf8").trim();
  } catch {
    throw new Error("Signing key unavailable. Set SZTU_UPDATER_KEY_PATH or TAURI_SIGNING_PRIVATE_KEY; see UPDATING.md.");
  }
}
env.TAURI_SIGNING_PRIVATE_KEY_PASSWORD ??= "";
const result = spawnSync(process.execPath, [
  path.join(desktop, "node_modules/@tauri-apps/cli/tauri.js"),
  "build", "--bundles", "nsis,msi", "--config",
  JSON.stringify({ bundle: { createUpdaterArtifacts: true } }),
], { cwd: desktop, env, stdio: "inherit", windowsHide: true });
if (result.error) throw result.error;
if (result.status !== 0) process.exit(result.status ?? 1);

const bundle = path.join(desktop, "src-tauri/target/release/bundle");
const platforms = {};
const checksums = [];
for (const [kind, name] of [
  ["nsis", `SztuCode_${version}_x64-setup.exe`],
  ["msi", `SztuCode_${version}_x64_zh-CN.msi`],
]) {
  const installer = path.join(bundle, kind, name);
  const signature = readFileSync(`${installer}.sig`, "utf8").trim();
  if (!signature) throw new Error(`Missing signature for ${name}`);
  platforms[`windows-x86_64-${kind}`] = {
    signature,
    url: `https://github.com/rojim666/SztuCode/releases/download/${encodeURIComponent(releaseTag)}/${name}`,
  };
  checksums.push(`${createHash("sha256").update(readFileSync(installer)).digest("hex")}  ${name}`);
}
// Older updater clients without installer-specific target support use NSIS.
platforms["windows-x86_64"] = platforms["windows-x86_64-nsis"];
writeFileSync(path.join(bundle, "latest.json"), JSON.stringify({
  version, notes, pub_date: new Date().toISOString(), platforms,
}, null, 2) + "\n");
writeFileSync(path.join(bundle, `SHA256SUMS-v${version}.txt`), checksums.join("\n") + "\n");
console.log(`Signed installers, signatures, latest.json and checksums are ready in ${bundle}`);
console.log("Upload installers and signatures first; publish latest.json last.");
