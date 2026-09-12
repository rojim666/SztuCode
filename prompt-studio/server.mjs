// Prompt Studio server.
//
// A zero-dependency local console for inspecting, editing and re-composing the
// SztuCode system prompts that the TypeScript runtime actually loads. It maps
// directly onto the on-disk prompt bundle and the real composition functions
// under packages/runtime-ts, so what you see is what the daemon would send.
import http from "node:http";
import path from "node:path";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { promises as fs } from "node:fs";

const here = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(here, "..");
const PROMPT_ROOT = path.join(REPO_ROOT, "packages", "runtime-ts", "prompts", "content");
const Sztubuddy_ROOT = path.join(REPO_ROOT, "packages", "runtime-ts", "prompts", "Sztubuddy");
const PUBLIC_DIR = path.join(here, "public");
const BACKUP_ROOT = path.join(REPO_ROOT, ".sztu", "prompt-studio-backups");
const COMPOSE_WORKER = path.join(here, "lib", "compose.mjs");
const PORT = Number(process.env.PROMPT_STUDIO_PORT || 7440);
const HOST = process.env.PROMPT_STUDIO_HOST || "127.0.0.1";

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
};

const sha256 = (text) => createHash("sha256").update(text, "utf8").digest("hex");

function sendJson(res, status, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(status, { "content-type": "application/json; charset=utf-8", "content-length": Buffer.byteLength(body) });
  res.end(body);
}

function readBody(req, limit = 4_000_000) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > limit) { reject(new Error("Request body too large")); req.destroy(); return; }
      chunks.push(chunk);
    });
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

// Resolve a user-supplied relative path inside one allow-listed root and reject
// traversal or symlink escapes (mirrors the runtime's bundle-boundary checks).
function resolveInside(root, relative) {
  if (!relative || path.isAbsolute(relative)) throw new Error("path must be bundle-relative");
  const parts = relative.split(/[\\/]/);
  if (parts.some((part) => part === ".." || part === "")) throw new Error("path must not contain traversal");
  const candidate = path.resolve(root, relative);
  const rel = path.relative(root, candidate);
  if (!rel || rel.startsWith("..") || path.isAbsolute(rel)) throw new Error("path escapes the prompt bundle");
  return candidate;
}

async function writeWithBackup(target, content, backupKey) {
  const existing = await fs.readFile(target, "utf8").catch(() => null);
  if (existing === null) throw new Error("refusing to create a new prompt file; edit an existing entry");
  if (existing === content) return { changed: false };
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const backupPath = path.join(BACKUP_ROOT, stamp, backupKey);
  await fs.mkdir(path.dirname(backupPath), { recursive: true });
  await fs.writeFile(backupPath, existing, "utf8");
  const tmp = `${target}.prompt-studio.tmp`;
  await fs.writeFile(tmp, content, "utf8");
  await fs.rename(tmp, target);
  return { changed: true, backupPath };
}

async function listContentGroups() {
  const dirents = await fs.readdir(PROMPT_ROOT, { withFileTypes: true });
  const groups = [];
  for (const dirent of dirents) {
    if (!dirent.isDirectory()) continue;
    const indexFile = path.join(PROMPT_ROOT, dirent.name, "index.json");
    let index;
    try { index = JSON.parse(await fs.readFile(indexFile, "utf8")); } catch { continue; }
    if (index.version !== 1 || !Array.isArray(index.sections)) continue;
    const entries = [];
    for (const raw of index.sections) {
      const id = String(raw.id ?? "");
      const file = String(raw.file ?? "");
      const status = raw.status === "reference-only" ? "reference-only" : "active";
      if (!id || !file) continue;
      let chars = 0;
      try { chars = (await fs.readFile(path.join(PROMPT_ROOT, dirent.name, file), "utf8")).length; } catch { chars = -1; }
      entries.push({ id, file, status, chars });
    }
    groups.push({ name: dirent.name, entries });
  }
  groups.sort((a, b) => a.name.localeCompare(b.name));
  return groups;
}

async function listFiles(dir, root) {
  const out = [];
  let dirents;
  try { dirents = await fs.readdir(dir, { withFileTypes: true }); } catch { return out; }
  for (const dirent of dirents) {
    const full = path.join(dir, dirent.name);
    if (dirent.isDirectory()) continue;
    if (!dirent.name.endsWith(".md") && !dirent.name.endsWith(".tpl")) continue;
    const chars = (await fs.readFile(full, "utf8")).length;
    out.push({ path: path.relative(root, full).split(path.sep).join("/"), chars });
  }
  return out.sort((a, b) => a.path.localeCompare(b.path));
}

async function listSztubuddy() {
  const result = { main: [], styles: [], modes: {}, contract: [] };
  result.main = await listFiles(path.join(Sztubuddy_ROOT, "main"), Sztubuddy_ROOT);
  result.styles = await listFiles(path.join(Sztubuddy_ROOT, "styles"), Sztubuddy_ROOT);
  result.contract = await listFiles(Sztubuddy_ROOT, Sztubuddy_ROOT);
  const modesDir = path.join(Sztubuddy_ROOT, "modes");
  let modeDirs = [];
  try { modeDirs = (await fs.readdir(modesDir, { withFileTypes: true })).filter((d) => d.isDirectory()).map((d) => d.name); } catch { /* none */ }
  for (const mode of modeDirs.sort()) {
    result.modes[mode] = await listFiles(path.join(modesDir, mode, "fragments"), Sztubuddy_ROOT);
  }
  return result;
}

// process.execPath is not always spawnable (Windows shims without an extension),
// so try the requested binary and transparently fall back to PATH-resolved node.
function spawnCompose(binary, input) {
  return new Promise((resolve) => {
    const child = spawn(binary, [COMPOSE_WORKER], { cwd: REPO_ROOT, stdio: ["pipe", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => { stdout += chunk; });
    child.stderr.on("data", (chunk) => { stderr += chunk; });
    child.on("error", (error) => resolve({ spawnError: error }));
    child.on("close", (code) => {
      if (code !== 0 && !stdout) return resolve({ status: 500, payload: { ok: false, error: stderr || `compose worker exited ${code}` } });
      try { resolve({ status: 200, payload: JSON.parse(stdout) }); }
      catch { resolve({ status: 500, payload: { ok: false, error: stderr || "compose worker produced invalid JSON" } }); }
    });
    child.stdin.end(JSON.stringify(input));
  });
}

async function runCompose(input) {
  const preferred = process.env.PROMPT_STUDIO_NODE || process.execPath;
  let result = await spawnCompose(preferred, input);
  if (result.spawnError && result.spawnError.code === "ENOENT" && preferred !== "node") {
    result = await spawnCompose("node", input);
  }
  if (result.spawnError) return { status: 500, payload: { ok: false, error: result.spawnError.message } };
  return result;
}

async function handleApi(req, res, url) {
  if (req.method === "GET" && url.pathname === "/api/state") {
    const [groups, Sztubuddy] = await Promise.all([listContentGroups(), listSztubuddy()]);
    return sendJson(res, 200, {
      repoRoot: REPO_ROOT,
      promptRoot: PROMPT_ROOT,
      SztubuddyRoot: Sztubuddy_ROOT,
      groups,
      Sztubuddy,
    });
  }

  if (req.method === "GET" && (url.pathname === "/api/content" || url.pathname === "/api/Sztubuddy")) {
    const isContent = url.pathname === "/api/content";
    const relative = isContent
      ? `${url.searchParams.get("group") ?? ""}/${url.searchParams.get("file") ?? ""}`
      : url.searchParams.get("path") ?? "";
    const root = isContent ? PROMPT_ROOT : Sztubuddy_ROOT;
    const target = resolveInside(root, relative);
    const content = await fs.readFile(target, "utf8");
    return sendJson(res, 200, { path: relative, content, chars: content.length, sha256: sha256(content) });
  }

  if (req.method === "PUT" && (url.pathname === "/api/content" || url.pathname === "/api/Sztubuddy")) {
    const body = JSON.parse(await readBody(req));
    if (typeof body.content !== "string") throw new Error("content must be a string");
    const isContent = url.pathname === "/api/content";
    const relative = isContent ? `${body.group ?? ""}/${body.file ?? ""}` : body.path ?? "";
    const root = isContent ? PROMPT_ROOT : Sztubuddy_ROOT;
    const target = resolveInside(root, relative);
    if (!target.endsWith(".md") && !target.endsWith(".tpl")) throw new Error("only .md and .tpl prompt files can be edited");
    if (body.expectedSha256) {
      const current = await fs.readFile(target, "utf8");
      if (sha256(current) !== body.expectedSha256) return sendJson(res, 409, { ok: false, error: "file changed on disk since it was loaded" });
    }
    const result = await writeWithBackup(target, body.content, relative);
    return sendJson(res, 200, { ok: true, changed: result.changed, backupPath: result.backupPath ?? null, chars: body.content.length, sha256: sha256(body.content) });
  }

  if (req.method === "POST" && url.pathname === "/api/compose") {
    const body = JSON.parse(await readBody(req));
    const { status, payload } = await runCompose(body);
    return sendJson(res, status, payload);
  }

  return sendJson(res, 404, { ok: false, error: `unknown endpoint ${req.method} ${url.pathname}` });
}

async function serveStatic(req, res, url) {
  const requested = url.pathname === "/" ? "/index.html" : url.pathname;
  const target = path.join(PUBLIC_DIR, path.normalize(requested).replace(/^([/\\])+/, ""));
  const rel = path.relative(PUBLIC_DIR, target);
  if (rel.startsWith("..") || path.isAbsolute(rel)) { res.writeHead(403); res.end("Forbidden"); return; }
  try {
    const content = await fs.readFile(target);
    res.writeHead(200, { "content-type": MIME[path.extname(target)] ?? "application/octet-stream", "content-length": content.length });
    res.end(content);
  } catch {
    res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    res.end("Not found");
  }
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);
  try {
    if (url.pathname.startsWith("/api/")) await handleApi(req, res, url);
    else await serveStatic(req, res, url);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (!res.headersSent) sendJson(res, 400, { ok: false, error: message });
    else res.end();
  }
});

server.listen(PORT, HOST, () => {
  process.stdout.write(`Prompt Studio running at http://${HOST}:${PORT}\n`);
  process.stdout.write(`  prompt root   : ${path.relative(REPO_ROOT, PROMPT_ROOT) || PROMPT_ROOT}\n`);
  process.stdout.write(`  Sztubuddy root: ${path.relative(REPO_ROOT, Sztubuddy_ROOT) || Sztubuddy_ROOT}\n`);
  process.stdout.write(`  backups       : ${path.relative(REPO_ROOT, BACKUP_ROOT) || BACKUP_ROOT}\n`);
});
