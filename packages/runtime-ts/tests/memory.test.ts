import assert from "node:assert/strict";
import test from "node:test";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createMemoryTools, loadMemoryCatalog, MemoryCatalog } from "../src/memory.js";
import { SessionStore } from "../src/session-store.js";
import { Workspace } from "../src/workspace.js";
import type { Tool, ToolResult } from "../src/tools.js";

// 按名称调用工具，未注册直接断言失败
const invoke = async (tools: Tool[], name: string, params: Record<string, unknown>, root: string): Promise<ToolResult> => {
  const tool = tools.find((candidate) => candidate.name === name);
  assert.ok(tool, `tool not registered: ${name}`);
  return tool.invoke(params, { workspace: new Workspace(root) });
};
// 临时 home/workspace/session fixture：loadMemoryCatalog 的全局层取自 USERPROFILE，重定向到临时目录隔离
const fixture = async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), "sztu-mem-home-"));
  const workspace = await mkdtemp(path.join(os.tmpdir(), "sztu-mem-ws-"));
  const sessionRoot = await mkdtemp(path.join(os.tmpdir(), "sztu-mem-sess-"));
  const sessions = new SessionStore(sessionRoot);
  const session = await sessions.create();
  const previousHome = process.env.USERPROFILE;
  process.env.USERPROFILE = home;
  try { return { home, workspace, sessionRoot, sessions, session, catalog: await loadMemoryCatalog(workspace, sessions, session.id) }; }
  finally { process.env.USERPROFILE = previousHome; }
};
const cleanup = (...dirs: string[]) => Promise.all(dirs.map((dir) => rm(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 })));

test("scored search ranks heading hits above body hits and reports all matches", () => {
  const content = ["plain redis alpha line", "another redis beta line", "filler one", "filler two", "## Redis deep dive", "details about eviction"].join("\n");
  const catalog = new MemoryCatalog([{ name: "project", source: ".sztu/context.md", content }]);
  const output = catalog.read("project", "redis", 0, 4_000);
  assert.ok(output.indexOf("Redis deep dive") >= 0 && output.indexOf("Redis deep dive") < output.indexOf("plain redis alpha line"), "heading hit (x2 weight) must rank first");
  assert.match(output, /\[memory search: "redis", matches 1-3\/3, end\]/);
});

test("phrase match and conjunction bonuses outrank scattered word hits", () => {
  const content = ["beta alpha mismatch", "only alpha here", "f2", "f3", "the alpha beta phrase"].join("\n");
  const catalog = new MemoryCatalog([{ name: "project", source: ".sztu/context.md", content }]);
  const output = catalog.read("project", "alpha beta", 0, 4_000);
  assert.ok(output.indexOf("the alpha beta phrase") < output.indexOf("beta alpha mismatch"), "full phrase (+3) plus all-words (+2) must rank first");
  assert.ok(output.indexOf("beta alpha mismatch") < output.indexOf("only alpha here"), "all-words conjunction (+2) must outrank a single-word hit");
});

test("CJK queries keep contiguous runs as whole words and drop sub-2-char tokens", () => {
  const catalog = new MemoryCatalog([{ name: "project", source: ".sztu/context.md", content: "记忆系统支持评分检索\n普通行" }]);
  assert.match(catalog.read("project", "记忆系统", 0, 400), /记忆系统支持评分检索/);
  assert.equal(catalog.read("project", "记", 0, 400), 'No matches for "记".');
});

test("search without hits returns an explicit no-match message", () => {
  const catalog = new MemoryCatalog([{ name: "project", source: ".sztu/context.md", content: "# Build\nuse npm test" }]);
  assert.equal(catalog.read("project", "zzz", 0, 100), 'No matches for "zzz".');
  assert.equal(catalog.read("project", "x", 0, 100), 'No matches for "x".');
});

test("search pagination walks scored hit blocks via next_offset", () => {
  const catalog = new MemoryCatalog([{ name: "session", source: "session/notes.md", content: ["hit one", "hit two", "hit three"].join("\n") }]);
  assert.match(catalog.read("session", "hit", 0, 10), /next_offset=1/);
  assert.match(catalog.read("session", "hit", 1, 4_000), /\[memory search: "hit", matches 2-3\/3, end\]/);
});

test("memory_read without query returns the heading TOC with char count", () => {
  const catalog = new MemoryCatalog([{ name: "project", source: ".sztu/context.md", content: "# Build\nsecret\n## Tests\nnpm test" }], 10);
  const toc = catalog.read("project");
  assert.match(toc, /- Build/);
  assert.match(toc, /- Tests/);
  assert.match(toc, /\d+ chars/);
  assert.doesNotMatch(toc, /secret/);
  assert.match(catalog.read("project", "", 1, 20), /\[memory page: project, chars 1:\d+\/\d+, next_offset=\d+\]/);
});

test("note_save followed by memory_read sees fresh session notes within one run", async () => {
  const { workspace, sessionRoot, sessions, session, catalog, home } = await fixture();
  try {
    const tools = createMemoryTools(catalog, sessions, session.id, "run-live");
    const saved = await invoke(tools, "note_save", { content: "Prefer PostgreSQL for analytics" }, workspace);
    assert.match(saved.output, /saved \(note-[a-f0-9]+\)/);
    const read = await invoke(tools, "memory_read", { layer: "session", query: "PostgreSQL" }, workspace);
    assert.equal(read.ok, true);
    assert.match(read.output, /Prefer PostgreSQL for analytics/);
  } finally { await cleanup(home, workspace, sessionRoot); }
});

test("memory_read sees external edits to project context.md without a restart", async () => {
  const { workspace, sessions, session, catalog, home } = await fixture();
  try {
    const tools = createMemoryTools(catalog, sessions, session.id, "run-live");
    await mkdir(path.join(workspace, ".sztu"), { recursive: true });
    await writeFile(path.join(workspace, ".sztu", "context.md"), "# Ops\nKubernetes rollout on Fridays\n", "utf8");
    const read = await invoke(tools, "memory_read", { layer: "project", query: "Kubernetes" }, workspace);
    assert.equal(read.ok, true);
    assert.match(read.output, /Kubernetes rollout on Fridays/);
  } finally { await cleanup(home, workspace); }
});

test("memory_consolidate appends active notes once and skips duplicates by note id", async () => {
  const { workspace, sessions, session, catalog, home } = await fixture();
  try {
    const tools = createMemoryTools(catalog, sessions, session.id, "run-consolidate");
    const first = await invoke(tools, "note_save", { content: "Use TypeScript strict mode" }, workspace);
    await invoke(tools, "note_save", { content: "Deploy via GitHub Actions" }, workspace);
    const consolidated = await invoke(tools, "memory_consolidate", {}, workspace);
    assert.equal(consolidated.ok, true);
    assert.equal(consolidated.output, "Consolidated 2 note(s) into project context (0 skipped as duplicates).");
    const contextFile = path.join(workspace, ".sztu", "context.md");
    const text = await readFile(contextFile, "utf8");
    assert.match(text, /## Consolidated notes \(\d{4}-\d{2}-\d{2}\)/);
    assert.match(text, /Use TypeScript strict mode/);
    assert.match(text, /Deploy via GitHub Actions/);
    const again = await invoke(tools, "memory_consolidate", {}, workspace);
    assert.equal(again.output, "Consolidated 0 note(s) into project context (2 skipped as duplicates).");
    assert.equal(await readFile(contextFile, "utf8"), text);
    await invoke(tools, "note_save", { content: "Rotate API keys quarterly" }, workspace);
    await invoke(tools, "memory_consolidate", {}, workspace);
    const finalText = await readFile(contextFile, "utf8");
    assert.equal(finalText.match(/## Consolidated notes \(/g)?.length, 1, "same-day consolidation reuses one section");
    assert.match(finalText, /Rotate API keys quarterly/);
    assert.match(first.output, /note-[a-f0-9]+/);
  } finally { await cleanup(home, workspace); }
});

test("readNotes keeps multi-line note bodies intact", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-mem-multiline-"));
  try {
    const sessions = new SessionStore(root); const session = await sessions.create();
    await sessions.appendNote(session.id, "line one\nline two\nline three", "run-ml");
    assert.match(await sessions.readNotes(session.id), /line one\nline two\nline three/);
  } finally { await cleanup(root); }
});

test("memory_consolidate without active notes succeeds with a hint", async () => {
  const { workspace, sessions, session, catalog, home } = await fixture();
  try {
    const tools = createMemoryTools(catalog, sessions, session.id, "run-empty");
    const result = await invoke(tools, "memory_consolidate", {}, workspace);
    assert.equal(result.ok, true);
    assert.match(result.output, /no active/i);
  } finally { await cleanup(home, workspace); }
});

test("note_save and note_update reject content above 20000 chars", async () => {
  const { workspace, sessions, session, catalog, home } = await fixture();
  try {
    const tools = createMemoryTools(catalog, sessions, session.id, "run-limit");
    const before = (await sessions.noteBlocks(session.id)).length;
    const tooLarge = await invoke(tools, "note_save", { content: "x".repeat(20_001) }, workspace);
    assert.equal(tooLarge.ok, false);
    assert.match(tooLarge.error ?? "", /note too large \(>20000 chars\)/);
    assert.equal((await sessions.noteBlocks(session.id)).length, before);
    const saved = await invoke(tools, "note_save", { content: "small note" }, workspace);
    const noteId = saved.output.match(/note-[a-f0-9]+/)?.[0];
    assert.ok(noteId);
    const update = await invoke(tools, "note_update", { note_id: noteId, content: "y".repeat(20_001) }, workspace);
    assert.equal(update.ok, false);
    assert.match(update.error ?? "", /note too large \(>20000 chars\)/);
  } finally { await cleanup(home, workspace); }
});

test("notes.md trims oldest archived blocks at the 512KB cap and never removes active notes", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-mem-cap-"));
  try {
    const sessions = new SessionStore(root); const session = await sessions.create();
    for (let index = 0; index < 20; index += 1) {
      const noteId = await sessions.appendNote(session.id, `old-fact-${index} ${"x".repeat(19_000)}`, "run-cap");
      assert.ok(await sessions.updateNote(session.id, noteId, `new-fact-${index} ${"y".repeat(19_000)}`, "run-cap"));
    }
    const raw = await readFile(path.join(root, session.id, "notes.md"), "utf8");
    assert.ok(Buffer.byteLength(raw, "utf8") <= 512 * 1024, "notes.md must stay under the 512KB cap");
    assert.ok(!raw.includes("old-fact-0"), "oldest archived blocks are trimmed first");
    for (let index = 0; index < 20; index += 1) assert.ok(raw.includes(`new-fact-${index}`), `active note ${index} must survive trimming`);
  } finally { await cleanup(root); }
});

test("consolidation drops the oldest consolidated section when project context exceeds 256KB", async () => {
  const { workspace, sessions, session, catalog, home } = await fixture();
  try {
    const contextFile = path.join(workspace, ".sztu", "context.md");
    await mkdir(path.dirname(contextFile), { recursive: true });
    const filler = `## Consolidated notes (2000-01-01)\n${"- filler entry padding line\n".repeat(9_500)}`;
    await writeFile(contextFile, `# Project\n\nkeep me\n\n${filler}\n`, "utf8");
    const tools = createMemoryTools(catalog, sessions, session.id, "run-context-cap");
    await invoke(tools, "note_save", { content: "consolidated survivor fact" }, workspace);
    const consolidated = await invoke(tools, "memory_consolidate", {}, workspace);
    assert.equal(consolidated.ok, true);
    const after = await readFile(contextFile, "utf8");
    assert.ok(Buffer.byteLength(after, "utf8") <= 256 * 1024, "project context.md must stay under 256KB");
    assert.ok(!after.includes("filler entry"), "oldest consolidated section is removed wholesale");
    assert.match(after, /keep me/);
    assert.match(after, /consolidated survivor fact/);
  } finally { await cleanup(home, workspace); }
});
