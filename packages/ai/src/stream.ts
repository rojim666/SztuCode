import { normalizeProviderError } from "./errors.js";
import type { AssistantMessage, Model, ModelContext, ModelEvent, StreamOptions, Usage } from "./types.js";

export type CompletionCallbacks = {
  onToken?: (text: string) => void;
  onThinking?: (text: string) => void;
};
export type CompletionFn = (model: Model, context: ModelContext, options: StreamOptions, callbacks: CompletionCallbacks) => Promise<AssistantMessage>;

/** Bridges callback-based providers while preserving incremental events. */
export async function* streamFromCompletion(run: CompletionFn, model: Model, context: ModelContext, options: StreamOptions = {}): AsyncIterable<ModelEvent> {
  const queue: ModelEvent[] = [];
  let wake: (() => void) | undefined;
  let finished = false;
  const push = (event: ModelEvent) => { queue.push(event); wake?.(); wake = undefined; };
  const task = run(model, context, options, { onToken: (text) => push({ type: "token", text }), onThinking: (text) => push({ type: "thinking", text }) })
    .then((message) => { for (const call of message.toolCalls) push({ type: "tool_call", call }); if (message.usage) push({ type: "usage", usage: message.usage }); push({ type: "completed", message }); })
    .catch((error) => { const normalized = normalizeProviderError(error); if (normalized.kind === "aborted") push({ type: "aborted", reason: normalized.message }); else push({ type: "error", error: normalized }); })
    .finally(() => { finished = true; wake?.(); wake = undefined; });
  void task;
  while (!finished || queue.length) {
    if (!queue.length) await new Promise<void>((resolve) => { wake = resolve; });
    while (queue.length) yield queue.shift()!;
  }
}

export function usageFromLegacy(usage: Partial<{ input_tokens: number; output_tokens: number; cache_read_input_tokens: number; cache_creation_input_tokens: number }>): Usage {
  const inputTokens = Number(usage.input_tokens ?? 0); const outputTokens = Number(usage.output_tokens ?? 0); const cacheReadTokens = Number(usage.cache_read_input_tokens ?? 0); const cacheWriteTokens = Number(usage.cache_creation_input_tokens ?? 0);
  return { inputTokens, outputTokens, cacheReadTokens, cacheWriteTokens, totalTokens: inputTokens + outputTokens + cacheReadTokens + cacheWriteTokens };
}

export function modelRef(model: Model): { provider: string; id: string } { return { provider: model.provider, id: model.id }; }
