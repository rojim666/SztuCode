import net from "node:net";
import type { ClientTransportFactory } from "./transport.js";

export interface TcpClientOptions { host?: string; port?: number; connectTimeoutMs?: number }

/** Node TCP adapter. Browser/desktop callers can provide their own bridge factory. */
export function createTcpTransportFactory(options: TcpClientOptions = {}): ClientTransportFactory {
  const host = options.host ?? process.env.SZTU_TS_HOST ?? process.env.SZTU_HOST ?? "127.0.0.1";
  const port = options.port ?? Number(process.env.SZTU_TS_PORT ?? process.env.SZTU_PORT ?? 7438);
  const timeoutMs = options.connectTimeoutMs ?? 10_000;
  return (handlers) => new Promise((resolve, reject) => {
    const socket = net.createConnection({ host, port });
    let settled = false;
    const fail = (error: Error) => { if (!settled) { settled = true; reject(error); } else handlers.onError(error); socket.destroy(); };
    const timer = setTimeout(() => fail(new Error(`Unable to connect to ${host}:${port}`)), timeoutMs); timer.unref?.();
    socket.once("connect", () => {
      clearTimeout(timer); settled = true; socket.off("error", fail); socket.setEncoding("utf8");
      socket.on("data", (chunk: string) => handlers.onData(chunk));
      socket.on("close", () => handlers.onClose());
      socket.on("error", (error) => handlers.onError(error));
      resolve({ send: (frame) => new Promise<void>((res, rej) => socket.write(frame, (error) => error ? rej(error) : res())), close: () => { socket.destroy(); } });
    });
    socket.once("error", fail);
  });
}
