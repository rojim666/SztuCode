// 容器内 runner（TS runtime 版）：在 Harbor 任务容器里拉起 SztuCode TS daemon
// 并驱动其完成 Terminal-Bench 任务。
//
// 本脚本由 eval.terminalbench.agent.SztuCodeTsAgent（host 端 Harbor agent）通过
// environment.exec 在容器内执行，不要在 host 上直接运行。
//
// 与 runner.py 等价的零依赖 Node 实现（仅用 node:net / node:fs / node:child_process）：
//   1. spawn daemon: node packages/runtime-ts/dist/main.js（SZTU_PORT 指定端口，
//      日志写入 --daemon-log）
//   2. core.ping 轮询直到就绪
//   3. permission.set_mode(auto) → event.subscribe → workspace.open(workspace)
//   4. session.create(one_shot) → session.send_message(指令全文)
//   5. 等待 run.finished 事件（--timeout 秒）
//   6. 从 run.finished 提取状态/token（TS 的 run.finished 直接携带 total_* 字段，
//      不依赖 llm.usage 事件）→ 写 --result-file JSON
//   7. 关闭 session，杀掉 daemon（独立进程组）
//
// 结果 JSON schema 与 runner.py 完全一致，agent._populate_context 无需区分 runtime。
import net from "node:net";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const RUNTIME_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const DAEMON_ENTRY = path.join(RUNTIME_DIR, "packages/runtime-ts/dist/main.js");
const DAEMON_READY_TIMEOUT_MS = 120_000;

function parseArgs(argv) {
  const args = { instructionFile: "", workspace: "", port: 7457, resultFile: "", timeout: 21_600, daemonLog: "/tmp/sztu-daemon.log" };
  for (let i = 0; i < argv.length; i += 2) {
    const key = String(argv[i]).replace(/^--/, "").replace(/-/g, "_");
    const value = argv[i + 1];
    if (key in args && value !== undefined) args[key] = Number.isInteger(args[key]) ? Number(value) : String(value);
  }
  return args;
}

function log(line) { console.log(`[runner] ${line}`); }

// ──────────────────── JSON-RPC over TCP NDJSON ────────────────────

class RpcClient {
  constructor(host, port) {
    this.host = host;
    this.port = port;
    this.pending = new Map();
    this.eventHandlers = [];
    this.buffer = "";
    this.socket = null;
  }

  connect() {
    return new Promise((resolve, reject) => {
      this.socket = net.connect({ host: this.host, port: this.port });
      this.socket.on("connect", () => resolve());
      this.socket.on("error", (err) => { if (!this.socket?.readyState || this.socket.readyState === "closed") reject(err); });
      this.socket.on("data", (chunk) => this.onData(chunk));
      this.socket.on("close", () => {
        for (const { reject: fail } of this.pending.values()) fail(new Error("connection closed"));
        this.pending.clear();
      });
    });
  }

  onData(chunk) {
    this.buffer += chunk.toString("utf8");
    let index;
    while ((index = this.buffer.indexOf("\n")) >= 0) {
      const line = this.buffer.slice(0, index).trim();
      this.buffer = this.buffer.slice(index + 1);
      if (!line) continue;
      this.dispatch(line);
    }
  }

  dispatch(line) {
    let message;
    try { message = JSON.parse(line); } catch { return; }
    if (message.jsonrpc && message.id !== undefined) {
      const pending = this.pending.get(message.id);
      if (pending) {
        this.pending.delete(message.id);
        if (message.error) pending.reject(new Error(`[${message.error.code}] ${message.error.message}`));
        else pending.resolve(message.result ?? {});
      }
    } else if (message.kind === "event") {
      for (const handler of this.eventHandlers) handler(message.event ?? {});
    }
  }

  onEvent(handler) { this.eventHandlers.push(handler); }

  send(method, params) {
    return new Promise((resolve, reject) => {
      if (!this.socket || this.socket.destroyed) { reject(new Error("not connected")); return; }
      const id = crypto.randomUUID();
      this.pending.set(id, { resolve, reject });
      this.socket.write(`${JSON.stringify({ jsonrpc: "2.0", id, method, params })}\n`);
    });
  }

  close() {
    this.socket?.end();
    this.socket?.destroy();
  }
}

// ──────────────────── daemon 生命周期 ────────────────────

function spawnDaemon(args) {
  if (!fs.existsSync(DAEMON_ENTRY)) throw new Error(`daemon entry not found: ${DAEMON_ENTRY}`);
  const env = { ...process.env, SZTU_HOST: "127.0.0.1", SZTU_PORT: String(args.port) };
  const out = fs.openSync(args.daemonLog, "a");
  const child = spawn(process.execPath, [DAEMON_ENTRY], { cwd: RUNTIME_DIR, env, stdio: ["ignore", out, out], detached: true });
  child.unref();
  fs.closeSync(out);
  return child;
}

function terminateDaemon(daemon) {
  if (daemon.exitCode !== null || daemon.signalCode !== null) return;
  try { process.kill(-daemon.pid, "SIGTERM"); } catch { daemon.kill("SIGTERM"); }
  const deadline = Date.now() + 3_000;
  while (Date.now() < deadline && daemon.exitCode === null && daemon.signalCode === null) Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 100);
  if (daemon.exitCode === null && daemon.signalCode === null) {
    try { process.kill(-daemon.pid, "SIGKILL"); } catch { daemon.kill("SIGKILL"); }
  }
}

async function waitDaemonReady(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  let lastError = null;
  while (Date.now() < deadline) {
    const client = new RpcClient("127.0.0.1", port);
    try {
      await withTimeout(client.connect(), 2_000);
      await withTimeout(client.send("core.ping", {}), 5_000);
      return;
    } catch (error) { lastError = error; } finally { client.close(); }
    await sleep(1_000);
  }
  throw new Error(`daemon not ready on port ${port}: ${lastError}`);
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const withTimeout = (promise, ms) => Promise.race([promise, sleep(ms).then(() => { throw new Error(`timeout after ${ms}ms`); })]);

// ──────────────────── 任务执行 ────────────────────

async function runTask(args, instruction) {
  const result = { status: "error", reason: null, steps: 0, run_id: null, error: null, elapsed_s: 0, input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 };
  const client = new RpcClient("127.0.0.1", args.port);
  let runId = null;
  let finished = false;
  let finishedEvent = null;
  const start = Date.now();

  const onEvent = (event) => {
    if (runId === null || String(event.run_id ?? "") !== runId) return;
    const type = event.type ?? "";
    if (type === "step.started") log(`step ${event.step} planning`);
    else if (type === "tool.call_started") log(`tool ${event.tool_name}`);
    else if (type === "tool.call_failed") log(`tool FAIL: ${event.error_message ?? ""}`);
    else if (type === "run.finished") { finished = true; finishedEvent = event; }
  };

  let sessionId = null;
  try {
    await client.connect();
    client.onEvent(onEvent);

    await client.send("permission.set_mode", { mode: "auto" });
    log("permission mode: auto");

    // 先订阅再发消息，避免漏掉 run.finished
    await client.send("event.subscribe", { topics: ["run.*", "step.*", "tool.*"], scope: "global" });

    const ws = await client.send("workspace.open", { path: args.workspace });
    const workspaceId = ws.workspace?.workspace_id ?? "";
    log(`workspace: ${workspaceId} (${args.workspace})`);

    const session = await client.send("session.create", { mode: "one_shot", title: "terminal-bench", workspace_id: workspaceId });
    sessionId = session.session_id ?? "";

    const sent = await client.send("session.send_message", { session_id: sessionId, content: instruction });
    runId = String(sent.run_id ?? "");
    if (!runId) throw new Error("daemon returned an empty run_id");
    result.run_id = runId;
    log(`run started: ${runId}`);

    const deadline = Date.now() + args.timeout * 1000;
    while (!finished && Date.now() < deadline) await sleep(500);
    if (!finished) {
      result.status = "timeout";
      result.error = `run not finished within ${args.timeout}s`;
      try { await client.send("run.cancel", { run_id: runId }); } catch { /* daemon 已退出时忽略 */ }
    } else {
      result.status = finishedEvent.status ?? "unknown";
      result.reason = finishedEvent.reason ?? null;
      result.steps = Number(finishedEvent.steps ?? 0);
      result.input_tokens = Number(finishedEvent.total_input_tokens ?? 0);
      result.output_tokens = Number(finishedEvent.total_output_tokens ?? 0);
      result.cache_read_input_tokens = Number(finishedEvent.cache_read_input_tokens ?? 0);
      result.cache_creation_input_tokens = Number(finishedEvent.cache_creation_input_tokens ?? 0);
    }
  } catch (error) {
    result.error = `RPC error: ${error instanceof Error ? error.message : String(error)}`;
  } finally {
    if (sessionId) { try { await client.send("session.close", { session_id: sessionId }); } catch { /* 清理失败不影响结果 */ } }
    client.close();
    result.elapsed_s = Math.round((Date.now() - start) / 100) / 10;
  }
  return result;
}

function writeResult(filePath, payload) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
}

// ──────────────────── main ────────────────────

const args = parseArgs(process.argv.slice(2));
if (!args.instructionFile || !args.workspace || !args.resultFile) {
  console.error("usage: runner.mjs --instruction-file F --workspace D --result-file F [--port P] [--timeout S] [--daemon-log L]");
  process.exit(2);
}

const instruction = fs.readFileSync(args.instructionFile, "utf8");
if (!instruction.trim()) {
  writeResult(args.resultFile, { status: "error", error: "empty instruction" });
  process.exit(2);
}

const daemon = spawnDaemon(args);
log(`daemon pid=${daemon.pid} port=${args.port} workspace=${args.workspace}`);

let result;
try {
  await waitDaemonReady(args.port, DAEMON_READY_TIMEOUT_MS);
  log("daemon ready");
  result = await runTask(args, instruction);
} catch (error) {
  result = { status: "error", error: `${error instanceof Error ? error.message : String(error)}`, elapsed_s: 0 };
} finally {
  terminateDaemon(daemon);
}

writeResult(args.resultFile, result);
log(`done status=${result.status} steps=${result.steps ?? 0} elapsed=${result.elapsed_s}s tokens(in/out/cache)=${result.input_tokens ?? 0}/${result.output_tokens ?? 0}/${result.cache_read_input_tokens ?? 0}`);
process.exit(result.status === "success" ? 0 : 1);
