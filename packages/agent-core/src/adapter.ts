import { streamFromCompletion, usageFromLegacy } from "@sztucode/ai";
import type { AssistantMessage, Model, ModelContext, StreamFn, StreamOptions } from "@sztucode/ai";

export interface LegacyToolRegistry {
  list(): unknown[];
}

export interface LegacyModelResponse {
  text: string;
  tool_calls: Array<{ id: string; name: string; input: Record<string, unknown> }>;
  stop_reason: string;
  thinking_blocks?: Array<{ type: string; [key: string]: unknown }>;
  reasoning_content?: string;
  usage?: Partial<{ input_tokens: number; output_tokens: number; cache_read_input_tokens: number; cache_creation_input_tokens: number }>;
  model?: string;
}

export interface LegacyModelProvider {
  complete(messages: ModelContext["messages"], tools: LegacyToolRegistry, signal?: AbortSignal, onToken?: (token: string) => void, invocation?: StreamOptions["invocation"], onThinking?: (thinking: string) => void): Promise<LegacyModelResponse>;
}

/** Adapts the existing callback-based runtime provider contract to the ai StreamFn contract. */
export function createStreamFn(provider: LegacyModelProvider): StreamFn {
  return (model, context, options = {}) => streamFromCompletion(async (_model, currentContext, streamOptions, callbacks): Promise<AssistantMessage> => {
    const response = await provider.complete(currentContext.messages, { list: () => (currentContext.tools ?? []).map((tool) => ({ name: tool.name, description: tool.description, schema: tool.schema })) }, streamOptions.signal, callbacks.onToken, streamOptions.invocation, callbacks.onThinking);
    return { role: "assistant", text: response.text, toolCalls: response.tool_calls, stopReason: response.stop_reason, ...(response.thinking_blocks ? { thinkingBlocks: response.thinking_blocks } : {}), ...(response.reasoning_content ? { reasoningContent: response.reasoning_content } : {}), ...(response.usage ? { usage: usageFromLegacy(response.usage) } : {}), model: { provider: model.provider, id: response.model ?? model.id } };
  }, model, context, options);
}
