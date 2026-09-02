import assert from "node:assert/strict";
import net from "node:net";
import test from "node:test";
import { mkdtemp, writeFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { McpClient, McpManager, mcpTool, mcpToolPermission, type McpToolDefinition } from "../src/mcp.js";

test("MCP negotiates the current protocol, preserves non-text content, and defaults to askable permission", async () => {
  let protocolVersion = "";
  const server = net.createServer((socket) => {
    let buffer = ""; socket.setEncoding("utf8"); socket.on("data", (chunk) => {
      buffer += chunk; let newline = buffer.indexOf("\n");
      while (newline >= 0) {
        const request = JSON.parse(buffer.slice(0, newline)); buffer = buffer.slice(newline + 1); newline = buffer.indexOf("\n");
        if (request.method === "initialize") protocolVersion = request.params.protocolVersion;
        if (request.id) socket.write(`${JSON.stringify({ jsonrpc: "2.0", id: request.id, result: request.method === "tools/call" ? { content: [{ type: "text", text: "ok" }, { type: "image", data: "abc", mimeType: "image/png" }] } : {} })}\n`);
      }
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address(); if (!address || typeof address === "string") throw new Error("missing server address");
  const client = new McpClient(200);
  try {
    await client.connectTcp("127.0.0.1", address.port);
    const output = await client.callTool("inspect", {});
    assert.equal(protocolVersion, "2025-06-18"); assert.match(output, /^ok\n/); assert.match(output, /"type":"image"/);
    assert.equal(mcpTool(client, { name: "inspect", description: "inspect", inputSchema: { type: "object" } }).permission, "workspace_write");
  } finally { await client.close(); await new Promise<void>((resolve) => server.close(() => resolve())); }
});

test("MCP calls have a deadline", async () => {
  const server = net.createServer((socket) => { socket.setEncoding("utf8"); socket.once("data", (chunk) => { const request = JSON.parse(String(chunk).split("\n")[0]!); socket.write(`${JSON.stringify({ jsonrpc: "2.0", id: request.id, result: {} })}\n`); }); });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address(); if (!address || typeof address === "string") throw new Error("missing server address");
  const client = new McpClient(20);
  try { await client.connectTcp("127.0.0.1", address.port); await assert.rejects(client.callTool("hang", {}), /timed out/); }
  finally { await client.close(); await new Promise<void>((resolve) => server.close(() => resolve())); }
});

// 公共的 until 轮询助手：等待条件成立或超时
const until = async (check: () => boolean, ms = 3000): Promise<void> => { const deadline = Date.now() + ms; while (!check()) { if (Date.now() > deadline) throw new Error("timed out waiting for condition"); await new Promise((resolve) => setTimeout(resolve, 10)); } };
// stdio 测试服务器：响应 initialize / tools/list，tools/call 时先向 stderr 写 256KB 日志并等待 drain 后才响应（父进程不排空 stderr 则子进程永远等不到 drain，形成死锁）
const drainScript = `let buf="";process.stdin.setEncoding("utf8");process.stdin.on("data",(c)=>{buf+=c;let i;while((i=buf.indexOf("\\n"))>=0){const line=buf.slice(0,i);buf=buf.slice(i+1);let m;try{m=JSON.parse(line);}catch(e){continue;}if(m.method==="initialize"){process.stdout.write(JSON.stringify({jsonrpc:"2.0",id:m.id,result:{capabilities:{}}})+"\\n");}else if(m.method==="tools/list"){process.stdout.write(JSON.stringify({jsonrpc:"2.0",id:m.id,result:{tools:[{name:"echo",description:"echo",inputSchema:{type:"object"}}]}})+"\\n");}else if(m.method==="tools/call"){const respond=()=>process.stdout.write(JSON.stringify({jsonrpc:"2.0",id:m.id,result:{content:[{type:"text",text:"drained"}]}})+"\\n");const ok=process.stderr.write("L".repeat(262144));if(ok){respond();}else{process.stderr.once("drain",respond);}}}});`;
// stdio 测试服务器：tools/call 时向 stderr 写诊断标记，等 100ms 确保父进程消费完 stderr 数据后再退出（验证退出错误携带 stderr 尾部）
const crashScript = `let buf="";process.stdin.setEncoding("utf8");process.stdin.on("data",(c)=>{buf+=c;let i;while((i=buf.indexOf("\\n"))>=0){const line=buf.slice(0,i);buf=buf.slice(i+1);let m;try{m=JSON.parse(line);}catch(e){continue;}if(m.method==="initialize"){process.stdout.write(JSON.stringify({jsonrpc:"2.0",id:m.id,result:{capabilities:{}}})+"\\n");}else if(m.method==="tools/call"){const die=()=>setTimeout(()=>process.exit(3),100);const ok=process.stderr.write("BOOM-MARKER fatal server detail");if(ok){die();}else{process.stderr.once("drain",die);}}}});`;

test("MCP stdio drains stderr so chatty servers do not deadlock the client", async () => {
  const client = new McpClient({ timeoutMs: 5000, reconnectDelaysMs: [10] });
  const started = Date.now();
  try {
    await client.connectStdio(process.execPath, ["-e", drainScript]);
    assert.equal(await client.callTool("echo", {}), "drained"); // stderr 未排空时该调用会卡到超时
    assert.ok(Date.now() - started < 5000, "stdio call should not deadlock");
  } finally { await client.close(); }
});

test("MCP stdio exit errors carry the stderr tail and reconnect respawns the server", async () => {
  const client = new McpClient({ timeoutMs: 5000, reconnectDelaysMs: [10, 10, 10] });
  try {
    await client.connectStdio(process.execPath, ["-e", crashScript]);
    // 第一次调用被进程退出拒绝（带 stderr 尾部）→ 自动重连并重试 → 子进程再次退出 → 抛出含标记的错误
    await assert.rejects(client.callTool("hang", {}), (error: Error) => /BOOM-MARKER/.test(error.message) && /stderr tail/.test(error.message));
  } finally { await client.close(); }
});

test("MCP reconnects with backoff after the connection drops and retries the request", async () => {
  const sockets: net.Socket[] = []; let connections = 0;
  const server = net.createServer((socket) => {
    connections += 1; sockets.push(socket); let buffer = ""; socket.setEncoding("utf8");
    socket.on("data", (chunk) => { buffer += chunk; let newline = buffer.indexOf("\n"); while (newline >= 0) { const request = JSON.parse(buffer.slice(0, newline)); buffer = buffer.slice(newline + 1); newline = buffer.indexOf("\n"); if (request.id !== undefined) socket.write(`${JSON.stringify({ jsonrpc: "2.0", id: request.id, result: request.method === "tools/call" ? { content: [{ type: "text", text: "after-reconnect" }] } : {} })}\n`); } });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address(); if (!address || typeof address === "string") throw new Error("missing server address");
  const client = new McpClient({ timeoutMs: 2000, reconnectDelaysMs: [10, 10, 10] });
  try {
    await client.connectTcp("127.0.0.1", address.port); assert.equal(client.connected, true);
    sockets[0]!.destroy(); // 模拟服务器断开
    assert.equal(await client.callTool("ping", {}), "after-reconnect"); // 断开后自动重连并重试成功
    await until(() => connections >= 2); assert.equal(client.connected, true); assert.equal(connections, 2);
  } finally { await client.close(); await new Promise<void>((resolve) => server.close(() => resolve())); }
});

test("MCP reconnect failures surface the last error after the retry budget is spent", async () => {
  const sockets: net.Socket[] = [];
  const server = net.createServer((socket) => { sockets.push(socket); socket.setEncoding("utf8"); socket.on("data", (chunk) => { const line = String(chunk).split("\n")[0]!; const request = JSON.parse(line); if (request.id !== undefined) socket.write(`${JSON.stringify({ jsonrpc: "2.0", id: request.id, result: {} })}\n`); }); });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address(); if (!address || typeof address === "string") throw new Error("missing server address");
  const client = new McpClient({ timeoutMs: 2000, reconnectDelaysMs: [10, 10, 10] });
  try {
    await client.connectTcp("127.0.0.1", address.port);
    sockets[0]!.destroy(); // 先断开既有连接：server.close(cb) 会等待活动连接关闭，必须先断开再关闭监听，否则互相死锁
    await new Promise<void>((resolve) => server.close(resolve)); // 再无活动连接，回调立即触发；重连必然失败
    await assert.rejects(client.callTool("ping", {}), (error: Error) => /ECONNREFUSED|refused/i.test(error.message));
    assert.equal(client.connected, false); assert.ok(client.lastError); // 保留最后一次错误
  } finally { await client.close(); }
});

test("MCP refreshes the tool cache on tools/list_changed and ignores unknown notifications", async () => {
  let listCalls = 0;
  const server = net.createServer((socket) => {
    let buffer = ""; socket.setEncoding("utf8");
    socket.on("data", (chunk) => {
      buffer += chunk; let newline = buffer.indexOf("\n");
      while (newline >= 0) {
        const request = JSON.parse(buffer.slice(0, newline)); buffer = buffer.slice(newline + 1); newline = buffer.indexOf("\n");
        if (request.method === "tools/list") { listCalls += 1; const tools = listCalls === 1 ? [{ name: "a", description: "a", inputSchema: { type: "object" } }] : [{ name: "a", description: "a", inputSchema: { type: "object" } }, { name: "b", description: "b", inputSchema: { type: "object" } }]; socket.write(`${JSON.stringify({ jsonrpc: "2.0", id: request.id, result: { tools } })}\n`); if (listCalls === 1) { socket.write(`${JSON.stringify({ jsonrpc: "2.0", method: "notifications/tools/list_changed" })}\n`); socket.write(`${JSON.stringify({ jsonrpc: "2.0", method: "notifications/mystery" })}\n`); } }
        else if (request.id !== undefined) socket.write(`${JSON.stringify({ jsonrpc: "2.0", id: request.id, result: {} })}\n`);
      }
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address(); if (!address || typeof address === "string") throw new Error("missing server address");
  const changed: McpToolDefinition[][] = [];
  const client = new McpClient({ timeoutMs: 2000, reconnectDelaysMs: [10], onToolsChanged: (tools) => changed.push(tools) });
  try {
    await client.connectTcp("127.0.0.1", address.port);
    assert.deepEqual((await client.listTools()).map((tool) => tool.name), ["a"]);
    await until(() => changed.length > 0); // list_changed 触发自动刷新与回调
    assert.deepEqual(changed[0]!.map((tool) => tool.name), ["a", "b"]);
    assert.deepEqual(client.toolCache.map((tool) => tool.name), ["a", "b"]);
    assert.equal(client.connected, true); // 未知通知被忽略且不抛错
  } finally { await client.close(); await new Promise<void>((resolve) => server.close(() => resolve())); }
});

test("MCP stores negotiated server capabilities and records listChanged=false", async () => {
  const server = net.createServer((socket) => { socket.setEncoding("utf8"); socket.on("data", (chunk) => { const line = String(chunk).split("\n")[0]!; const request = JSON.parse(line); if (request.id !== undefined) socket.write(`${JSON.stringify({ jsonrpc: "2.0", id: request.id, result: request.method === "initialize" ? { capabilities: { tools: { listChanged: false } } } : {} })}\n`); }); });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address(); if (!address || typeof address === "string") throw new Error("missing server address");
  const client = new McpClient(2000);
  try {
    await client.connectTcp("127.0.0.1", address.port);
    assert.deepEqual(client.serverCapabilities, { tools: { listChanged: false } }); // 能力被保存并只读暴露
    assert.equal(client.toolsListChangedSupported, false); // listChanged=false 事实被记录
  } finally { await client.close(); await new Promise<void>((resolve) => server.close(() => resolve())); }
});

test("mcpTool splits permissions between read-only and write tools", () => {
  // annotations.readOnlyHint=true 提升为只读；false 不否决命名列表中的观测工具（chrome-devtools-mcp 会把快照/截图误标为 false）
  assert.equal(mcpToolPermission({ name: "click", description: "", inputSchema: {}, annotations: { readOnlyHint: true } }), "read_only");
  assert.equal(mcpToolPermission({ name: "take_snapshot", description: "", inputSchema: {}, annotations: { readOnlyHint: false } }), "read_only");
  // 命名启发式：快照/截图/列表/查询类只读免确认，交互写操作保持询问
  assert.equal(mcpToolPermission({ name: "take_snapshot", description: "", inputSchema: {} }), "read_only");
  assert.equal(mcpToolPermission({ name: "take_screenshot", description: "", inputSchema: {} }), "read_only");
  assert.equal(mcpToolPermission({ name: "list_pages", description: "", inputSchema: {} }), "read_only");
  assert.equal(mcpToolPermission({ name: "get_console_message", description: "", inputSchema: {} }), "read_only");
  assert.equal(mcpToolPermission({ name: "click", description: "", inputSchema: {} }), "workspace_write");
  assert.equal(mcpToolPermission({ name: "fill", description: "", inputSchema: {} }), "workspace_write");
  assert.equal(mcpToolPermission({ name: "navigate_page", description: "", inputSchema: {} }), "workspace_write");
});

test("mcpTool routes image content to structured images and keeps base64 out of text output", async () => {
  const imageData = Buffer.from("fake-png-bytes").toString("base64");
  const server = net.createServer((socket) => { let buffer = ""; socket.setEncoding("utf8"); socket.on("data", (chunk) => { buffer += chunk; let newline = buffer.indexOf("\n"); while (newline >= 0) { const request = JSON.parse(buffer.slice(0, newline)); buffer = buffer.slice(newline + 1); newline = buffer.indexOf("\n"); if (request.id !== undefined) socket.write(`${JSON.stringify({ jsonrpc: "2.0", id: request.id, result: request.method === "tools/call" ? { content: [{ type: "text", text: "page captured" }, { type: "image", data: imageData, mimeType: "image/png" }] } : {} })}\n`); } }); });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address(); if (!address || typeof address === "string") throw new Error("missing server address");
  const client = new McpClient(2000);
  try {
    await client.connectTcp("127.0.0.1", address.port);
    const tool = mcpTool(client, { name: "take_screenshot", description: "", inputSchema: { type: "object" } });
    assert.equal(tool.permission, "read_only"); // 只读截图免确认
    const result = await tool.invoke({}, {} as never);
    assert.ok(result.ok);
    assert.deepEqual(result.images, [{ mimeType: "image/png", data: imageData }]); // 图片结构化传递
    assert.match(result.output, /page captured/);
    assert.match(result.output, /\[图片 image\/png/); // LLM 上下文只留占位符
    assert.ok(!result.output.includes(imageData), "base64 不应进入文本输出");
  } finally { await client.close(); await new Promise<void>((resolve) => server.close(() => resolve())); }
});

test("McpManager loads servers in parallel and isolates per-server failures", async () => {
  const server = net.createServer((socket) => { let buffer = ""; socket.setEncoding("utf8"); socket.on("data", (chunk) => { buffer += chunk; let newline = buffer.indexOf("\n"); while (newline >= 0) { const request = JSON.parse(buffer.slice(0, newline)); buffer = buffer.slice(newline + 1); newline = buffer.indexOf("\n"); if (request.id !== undefined) socket.write(`${JSON.stringify({ jsonrpc: "2.0", id: request.id, result: request.method === "tools/list" ? { tools: [{ name: "echo", description: "echo", inputSchema: { type: "object" } }] } : {} })}\n`); } }); });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address(); if (!address || typeof address === "string") throw new Error("missing server address");
  const placeholder = net.createServer(); await new Promise<void>((resolve) => placeholder.listen(0, "127.0.0.1", resolve));
  const deadAddress = placeholder.address(); if (!deadAddress || typeof deadAddress === "string") throw new Error("missing placeholder address"); const deadPort = deadAddress.port;
  await new Promise<void>((resolve) => placeholder.close(() => resolve())); // 该端口无人监听，bad 服务器必然连接失败
  const directory = await mkdtemp(path.join(os.tmpdir(), "sztu-mcp-manager-")); const configPath = path.join(directory, "mcp.json");
  await writeFile(configPath, JSON.stringify({ mcpServers: { good: { host: "127.0.0.1", port: address.port, timeout_ms: 2000 }, bad: { host: "127.0.0.1", port: deadPort, timeout_ms: 500 }, off: { host: "127.0.0.1", port: address.port, enabled: false } } }), "utf8");
  const manager = new McpManager(configPath);
  try {
    await manager.load(); // 并行连接：bad 失败不阻塞 good
    const status = manager.status(); const good = status.find((item) => item.name === "good"); const bad = status.find((item) => item.name === "bad");
    assert.ok(good && bad); assert.equal(status.length, 2); // enabled=false 的 off 不加载
    assert.deepEqual({ connected: good!.connected, transport: good!.transport, toolCount: good!.toolCount }, { connected: true, transport: "tcp", toolCount: 1 });
    assert.equal(bad!.connected, false); assert.equal(bad!.toolCount, 0); assert.ok(bad!.error); // 失败服务器记录错误且工具集为空
    assert.deepEqual(manager.listTools().map((tool) => tool.name), ["mcp__good__echo"]);
    assert.deepEqual(manager.statuses().find((item) => item.name === "good"), { name: "good", status: "connected", tool_count: 1, error: undefined }); // 旧 statuses() 形状兼容
  } finally { await manager.close(); await new Promise<void>((resolve) => server.close(() => resolve())); await rm(directory, { recursive: true, force: true }); }
});
