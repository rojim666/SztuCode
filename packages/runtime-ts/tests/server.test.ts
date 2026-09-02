import assert from "node:assert/strict";
import net from "node:net";
import test from "node:test";
import { execFile } from "node:child_process";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { RuntimeServer } from "../src/server.js";

const execFileAsync = promisify(execFile);

function restoreEnv(name: string, value: string | undefined): void {
  if (value === undefined) delete process.env[name];
  else process.env[name] = value;
}

async function rpc(socket: net.Socket, method: string, params: Record<string, unknown> = {}): Promise<any> {
  const id = `${Date.now()}-${Math.random()}`;
  return new Promise((resolve, reject) => {
    let buffer = "";
    const onData = (chunk: string) => { buffer += chunk; const index = buffer.indexOf("\n"); if (index < 0) return; const message = JSON.parse(buffer.slice(0, index)); socket.off("data", onData); if (message.error) reject(Object.assign(new Error(message.error.message), { code: message.error.code })); else resolve(message.result); };
    socket.on("data", onData); socket.write(`${JSON.stringify({ jsonrpc: "2.0", id, method, params })}\n`);
  });
}

test("runtime server exposes JSON-RPC and classified errors over NDJSON", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-runtime-test-")); const previous = process.env.SZTU_DATA_DIR; process.env.SZTU_DATA_DIR = root;
  const server = new RuntimeServer("127.0.0.1", 0); const address = await server.listen(); const port = Number(address.split(":").at(-1)); const socket = net.createConnection({ host: "127.0.0.1", port }); await new Promise<void>((resolve, reject) => { socket.once("connect", () => resolve()); socket.once("error", reject); });
  try {
    const pong = await rpc(socket, "core.ping", { client: "test" }); assert.equal(pong.server_version, "ts-0.2.0");
    await assert.rejects(() => rpc(socket, "session.send_message", { session_id: "missing", content: "x" }), (error: any) => error.code === -32004);
    await assert.rejects(() => rpc(socket, "unknown.method"), (error: any) => error.code === -32601);
  } finally { socket.destroy(); await server.close(); restoreEnv("SZTU_DATA_DIR", previous); await rm(root, { recursive: true, force: true }); }
});

test("runtime server traces IPC traffic and reports the actual bound address", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-runtime-trace-"));
  const previousData = process.env.SZTU_DATA_DIR; const previousTrace = process.env.SZTU_TRACE_FILE;
  const traceFile = path.join(root, "structured.jsonl"); process.env.SZTU_DATA_DIR = root; process.env.SZTU_TRACE_FILE = traceFile;
  const server = new RuntimeServer("127.0.0.1", 0);
  let startedAddress = "";
  server.events.subscribe((event) => { if (event.type === "core.started") startedAddress = event.listen_addr; });
  const address = await server.listen(); const port = Number(address.split(":").at(-1));
  const socket = net.createConnection({ host: "127.0.0.1", port }); await new Promise<void>((resolve, reject) => { socket.once("connect", resolve); socket.once("error", reject); });
  try {
    assert.equal(startedAddress, address); assert.notEqual(port, 0);
    await rpc(socket, "core.ping", { client: "trace-test" });
  } finally {
    socket.destroy(); await server.close(); restoreEnv("SZTU_DATA_DIR", previousData); restoreEnv("SZTU_TRACE_FILE", previousTrace);
  }
  try {
    const rows = (await readFile(traceFile, "utf8")).trim().split(/\r?\n/).map((line) => JSON.parse(line));
    assert.ok(rows.some((row) => row.direction === "CORE" && row.kind === "event" && row.data.type === "core.started"));
    assert.ok(rows.some((row) => row.direction === "CLIENT→CORE" && row.kind === "command" && row.data.method === "core.ping"));
    assert.ok(rows.some((row) => row.direction === "CORE→CLIENT" && row.kind === "response" && row.data.result.server_version === "ts-0.2.0"));
  } finally { await rm(root, { recursive: true, force: true }); }
});

test("runtime server rejects oversized NDJSON frames", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-runtime-frame-")); const previous = process.env.SZTU_DATA_DIR; process.env.SZTU_DATA_DIR = root;
  const server = new RuntimeServer("127.0.0.1", 0, undefined, 1024); const address = await server.listen(); const port = Number(address.split(":").at(-1));
  const socket = net.createConnection({ host: "127.0.0.1", port }); await new Promise<void>((resolve, reject) => { socket.once("connect", resolve); socket.once("error", reject); });
  try {
    const response = new Promise<any>((resolve) => { let data = ""; socket.on("data", (chunk: Buffer) => { data += chunk.toString("utf8"); if (data.includes("\n")) resolve(JSON.parse(data.slice(0, data.indexOf("\n")))); }); });
    socket.write("x".repeat(1025));
    const message = await response; assert.equal(message.error.code, -32600); assert.equal(message.error.message, "Request too large");
  } finally { socket.destroy(); await server.close(); restoreEnv("SZTU_DATA_DIR", previous); await rm(root, { recursive: true, force: true }); }
});

test("runtime server shutdown aborts active agent runs", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-runtime-shutdown-")); const previous = process.env.SZTU_DATA_DIR; process.env.SZTU_DATA_DIR = root;
  let aborted = false; let entered!: () => void; const started = new Promise<void>((resolve) => { entered = resolve; });
  const provider = { complete: async (_messages: unknown, _tools: unknown, signal?: AbortSignal) => new Promise<never>((_resolve, reject) => { entered(); signal?.addEventListener("abort", () => { aborted = true; reject(signal.reason); }, { once: true }); }) };
  const server = new RuntimeServer("127.0.0.1", 0, provider as never); await server.listen();
  try {
    server.runs.start("wait forever"); await started; await server.close(); assert.equal(aborted, true);
  } finally { restoreEnv("SZTU_DATA_DIR", previous); await rm(root, { recursive: true, force: true }); }
});

test("workflow runs can be cancelled and queried through the shared run controls", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-workflow-cancel-server-")); const previous = process.env.SZTU_DATA_DIR; process.env.SZTU_DATA_DIR = root;
  const provider = { complete: async (_messages: unknown, _tools: unknown, signal?: AbortSignal) => new Promise<never>((_resolve, reject) => { signal?.addEventListener("abort", () => reject(signal.reason), { once: true }); }) };
  const server = new RuntimeServer("127.0.0.1", 0, provider as never); await server.listen();
  try {
    let workflowRunId = "";
    const started = new Promise<void>((resolve) => { server.events.subscribe((event) => { if (event.type === "workflow.started") { workflowRunId = event.run_id; resolve(); } }); });
    const graph = { workflow_id: "cancel-rpc", goal: "cancel me", planner_summary: "one task", tasks: [{ id: "plan", title: "plan", description: "wait", owner: "planner", dependencies: [], completion_criteria: ["done"], allowed_paths: [], depth: 0, token_budget: 0, time_budget_s: 0, max_retries: 0 }] };
    const dispatch = (server as any).dispatch.bind(server) as (request: Record<string, unknown>, socket: net.Socket) => Promise<any>;
    const workflow = dispatch({ jsonrpc: "2.0", id: "workflow", method: "workflow.run", params: { graph } }, {} as net.Socket);
    await started;
    const cancel = await dispatch({ jsonrpc: "2.0", id: "cancel", method: "run.cancel", params: { run_id: workflowRunId } }, {} as net.Socket);
    assert.equal(cancel.result.status, "cancelling");
    assert.equal((await workflow).result.status, "cancelled");
    const current = await dispatch({ jsonrpc: "2.0", id: "get", method: "run.get", params: { run_id: workflowRunId } }, {} as net.Socket);
    assert.equal(current.result.status, "cancelled");
  } finally { await server.close(); restoreEnv("SZTU_DATA_DIR", previous); await rm(root, { recursive: true, force: true }); }
});

test("session.fork clones history into a new session and leaves the original intact", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-runtime-fork-test-")); const previous = process.env.SZTU_DATA_DIR; process.env.SZTU_DATA_DIR = root;
  const server = new RuntimeServer("127.0.0.1", 0);
  const address = await server.listen(); const port = Number(address.split(":").at(-1)); const socket = net.createConnection({ host: "127.0.0.1", port }); await new Promise<void>((resolve, reject) => { socket.once("connect", () => resolve()); socket.once("error", reject); });
  try {
    const created = await rpc(socket, "session.create", { mode: "chat", title: "original" });
    const sessionId = created.session_id;
    await server.sessions.appendMessage(sessionId, { role: "user", content: "first user turn" });
    await server.sessions.appendMessage(sessionId, { role: "assistant", content: "first assistant turn" });

    const forked = await rpc(socket, "session.fork", { session_id: sessionId });
    const forkId = forked.session.session_id;
    assert.notEqual(forkId, sessionId);
    assert.equal(forked.session.status, "waiting_for_input");
    assert.equal(forked.session.workspace_id, null);
    assert.match(forked.session.title, /Fork of original/);

    const forkHistory = await rpc(socket, "session.history", { session_id: forkId });
    assert.equal(forkHistory.messages.length, 2);
    assert.equal(forkHistory.messages[0].role, "user");
    assert.equal(forkHistory.messages[0].content, "first user turn");
    assert.equal(forkHistory.messages[1].role, "assistant");
    assert.equal(forkHistory.messages[1].content, "first assistant turn");

    // 原会话历史不受 fork 影响
    const originalHistory = await rpc(socket, "session.history", { session_id: sessionId });
    assert.equal(originalHistory.messages.length, 2);
    assert.equal(originalHistory.messages[0].content, "first user turn");

    // fork 不存在的源 session 报错
    await assert.rejects(() => rpc(socket, "session.fork", { session_id: "missing" }));
  } finally { socket.destroy(); await server.close(); restoreEnv("SZTU_DATA_DIR", previous); await rm(root, { recursive: true, force: true }); }
});

test("manual session.compact uses provider summary and persists continuation messages", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-runtime-compact-test-")); const previous = process.env.SZTU_DATA_DIR; process.env.SZTU_DATA_DIR = root;
  let compactionPrompt = "";
  const server = new RuntimeServer("127.0.0.1", 0, {
    complete: async (messages) => {
      compactionPrompt = String(messages[0]?.content ?? "");
      return { text: "Goal\nKeep the API contract.\nProgress\nEarlier work is complete.\nDecisions\nUse the TypeScript runtime.\nOpen Issues\nNone known.\nNext Steps\nContinue with the current task.", tool_calls: [], stop_reason: "end_turn", usage: { output_tokens: 30 } };
    },
  });
  const address = await server.listen(); const port = Number(address.split(":").at(-1)); const socket = net.createConnection({ host: "127.0.0.1", port }); await new Promise<void>((resolve, reject) => { socket.once("connect", () => resolve()); socket.once("error", reject); });
  try {
    const created = await rpc(socket, "session.create", { mode: "chat" });
    for (let index = 0; index < 12; index += 1) await server.sessions.appendMessage(created.session_id, { role: index % 2 ? "assistant" : "user", content: `message ${index} with enough detail to make the old context worth summarizing` });
    const result = await rpc(socket, "session.compact", { session_id: created.session_id, focus: "preserve the API contract" });
    assert.equal(result.used_model, true);
    assert.ok(result.removed_messages > 0);
    assert.match(compactionPrompt, /preserve the API contract/);
    const history = await rpc(socket, "session.history", { session_id: created.session_id });
    assert.match(history.messages[0].content, /This session is being continued from a previous conversation/);
    const modelHistory = JSON.parse(await readFile(path.join(root, "sessions", created.session_id, "context.json"), "utf8"));
    assert.ok(modelHistory.some((message: any) => typeof message.content === "string" && message.content.includes("This session is being continued")));
    const summaryFiles = (await import("node:fs/promises")).readdir(path.join(root, "sessions", created.session_id));
    assert.ok((await summaryFiles).some((name) => name.startsWith("summary_") && name.endsWith(".md")));
  } finally { socket.destroy(); await server.close(); restoreEnv("SZTU_DATA_DIR", previous); await rm(root, { recursive: true, force: true }); }
});

test("desktop workspace, provider, file preview, and git contracts remain complete", async () => {
  const dataRoot = await mkdtemp(path.join(os.tmpdir(), "sztu-runtime-contract-data-")); const projectRoot = await mkdtemp(path.join(os.tmpdir(), "sztu-runtime-contract-project-")); const previous = process.env.SZTU_DATA_DIR; process.env.SZTU_DATA_DIR = dataRoot;
  await mkdir(path.join(projectRoot, ".sztu", "skills", "contract-skill"), { recursive: true });
  await writeFile(path.join(projectRoot, ".sztu", "skills", "contract-skill", "SKILL.md"), "---\nname: contract-skill\ndescription: Contract fixture\n---\nUse the contract fixture.", "utf8");
  const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=", "base64"); await writeFile(path.join(projectRoot, "pixel.png"), png);
  await execFileAsync("git", ["init"], { cwd: projectRoot }); await execFileAsync("git", ["config", "user.name", "Sztu Test"], { cwd: projectRoot }); await execFileAsync("git", ["config", "user.email", "sztu@example.test"], { cwd: projectRoot }); await writeFile(path.join(projectRoot, "tracked.txt"), "tracked\n", "utf8"); await execFileAsync("git", ["add", "tracked.txt"], { cwd: projectRoot }); await execFileAsync("git", ["commit", "-m", "initial"], { cwd: projectRoot });
  const server = new RuntimeServer("127.0.0.1", 0); const address = await server.listen(); const port = Number(address.split(":").at(-1)); const socket = net.createConnection({ host: "127.0.0.1", port }); await new Promise<void>((resolve, reject) => { socket.once("connect", () => resolve()); socket.once("error", reject); });
  try {
    const opened = await rpc(socket, "workspace.open", { path: projectRoot }); const workspaceId = opened.workspace.workspace_id;
    await rpc(socket, "workspace.archive", { workspace_id: workspaceId }); const listed = await rpc(socket, "workspace.list"); assert.equal(listed.workspaces.find((item: any) => item.workspace_id === workspaceId)?.archived, true);
    const preview = await rpc(socket, "file.read", { workspace_id: workspaceId, path: "pixel.png" }); assert.equal(preview.binary, true); assert.equal(preview.mime_type, "image/png"); assert.equal(preview.media_base64, png.toString("base64"));
    const skills = await rpc(socket, "skill.list", { workspace_id: workspaceId }); assert.ok(skills.skills.some((item: any) => item.name === "contract-skill")); const status = await rpc(socket, "provider.status"); assert.ok(Array.isArray(status.skills)); assert.ok(status.skills.length > 0);
    const history = await rpc(socket, "git.history", { workspace_id: workspaceId }); assert.equal(history.commits[0].is_head, true); assert.ok(history.commits[0].refs.some((item: any) => item.kind === "head"));
  } finally { socket.destroy(); await server.close(); restoreEnv("SZTU_DATA_DIR", previous); await rm(dataRoot, { recursive: true, force: true }); await rm(projectRoot, { recursive: true, force: true }); }
});

test("session lifecycle and model profiles preserve desktop invariants", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-runtime-state-test-")); const previous = process.env.SZTU_DATA_DIR; process.env.SZTU_DATA_DIR = root;
  const server = new RuntimeServer("127.0.0.1", 0); const address = await server.listen(); const port = Number(address.split(":").at(-1)); const socket = net.createConnection({ host: "127.0.0.1", port }); await new Promise<void>((resolve, reject) => { socket.once("connect", () => resolve()); socket.once("error", reject); });
  try {
    const created = await rpc(socket, "session.create", { mode: "chat" }); const sessionId = created.session_id;
    await rpc(socket, "session.pin", { session_id: sessionId, pinned: true }); const archived = await rpc(socket, "session.archive", { session_id: sessionId }); assert.equal(archived.session.archived, true); assert.equal(archived.session.pinned, false);
    await assert.rejects(() => rpc(socket, "session.pin", { session_id: sessionId, pinned: true }), /archived session cannot be pinned/);
    await rpc(socket, "session.close", { session_id: sessionId }); const resumed = await rpc(socket, "session.resume", { session_id: sessionId }); assert.equal(resumed.session.status, "waiting_for_input");

    const modeEvents: any[] = []; server.events.subscribe((event) => { if (event.type === "permission.mode_changed") modeEvents.push(event); });
    const settingsUpdate = await rpc(socket, "settings.update", { permission_mode: "auto" }); assert.deepEqual(settingsUpdate.updated, ["permission_mode"]); assert.deepEqual(modeEvents.map((event) => [event.old_mode, event.new_mode]), [["normal", "auto"]]);
    const unchanged = await rpc(socket, "settings.update", { permission_mode: "auto" }); assert.deepEqual(unchanged.updated, []); assert.equal(modeEvents.length, 1);
    const linked = await rpc(socket, "settings.update", { provider: "anthropic", unknown_field: "ignored" }); assert.equal(linked.settings.provider, "anthropic"); assert.equal(linked.settings.api_format, "anthropic_messages"); assert.deepEqual(linked.updated, ["provider"]);
    const formatWins = await rpc(socket, "settings.update", { provider: "anthropic", api_format: "openai_responses" }); assert.equal(formatWins.settings.provider, "openai"); assert.equal(formatWins.settings.api_format, "openai_responses"); assert.deepEqual(formatWins.updated, ["api_format"]);
    await assert.rejects(() => rpc(socket, "settings.update", { max_retries: 11 }), (error: any) => error.code === -32602);
    // 内置 opencode Zen 免 key profile：列表包含 builtin 条目且视为已就绪，不允许删除
    const initialModels = await rpc(socket, "provider.model_list"); assert.ok(Array.isArray(initialModels.models));
    const zen = initialModels.models.find((item: any) => item.id === "builtin-opencode-zen-mimo-v2.5-free"); assert.ok(zen); assert.equal(zen.base_url, "https://opencode.ai/zen/v1"); assert.equal(zen.has_api_key, true); assert.equal(zen.builtin, true);
    await assert.rejects(() => rpc(socket, "provider.model_delete", { model_id: zen.id }), /builtin profiles cannot be deleted/);

    const shared = { vendor: "Test", provider: "openai", api_format: "openai_chat_completions", model: "same-model", base_url: "https://example.test/v1", api_key: "secret", context_window: 16_000, max_output_tokens: 1024, temperature: null, top_p: null, reasoning_effort: "", timeout_s: 30, max_retries: 1, cache_control: true };
    const first = await rpc(socket, "provider.model_save", { ...shared, name: "First" }); const firstId = first.models.find((item: any) => item.name === "First").id;
    // 切换模型 profile 不得重置权限模式；配置了 api_key 后 provider 应就绪
    const reselected = await rpc(socket, "provider.model_select", { model_id: firstId }); assert.equal(reselected.settings.permission_mode, "auto"); const status = await rpc(socket, "provider.status"); assert.equal(status.ready_for_next_run, true);
    const second = await rpc(socket, "provider.model_save", { ...shared, name: "Second" }); const secondId = second.models.find((item: any) => item.name === "Second").id; assert.deepEqual(second.models.filter((item: any) => item.is_current).map((item: any) => item.id), [secondId]);
    await assert.rejects(() => rpc(socket, "provider.model_delete", { model_id: secondId }), /current model profile cannot be deleted/); const deleted = await rpc(socket, "provider.model_delete", { model_id: firstId }); assert.ok(!deleted.models.some((item: any) => item.id === firstId));
  } finally { socket.destroy(); await server.close(); restoreEnv("SZTU_DATA_DIR", previous); await rm(root, { recursive: true, force: true }); }
});

test("workspace.tree lists direct children for max_depth=0 and skips hidden dirs", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-tree-test-"));
  const data = path.join(root, "data");
  const previous = process.env.SZTU_DATA_DIR; process.env.SZTU_DATA_DIR = data;
  try {
    const project = path.join(root, "project");
    await mkdir(path.join(project, "src"), { recursive: true });
    await mkdir(path.join(project, "node_modules", "pkg"), { recursive: true });
    await writeFile(path.join(project, "a.txt"), "a");
    await writeFile(path.join(project, ".hidden"), "h");
    await writeFile(path.join(project, "src", "index.ts"), "export {};");

    const server = new RuntimeServer("127.0.0.1", 0); const address = await server.listen(); const port = Number(address.split(":").at(-1));
    const socket = net.createConnection({ host: "127.0.0.1", port }); await new Promise<void>((resolve, reject) => { socket.once("connect", () => resolve()); socket.once("error", reject); });
    try {
      const opened = await rpc(socket, "workspace.open", { path: project });
      const workspaceId = opened.workspace.workspace_id;

      // max_depth=0：只列直接子项，目录不预取 children（由前端懒加载）
      const shallow = await rpc(socket, "workspace.tree", { workspace_id: workspaceId, path: "", max_depth: 0 });
      assert.deepEqual(shallow.nodes.map((node: any) => [node.name, node.kind]), [["src", "directory"], ["a.txt", "file"]]);
      assert.equal(shallow.nodes.find((node: any) => node.name === "src").children, undefined);

      // max_depth=2：目录 children 递归展开
      const deep = await rpc(socket, "workspace.tree", { workspace_id: workspaceId, path: "", max_depth: 2 });
      const srcDeep = deep.nodes.find((node: any) => node.name === "src");
      assert.deepEqual(srcDeep.children.map((node: any) => [node.name, node.kind]), [["index.ts", "file"]]);
    } finally { socket.destroy(); await server.close(); }
  } finally { restoreEnv("SZTU_DATA_DIR", previous); await rm(root, { recursive: true, force: true }); }
});
