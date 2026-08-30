import assert from "node:assert/strict";
import net from "node:net";
import test from "node:test";
import { McpClient, mcpTool } from "../src/mcp.js";

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
