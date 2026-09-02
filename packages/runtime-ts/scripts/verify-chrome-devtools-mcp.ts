// 浏览器 MCP 链路验证：McpManager 加载 chrome-devtools-mcp → 连接 → 列工具 → 导航 → 快照
// 用法：npm run verify:browser-mcp  （首次运行 npx 会下载 chrome-devtools-mcp，耗时较长）
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { McpManager } from "../src/mcp.js";
import type { ToolContext } from "../src/tools.js";

const packageRoot = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const configPath = process.argv[2] ?? path.join(packageRoot, "mcp.chrome-devtools.json");
const context = { signal: AbortSignal.timeout(60_000) } as ToolContext;

const manager = new McpManager(configPath);
try {
  console.log(`[1/4] loading MCP servers from ${configPath}`);
  await manager.load();
  const server = manager.status().find((item) => item.name === "chrome-devtools");
  assert.ok(server, "config 中缺少 chrome-devtools 服务器");
  assert.ok(server.connected, `chrome-devtools 连接失败: ${server.error ?? "unknown"}`);
  console.log(`[2/4] connected via ${server.transport}, ${server.toolCount} tools`);

  const tools = manager.listTools();
  for (const tool of tools) console.log(`  - ${tool.name}`);
  const navigate = tools.find((tool) => tool.name === "mcp__chrome-devtools__navigate_page");
  const snapshot = tools.find((tool) => tool.name === "mcp__chrome-devtools__take_snapshot");
  assert.ok(navigate && snapshot, "缺少 navigate_page / take_snapshot 工具");

  console.log("[3/4] opening a data: URL page");
  const newPage = tools.find((tool) => tool.name === "mcp__chrome-devtools__new_page");
  assert.ok(newPage, "缺少 new_page 工具");
  const pageResult = await newPage.invoke({ url: "data:text/html,<title>sztu-mcp-ok</title><h1>browser chain ok</h1>" }, context);
  assert.ok(pageResult.ok, `new_page 失败: ${pageResult.error ?? pageResult.output}`);
  const pageId = /^(\d+): .*\[selected\]/m.exec(pageResult.output);
  assert.ok(pageId, `无法从 new_page 输出解析 pageId:\n${pageResult.output.slice(0, 400)}`);
  const page = Number(pageId[1]);
  console.log(`  page created, pageId=${page}`);

  console.log("[4/4] taking page snapshot");
  const snapResult = await snapshot.invoke({ pageId: page }, context);
  assert.ok(snapResult.ok, `take_snapshot 失败: ${snapResult.error ?? snapResult.output}`);
  assert.match(snapResult.output, /browser chain ok/i);
  console.log(`snapshot excerpt:\n${snapResult.output.slice(0, 400)}`);

  console.log("OK: browser MCP chain verified (connect -> tools -> navigate -> snapshot)");
} finally {
  await manager.close();
}
