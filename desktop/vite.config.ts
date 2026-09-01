/**
 * Vite 开发服务器配置
 *
 * 内置 WebSocket-to-TCP 代理，自动启动 daemon。
 * 只需运行 `npx vite` 即可，无需单独启动其他进程。
 */
import { defineConfig, type Plugin } from "vite";
import vue from "@vitejs/plugin-vue";
import { spawn } from "node:child_process";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { WebSocketServer } from "ws";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DAEMON_HOST = "127.0.0.1";
const DAEMON_PORT = 7438;
const WS_PROXY_PORT = 7439;

function isPortListening(host: string, port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    const done = (result: boolean) => {
      try { socket.destroy(); } catch { /* ignore */ }
      resolve(result);
    };
    socket.once("connect", () => done(true));
    socket.once("error", () => done(false));
    socket.connect(port, host);
  });
}

async function ensureDaemon(): Promise<void> {
  if (await isPortListening(DAEMON_HOST, DAEMON_PORT)) {
    console.log("[sztu-dev] daemon already running on port", DAEMON_PORT);
    return;
  }
  const daemonEntry = path.resolve(__dirname, "../packages/runtime-ts/dist/main.js");
  console.log("[sztu-dev] starting daemon:", daemonEntry);
  const child = spawn(process.execPath, [daemonEntry], {
    env: { ...process.env, SZTU_TS_PORT: String(DAEMON_PORT) },
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.stdout.on("data", (chunk) => process.stdout.write(`[daemon] ${chunk}`));
  child.stderr.on("data", (chunk) => process.stderr.write(`[daemon] ${chunk}`));
  child.on("exit", (code) => console.log("[sztu-dev] daemon exited with code", code));
  for (let i = 0; i < 60; i++) {
    await new Promise((r) => setTimeout(r, 250));
    if (await isPortListening(DAEMON_HOST, DAEMON_PORT)) {
      console.log("[sztu-dev] daemon is ready on port", DAEMON_PORT);
      return;
    }
  }
  console.warn("[sztu-dev] daemon did not become ready in time");
}

function startWsProxy(): void {
  // 先检测端口是否已被占用，如果是则跳过
  const testServer = net.createServer();
  testServer.once("error", (err: NodeJS.ErrnoException) => {
    if (err.code === "EADDRINUSE") {
      console.log(`[sztu-dev] WebSocket proxy port ${WS_PROXY_PORT} already in use, assuming existing proxy is running`);
    } else {
      console.error("[sztu-dev] port check error:", err);
    }
  });
  testServer.once("listening", () => {
    testServer.close(() => {
      // 端口空闲，启动 WebSocket 代理
      const wss = new WebSocketServer({ port: WS_PROXY_PORT });
      console.log(`[sztu-dev] WebSocket proxy listening on ws://${DAEMON_HOST}:${WS_PROXY_PORT}`);

      wss.on("connection", (ws) => {
        console.log("[sztu-dev] browser websocket connected, connecting to daemon...");
        const tcp = net.createConnection({ host: DAEMON_HOST, port: DAEMON_PORT }, () => {
          console.log("[sztu-dev] tcp connection to daemon established");
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

        const cleanup = (reason: string) => {
          console.log("[sztu-dev] ws-tcp proxy closed:", reason);
          try { ws.close(); } catch { /* ignore */ }
          try { tcp.destroy(); } catch { /* ignore */ }
        };

        tcp.on("error", (tErr) => cleanup(`tcp error: ${tErr.message}`));
        tcp.on("end", () => cleanup("tcp ended"));
        tcp.on("close", () => cleanup("tcp closed"));
        ws.on("error", (wErr) => cleanup(`ws error: ${wErr.message}`));
        ws.on("close", () => cleanup("ws closed"));
      });

      wss.on("error", (wErr: NodeJS.ErrnoException) => {
        console.error("[sztu-dev] WebSocket proxy error:", wErr);
      });
    });
  });
  testServer.listen(WS_PROXY_PORT, DAEMON_HOST);
}

function sztuDevPlugin(): Plugin {
  let started = false;
  return {
    name: "sztu-dev-proxy",
    configureServer() {
      if (started) return;
      started = true;
      void ensureDaemon();
      startWsProxy();
    },
  };
}

export default defineConfig({
  plugins: [vue(), sztuDevPlugin()],
  clearScreen: false,
  server: {
    port: 5174,
    strictPort: false,
    host: "127.0.0.1",
  },
  envPrefix: ["VITE_", "TAURI_"],
  build: {
    target: "es2022",
    minify: !process.env.TAURI_DEBUG ? "esbuild" : false,
    sourcemap: !!process.env.TAURI_DEBUG,
  },
});
