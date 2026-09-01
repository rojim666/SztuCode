/**
 * 手动启动 WebSocket-to-TCP 代理服务器
 * 用法: node ws-proxy.mjs
 */
import { WebSocketServer } from "ws";
import net from "net";
import { spawn } from "node:child_process";

const DAEMON_HOST = "127.0.0.1";
const DAEMON_PORT = 7438;
const WS_PORT = 7439;

function isPortListening(host, port) {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    const done = (result) => { socket.destroy(); resolve(result); };
    socket.once("connect", () => done(true));
    socket.once("error", () => done(false));
    socket.connect(port, host);
  });
}

async function ensureDaemon() {
  if (await isPortListening(DAEMON_HOST, DAEMON_PORT)) {
    console.log(`[ws-proxy] daemon already running on port ${DAEMON_PORT}`);
    return;
  }
  console.log("[ws-proxy] starting daemon...");
  const { execPath } = process;
  const daemonEntry = new URL("../packages/runtime-ts/dist/main.js", import.meta.url);
  const child = spawn(execPath, [daemonEntry], {
    env: { ...process.env, SZTU_TS_PORT: String(DAEMON_PORT) },
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.stdout.on("data", (chunk) => process.stdout.write(`[daemon] ${chunk}`));
  child.stderr.on("data", (chunk) => process.stderr.write(`[daemon] ${chunk}`));
  child.on("exit", (code) => console.log("[ws-proxy] daemon exited with code", code));
  for (let i = 0; i < 60; i++) {
    await new Promise((r) => setTimeout(r, 250));
    if (await isPortListening(DAEMON_HOST, DAEMON_PORT)) {
      console.log(`[ws-proxy] daemon is ready on port ${DAEMON_PORT}`);
      return;
    }
  }
}

await ensureDaemon();

const wss = new WebSocketServer({ port: WS_PORT });
console.log(`[ws-proxy] WebSocket proxy listening on ws://${DAEMON_HOST}:${WS_PORT}`);

wss.on("connection", (ws) => {
  console.log("[ws-proxy] browser connected");
  const tcp = net.createConnection({ host: DAEMON_HOST, port: DAEMON_PORT }, () => {
    console.log("[ws-proxy] tcp connection to daemon established");
  });

  ws.on("message", (data) => {
    const msg = data.toString();
    tcp.write(msg);
    if (!msg.endsWith("\n")) tcp.write("\n");
  });

  let buffer = "";
  tcp.on("data", (chunk) => {
    buffer += chunk.toString();
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed && ws.readyState === ws.OPEN) ws.send(trimmed);
    }
  });

  const cleanup = (reason) => {
    console.log("[ws-proxy] connection closed:", reason);
    try { ws.close(); } catch {}
    try { tcp.destroy(); } catch {}
  };

  tcp.on("error", (err) => cleanup(`tcp error: ${err.message}`));
  tcp.on("end", () => cleanup("tcp ended"));
  tcp.on("close", () => cleanup("tcp closed"));
  ws.on("error", (err) => cleanup(`ws error: ${err.message}`));
  ws.on("close", () => cleanup("ws closed"));
});
