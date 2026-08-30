import type { ChatMessage, ModelInvocation, ModelProvider, ModelResponse } from "../agent-loop.js";
import { providerHttpError } from "./errors.js";
import type { ToolRegistry } from "../tools.js";
import { streamFromCompletion, usageFromLegacy, type AssistantMessage, type Model, type ModelContext, type ModelEvent, type StreamOptions } from "@sztucode/ai";
import { normalizeStopReason, parseToolArguments } from "./output-normalization.js";

type AnthropicResponse = { content?: Array<{ type: string; text?: string; thinking?: string; signature?: string; id?: string; name?: string; input?: Record<string, unknown> }>; stop_reason?: string; usage?: { input_tokens?: number; output_tokens?: number; cache_read_input_tokens?: number; cache_creation_input_tokens?: number } };
export type AnthropicProviderOptions = { apiKey: string; baseUrl?: string; model: string; maxTokens?: number; timeoutMs?: number; temperature?: number | null; topP?: number | null; reasoningEffort?: string; cacheControl?: boolean };
type AnthropicBlock = Record<string, unknown> & { type: string };
type AnthropicMessage = { role: "user" | "assistant"; content: AnthropicBlock[] };

export class AnthropicMessagesProvider implements ModelProvider {
  constructor(private readonly options: AnthropicProviderOptions) {}
  stream(model: Model, context: ModelContext, options: StreamOptions = {}): AsyncIterable<ModelEvent> {
    return streamFromCompletion(async (_model, _context, streamOptions, callbacks): Promise<AssistantMessage> => {
      const response = await this.complete(_context.messages as ChatMessage[], { list: () => (_context.tools ?? []).map((tool) => ({ name: tool.name, description: tool.description ?? "", schema: tool.schema })) } as ToolRegistry, streamOptions.signal, callbacks.onToken, streamOptions.invocation as ModelInvocation | undefined, callbacks.onThinking);
      return { role: "assistant", text: response.text, toolCalls: response.tool_calls, stopReason: response.stop_reason, ...(response.thinking_blocks ? { thinkingBlocks: response.thinking_blocks } : {}), ...(response.reasoning_content ? { reasoningContent: response.reasoning_content } : {}), ...(response.usage ? { usage: usageFromLegacy(response.usage) } : {}), model: { provider: model.provider, id: response.model ?? model.id } };
    }, model, context, options);
  }
  async complete(messages: ChatMessage[], tools: ToolRegistry, signal?: AbortSignal, onToken?: (token: string) => void, _invocation?: ModelInvocation, onThinking?: (thinking: string) => void): Promise<ModelResponse> {
    const system = messages.filter((message) => message.role === "system").map((message) => typeof message.content === "string" ? message.content : JSON.stringify(message.content)).join("\n");
    const bodyMessages = toAnthropicMessages(messages);
    const controller = new AbortController(); const abort = () => controller.abort(signal?.reason); signal?.addEventListener("abort", abort, { once: true }); const timeout = setTimeout(() => controller.abort(), this.options.timeoutMs ?? 120_000);
    try {
      const systemValue = this.options.cacheControl && system ? [{ type: "text", text: system, cache_control: { type: "ephemeral" } }] : system ? system : undefined;
      const streaming = Boolean(onToken);
      const response = await fetch(`${(this.options.baseUrl ?? "https://api.anthropic.com/v1").replace(/\/$/, "")}/messages`, { method: "POST", headers: { "x-api-key": this.options.apiKey, "anthropic-version": "2023-06-01", "content-type": "application/json", ...(streaming ? { accept: "text/event-stream" } : {}) }, body: JSON.stringify({ model: this.options.model, max_tokens: this.options.maxTokens ?? 8192, stream: streaming, ...(systemValue ? { system: systemValue } : {}), messages: bodyMessages, tools: tools.list().map((tool, index, all) => ({ name: tool.name, description: tool.description, input_schema: tool.schema, ...(this.options.cacheControl && index === all.length - 1 ? { cache_control: { type: "ephemeral" } } : {}) })), ...(this.options.temperature != null ? { temperature: this.options.temperature } : {}), ...(this.options.topP != null ? { top_p: this.options.topP } : {}), ...(this.options.reasoningEffort ? { thinking: { type: "adaptive" }, output_config: { effort: this.options.reasoningEffort } } : {}) }), signal: controller.signal });
      if (!response.ok) throw await providerHttpError(response, "Anthropic");
      if (streaming && response.body) return await parseAnthropicStream(response.body, this.options.model, onToken, onThinking);
      const data = await response.json() as AnthropicResponse; const content = data.content ?? []; const text = content.filter((block) => block.type === "text").map((block) => block.text ?? "").join(""); const calls = content.filter((block) => block.type === "tool_use" && block.id && block.name).map((block) => ({ id: block.id!, name: block.name!, input: block.input ?? {} }));
      const thinking_blocks = content.filter((block) => block.type === "thinking").map((block) => ({ type: "thinking", thinking: block.thinking ?? "", signature: block.signature ?? "" }));
      if (thinking_blocks.length) onThinking?.(thinking_blocks.map((block) => block.thinking).filter(Boolean).join("\n\n"));
      if (text) onToken?.(text);
      return { text, thinking_blocks, tool_calls: calls, stop_reason: normalizeStopReason(data.stop_reason, calls.length > 0), model: this.options.model, streamed: Boolean(onToken), usage: { input_tokens: Number(data.usage?.input_tokens ?? 0), output_tokens: Number(data.usage?.output_tokens ?? 0), cache_read_input_tokens: Number(data.usage?.cache_read_input_tokens ?? 0), cache_creation_input_tokens: Number(data.usage?.cache_creation_input_tokens ?? 0) } };
    } finally { clearTimeout(timeout); signal?.removeEventListener("abort", abort); }
  }
}

export function toAnthropicMessages(messages: ChatMessage[]): AnthropicMessage[] {
  const output: AnthropicMessage[] = [];
  const append = (role: AnthropicMessage["role"], content: AnthropicBlock[]) => {
    if (!content.length) return;
    const previous = output.at(-1);
    if (previous?.role === role) previous.content.push(...content);
    else output.push({ role, content: [...content] });
  };

  for (let index = 0; index < messages.length; index += 1) {
    const message = messages[index]!;
    if (message.role === "system") continue;
    if (message.role === "tool") continue;
    if (message.role !== "assistant" || !message.tool_calls?.length) {
      append(message.role, contentBlocks(message.content));
      continue;
    }

    append("assistant", [
      ...contentBlocks(message.content),
      ...message.tool_calls.map((call) => ({ type: "tool_use", id: call.id, name: call.name, input: call.input })),
    ]);

    const results = new Map<string, ChatMessage>();
    while (messages[index + 1]?.role === "tool") {
      const result = messages[index + 1]!;
      index += 1;
      if (result.tool_call_id) results.set(result.tool_call_id, result);
    }
    append("user", message.tool_calls.map((call) => {
      const result = results.get(call.id);
      return {
        type: "tool_result",
        tool_use_id: call.id,
        content: result ? contentText(result.content) : "Tool execution was interrupted before a result was recorded.",
        ...(result?.is_error || !result ? { is_error: true } : {}),
      };
    }));
  }
  return output;
}

function contentBlocks(content: ChatMessage["content"]): AnthropicBlock[] {
  if (typeof content === "string") return content ? [{ type: "text", text: content }] : [];
  return content.map((block) => ({ ...block }));
}

function contentText(content: ChatMessage["content"]): string {
  return typeof content === "string" ? content : JSON.stringify(content);
}

type AnthropicStreamState = { text: string; stopReason: string; calls: Map<number, { id: string; name: string; inputJson: string }>; thinking: Map<number, { thinking: string; signature: string }>; usage: ModelResponse["usage"] };

async function parseAnthropicStream(body: ReadableStream<Uint8Array>, model: string, onToken?: (token: string) => void, onThinking?: (thinking: string) => void): Promise<ModelResponse> {
  const decoder = new TextDecoder();
  const state: AnthropicStreamState = { text: "", stopReason: "end_turn", calls: new Map(), thinking: new Map(), usage: {} };
  let buffer = "";
  const consume = (event: string, data: string) => {
    if (!data || data === "[DONE]") return;
    let payload: any;
    try { payload = JSON.parse(data); } catch { return; }
    if (event === "message_start") {
      state.usage = { ...state.usage, input_tokens: Number(payload.message?.usage?.input_tokens ?? 0), cache_read_input_tokens: Number(payload.message?.usage?.cache_read_input_tokens ?? 0), cache_creation_input_tokens: Number(payload.message?.usage?.cache_creation_input_tokens ?? 0) };
    } else if (event === "content_block_start") {
      const index = Number(payload.index ?? 0); const block = payload.content_block ?? {};
      if (block.type === "tool_use") { const initialInput = block.input; state.calls.set(index, { id: String(block.id ?? ""), name: String(block.name ?? ""), inputJson: initialInput && Object.keys(initialInput).length ? JSON.stringify(initialInput) : "" }); }
      if (block.type === "thinking") state.thinking.set(index, { thinking: String(block.thinking ?? ""), signature: String(block.signature ?? "") });
    } else if (event === "content_block_delta") {
      const delta = payload.delta ?? {}; const index = Number(payload.index ?? 0);
      if (delta.type === "text_delta" && typeof delta.text === "string") { state.text += delta.text; onToken?.(delta.text); }
      if (delta.type === "input_json_delta") { const call = state.calls.get(index); if (call) call.inputJson += String(delta.partial_json ?? ""); }
      if (delta.type === "thinking_delta") { const block = state.thinking.get(index) ?? { thinking: "", signature: "" }; const thinking = String(delta.thinking ?? ""); block.thinking += thinking; state.thinking.set(index, block); if (thinking) onThinking?.(thinking); }
      if (delta.type === "signature_delta") { const block = state.thinking.get(index) ?? { thinking: "", signature: "" }; block.signature += String(delta.signature ?? ""); state.thinking.set(index, block); }
    } else if (event === "message_delta") {
      state.stopReason = String(payload.delta?.stop_reason ?? state.stopReason);
      state.usage = { ...state.usage, output_tokens: Number(payload.usage?.output_tokens ?? state.usage?.output_tokens ?? 0) };
    }
  };
  const flush = (final: boolean) => {
    buffer = buffer.replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const frame = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
      let event = "message"; let data = "";
      for (const line of frame.split(/\r?\n/)) { if (line.startsWith("event:")) event = line.slice(6).trim(); else if (line.startsWith("data:")) data += line.slice(5).trim(); }
      consume(event, data); boundary = buffer.indexOf("\n\n");
    }
    if (final && buffer.trim()) { const frame = buffer.trim(); buffer = ""; let event = "message"; let data = ""; for (const line of frame.split(/\r?\n/)) { if (line.startsWith("event:")) event = line.slice(6).trim(); else if (line.startsWith("data:")) data += line.slice(5).trim(); } consume(event, data); }
  };
  for await (const chunk of body) { buffer += decoder.decode(chunk, { stream: true }); flush(false); }
  buffer += decoder.decode(); flush(true);
  const tool_calls = [...state.calls.values()].filter((call) => call.id && call.name).map((call) => ({ id: call.id, name: call.name, input: parseToolArguments(call.inputJson) }));
  const thinking_blocks = [...state.thinking.values()].filter((block) => block.thinking || block.signature).map((block) => ({ type: "thinking", thinking: block.thinking, signature: block.signature }));
  return { text: state.text, thinking_blocks, tool_calls, stop_reason: normalizeStopReason(state.stopReason, tool_calls.length > 0), model, streamed: true, usage: state.usage };
}
