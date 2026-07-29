import { useCallback, useRef, useState } from "react";
import { IpcClient, type IpcEvent } from "../lib/ipc";
import type { TimelineItem, PlanItem, TestResult } from "../types";
import { historyToTimeline } from "../types";

/** 时间线管理（事件处理、流式 Token、计划、测试结果） */
export function useTimeline() {
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [planItems, setPlanItems] = useState<PlanItem[]>([]);
  const [testResults, setTestResults] = useState<TestResult[]>([]);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const activeRunRef = useRef<string | null>(null);
  const selectedRunRef = useRef<string | null>(null);
  const streamId = useRef<string | null>(null);
  const sessionRef = useRef<string | null>(null);

  activeRunRef.current = activeRunId;

  // 同步外部 sessionId 到内部 ref（用于事件过滤）
  const syncSessionId = useCallback((id: string | null) => {
    sessionRef.current = id;
  }, []);

  // 从历史加载时间线
  const loadHistory = useCallback((messages: unknown[]) => {
    setTimeline(historyToTimeline(messages));
  }, []);

  // 添加用户消息到时间线
  const addUserMessage = useCallback((content: string) => {
    setTimeline((items) => [
      ...items,
      { id: crypto.randomUUID(), kind: "user", body: content },
    ]);
  }, []);

  // 核心事件处理器
  const handleEvent = useCallback(
    (event: IpcEvent, callbacks?: {
      onRunStarted?: () => void;
      onRunFinished?: (runId: string, status: string, reason: string) => void;
      onSessionWaiting?: () => void;
    }) => {
      const type = String(event.type ?? "");
      if (event.session_id && event.session_id !== sessionRef.current) return;
      const expectedRun = activeRunRef.current ?? selectedRunRef.current;
      if (event.run_id && expectedRun && event.run_id !== expectedRun) return;

      // 流式 Token
      if (type === "llm.token") {
        const token = String(event.token ?? "");
        if (!token) return;
        const id = streamId.current ?? crypto.randomUUID();
        streamId.current = id;
        setTimeline((items) => {
          const last = items.at(-1);
          if (last?.id === id)
            return [...items.slice(0, -1), { ...last, body: last.body + token }];
          return [...items, { id, kind: "agent", body: token }];
        });
        return;
      }
      streamId.current = null;

      if (type === "run.started") callbacks?.onRunStarted?.();
      if (type === "run.finished") {
        setActiveRunId(null);
        callbacks?.onRunFinished?.(
          String(event.run_id ?? ""),
          String(event.status ?? ""),
          String(event.reason ?? "未成功完成"),
        );
      }
      if (type === "session.waiting_for_input") callbacks?.onSessionWaiting?.();

      // 工具调用
      if (type === "tool.call_started") {
        setTimeline((items) => [
          ...items,
          {
            id: String(event.tool_use_id),
            kind: "tool",
            title: String(event.tool_name),
            body: JSON.stringify(event.params ?? {}, null, 2),
            state: "运行中",
          },
        ]);
      }
      if (type === "tool.call_finished" || type === "tool.call_failed") {
        const id = String(event.tool_use_id);
        const isFailed = type.endsWith("failed");
        setTimeline((items) =>
          items.map((item) =>
            item.id === id
              ? {
                  ...item,
                  body: String(event.output ?? event.error_message ?? item.body),
                  state: isFailed ? "失败" : "完成",
                }
              : item,
          ),
        );
      }

      // 计划
      if (type === "plan.updated") {
        setPlanItems((event.items as PlanItem[]) ?? []);
      }

      // 测试结果
      if (type === "test.result") {
        const result = event as unknown as TestResult;
        setTestResults((items) => [
          ...items.filter((item) => item.tool_use_id !== result.tool_use_id),
          result,
        ]);
      }

      return event; // 返回事件供其他处理器使用
    },
    [],
  );

  // 取消运行
  const cancelRun = useCallback(
    async (client: IpcClient, setNotice: (msg: string) => void) => {
      if (!activeRunRef.current) return;
      try {
        const result = await client.request("run.cancel", {
          run_id: activeRunRef.current,
        });
        setNotice(
          result.status === "cancelling" ? "已请求停止当前运行。" : "当前没有可停止的运行。",
        );
      } catch (error) {
        const err = error instanceof Error ? error.message : String(error);
        setNotice(`停止运行失败：${err}`);
      }
    },
    [],
  );

  return {
    timeline,
    planItems,
    testResults,
    activeRunId,
    activeRunRef,
    selectedRunRef,
    streamId,
    setTimeline,
    setPlanItems,
    setTestResults,
    setActiveRunId,
    loadHistory,
    addUserMessage,
    handleEvent,
    cancelRun,
    syncSessionId,
    // Refs（供外部读取/写入）
    sessionRef,
  };
}
