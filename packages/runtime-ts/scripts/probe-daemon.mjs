// 探活脚本：验证 daemon 在收到无效 HTTP 探测后仍能正常响应 JSON-RPC
import net from "node:net";

const request = { jsonrpc: "2.0", id: "probe-1", method: "core.ping", params: { client: "probe-script" } };
const socket = net.createConnection({ host: "127.0.0.1", port: 7438 });
let buffer = "";
const timeout = setTimeout(() => { console.error("probe timed out"); socket.destroy(); process.exit(1); }, 8000);
socket.on("connect", () => socket.write(`${JSON.stringify(request)}\n`));
socket.on("data", (chunk) => {
  buffer += chunk.toString("utf8");
  const newline = buffer.indexOf("\n");
  if (newline < 0) return;
  clearTimeout(timeout);
  const message = JSON.parse(buffer.slice(0, newline));
  console.log("probe response:", JSON.stringify(message));
  socket.destroy();
  process.exit(message.error ? 1 : 0);
});
socket.on("error", (error) => { clearTimeout(timeout); console.error("probe error:", error.message); process.exit(1); });
