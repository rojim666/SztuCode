import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");

test("every desktop RPC request has a TypeScript runtime handler", async () => {
  const desktop = await readFile(path.join(repositoryRoot, "desktop/src/services/sztu-runtime.ts"), "utf8");
  const server = await readFile(path.join(repositoryRoot, "packages/runtime-ts/src/server-service.ts"), "utf8");
  const requested = new Set([...desktop.matchAll(/client\.request\(\s*["']([^"']+)["']/g)].map((match) => match[1]));
  const handled = new Set([...server.matchAll(/case\s+["']([^"']+)["']/g)].map((match) => match[1]));
  assert.deepEqual([...requested].filter((method) => !handled.has(method)), []);
  assert.ok(requested.size >= 50, "desktop RPC extraction unexpectedly found too few methods");
});

test("Tauri production bundles and starts the TypeScript runtime resource", async () => {
  const config = JSON.parse(await readFile(path.join(repositoryRoot, "desktop/src-tauri/tauri.conf.json"), "utf8")) as { bundle?: { resources?: string[] } };
  const rust = await readFile(path.join(repositoryRoot, "desktop/src-tauri/src/main.rs"), "utf8");
  const prepare = await readFile(path.join(repositoryRoot, "desktop/scripts/prepare-runtime.js"), "utf8");
  assert.ok(config.bundle?.resources?.some((resource) => resource.startsWith("resources/runtime/")));
  assert.match(rust, /BaseDirectory::Resource/); assert.match(rust, /resources\/runtime\/main\.js/); assert.match(rust, /node\.exe/); assert.match(rust, /desktop-daemon\.log/); assert.match(rust, /cfg\(debug_assertions\)/); assert.match(rust, /strip_prefix\(r"\\\\\?\\"\)/);
  assert.match(prepare, /runtime-ts/); assert.match(prepare, /process\.execPath/); assert.match(prepare, /esbuildIsScript/); assert.match(prepare, /chmod\(bundledNode, 0o755\)/); assert.match(prepare, /resources["']?,\s*["']runtime/); assert.match(prepare, /prepareSkillAssets/); assert.match(prepare, /\["prompts",\s*"agents"\]/);
});
