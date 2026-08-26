import assert from "node:assert/strict";
import { createServer, type Server as HttpServer } from "node:http";
import net from "node:net";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";
import { spawn, type ChildProcess } from "node:child_process";
import { DaemonClient } from "@sztucode/client";
import { createTcpTransportFactory } from "@sztucode/client/tcp";
import type { RuntimeEvent } from "@sztucode/protocol";

const execFileAsync = promisify(execFile);
const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

type WireEvent = RuntimeEvent & { [key: string]: unknown };
type RpcResult = Record<string, any>;

interface DiagnosticContext { requestId?: string; sessionId?: string; runId?: string }

function diagnosticFailure(message: string, context: DiagnosticContext = {}, cause?: unknown): Error {
  const ids = [`request_id=${context.requestId ?? "n/a"}`, `session_id=${context.sessionId ?? "n/a"}`, `run_id=${context.runId ?? "n/a"}`].join(" ");
  const suffix = cause ? ` cause=${cause instanceof Error ? cause.stack ?? cause.message : String(cause)}` : "";
  return new Error(`[migration-validation] ${message} ${ids}${suffix}`);
}

function check(value: unknown, message: string, context: DiagnosticContext = {}): asserts value {
  if (!value) throw diagnosticFailure(message, context);
}

class LegacyRpcClient {
  private socket?: net.Socket;
  private buffer = "";
  private sequence = 0;
  private readonly pending = new Map<string, { resolve: (value: RpcResult) => void; reject: (error: Error) => void }>();
  readonly events: WireEvent[] = [];
  private readonly eventWaiters: Array<{ predicate: (event: WireEvent) => boolean; resolve: (event: WireEvent) => void; timer: ReturnType<typeof setTimeout> }> = [];

  constructor(private readonly port: number) {}

  async connect(): Promise<void> {
    this.socket = net.createConnection({ host: "127.0.0.1", port: this.port });
    this.socket.setEncoding("utf8");
    this.socket.on("data", (chunk: string) => this.receive(chunk));
    this.socket.on("close", () => this.rejectAll(new Error("legacy daemon connection closed")));
    await new Promise<void>((resolve, reject) => { this.socket!.once("connect", resolve); this.socket!.once("error", reject); });
  }

  async request(method: string, params: Record<string, unknown> = {}, context: DiagnosticContext = {}): Promise<RpcResult> {
    const socket = this.socket;
    if (!socket || socket.destroyed) throw diagnosticFailure(`legacy request ${method} on a closed socket`, context);
    const id = `legacy-${++this.sequence}`;
    const promise = new Promise<RpcResult>((resolve, reject) => this.pending.set(id, { resolve, reject }));
    socket.write(`${JSON.stringify({ jsonrpc: "2.0", id, method, params })}\n`);
    try { return await promise; }
    catch (error) { throw diagnosticFailure(`legacy RPC ${method} failed`, { ...context, requestId: id }, error); }
  }

  async subscribe(topics = ["*"]): Promise<void> { await this.request("event.subscribe", { topics, scope: "global" }); }

  async waitFor(predicate: (event: WireEvent) => boolean, context: DiagnosticContext = {}, timeoutMs = 15_000): Promise<WireEvent> {
    const existing = this.events.find(predicate);
    if (existing) return existing;
    return new Promise<WireEvent>((resolve, reject) => {
      const timer = setTimeout(() => { const index = this.eventWaiters.findIndex((item) => item.timer === timer); if (index >= 0) this.eventWaiters.splice(index, 1); reject(diagnosticFailure(`timed out waiting for daemon event recent=${this.events.slice(-12).map((event) => `${event.type}:${String(event.run_id ?? "")}`).join(",")}`, context)); }, timeoutMs);
      this.eventWaiters.push({ predicate, resolve, timer });
    });
  }

  close(): void { this.socket?.destroy(); this.socket = undefined; this.rejectAll(new Error("legacy client closed")); }

  private receive(chunk: string): void {
    this.buffer += chunk;
    let newline = this.buffer.indexOf("\n");
    while (newline >= 0) {
      const line = this.buffer.slice(0, newline).trim(); this.buffer = this.buffer.slice(newline + 1); newline = this.buffer.indexOf("\n");
      if (!line) continue;
      // Keep frame-level diagnostics available when a compatibility client sees a malformed response.
      let message: any;
      try { message = JSON.parse(line); } catch (error) { console.error(`[migration-parser] invalid line length=${line.length} head=${line.slice(0, 160)} error=${error instanceof Error ? error.message : String(error)}`); continue; }
      if (message.kind === "event") {
        const event = message.event as WireEvent; this.events.push(event);
        for (const waiter of [...this.eventWaiters]) if (waiter.predicate(event)) { clearTimeout(waiter.timer); this.eventWaiters.splice(this.eventWaiters.indexOf(waiter), 1); waiter.resolve(event); break; }
        continue;
      }
      const id = String(message.id ?? ""); const pending = this.pending.get(id); if (!pending) continue;
      this.pending.delete(id); if (message.error) pending.reject(Object.assign(new Error(String(message.error.message ?? "RPC error")), { code: message.error.code, data: message.error.data })); else pending.resolve(message.result ?? {});
    }
  }

  private rejectAll(error: Error): void { for (const pending of this.pending.values()) pending.reject(error); this.pending.clear(); }
}

interface MockProviderHandle { port: number; requests: () => number; close: () => Promise<void> }

async function startMockProvider(): Promise<MockProviderHandle> {
  let requestCount = 0;
  const server = createServer((request, response) => {
    let raw = ""; request.setEncoding("utf8"); request.on("data", (chunk) => { raw += chunk; });
    request.on("end", () => {
      requestCount += 1;
      let body: any = {}; try { body = JSON.parse(raw || "{}"); } catch { /* provider diagnostics are asserted by the daemon */ }
      const messages = Array.isArray(body.messages) ? body.messages : [];
      const isCompaction = raw.includes("Summarize the earlier agent conversation");
      const lastUser = [...messages].reverse().find((message: any) => message.role === "user");
      const text = typeof lastUser?.content === "string" ? lastUser.content.toLowerCase() : "";
      const hasToolResult = messages.at(-1)?.role === "tool";
      const delay = text.includes("abort") && !hasToolResult ? 10_000 : text.includes("steer") && !hasToolResult ? 300 : 0;
      const finish = () => {
        if (response.writableEnded) return;
        response.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
        const emit = (payload: unknown) => response.write(`data: ${JSON.stringify(payload)}\n\n`);
        let toolCall: { id: string; name: string; input: Record<string, unknown> } | undefined;
        if (!hasToolResult && text.includes("permission")) toolCall = { id: `call-permission-${requestCount}`, name: "bash", input: { command: "echo migration-permission" } };
        else if (!hasToolResult && text.includes("failure")) toolCall = { id: `call-failure-${requestCount}`, name: "migration_missing_tool", input: {} };
        else if (!hasToolResult && text.includes("mcp")) toolCall = { id: `call-mcp-${requestCount}`, name: "mcp__fixture__echo", input: { value: "migration-mcp" } };
        if (toolCall) {
          emit({ choices: [{ delta: { tool_calls: [{ index: 0, id: toolCall.id, function: { name: toolCall.name, arguments: JSON.stringify(toolCall.input) } }] } }] });
        } else {
          const answer = hasToolResult ? `MIGRATION_TOOL_OK:${String(messages.at(-1)?.content ?? "").slice(0, 80)}` : isCompaction || text.includes("summarize the earlier agent conversation") || text.includes("compact") ? "Goal\nMigration validation\nProgress\nContext compacted\nDecisions\nKeep protocol\nOpen Issues\nNone\nNext Steps\nContinue" : text.includes("subagent") || text.includes("workflow") ? '{"status":"succeeded","summary":"migration child complete","conclusion":"done","review_decision":"accept"}' : `MIGRATION_OK:${text || "empty"}`;
          for (const token of answer.match(/.{1,16}/g) ?? [answer]) emit({ choices: [{ delta: { content: token } }] });
        }
        emit({ choices: [], usage: { prompt_tokens: 24, completion_tokens: 8 } }); response.end("data: [DONE]\n\n");
      };
      if (delay) setTimeout(finish, delay); else finish();
    });
  });
  const port = await listenHttp(server);
  return { port, requests: () => requestCount, close: () => closeHttp(server) };
}

async function startMcpServer(): Promise<{ port: number; close: () => Promise<void> }> {
  const server = net.createServer((socket) => {
    socket.setEncoding("utf8"); let buffer = "";
    socket.on("data", (chunk: string) => {
      buffer += chunk; let newline = buffer.indexOf("\n");
      while (newline >= 0) {
        const line = buffer.slice(0, newline); buffer = buffer.slice(newline + 1); newline = buffer.indexOf("\n");
        let message: any; try { message = JSON.parse(line); } catch { continue; }
        if (message.id === undefined) continue;
        const result = message.method === "tools/list" ? { tools: [{ name: "echo", description: "Echo test tool", inputSchema: { type: "object", properties: { value: { type: "string" } }, required: ["value"] } }] } : message.method === "tools/call" ? { content: [{ type: "text", text: `MCP_ECHO:${String(message.params?.arguments?.value ?? "")}` }] } : {};
        socket.write(`${JSON.stringify({ jsonrpc: "2.0", id: message.id, result })}\n`);
      }
    });
  });
  const port = await listenNet(server);
  return { port, close: () => closeNet(server) };
}

class DaemonProcess {
  private process?: ChildProcess;
  private output = "";
  constructor(readonly dataRoot: string, readonly port: number, private readonly providerPort: number, private readonly mcpPort: number, private readonly contextWindow = 256) {}

  async start(): Promise<void> {
    const env: NodeJS.ProcessEnv = {
      ...process.env, SZTU_DATA_DIR: this.dataRoot, SZTU_TS_HOST: "127.0.0.1", SZTU_TS_PORT: String(this.port),
      SZTU_LLM_PROVIDER: "openai", SZTU_LLM_DEFAULT_MODEL: "migration-mock", OPENAI_API_KEY: "migration-test-key", OPENAI_BASE_URL: `http://127.0.0.1:${this.providerPort}/v1`,
      SZTU_PERMISSION_MODE: "normal", SZTU_LLM_CONTEXT_WINDOW: String(this.contextWindow), SZTU_MAX_STEPS: "8", SZTU_TRACE_ENABLED: "0",
      SZTU_MCP_CONFIG: path.join(this.dataRoot, "mcp.json"),
    };
    await writeFile(env.SZTU_MCP_CONFIG!, JSON.stringify({ mcpServers: { fixture: { host: "127.0.0.1", port: this.mcpPort } } }), "utf8");
    this.process = spawn(process.execPath, ["packages/runtime-ts/dist/main.js"], { cwd: repositoryRoot, env, stdio: ["ignore", "pipe", "pipe"], windowsHide: true });
    this.process.stdout?.on("data", (chunk) => { this.output += chunk.toString(); }); this.process.stderr?.on("data", (chunk) => { this.output += chunk.toString(); });
    await waitForDaemon(this.port, this.process, this.output);
  }

  async stop(graceful = true): Promise<void> {
    if (!this.process || this.process.exitCode !== null) return;
    if (graceful) {
      const client = new LegacyRpcClient(this.port); try { await client.connect(); await client.request("core.shutdown", {}); } catch { /* process may already be stopping */ } finally { client.close(); }
    } else this.process.kill("SIGTERM");
    await waitForExit(this.process, 12_000).catch(() => this.process?.kill("SIGKILL"));
  }

  diagnostics(): string { return this.output; }
}

async function runValidation(): Promise<void> {
  const dataRoot = await mkdtemp(path.join(os.tmpdir(), "sztu-migration-validation-"));
  const provider = await startMockProvider(); const mcp = await startMcpServer();
  const daemonPort = await availablePort(); const daemon = new DaemonProcess(dataRoot, daemonPort, provider.port, mcp.port); await daemon.start();
  const diagnostics: DiagnosticContext = {};
  let legacy: LegacyRpcClient | undefined; let modern: DaemonClient | undefined;
  const scenario = async (name: string, action: () => Promise<void>) => {
    try { await action(); console.log(`[migration] PASS ${name}`); }
    catch (error) { throw diagnosticFailure(`scenario ${name} failed`, diagnostics, error); }
  };
  try {
    legacy = new LegacyRpcClient(daemonPort); await legacy.connect(); await legacy.subscribe();
    await scenario("old client -> new daemon", async () => {
      const pong = await legacy!.request("core.ping", { client: "legacy-desktop/0.1" }); check(pong.server_version === "ts-0.2.0", "legacy ping response preserved");
      const created = await legacy!.request("session.create", { mode: "chat", title: "Migration legacy" }); diagnostics.sessionId = String(created.session_id); check(Boolean(diagnostics.sessionId), "legacy session id returned");
    });
    await scenario("new client -> compatibility-mode daemon", async () => {
      modern = await DaemonClient.connect({ transportFactory: createTcpTransportFactory({ host: "127.0.0.1", port: daemonPort }), clientName: "migration-new-client", requestTimeoutMs: 10_000 });
      const pong = await modern.ping(); check((pong as any).server_version === "ts-0.2.0", "new client hello/ping completed", diagnostics);
      await modern.subscribeEvents({ topics: ["*"] }, (event) => legacy!.events.push(event as WireEvent));
    });
    await scenario("session create/list/get", async () => {
      const created = await modern!.createSession({ name: "Migration modern" }, { idempotencyKey: "migration-create-1" }); diagnostics.sessionId = created.session_id;
      check(created.status === "active" && created.session_id === diagnostics.sessionId, "created session snapshot is complete", { ...diagnostics });
      const listed = await modern!.listSessions(); check(listed.some((item) => item.session_id === created.session_id), "new session appears in list", diagnostics);
      const fetched = await legacy!.request("session.get", { session_id: created.session_id }, { sessionId: created.session_id }); check(fetched.session.session_id === created.session_id, "legacy get sees modern session", diagnostics);
    });
    const sessionId = diagnostics.sessionId!;
    await scenario("prompt streaming events and final snapshot", async () => {
      const before = legacy!.events.length; const sent = await sendSessionMessage(legacy!, { session_id: sessionId, content: "streaming migration prompt", client_message_id: "migration-stream-1" }, { sessionId }); diagnostics.runId = String(sent.run_id);
      const finished = await legacy!.waitFor((event) => event.type === "run.finished" && event.run_id === diagnostics.runId, { ...diagnostics }); check(finished.status === "success", "prompt run completed", diagnostics);
      const runEvents = legacy!.events.slice(before).filter((event) => event.run_id === diagnostics.runId); const types: string[] = runEvents.map((event) => event.type);
      const index = (type: string) => types.indexOf(type); check(index("run.started") >= 0 && index("run.started") < index("step.started") && index("step.started") < index("llm.token") && index("llm.token") < index("step.finished") && index("step.finished") < index("run.finished"), `event order is stable: ${types.join(" -> ")}`, diagnostics);
      let snapshot: RpcResult = {};
      for (let attempt = 0; attempt < 100; attempt += 1) { try { snapshot = await legacy!.request("session.get", { session_id: sessionId }, diagnostics); if (snapshot.session.latest_run_id === diagnostics.runId && snapshot.session.status === "waiting_for_input") break; } catch { /* concurrent session metadata writes are retried below */ } await wait(20); }
      check(snapshot.session.latest_run_id === diagnostics.runId && snapshot.session.status === "waiting_for_input", "final session snapshot persisted", diagnostics);
    });
    await scenario("steer and follow-up", async () => {
      await waitForSessionStable(legacy!, sessionId, diagnostics);
      const sent = await sendSessionMessage(legacy!, { session_id: sessionId, content: "steer this run", client_message_id: "migration-steer-1" }, { sessionId }); diagnostics.runId = String(sent.run_id);
      await wait(30); await legacy!.request("session.steer_message", { session_id: sessionId, content: "follow-up steering" }, diagnostics);
      const steered = await legacy!.waitFor((event) => event.type === "session.message_steered" && event.run_id === diagnostics.runId, diagnostics); check(steered.session_id === sessionId, "steer event retains session/run correlation", diagnostics);
      await legacy!.waitFor((event) => event.type === "run.finished" && event.run_id === diagnostics.runId, diagnostics);
      await waitForSessionStable(legacy!, sessionId, diagnostics);
      const follow = await sendSessionMessage(legacy!, { session_id: sessionId, content: "follow-up after steer", client_message_id: "migration-follow-up-1" }, diagnostics); diagnostics.runId = String(follow.run_id); const done = await legacy!.waitFor((event) => event.type === "run.finished" && event.run_id === diagnostics.runId, diagnostics); check(done.status === "success", "follow-up run completed", diagnostics);
    });
    await scenario("tool permission", async () => {
      await waitForSessionStable(legacy!, sessionId, diagnostics);
      const sent = await sendSessionMessage(legacy!, { session_id: sessionId, content: "permission tool", client_message_id: "migration-permission-1" }, diagnostics); diagnostics.runId = String(sent.run_id);
      const requested = await legacy!.waitFor((event) => event.type === "permission.requested" && event.run_id === diagnostics.runId, diagnostics); const permissionId = String(requested.permission_id); await legacy!.request("permission.respond", { permission_id: permissionId, decision: "allow_once" }, { ...diagnostics, requestId: permissionId });
      const granted = await legacy!.waitFor((event) => event.type === "permission.granted" && event.run_id === diagnostics.runId, diagnostics); check(granted.tool_use_id === requested.tool_use_id, "permission grant matches tool call", diagnostics); await legacy!.waitFor((event) => event.type === "run.finished" && event.run_id === diagnostics.runId, diagnostics);
    });
    await scenario("tool failure", async () => {
      await waitForSessionStable(legacy!, sessionId, diagnostics);
      const sent = await sendSessionMessage(legacy!, { session_id: sessionId, content: "failure tool", client_message_id: "migration-failure-1" }, diagnostics); diagnostics.runId = String(sent.run_id);
      const failed = await legacy!.waitFor((event) => event.type === "tool.call_failed" && event.run_id === diagnostics.runId, diagnostics); check(failed.error_class !== "", "tool failure reports an error class", diagnostics); const done = await legacy!.waitFor((event) => event.type === "run.finished" && event.run_id === diagnostics.runId, diagnostics); check(done.status === "success", "agent recovers from tool failure", diagnostics);
    });
    await scenario("abort", async () => {
      await waitForSessionStable(legacy!, sessionId, diagnostics);
      const sent = await sendSessionMessage(legacy!, { session_id: sessionId, content: "abort this run", client_message_id: "migration-abort-1" }, diagnostics); diagnostics.runId = String(sent.run_id); await legacy!.waitFor((event) => event.type === "run.started" && event.run_id === diagnostics.runId, diagnostics); const cancel = await legacy!.request("run.cancel", { run_id: diagnostics.runId }, diagnostics); check(cancel.status === "cancelling", "run cancellation acknowledged", diagnostics); const done = await legacy!.waitFor((event) => event.type === "run.finished" && event.run_id === diagnostics.runId, diagnostics); check(done.status === "cancelled", "abort produces cancelled final event", diagnostics);
    });
    await scenario("session fork", async () => {
      const forked = await legacy!.request("session.fork", { session_id: sessionId, title: "Migration fork" }, diagnostics); const forkId = String(forked.session.session_id); check(forkId !== sessionId, "fork receives a new session id", { ...diagnostics, sessionId: forkId }); const history = await legacy!.request("session.history", { session_id: forkId }, { ...diagnostics, sessionId: forkId }); check(history.messages.length > 0, "fork copies visible history", { ...diagnostics, sessionId: forkId });
    });
    await scenario("context compaction", async () => {
      const compactSession = await legacy!.request("session.create", { mode: "chat", title: "Migration compact" }); const compactId = String(compactSession.session_id); diagnostics.sessionId = compactId;
      for (let index = 0; index < 8; index += 1) { await waitForSessionStable(legacy!, compactId, { sessionId: compactId }); const content = `compact turn ${index} with enough context to force a bounded summary ${"detail ".repeat(180)}`; const sent = await sendSessionMessage(legacy!, { session_id: compactId, content, client_message_id: `compact-${index}` }, { sessionId: compactId }); await legacy!.waitFor((event) => event.type === "run.finished" && event.run_id === String(sent.run_id), { sessionId: compactId, runId: String(sent.run_id) }); }
      await wait(500); const compacted = await legacy!.request("session.compact", { session_id: compactId, focus: "preserve migration contract" }, { sessionId: compactId }); check(Number.isInteger(Number(compacted.removed_messages)) && typeof compacted.used_model === "boolean", `compaction response is typed result=${JSON.stringify(compacted)}`, { sessionId: compactId }); const compactEvent = await legacy!.waitFor((event) => event.type === "context.compacted" && event.session_id === compactId, { sessionId: compactId }); check(compactEvent.summary_tokens !== undefined, "compaction event has summary token count", { sessionId: compactId });
    });
    await scenario("subagent", async () => {
      const parentRunId = "migration-parent-run"; const result = await legacy!.request("agent.subagent", { role: "coder", goal: "subagent migration check", parent_run_id: parentRunId, parent_session_id: sessionId }, { sessionId, runId: parentRunId }); check(Boolean(result.runId && result.sessionId), "subagent returns child run/session ids", { ...diagnostics, runId: String(result.runId), sessionId: String(result.sessionId) }); const child = await legacy!.waitFor((event) => event.type === "subagent.finished" && event.run_id === result.runId, { sessionId, runId: String(result.runId) }); check(child.parent_run_id === parentRunId && child.child_session_id === result.sessionId, "subagent event maps child to parent", { sessionId, runId: String(result.runId) });
    });
    await scenario("MCP tool", async () => {
      const status = await legacy!.request("provider.status", {}); check(status.mcp_servers?.some((server: any) => server.name === "fixture" && server.status === "connected"), "MCP fixture is connected", diagnostics); await legacy!.request("permission.set_mode", { mode: "auto" }); const sent = await sendSessionMessage(legacy!, { session_id: sessionId, content: "mcp tool", client_message_id: "migration-mcp-1" }, diagnostics); diagnostics.runId = String(sent.run_id); const tool = await legacy!.waitFor((event) => event.type === "tool.call_finished" && event.run_id === diagnostics.runId && String(event.tool_name).startsWith("mcp__fixture__"), diagnostics); check(String(tool.output).includes("MCP_ECHO"), "MCP output reaches agent event", diagnostics); await legacy!.waitFor((event) => event.type === "run.finished" && event.run_id === diagnostics.runId, diagnostics);
    });
    await scenario("daemon restart", async () => {
      const persistedSession = sessionId; legacy!.close(); legacy = undefined; await modern!.close(); modern = undefined; await daemon.stop(); await daemon.start(); legacy = new LegacyRpcClient(daemonPort); await legacy.connect(); const fetched = await legacy.request("session.get", { session_id: persistedSession }, { sessionId: persistedSession }); check(fetched.session.session_id === persistedSession, "session survives daemon restart", { sessionId: persistedSession }); const listed = await legacy.request("session.list", { include_archived: true }, { sessionId: persistedSession }); check(listed.sessions.some((item: any) => item.session_id === persistedSession), "restart list contains persisted session", { sessionId: persistedSession });
    });
    await scenario("desktop contract", async () => {
      const desktop = await readFile(path.join(repositoryRoot, "desktop/src/services/sztu-runtime.ts"), "utf8"); const server = await readFile(path.join(repositoryRoot, "packages/runtime-ts/src/server-service.ts"), "utf8"); const requested = new Set([...desktop.matchAll(/client\.request\(\s*["']([^"']+)["']/g)].map((match) => match[1])); const handled = new Set([...server.matchAll(/case\s+["']([^"']+)["']/g)].map((match) => match[1])); check(requested.size >= 50, "desktop RPC extraction found expected surface"); check([...requested].every((method) => handled.has(method)), `desktop methods missing: ${[...requested].filter((method) => !handled.has(method)).join(",")}`);
    });
    await scenario("Python runtime unaffected", async () => {
      try {
        const result = await execFileAsync("uv", ["run", "--project", "py-runtime", "--offline", "pytest", "-q", "py-runtime/tests/integration/test_ping_roundtrip.py"], { cwd: repositoryRoot, timeout: 120_000, env: { ...process.env, PYTHONPATH: path.join(repositoryRoot, "py-runtime", "src") } });
        check(/passed/.test(`${result.stdout}${result.stderr}`), "Python ping contract passed", { requestId: "python-ping-smoke" });
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        if (!/spawn uv EACCES|ENOENT|not found/i.test(message)) throw diagnosticFailure("Python runtime ping contract failed", { requestId: "python-ping-smoke" }, error);
        const fallback = await execFileAsync("python3", ["-m", "compileall", "-q", "py-runtime/src"], { cwd: repositoryRoot, timeout: 30_000 });
        check(fallback.stderr === "", "Python runtime source compiles in fallback mode", { requestId: "python-compileall" });
        console.log("[migration] INFO Python ping integration skipped: uv/pytest unavailable; compileall isolation check passed");
      }
    });
    console.log(JSON.stringify({ status: "passed", daemon_port: daemonPort, mock_llm_requests: provider.requests(), scenarios: 15 }, null, 2));
  } catch (error) {
    throw diagnosticFailure("migration validation failed", diagnostics, error instanceof Error ? `${error.message}\ndaemon_output=${daemon.diagnostics()}` : error);
  } finally {
    legacy?.close(); await modern?.close().catch(() => undefined); await daemon.stop().catch(() => undefined); await provider.close(); await mcp.close(); await rm(dataRoot, { recursive: true, force: true });
  }
}

async function waitForDaemon(port: number, child: ChildProcess, output: string): Promise<void> {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    if (child.exitCode !== null) throw diagnosticFailure(`daemon exited before ready code=${child.exitCode}`, { requestId: "daemon-start" }, output);
    const client = new LegacyRpcClient(port);
    try { await client.connect(); await client.request("core.ping", { client: "migration-harness" }, { requestId: "daemon-ready" }); client.close(); return; } catch { client.close(); await wait(100); }
  }
  throw diagnosticFailure(`daemon did not listen on ${port}`, { requestId: "daemon-start" });
}

async function waitForSessionStable(client: LegacyRpcClient, sessionId: string, context: DiagnosticContext): Promise<RpcResult> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try { const snapshot = await client.request("session.get", { session_id: sessionId }, context); await wait(100); return snapshot; }
    catch (error) { lastError = error; await wait(20); }
  }
  throw diagnosticFailure("session metadata did not become readable", { ...context, sessionId }, lastError);
}

async function sendSessionMessage(client: LegacyRpcClient, params: Record<string, unknown>, context: DiagnosticContext): Promise<RpcResult> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try { return await client.request("session.send_message", params, context); }
    catch (error) {
      lastError = error;
      if (!/Unexpected end of JSON input|ENOENT/.test(String(error))) throw error;
      await wait(20);
    }
  }
  throw diagnosticFailure("session.send_message did not become readable", context, lastError);
}

async function waitForExit(child: ChildProcess, timeoutMs: number): Promise<void> {
  if (child.exitCode !== null) return;
  await Promise.race([new Promise<void>((resolve) => child.once("exit", () => resolve())), new Promise<never>((_, reject) => setTimeout(() => reject(new Error("daemon exit timeout")), timeoutMs))]);
}

async function availablePort(): Promise<number> { const server = net.createServer(); const port = await listenNet(server); await closeNet(server); return port; }
async function listenNet(server: net.Server): Promise<number> { await new Promise<void>((resolve, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", resolve); }); const address = server.address(); if (!address || typeof address === "string") throw new Error("unable to allocate TCP port"); return address.port; }
async function closeNet(server: net.Server): Promise<void> { await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve())); }
async function listenHttp(server: HttpServer): Promise<number> { await new Promise<void>((resolve, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", resolve); }); const address = server.address(); if (!address || typeof address === "string") throw new Error("unable to allocate HTTP port"); return address.port; }
async function closeHttp(server: HttpServer): Promise<void> { await new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve())); }

runValidation().catch((error) => { console.error(error instanceof Error ? error.stack ?? error.message : error); process.exitCode = 1; });
