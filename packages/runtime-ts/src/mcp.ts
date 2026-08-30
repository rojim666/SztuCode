import net from "node:net";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import type { Tool, ToolContext, ToolResult } from "./tools.js";

type Pending = { resolve: (value: Record<string, unknown>) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout>; cleanup: () => void };
export type McpToolDefinition = { name: string; description: string; inputSchema: Record<string, unknown> };
export type McpContent = { type: string; text?: string; [key: string]: unknown };

export class McpClient {
  private id = 0; private readonly pending = new Map<string, Pending>(); private buffer = ""; private process: ChildProcessWithoutNullStreams | null = null; private socket: net.Socket | null = null;
  constructor(private readonly timeoutMs = 30_000) {}
  async connectStdio(command: string, args: string[] = [], env: Record<string, string> = {}): Promise<void> { this.process = spawn(command, args, { stdio: "pipe", env: { ...process.env, ...env }, windowsHide: true }); this.process.stdout.setEncoding("utf8"); this.process.stdout.on("data", (chunk: string) => this.receive(chunk)); this.process.once("exit", () => this.rejectPending(new Error("MCP server exited"))); this.process.once("error", (error) => this.rejectPending(error)); await this.initialize(); }
  async connectTcp(host: string, port: number): Promise<void> { this.socket = net.createConnection({ host, port }); this.socket.setEncoding("utf8"); this.socket.on("data", (chunk: string) => this.receive(chunk)); this.socket.once("close", () => this.rejectPending(new Error("MCP connection closed"))); await new Promise<void>((resolve, reject) => { this.socket!.once("connect", resolve); this.socket!.once("error", reject); }); await this.initialize(); }
  async listTools(signal?: AbortSignal): Promise<McpToolDefinition[]> { const result = await this.call("tools/list", {}, signal); return (result.tools as McpToolDefinition[] | undefined) ?? []; }
  async listResources(signal?: AbortSignal): Promise<Record<string, unknown>[]> { const result = await this.call("resources/list", {}, signal); return (result.resources as Record<string, unknown>[] | undefined) ?? []; }
  async listPrompts(signal?: AbortSignal): Promise<Record<string, unknown>[]> { const result = await this.call("prompts/list", {}, signal); return (result.prompts as Record<string, unknown>[] | undefined) ?? []; }
  async callTool(name: string, arguments_: Record<string, unknown>, signal?: AbortSignal): Promise<string> { const result = await this.call("tools/call", { name, arguments: arguments_ }, signal); const content = Array.isArray(result.content) ? result.content.filter((item): item is McpContent => !!item && typeof item === "object") : []; return content.map((item) => item.type === "text" ? item.text ?? "" : JSON.stringify(item)).filter(Boolean).join("\n"); }
  async close(): Promise<void> { this.rejectPending(new Error("MCP client closed")); this.process?.kill(); this.socket?.destroy(); }
  private async initialize(): Promise<void> { await this.call("initialize", { protocolVersion: "2025-06-18", capabilities: { roots: { listChanged: false } }, clientInfo: { name: "sztucode-ts", version: "0.2.0" } }); this.notify("notifications/initialized", {}); }
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
  private receive(chunk: string): void { this.buffer += chunk; let newline = this.buffer.indexOf("\n"); while (newline >= 0) { const line = this.buffer.slice(0, newline); this.buffer = this.buffer.slice(newline + 1); newline = this.buffer.indexOf("\n"); try { const message = JSON.parse(line) as { id?: string | number; result?: Record<string, unknown>; error?: { message?: string } }; const id = String(message.id ?? ""); const pending = this.pending.get(id); if (!pending) continue; if (message.error) pending.reject(new Error(message.error.message ?? "MCP error")); else pending.resolve(message.result ?? {}); } catch { /* ignore non-JSON output */ } } }
  private rejectPending(error: Error): void { for (const pending of [...this.pending.values()]) pending.reject(error); }
}

export function mcpTool(client: McpClient, definition: McpToolDefinition, prefix = "mcp"): Tool {
  return { name: `${prefix}__${definition.name}`, description: definition.description, permission: "workspace_write", retryable: false, schema: definition.inputSchema, async invoke(params: Record<string, unknown>, context: ToolContext): Promise<ToolResult> { try { return { ok: true, output: await client.callTool(definition.name, params, context.signal) }; } catch (error) { const message = error instanceof Error ? error.message : String(error); return { ok: false, output: "", error: message, errorType: /timed out/i.test(message) ? "timeout" : "runtime_error" }; } } };
}

export type McpServerConfig = { command?: string; args?: string[]; env?: Record<string, string>; host?: string; port?: number; enabled?: boolean; timeout_ms?: number };
export class McpManager {
  private readonly clients: McpClient[] = []; private readonly tools: Tool[] = []; private readonly states: Array<{ name: string; status: string; tool_count: number; error?: string }> = [];
  constructor(private readonly configPath = process.env.SZTU_MCP_CONFIG ?? "") {}
  async load(): Promise<void> {
    if (!this.configPath) return;
    let servers: Record<string, McpServerConfig>; try { const { readFile } = await import("node:fs/promises"); const payload = JSON.parse(await readFile(this.configPath, "utf8")) as { mcpServers?: Record<string, McpServerConfig> }; servers = payload.mcpServers ?? {}; } catch { return; }
    for (const [name, config] of Object.entries(servers)) {
      if (config.enabled === false) continue; const client = new McpClient(config.timeout_ms);
      try { if (config.command) await client.connectStdio(config.command, config.args ?? [], config.env ?? {}); else if (config.host && config.port) await client.connectTcp(config.host, config.port); else throw new Error("command or host/port is required"); const definitions = await client.listTools(); this.clients.push(client); this.tools.push(...definitions.map((definition) => mcpTool(client, definition, `mcp__${name}`))); this.states.push({ name, status: "connected", tool_count: definitions.length }); } catch (error) { await client.close(); this.states.push({ name, status: "failed", tool_count: 0, error: error instanceof Error ? error.message : String(error) }); }
    }
  }
  listTools(): Tool[] { return [...this.tools]; }
  statuses(): Array<{ name: string; status: string; tool_count: number; error?: string }> { return [...this.states]; }
  async close(): Promise<void> { await Promise.all(this.clients.map((client) => client.close())); this.clients.length = 0; this.tools.length = 0; this.states.length = 0; }
}
