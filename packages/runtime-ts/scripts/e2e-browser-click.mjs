// 桌面等价 E2E：浏览器点击任务全链路
// 复刻 desktop 与 daemon 的交互：session.create → event.subscribe → session.send_message → permission.respond
// 断言：浏览器工具被调用、写操作触发权限询问、只读工具免询问、截图以 images 下发
// 前置：daemon 已带 SZTU_MCP_CONFIG 启动（npm run dev）
import net from "node:net";

const DATA_URL = "data:text/html,<title>e2e</title><button id=\"b\" onclick=\"this.textContent='clicked-ok';document.title='clicked'\">go</button>";
const INSTRUCTION = `请严格按顺序使用浏览器 MCP 工具完成，不要省略步骤、不要调用其他工具：
1. 调用 mcp__chrome-devtools__new_page，参数 url = ${DATA_URL} ，记住返回的 pageId
2. 调用 mcp__chrome-devtools__take_snapshot（带 pageId），找到按钮 "go" 的 uid
3. 调用 mcp__chrome-devtools__click（带 pageId 和该 uid）点击按钮
4. 调用 mcp__chrome-devtools__take_screenshot（带 pageId）截图
完成后回复"任务完成"。`;

const socket = net.createConnection({ host: "127.0.0.1", port: 7438 });
let buffer = "";
let rpcId = 0;
const pending = new Map();
const send = (method, params) => new Promise((resolve, reject) => {
  const id = `e2e-${++rpcId}`;
  pending.set(id, { resolve, reject });
  socket.write(`${JSON.stringify({ jsonrpc: "2.0", id, method, params })}\n`);
});

const started = [];
const finished = new Map();
const permissionAsked = [];
const screenshotImages = [];
let runStatus = null;
let done;
const finishedPromise = new Promise((resolve) => { done = resolve; });

socket.on("data", (chunk) => {
  buffer += chunk.toString("utf8");
  let newline = buffer.indexOf("\n");
  while (newline >= 0) {
    const line = buffer.slice(0, newline).trim(); buffer = buffer.slice(newline + 1); newline = buffer.indexOf("\n");
    if (!line) continue;
    const message = JSON.parse(line);
    if (message.id !== undefined && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id); pending.delete(message.id);
      message.error ? reject(new Error(message.error.message)) : resolve(message.result);
      continue;
    }
    if (message.kind !== "event") continue;
    const event = message.event;
    if (event.type === "tool.call_started") { started.push(event.tool_name); console.log(`  [tool→] ${event.tool_name}`); }
    if (event.type === "tool.call_finished") {
      finished.set(event.tool_name, (finished.get(event.tool_name) ?? 0) + 1);
      if (event.tool_name === "mcp__chrome-devtools__take_screenshot" && Array.isArray(event.images) && event.images.length) {
        screenshotImages.push(...event.images);
        console.log(`  [tool✓] take_screenshot 携带 ${event.images.length} 张截图（${event.images[0].mimeType}）`);
      }
    }
    if (event.type === "permission.requested") {
      permissionAsked.push(event.tool_name);
      console.log(`  [权限?] ${event.tool_name} → allow_once`);
      void send("permission.respond", { permission_id: event.permission_id, decision: "allow_once" });
    }
    if (event.type === "run.finished") { runStatus = event.status; console.log(`  [run] finished: ${event.status}, steps=${event.steps}, tokens=${event.total_input_tokens}+${event.total_output_tokens}${event.reason ? `, reason=${event.reason}` : ""}`); done(); }
  }
});

const watchdog = setTimeout(() => { console.error("E2E 超时（300s）"); process.exit(1); }, 300_000);
await new Promise((resolve) => socket.on("connect", resolve));

console.log("[1/5] ping");
await send("core.ping", { client: "e2e-browser-click" });

console.log("[2/5] 选择免 key 模型（opencode zen mimo-v2.5-free，可用 MODEL_ID 覆盖）");
await send("provider.model_select", { model_id: process.env.MODEL_ID ?? "builtin-opencode-zen-mimo-v2.5-free" });

console.log("[3/5] 订阅事件 + 创建会话（权限模式临时切到 normal 以验证询问链路）");
await send("event.subscribe", { topics: ["*"] });
const previousSettings = await send("settings.get", {});
const previousMode = previousSettings.settings?.permission_mode ?? "auto";
await send("permission.set_mode", { mode: "normal" });
const created = await send("session.create", { mode: "chat", title: "browser-click-e2e" });
const sessionId = created.session?.id ?? created.session_id;
console.log(`  session=${sessionId}`);

console.log("[4/5] 发送浏览器点击指令");
await send("session.send_message", { session_id: sessionId, content: INSTRUCTION });

console.log("[5/5] 等待 run 完成…");
await finishedPromise;
clearTimeout(watchdog);
await send("permission.set_mode", { mode: previousMode }).catch(() => {}); // 恢复用户原权限模式

const called = (suffix) => started.includes(`mcp__chrome-devtools__${suffix}`);
const failures = [];
if (!called("new_page") && !called("navigate_page")) failures.push("未调用 new_page/navigate_page");
if (!called("click")) failures.push("未调用 click");
if (!screenshotImages.length) failures.push("take_screenshot 未携带 images");
if (!permissionAsked.some((name) => name === "mcp__chrome-devtools__click" || name === "mcp__chrome-devtools__new_page")) failures.push("写操作未触发权限询问");
if (permissionAsked.some((name) => name === "mcp__chrome-devtools__take_snapshot" || name === "mcp__chrome-devtools__take_screenshot")) failures.push("只读工具不应触发权限询问");
if (runStatus !== "success") failures.push(`run 状态异常: ${runStatus}`);

console.log("\n===== E2E 结果 =====");
console.log("调用过的工具:", started.join(", "));
console.log("权限询问过的工具:", permissionAsked.join(", ") || "(无)");
if (failures.length) { console.error("FAILED:\n - " + failures.join("\n - ")); process.exit(1); }
console.log("OK: 浏览器点击任务全链路通过（工具调用、权限细分、截图 images 下发均符合预期）");
process.exit(0);
