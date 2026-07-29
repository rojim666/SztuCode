import { useCallback, useEffect, useRef, useState } from "react";
import { IpcClient, type IpcEvent } from "../lib/ipc";
import type { ConnectionState, DaemonStartResult } from "../types";
import { errorText } from "../types";
import { invoke } from "@tauri-apps/api/core";

const client = new IpcClient();
const topics = [
  "session.*", "run.*", "step.*", "tool.*", "llm.*",
  "permission.*", "context.*", "subagent.*", "change.*", "log.*",
];

// ── 全局单例 client 引用，供所有 hooks 共享 ──────────────
export function getClient(): IpcClient {
  return client;
}

// ── Hook: 守护进程连接 ────────────────────────────────────

export function useDaemonConnection(onEvent: (event: IpcEvent) => void) {
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [daemonStarting, setDaemonStarting] = useState(false);
  const [notice, setNotice] = useState("选择一个本地仓库，开始可审阅的编码任务。");
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  // 启动本地守护进程
  const startLocalService = useCallback(async () => {
    setDaemonStarting(true);
    setNotice("正在启动本地 Agent 服务…");
    try {
      const result = await invoke<DaemonStartResult>("daemon_start");
      setNotice(`${result.detail}，工作台将在连接就绪后自动恢复。`);
    } catch (error) {
      setNotice(`启动失败：${errorText(error)}`);
    } finally {
      setDaemonStarting(false);
    }
  }, []);

  // 连接 + 自动重连
  useEffect(() => {
    let stopped = false;
    let retryTimer: number | undefined;
    const reconnect = async () => {
      if (stopped) return;
      setConnection("connecting");
      try {
        await client.connect("127.0.0.1", 7437);
        await client.request("event.subscribe", { topics, scope: "global" });
        setConnection("ready");
      } catch (error) {
        setConnection("offline");
        setNotice(`本地服务暂不可用：${errorText(error)}。正在自动重试。`);
        retryTimer = window.setTimeout(() => void reconnect(), 2_000);
      }
    };
    const stopEvents = client.onEvent((event) => onEventRef.current(event));
    const stopDisconnect = client.onDisconnect((reason) => {
      if (stopped) return;
      setConnection("offline");
      setNotice(`连接已断开：${reason}。正在恢复工作台。`);
      window.clearTimeout(retryTimer);
      retryTimer = window.setTimeout(() => void reconnect(), 1_200);
    });
    void reconnect();
    return () => {
      stopped = true;
      window.clearTimeout(retryTimer);
      stopEvents();
      stopDisconnect();
      client.dispose();
    };
  }, []);

  return { client, connection, daemonStarting, notice, setNotice, startLocalService };
}
