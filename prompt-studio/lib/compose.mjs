// Prompt Studio compose worker.
//
// Runs in a fresh child process on every request so the process-level prompt
// caches inside the runtime (Sztubuddy templates, per-group index cache) never
// serve stale text after an edit. It calls the REAL runtime functions from
// packages/runtime-ts/dist, so the preview is authoritative rather than a
// re-implementation of the composition rules.
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "..", "..");
const distDir = path.join(repoRoot, "packages", "runtime-ts", "dist");

const load = (name) => import(pathToFileURL(path.join(distDir, `${name}.js`)).href);

const { buildSystemPrompt, buildDynamicContext } = await load("prompt-loader");
const { runtimePromptEntries, dynamicRuntimePromptEntries } = await load("prompt-harness");
const { buildSztubuddyBase } = await load("Sztubuddy-resources");

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => { data += chunk; });
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

const raw = await readStdin();
const input = raw.trim() ? JSON.parse(raw) : {};

const workspaceRoot = input.workspaceRoot || repoRoot;
const role = input.role || "coder";
const context = {
  permissionMode: input.permissionMode || "normal",
  memoryEnabled: Boolean(input.memoryEnabled),
  toolNames: Array.isArray(input.tools) ? input.tools : [],
  taskText: input.taskText || "",
};
// The harness treats a present-but-empty interactionMode as an invalid mode, so
// only forward it when a real mode was chosen (mirrors the runtime, which omits it).
if (input.interactionMode) context.interactionMode = input.interactionMode;

const approxTokens = (text) => Math.round(text.length / 3.5);

try {
  const base = buildSztubuddyBase();
  const roleLine = `# Runtime context\n- Agent role: ${role}`;
  const staticBase = [base, roleLine].join("\n\n");
  const runtimeEntries = await runtimePromptEntries(context);
  const dynamicEntries = await dynamicRuntimePromptEntries(context);
  const systemPrompt = await buildSystemPrompt(workspaceRoot, role, context);
  const dynamicContext = await buildDynamicContext(workspaceRoot, context, []);

  process.stdout.write(JSON.stringify({
    ok: true,
    workspaceRoot,
    role,
    context,
    staticBase,
    runtimeEntries,
    staticSections: {
      SztubuddyBase: base,
      roleLine,
    },
    systemPrompt,
    dynamicEntries,
    dynamicContext,
    metrics: {
      SztubuddyBaseChars: base.length,
      staticBaseChars: staticBase.length,
      runtimeEntriesChars: runtimeEntries.reduce((sum, entry) => sum + entry.length, 0),
      systemPromptChars: systemPrompt.length,
      dynamicContextChars: dynamicContext.length,
      totalChars: systemPrompt.length + dynamicContext.length,
      systemPromptTokens: approxTokens(systemPrompt),
      dynamicContextTokens: approxTokens(dynamicContext),
      totalTokens: approxTokens(systemPrompt) + approxTokens(dynamicContext),
    },
  }));
} catch (error) {
  process.stdout.write(JSON.stringify({ ok: false, error: error instanceof Error ? error.message : String(error) }));
  process.exitCode = 1;
}
