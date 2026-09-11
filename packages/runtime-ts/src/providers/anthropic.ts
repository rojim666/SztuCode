import { anthropicReasoningParams } from "./reasoning.js";
import type { ChatMessage, ModelInvocation, ModelProvider, ModelResponse } from "../agent-loop.js";
import { ProviderTimeoutError, providerHttpError } from "./errors.js";
import type { ToolRegistry } from "../tools.js";
import { streamFromCompletion, usageFromLegacy, type AssistantMessage, type Model, type ModelContext, type ModelEvent, type StreamOptions } from "@sztucode/ai";
import { normalizeStopReason, parseToolArguments } from "./output-normalization.js";
import { base64FromDataUrl, base64ImageSource } from "./image-utils.js";

type AnthropicResponse = { content?: Array<{ type: string; text?: string; thinking?: string; signature?: string; id?: string; name?: string; input?: Record<string, unknown> }>; stop_reason?: string; usage?: { input_tokens?: number; output_tokens?: number; cache_read_input_tokens?: number; cache_creation_input_tokens?: number } };
export type AnthropicProviderOptions = { apiKey: string; baseUrl?: string; model: string; maxTokens?: number; timeoutMs?: number; temperature?: number | null; topP?: number | null; reasoningEffort?: string; cacheControl?: boolean };
type AnthropicBlock = Record<string, unknown> & { type: string };
type AnthropicMessage = { role: "user" | "assistant"; content: AnthropicBlock[] };

/** 超时管理器：到期前可重置（首字节到达或流块到达时续期），实现首字节 + 空闲超时而非全程总超时。 */
function createIdleTimeout(onFire: () => void, ms: number): { reset: () => void; clear: () => void } {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const clear = () => { if (timer !== undefined) clearTimeout(timer); timer = undefined; };
  const reset = () => { clear(); timer = setTimeout(onFire, ms); };
  reset();
  return { reset, clear };
}


export class AnthropicMessagesProvider implements ModelProvider {
  /** 滚动断点：上次成功请求的末块指纹。steering/干预/错误回注在 assistant 后追加 user
   * 消息时，推导边界会漂移到新消息上；显式沿用旧锚点保证上次写入的前缀缓存仍可命中。 */
  private priorAnchor: AnchorFingerprint | null = null;
  constructor(private readonly options: AnthropicProviderOptions) {}
  stream(model: Model, context: ModelContext, options: StreamOptions = {}): AsyncIterable<ModelEvent> {
    return streamFromCompletion(async (_model, _context, streamOptions, callbacks): Promise<AssistantMessage> => {
      const response = await this.complete(_context.messages as ChatMessage[], { list: () => (_context.tools ?? []).map((tool) => ({ name: tool.name, description: tool.description ?? "", schema: tool.schema })) } as ToolRegistry, streamOptions.signal, callbacks.onToken, streamOptions.invocation as ModelInvocation | undefined, callbacks.onThinking);
      return { role: "assistant", text: response.text, toolCalls: response.tool_calls, stopReason: response.stop_reason, ...(response.thinking_blocks ? { thinkingBlocks: response.thinking_blocks } : {}), ...(response.reasoning_content ? { reasoningContent: response.reasoning_content } : {}), ...(response.usage ? { usage: usageFromLegacy(response.usage) } : {}), model: { provider: model.provider, id: response.model ?? model.id } };
    }, model, context, options);
  }
  async complete(messages: ChatMessage[], tools: ToolRegistry, signal?: AbortSignal, onToken?: (token: string) => void, _invocation?: ModelInvocation, onThinking?: (thinking: string) => void): Promise<ModelResponse> {
    // The first system message is the stable base; additional system messages are
    // caller-owned tails and must not move the breakpoint past that base.
    const system = messages.filter((message) => message.role === "system").flatMap((message) =>
      typeof message.content === "string" ? [{ type: "text", text: message.content }] : message.content.map(({ cache_control: _cache, ...block }) => block));
    const bodyMessages = toAnthropicMessages(messages);
    annotateConversationCache(bodyMessages, Boolean(this.options.cacheControl), this.priorAnchor);
    const timeoutMs = this.options.timeoutMs ?? 120_000;
    const controller = new AbortController(); const abort = () => controller.abort(signal?.reason); signal?.addEventListener("abort", abort, { once: true });
    let timedOut = false; const timeout = createIdleTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
    try {
      const systemValue = system.length ? system.map((block, index) => ({ ...block, ...(this.options.cacheControl && index === 0 ? { cache_control: { type: "ephemeral" } } : {}) })) : undefined;
      const streaming = Boolean(onToken);
      const baseMaxTokens = this.options.maxTokens ?? 8192;
      const { max_tokens: maxTokens, thinking } = anthropicReasoningParams(this.options.reasoningEffort, baseMaxTokens);
      const response = await fetch(`${(this.options.baseUrl ?? "https://api.anthropic.com/v1").replace(/\/$/, "")}/messages`, { method: "POST", headers: { "x-api-key": this.options.apiKey, "anthropic-version": "2023-06-01", "content-type": "application/json", ...(streaming ? { accept: "text/event-stream" } : {}) }, body: JSON.stringify({ model: this.options.model, max_tokens: maxTokens, stream: streaming, ...(systemValue ? { system: systemValue } : {}), messages: bodyMessages, tools: tools.list().slice().sort((a, b) => a.name < b.name ? -1 : a.name > b.name ? 1 : 0).map((tool, index, all) => ({ name: tool.name, description: tool.description, input_schema: tool.schema, ...(this.options.cacheControl && index === all.length - 1 ? { cache_control: { type: "ephemeral" } } : {}) })), ...(!thinking && this.options.temperature != null ? { temperature: this.options.temperature } : {}), ...(!thinking && this.options.topP != null ? { top_p: this.options.topP } : {}), ...(thinking ? { thinking } : {}) }), signal: controller.signal });
      if (!response.ok) throw await providerHttpError(response, "Anthropic");
      timeout.reset();
      if (streaming && response.body) {
        const result = await parseAnthropicStream(response.body, this.options.model, onToken, onThinking, timeout.reset);
        this.priorAnchor = anchorFingerprint(bodyMessages.at(-1));
        return result;
      }
      const data = await response.json() as AnthropicResponse; const content = data.content ?? []; const text = content.filter((block) => block.type === "text").map((block) => block.text ?? "").join(""); const calls = content.filter((block) => block.type === "tool_use" && block.id && block.name).map((block) => ({ id: block.id!, name: block.name!, input: block.input ?? {} }));
      const thinking_blocks = content.filter((block) => block.type === "thinking").map((block) => ({ type: "thinking" as const, thinking: block.thinking ?? "", signature: block.signature ?? "" }));
      if (thinking_blocks.length) onThinking?.(thinking_blocks.map((block) => block.thinking).filter(Boolean).join("\n\n"));
      if (text) onToken?.(text);
      this.priorAnchor = anchorFingerprint(bodyMessages.at(-1));
      return { text, thinking_blocks, tool_calls: calls, stop_reason: normalizeStopReason(data.stop_reason, calls.length > 0), model: this.options.model, streamed: Boolean(onToken), usage: { input_tokens: Number(data.usage?.input_tokens ?? 0), output_tokens: Number(data.usage?.output_tokens ?? 0), cache_read_input_tokens: Number(data.usage?.cache_read_input_tokens ?? 0), cache_creation_input_tokens: Number(data.usage?.cache_creation_input_tokens ?? 0) } };
    } catch (error) { if (timedOut) throw new ProviderTimeoutError("Anthropic", timeoutMs); throw error; } finally { timeout.clear(); signal?.removeEventListener("abort", abort); }
  }
}

type AnchorFingerprint = { role: "user" | "assistant"; blockType: string; text: string };

/** 块的稳定指纹文本：tool_result 取 content、其余取 text/thinking/id，截断防指纹膨胀。 */
function anchorBlockText(block: AnthropicBlock): string {
  if (block.type === "tool_result") return typeof block.content === "string" ? block.content : JSON.stringify(block.content ?? "");
  return String(block.text ?? block.thinking ?? block.id ?? "");
}

function markableBlock(message: AnthropicMessage | undefined): AnthropicBlock | undefined {
  return message?.content.slice().reverse().find((block) => block.type !== "thinking" && block.type !== "redacted_thinking" && (block.type !== "text" || Boolean(block.text)));
}

function anchorFingerprint(message: AnthropicMessage | undefined): AnchorFingerprint | null {
  const block = markableBlock(message);
  if (!message || !block) return null;
  return { role: message.role, blockType: block.type, text: anchorBlockText(block).slice(0, 128) };
}

function findAnchorBlock(messages: AnthropicMessage[], anchor: AnchorFingerprint): AnthropicBlock | undefined {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]!;
    if (message.role !== anchor.role) continue;
    const block = message.content.slice().reverse().find((candidate) => candidate.type === anchor.blockType && anchorBlockText(candidate).slice(0, 128) === anchor.text);
    if (block) return block;
  }
  return undefined;
}

/** Two conversation anchors leave room for the system and tool breakpoints. */
function annotateConversationCache(messages: AnthropicMessage[], enabled: boolean, priorAnchor: AnchorFingerprint | null): void {
  // Persisted summaries can carry old annotations. Rebuild rather than exceed
  // Anthropic's four-breakpoint limit or leave caching active when disabled.
  for (const message of messages) for (const block of message.content) delete block.cache_control;
  if (!enabled) return;
  const last = messages.at(-1);
  const lastBlock = markableBlock(last);
  // 读取锚点：上次请求的末块（滚动断点）优先——steering/干预/错误回注只在旧 assistant
  // 之后追加 user 消息，推导边界会漂移到新消息，而旧缓存前缀仍需一个断点才能命中。
  // 锚点等于当前末块（同集重试）或已不存在（压缩重写）时回退到推导边界。
  const priorBlock = priorAnchor ? findAnchorBlock(messages, priorAnchor) : undefined;
  const anchorBlock = priorBlock && priorBlock !== lastBlock
    ? priorBlock
    : (() => {
      // This user boundary preceded the newest assistant response, so it was part
      // of the previous request. Keep it reachable even after >20 new tool blocks.
      const assistant = messages.map((message) => message.role).lastIndexOf("assistant");
      const derived = assistant > 0 ? messages[assistant - 1] : undefined;
      return derived !== last ? markableBlock(derived) : undefined;
    })();
  if (anchorBlock) anchorBlock.cache_control = { type: "ephemeral" };
  if (lastBlock) lastBlock.cache_control = { type: "ephemeral" };
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
  return content.map((block) => {
    if (block.type === "image") {
      const source = base64ImageSource(block);
      if (!source) throw new Error("Anthropic image block requires a base64 source");
      return { type: "image", source: { type: "base64", media_type: source.mediaType, data: source.data } };
    }
    if (block.type === "image_url") {
      const candidate = block.image_url;
      const imageUrl = typeof candidate === "string" ? candidate : candidate && typeof candidate === "object" && !Array.isArray(candidate) ? String((candidate as Record<string, unknown>).url ?? "") : "";
      const embedded = base64FromDataUrl(imageUrl);
      if (embedded) return { type: "image", source: { type: "base64", media_type: embedded.mediaType, data: embedded.data } };
      if (!/^https?:\/\//i.test(imageUrl)) throw new Error("Anthropic image_url requires an http(s) URL");
      return { type: "image", source: { type: "url", url: imageUrl } };
    }
    return { ...block };
  });
}

function contentText(content: ChatMessage["content"]): string {
  return typeof content === "string" ? content : JSON.stringify(content);
}

type AnthropicStreamState = { text: string; stopReason: string; calls: Map<number, { id: string; name: string; inputJson: string }>; thinking: Map<number, { thinking: string; signature: string }>; usage: ModelResponse["usage"] };

async function parseAnthropicStream(body: ReadableStream<Uint8Array>, model: string, onToken?: (token: string) => void, onThinking?: (thinking: string) => void, onProgress?: () => void): Promise<ModelResponse> {
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
  for await (const chunk of body) { onProgress?.(); buffer += decoder.decode(chunk, { stream: true }); flush(false); }
  buffer += decoder.decode(); flush(true);
  const tool_calls = [...state.calls.values()].filter((call) => call.id && call.name).map((call) => ({ id: call.id, name: call.name, input: parseToolArguments(call.inputJson) }));
  const thinking_blocks = [...state.thinking.values()].filter((block) => block.thinking || block.signature).map((block) => ({ type: "thinking" as const, thinking: block.thinking, signature: block.signature }));
  return { text: state.text, thinking_blocks, tool_calls, stop_reason: normalizeStopReason(state.stopReason, tool_calls.length > 0), model, streamed: true, usage: state.usage };
}
