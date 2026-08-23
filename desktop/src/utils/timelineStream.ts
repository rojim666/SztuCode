import type { TimelineStep } from "../components/timeline/types";

export type TokenBatch = {
  runId: string;
  step: number;
  tokens: string[];
};

type ScheduleFrame = (callback: () => void) => number;
type CancelFrame = (handle: number) => void;

export function appendTokenBatch(step: TimelineStep, tokens: string[]): TimelineStep {
  if (!tokens.length) return step;

  const text = tokens.join("");
  const events = [...(step.events ?? [])];
  const lastIndex = events.length - 1;
  const last = events[lastIndex];

  if (last?.kind === "text") {
    events[lastIndex] = { ...last, text: `${last.text ?? ""}${text}` };
  } else {
    events.push({
      id: `text-live-${step.runId ?? "run"}-${Date.now()}`,
      kind: "text",
      text,
    });
  }

  return {
    ...step,
    status: "thinking",
    streamText: `${step.streamText ?? step.tokens.join("")}${text}`,
    events,
  };
}

// 把一帧内合批的思考块折进 step（借鉴 dsh assistant.ts updateChunk）：
// 追加到 thinking 字段并替换尾部 thinking 事件对象（不可变，旧快照引用保持稳定）
export function appendThinkingBatch(step: TimelineStep, thinking: string[]): TimelineStep {
  if (!thinking.length) return step;

  const text = thinking.join("");
  const events = [...(step.events ?? [])];
  const lastIndex = events.length - 1;
  const last = events[lastIndex];

  if (last?.kind === "thinking") {
    events[lastIndex] = { ...last, text: `${last.text ?? ""}${text}` };
  } else {
    events.push({
      id: `thinking-live-${step.runId ?? "run"}-${Date.now()}`,
      kind: "thinking",
      text,
    });
  }

  return { ...step, thinking: `${step.thinking ?? ""}${text}`, events };
}

export function createTokenFrameBatcher(
  onBatch: (batch: TokenBatch) => void,
  scheduleFrame: ScheduleFrame,
  cancelFrame: CancelFrame,
) {
  const pending = new Map<string, TokenBatch>();
  let frameHandle: number | undefined;

  function drain(matches: (batch: TokenBatch) => boolean) {
    for (const [key, batch] of pending) {
      if (!matches(batch)) continue;
      pending.delete(key);
      onBatch({ ...batch, tokens: [...batch.tokens] });
    }
  }

  function cancelEmptyFrame() {
    if (pending.size || frameHandle === undefined) return;
    cancelFrame(frameHandle);
    frameHandle = undefined;
  }

  function flushAll() {
    if (frameHandle !== undefined) cancelFrame(frameHandle);
    frameHandle = undefined;
    drain(() => true);
  }

  return {
    enqueue(runId: string, step: number, token: string) {
      const key = `${runId}\u0000${step}`;
      const batch = pending.get(key);
      if (batch) batch.tokens.push(token);
      else pending.set(key, { runId, step, tokens: [token] });

      if (frameHandle !== undefined) return;
      frameHandle = scheduleFrame(() => {
        frameHandle = undefined;
        drain(() => true);
      });
    },

    flushRun(runId: string) {
      drain((batch) => batch.runId === runId);
      cancelEmptyFrame();
    },

    flushAll,

    clear() {
      pending.clear();
      if (frameHandle !== undefined) cancelFrame(frameHandle);
      frameHandle = undefined;
    },
  };
}
