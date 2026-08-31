import net from "node:net";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import type { Tool, ToolContext, ToolResult } from "./tools.js";

type Pending = { resolve: (value: Record<string, unknown>) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout>; cleanup: () => void };
export type McpToolDefinition = { name: string; description: string; inputSchema: Record<string, unknown> };
export type McpContent = { type: string; text?: string; [key: string]: unknown };
export type McpClientOptions = { timeoutMs?: number; reconnectDelaysMs?: readonly number[]; onToolsChanged?: (tools: McpToolDefinition[]) => void };
export type McpServerStatus = { name: string; transport: "stdio" | "tcp"; connected: boolean; error?: string; toolCount: number };
export type McpManagerOptions = { onToolsChanged?: (serverName: string, tools: McpToolDefinition[]) => void };

// 断开类错误：请求因此失败时可触发自动重连并重试
class McpDisconnectedError extends Error { constructor(message: string) { super(message); this.name = "McpDisconnectedError"; } }

const STDERR_TAIL_BYTES = 4096; // 错误诊断只保留 stderr 尾部 4KB
const DEFAULT_RECONNECT_DELAYS_MS: readonly number[] = [500, 1000, 2000]; // 指数退避：最多重连 3 次
const abortReason = (signal?: AbortSignal): Error => signal?.reason instanceof Error ? signal.reason : new Error("MCP operation aborted");
const sleep = (ms: number, signal?: AbortSignal): Promise<void> => new Promise((resolve, reject) => { if (signal?.aborted) { reject(abortReason(signal)); return; } const timer = setTimeout(() => { signal?.removeEventListener("abort", abort); resolve(); }, ms); const abort = () => { clearTimeout(timer); reject(abortReason(signal)); }; signal?.addEventListener("abort", abort, { once: true }); });
// 让等待方可被 AbortSignal 提前打断（不取消被等待的 Promise 本身）
function withAbort<T>(promise: Promise<T>, signal?: AbortSignal): Promise<T> { if (!signal) return promise; return new Promise<T>((resolve, reject) => { if (signal.aborted) { reject(abortReason(signal)); return; } const abort = () => reject(abortReason(signal)); signal.addEventListener("abort", abort, { once: true }); promise.then((value) => { signal.removeEventListener("abort", abort); resolve(value); }, (error: Error) => { signal.removeEventListener("abort", abort); reject(error); }); }); }

export class McpClient {
  private id = 0; private readonly pending = new Map<string, Pending>(); private buffer = ""; private process: ChildProcessWithoutNullStreams | null = null; private socket: net.Socket | null = null;
  private readonly timeoutMs: number; private readonly reconnectDelaysMs: readonly number[];
  private alive = false; private closed = false; private disconnectText = ""; private stderrTail = ""; private lastErrorValue: Error | null = null; private reconnecting: Promise<void> | null = null;
  private stdioConfig: { command: string; args: string[]; env: Record<string, string> } | null = null; private tcpConfig: { host: string; port: number } | null = null;
  private serverCapabilitiesValue: Readonly<Record<string, unknown>> = {}; private listChangedSupported = true; private cachedTools: McpToolDefinition[] = [];
  onToolsChanged?: (tools: McpToolDefinition[]) => void;
  constructor(options: number | McpClientOptions = {}) { const opts = typeof options === "number" ? { timeoutMs: options } : options; this.timeoutMs = opts.timeoutMs ?? 30_000; this.reconnectDelaysMs = opts.reconnectDelaysMs ?? DEFAULT_RECONNECT_DELAYS_MS; if (opts.onToolsChanged) this.onToolsChanged = opts.onToolsChanged; }
  get connected(): boolean { return this.alive; }
  get disconnectReason(): string { return this.disconnectText; }
  get lastError(): Error | null { return this.lastErrorValue; }
  get serverCapabilities(): Readonly<Record<string, unknown>> { return this.serverCapabilitiesValue; }
  get toolsListChangedSupported(): boolean { return this.listChangedSupported; }
  get toolCache(): readonly McpToolDefinition[] { return this.cachedTools; }
  async connectStdio(command: string, args: string[] = [], env: Record<string, string> = {}): Promise<void> { this.stdioConfig = { command, args, env }; await this.spawnStdio(); }
  async connectTcp(host: string, port: number): Promise<void> { this.tcpConfig = { host, port }; await this.openTcp(); }
  async listTools(signal?: AbortSignal): Promise<McpToolDefinition[]> { const result = await this.request("tools/list", {}, signal); const tools = (result.tools as McpToolDefinition[] | undefined) ?? []; this.cachedTools = tools; return tools; }
  async listResources(signal?: AbortSignal): Promise<Record<string, unknown>[]> { const result = await this.request("resources/list", {}, signal); return (result.resources as Record<string, unknown>[] | undefined) ?? []; }
  async listPrompts(signal?: AbortSignal): Promise<Record<string, unknown>[]> { const result = await this.request("prompts/list", {}, signal); return (result.prompts as Record<string, unknown>[] | undefined) ?? []; }
  async callTool(name: string, arguments_: Record<string, unknown>, signal?: AbortSignal): Promise<string> { const result = await this.request("tools/call", { name, arguments: arguments_ }, signal); const content = Array.isArray(result.content) ? result.content.filter((item): item is McpContent => !!item && typeof item === "object") : []; return content.map((item) => item.type === "text" ? item.text ?? "" : JSON.stringify(item)).filter(Boolean).join("\n"); }
  async close(): Promise<void> { this.closed = true; this.alive = false; this.buffer = ""; this.rejectPending(new Error("MCP client closed")); this.cleanupTransport(); }
  private async spawnStdio(): Promise<void> {
    const config = this.stdioConfig; if (!config) throw new Error("MCP stdio transport is not configured");
    this.cleanupTransport(); this.buffer = ""; this.stderrTail = "";
    this.process = spawn(config.command, config.args, { stdio: "pipe", env: { ...process.env, ...config.env }, windowsHide: true });
    this.process.stdout.setEncoding("utf8"); this.process.stdout.on("data", (chunk: string) => this.receive(chunk));
    // 持续排空 stderr 并只保留尾部 4KB 供诊断，避免服务器日志写满管道缓冲导致死锁
    this.process.stderr.setEncoding("utf8"); this.process.stderr.on("data", (chunk: string) => { this.stderrTail = `${this.stderrTail}${chunk}`.slice(-STDERR_TAIL_BYTES); });
    this.process.stdin.on("error", () => { /* 进程退出后的 stdin 写入失败由 exit 事件统一处理 */ });
    this.process.once("exit", (code, signalName) => this.handleDisconnect(`MCP server exited (code=${code ?? signalName ?? "unknown"})`));
    this.process.once("error", (error) => this.handleDisconnect(`MCP server spawn failed: ${error.message}`));
    await this.initialize(); this.alive = true; this.disconnectText = "";
  }
  private async openTcp(): Promise<void> {
    const config = this.tcpConfig; if (!config) throw new Error("MCP tcp transport is not configured");
    this.cleanupTransport(); this.buffer = "";
    const socket = net.createConnection({ host: config.host, port: config.port }); this.socket = socket;
    socket.setEncoding("utf8"); socket.on("data", (chunk: string) => this.receive(chunk));
    socket.once("close", () => this.handleDisconnect("MCP connection closed"));
    socket.on("error", (error) => { this.lastErrorValue = error; }); // 记录错误细节，断开处理由 close 事件统一触发
    await new Promise<void>((resolve, reject) => { socket.once("connect", resolve); socket.once("error", reject); });
    await this.initialize(); this.alive = true; this.disconnectText = "";
  }
  private cleanupTransport(): void { if (this.process) { const proc = this.process; this.process = null; proc.removeAllListeners(); proc.stdin.destroy(); proc.stdout.destroy(); proc.stderr.destroy(); proc.kill(); } if (this.socket) { const socket = this.socket; this.socket = null; socket.removeAllListeners(); socket.destroy(); } }
  // 记录断开状态与原因，拒绝挂起请求；退出错误信息附带 stderr 尾部
  private handleDisconnect(reason: string): void { const wasAlive = this.alive; this.alive = false; this.buffer = ""; if (wasAlive || !this.disconnectText) this.disconnectText = reason; this.rejectPending(new McpDisconnectedError(`${reason}${this.stderrTail ? ` | stderr tail: ${this.stderrTail}` : ""}`)); }
  // 保存服务器协商出的能力；协议版本声明保持不变
  private async initialize(): Promise<void> { const result = await this.call("initialize", { protocolVersion: "2025-06-18", capabilities: { roots: { listChanged: false } }, clientInfo: { name: "sztucode-ts", version: "0.2.0" } }); const capabilities = result.capabilities; this.serverCapabilitiesValue = capabilities && typeof capabilities === "object" ? capabilities as Record<string, unknown> : {}; const toolsCapability = this.serverCapabilitiesValue.tools as { listChanged?: boolean } | undefined; this.listChangedSupported = toolsCapability?.listChanged !== false; this.notify("notifications/initialized", {}); }
  // 公开请求入口：发现断开先自动退避重连，重连成功后重试一次原请求
  private async request(method: string, params: Record<string, unknown>, signal?: AbortSignal): Promise<Record<string, unknown>> { if (!this.alive) await this.ensureConnected(signal); try { return await this.call(method, params, signal); } catch (error) { if (error instanceof McpDisconnectedError && !this.closed) { await this.ensureConnected(signal); return await this.call(method, params, signal); } throw error; } }
  private async ensureConnected(signal?: AbortSignal): Promise<void> { if (this.alive) return; if (this.closed) throw new Error("MCP client is closed"); if (!this.stdioConfig && !this.tcpConfig) throw new Error(this.lastErrorValue?.message || this.disconnectText || "MCP client is not connected"); const attempt = this.reconnecting ?? this.reconnect(signal); this.reconnecting = attempt; try { await withAbort(attempt, signal); } finally { if (this.reconnecting === attempt) this.reconnecting = null; } }
  // stdio 重连 = 重新 spawn；tcp 重连 = 重新 createConnection + initialize 握手
  private async reconnect(signal?: AbortSignal): Promise<void> { let lastError: Error = this.lastErrorValue ?? new Error(this.disconnectText || "MCP connection lost"); for (const delay of this.reconnectDelaysMs) { await sleep(delay, signal); if (this.closed) throw new Error("MCP client is closed"); try { if (this.stdioConfig) await this.spawnStdio(); else await this.openTcp(); this.lastErrorValue = null; return; } catch (error) { lastError = error instanceof Error ? error : new Error(String(error)); } } this.lastErrorValue = lastError; throw lastError; }
  private call(method: string, params: Record<string, unknown>, signal?: AbortSignal): Promise<Record<string, unknown>> {
    const id = String(++this.id);
    return new Promise((resolve, reject) => {
      const finish = () => { const pending = this.pending.get(id); if (!pending) return; clearTimeout(pending.timer); pending.cleanup(); this.pending.delete(id); };
      const abort = () => { finish(); reject(signal?.reason instanceof Error ? signal.reason : new Error(`MCP ${method} aborted`)); };
      const timer = setTimeout(() => { finish(); reject(new Error(`MCP ${method} timed out after ${this.timeoutMs}ms`)); }, this.timeoutMs);
      const cleanup = () => signal?.removeEventListener("abort", abort);
      this.pending.set(id, { resolve: (value) => { finish(); resolve(value); }, reject: (error) => { finish(); reject(error); }, timer, cleanup });
      signal?.addEventListener("abort", abort, { once: true });
      if (signal?.aborted) return abort();
      try { this.send({ jsonrpc: "2.0", id, method, params }); } catch (error) { finish(); reject(error); }
    });
  }
  private notify(method: string, params: Record<string, unknown>): void { this.send({ jsonrpc: "2.0", method, params }); }
  private send(message: Record<string, unknown>): void { const line = `${JSON.stringify(message)}\n`; if (this.process) this.process.stdin.write(line); else if (this.socket) this.socket.write(line); else throw new Error("MCP client is not connected"); }
  private receive(chunk: string): void { this.buffer += chunk; let newline = this.buffer.indexOf("\n"); while (newline >= 0) { const line = this.buffer.slice(0, newline); this.buffer = this.buffer.slice(newline + 1); newline = this.buffer.indexOf("\n"); try { const message = JSON.parse(line) as { id?: string | number | null; method?: string; result?: Record<string, unknown>; error?: { message?: string } }; if (message.id === undefined || message.id === null) { if (message.method === "notifications/tools/list_changed") void this.refreshTools(); continue; } const pending = this.pending.get(String(message.id)); if (!pending) continue; if (message.error) pending.reject(new Error(message.error.message ?? "MCP error")); else pending.resolve(message.result ?? {}); } catch { /* 忽略非 JSON 输出 */ } } }
  // tools/list_changed 通知：刷新本服务器工具缓存并回调上层；未知通知直接忽略
  private async refreshTools(): Promise<void> { try { const tools = await this.listTools(); this.onToolsChanged?.(tools); } catch { /* 刷新失败不影响主链路 */ } }
  private rejectPending(error: Error): void { for (const pending of [...this.pending.values()]) pending.reject(error); }
}

export function mcpTool(client: McpClient, definition: McpToolDefinition, prefix = "mcp"): Tool {
  return { name: `${prefix}__${definition.name}`, description: definition.description, permission: "workspace_write", retryable: false, schema: definition.inputSchema, async invoke(params: Record<string, unknown>, context: ToolContext): Promise<ToolResult> { try { return { ok: true, output: await client.callTool(definition.name, params, context.signal) }; } catch (error) { const message = error instanceof Error ? error.message : String(error); return { ok: false, output: "", error: message, errorType: /timed out/i.test(message) ? "timeout" : "runtime_error" }; } } };
}

export type McpServerConfig = { command?: string; args?: string[]; env?: Record<string, string>; host?: string; port?: number; enabled?: boolean; timeout_ms?: number };
type ManagedServer = { name: string; transport: "stdio" | "tcp"; client: McpClient; tools: Tool[]; error?: string };
export class McpManager {
  private readonly servers = new Map<string, ManagedServer>();
  constructor(private readonly configPath = process.env.SZTU_MCP_CONFIG ?? "", private readonly options: McpManagerOptions = {}) {}
  async load(): Promise<void> {
    if (!this.configPath) return;
    let servers: Record<string, McpServerConfig>; try { const { readFile } = await import("node:fs/promises"); const payload = JSON.parse(await readFile(this.configPath, "utf8")) as { mcpServers?: Record<string, McpServerConfig> }; servers = payload.mcpServers ?? {}; } catch { return; }
    // 并行连接所有启用的服务器：单个失败不阻塞其他，失败者的工具集为空
    await Promise.allSettled(Object.entries(servers).filter(([, config]) => config.enabled !== false).map(([name, config]) => this.connectServer(name, config)));
  }
  private async connectServer(name: string, config: McpServerConfig): Promise<void> {
    const transport: "stdio" | "tcp" = config.command ? "stdio" : "tcp"; const client = new McpClient(config.timeout_ms); const state: ManagedServer = { name, transport, client, tools: [] }; this.servers.set(name, state);
    try {
      if (config.command) await client.connectStdio(config.command, config.args ?? [], config.env ?? {}); else if (config.host && config.port) await client.connectTcp(config.host, config.port); else throw new Error("command or host/port is required");
      client.onToolsChanged = (tools) => { state.tools = tools.map((definition) => mcpTool(client, definition, `mcp__${name}`)); this.options.onToolsChanged?.(name, tools); };
      const definitions = await client.listTools(); state.tools = definitions.map((definition) => mcpTool(client, definition, `mcp__${name}`));
    } catch (error) { state.error = error instanceof Error ? error.message : String(error); await client.close(); }
  }
  listTools(): Tool[] { return [...this.servers.values()].flatMap((server) => server.tools); }
  status(): McpServerStatus[] { return [...this.servers.values()].map((server) => ({ name: server.name, transport: server.transport, connected: server.client.connected, error: server.error ?? (server.client.connected ? undefined : server.client.disconnectReason || undefined), toolCount: server.tools.length })); }
  statuses(): Array<{ name: string; status: string; tool_count: number; error?: string }> { return this.status().map((server) => ({ name: server.name, status: server.connected ? "connected" : server.error ? "failed" : "disconnected", tool_count: server.toolCount, error: server.error })); }
  async close(): Promise<void> { await Promise.all([...this.servers.values()].map((server) => server.client.close())); this.servers.clear(); }
}
