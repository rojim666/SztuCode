import { useCallback, useRef, useState } from "react";
import { IpcClient } from "../lib/ipc";
import type { Session, Workspace } from "../types";
import { errorText } from "../types";

/** 会话管理（创建、恢复、列表、重命名、归档、固定） */
export function useSessions(client: IpcClient) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const sessionRef = useRef<string | null>(null);
  const selectionRef = useRef(0);

  sessionRef.current = sessionId;

  // 刷新会话列表
  const refreshSessions = useCallback(async () => {
    const result = await client.request("session.list", { limit: 50 });
    setSessions((result.sessions as Session[]) ?? []);
  }, [client]);

  // 选择/恢复会话
  const selectSession = useCallback(
    async (id: string, { announce = true } = {}): Promise<Session | undefined> => {
      const selection = ++selectionRef.current;
      setSessionId(id);
      sessionRef.current = id;
      try {
        const resumed = await client.request("session.resume", { session_id: id });
        if (selection !== selectionRef.current) return undefined;
        const session = resumed.session as Session | undefined;
        return session;
      } catch (error) {
        if (selection === selectionRef.current)
          console.error(`恢复任务失败：${errorText(error)}`);
        return undefined;
      }
    },
    [client],
  );

  // 选择会话并获取历史消息
  const selectSessionWithHistory = useCallback(
    async (
      id: string,
      { announce = true } = {},
    ): Promise<{ session?: Session; messages: unknown[] }> => {
      const selection = ++selectionRef.current;
      setSessionId(id);
      sessionRef.current = id;
      try {
        const [resumed, history] = await Promise.all([
          client.request("session.resume", { session_id: id }),
          client.request("session.get_history", { session_id: id }),
        ]);
        if (selection !== selectionRef.current) return { messages: [] };
        return {
          session: resumed.session as Session | undefined,
          messages: (history.messages as unknown[]) ?? [],
        };
      } catch (error) {
        if (selection === selectionRef.current)
          console.error(`恢复任务失败：${errorText(error)}`);
        return { messages: [] };
      }
    },
    [client],
  );

  // 创建新任务
  const newTask = useCallback(
    async (workspace: Workspace | null, setNotice: (msg: string) => void) => {
      if (!workspace) {
        setNotice("请先选择工作区，再创建任务。这样执行上下文、文件和变更才会保持一致。");
        return undefined;
      }
      try {
        const result = await client.request("session.create", {
          mode: "chat",
          title: "",
          workspace_id: workspace.workspace_id,
        });
        ++selectionRef.current;
        const nextId = String(result.session_id);
        setSessionId(nextId);
        sessionRef.current = nextId;
        await refreshSessions();
        setNotice("新任务已创建。描述希望 Agent 在工作区完成的目标。");
        return nextId;
      } catch (error) {
        setNotice(`创建任务失败：${errorText(error)}`);
        return undefined;
      }
    },
    [client, refreshSessions],
  );

  // 提交消息并开始运行
  const sendMessage = useCallback(
    async (
      content: string,
      workspace: Workspace | null,
      setNotice: (msg: string) => void,
    ): Promise<{ sessionId: string; runId: string } | null> => {
      if (!workspace) {
        setNotice("请先选择工作区，这样任务、文件和变更才会归属同一个仓库。");
        return null;
      }
      let target = sessionRef.current;
      if (!target) {
        const created = await client.request("session.create", {
          mode: "chat",
          title: content.slice(0, 40),
          workspace_id: workspace.workspace_id,
        });
        target = String(created.session_id);
        setSessionId(target);
        sessionRef.current = target;
        await refreshSessions();
      }
      try {
        const result = await client.request("session.send_message", {
          session_id: target,
          content,
        });
        return { sessionId: target, runId: String(result.run_id) };
      } catch (error) {
        setNotice(`发送失败：${errorText(error)}`);
        return null;
      }
    },
    [client, refreshSessions],
  );

  // 重命名
  const renameTask = useCallback(
    async (id: string, title: string, setNotice: (msg: string) => void) => {
      try {
        await client.request("session.rename", { session_id: id, title });
        await refreshSessions();
        setNotice("任务名称已更新。");
      } catch (error) {
        setNotice(`重命名失败：${errorText(error)}`);
      }
    },
    [client, refreshSessions],
  );

  // 归档
  const archiveTask = useCallback(
    async (id: string, setNotice: (msg: string) => void) => {
      try {
        await client.request("session.archive", { session_id: id });
        ++selectionRef.current;
        setSessionId(null);
        sessionRef.current = null;
        await refreshSessions();
        setNotice("任务已归档；历史记录和运行回放仍会保留在本机。");
      } catch (error) {
        setNotice(`归档失败：${errorText(error)}`);
      }
    },
    [client, refreshSessions],
  );

  // 固定/取消固定
  const togglePin = useCallback(
    async (id: string, pinned: boolean, setNotice: (msg: string) => void) => {
      try {
        await client.request("session.pin", { session_id: id, pinned });
        await refreshSessions();
        setNotice(pinned ? "任务已固定在侧栏顶部。" : "任务已从固定区移回最近任务。");
      } catch (error) {
        setNotice(`更新固定状态失败：${errorText(error)}`);
      }
    },
    [client, refreshSessions],
  );

  return {
    sessions,
    sessionId,
    sessionRef,
    selectionRef,
    setSessionId,
    refreshSessions,
    selectSession,
    selectSessionWithHistory,
    newTask,
    sendMessage,
    renameTask,
    archiveTask,
    togglePin,
  };
}
