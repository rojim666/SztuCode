import type { ChatMessage, ModelInvocation, ModelProvider, ModelResponse } from "../agent-loop.js";
import { ProviderTimeoutError, providerHttpError } from "./errors.js";
import type { ToolRegistry } from "../tools.js";
import { streamFromCompletion, usageFromLegacy, type AssistantMessage, type Model, type ModelContext, type ModelEvent, type StreamOptions } from "@sztucode/ai";
import { normalizeStopReason, parseToolArguments } from "./output-normalization.js";

type OpenAiResponse = { choices?: Array<{ finish_reason?: string | null; message?: { content?: string | null; reasoning_content?: string | null; tool_calls?: Array<{ id?: string; function?: { name?: string; arguments?: string } }> }; delta?: { content?: string | null; reasoning_content?: string | null; tool_calls?: Array<{ index?: number; id?: string; function?: { name?: string; arguments?: string } }> } }>; usage?: { prompt_tokens?: number; completion_tokens?: number; input_tokens?: number; output_tokens?: number; prompt_tokens_details?: { cached_tokens?: number }; input_tokens_details?: { cached_tokens?: number } } };
type ResponsesOutput = { type?: string; id?: string; call_id?: string; name?: string; arguments?: string; summary?: Array<{ type?: string; text?: string }>; content?: Array<{ type?: string; text?: string }> };
type ResponsesResponse = { output_text?: string; output?: ResponsesOutput[]; status?: string; incomplete_details?: { reason?: string | null }; usage?: { input_tokens?: number; output_tokens?: number; input_tokens_details?: { cached_tokens?: number } } };
/** 网关类与部分推理模型对标准 OpenAI 请求存在差异，compat 用于逐项修正而不影响默认行为。 */
export type ProviderCompat = { headers?: Record<string, string>; extraBody?: Record<string, unknown>; dropTemperature?: boolean; dropTopP?: boolean; disableCacheControl?: boolean };
export type OpenAiProviderOptions = { apiKey?: string; baseUrl?: string; model: string; timeoutMs?: number; apiFormat?: "openai_chat_completions" | "openai_responses"; maxOutputTokens?: number; temperature?: number | null; topP?: number | null; reasoningEffort?: string; stream?: boolean; cacheControl?: boolean; compat?: ProviderCompat };

type NormalizedContent = { content: string | Array<Record<string, unknown>> | null; reasoningContent?: string };

/** 超时管理器：到期前可重置（首字节到达或流块到达时续期），实现首字节 + 空闲超时而非全程总超时。 */
function createIdleTimeout(onFire: () => void, ms: number): { reset: () => void; clear: () => void } {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const clear = () => { if (timer !== undefined) clearTimeout(timer); timer = undefined; };
  const reset = () => { clear(); timer = setTimeout(onFire, ms); };
  reset();
  return { reset, clear };
}

/** 推理模型（o 系列 / gpt-5 或带 reasoning 标记）拒绝 temperature/top_p 等采样参数。 */
function isReasoningModel(model: string): boolean {
  return /^o[1-9]|^gpt-5|reasoning/i.test(model);
}

function dataUrlFromImageBlock(block: Record<string, unknown>): string {
  const source = block.source;
  if (!source || typeof source !== "object" || Array.isArray(source)) return "";
  const value = source as Record<string, unknown>;
  const mediaType = String(value.media_type ?? "");
  const data = String(value.data ?? "");
  return mediaType && data ? `data:${mediaType};base64,${data}` : "";
}

function imageUrlFromBlock(block: Record<string, unknown>): string {
  if (block.type === "image") return dataUrlFromImageBlock(block);
  const imageUrl = block.image_url;
  if (typeof imageUrl === "string") return imageUrl;
  if (imageUrl && typeof imageUrl === "object" && !Array.isArray(imageUrl)) return String((imageUrl as Record<string, unknown>).url ?? "");
  return "";
}

/** Convert provider-neutral/Anthropic history into strict OpenAI chat content. */
function normalizeChatContent(message: ChatMessage): NormalizedContent {
  if (typeof message.content === "string") return {
    content: message.content || (message.role === "assistant" ? "" : ""),
    ...(message.reasoning_content ? { reasoningContent: message.reasoning_content } : {}),
  };
  const text: string[] = [];
  const media: Array<Record<string, unknown>> = [];
  for (const block of message.content) {
    if (block.type === "thinking") {
      continue;
    }
    if (block.type === "text") {
      const value = String(block.text ?? block.content ?? "");
      if (value) text.push(value);
      continue;
    }
    if (block.type === "image" || block.type === "image_url") {
      const url = imageUrlFromBlock(block);
      if (url) media.push({ type: "image_url", image_url: { url } });
      continue;
    }
    if (block.type === "file" && block.file && typeof block.file === "object") {
      media.push({ type: "file", file: block.file });
      continue;
    }
    // tool_use is represented by message.tool_calls. Preserve readable content from
    // legacy blocks without forwarding their provider-specific discriminator.
    if (block.type !== "tool_use") {
      const value = block.text ?? block.content;
      if (typeof value === "string" && value) text.push(value);
    }
  }
  const content = media.length
    ? [...(text.length ? [{ type: "text", text: text.join("\n") }] : []), ...media]
    : text.join("\n") || "";
  const reasoningContent = message.reasoning_content || undefined;
  return { content, ...(reasoningContent ? { reasoningContent } : {}) };
}

function responseInputContent(content: ChatMessage["content"]): string | Array<Record<string, unknown>> {
  if (typeof content === "string") return content;
  const output: Array<Record<string, unknown>> = [];
  for (const block of content) {
    if (block.type === "text") {
      const text = String(block.text ?? block.content ?? "");
      if (text) output.push({ type: "input_text", text });
    } else if (block.type === "image" || block.type === "image_url") {
      const imageUrl = imageUrlFromBlock(block);
      if (imageUrl) output.push({ type: "input_image", image_url: imageUrl });
    } else if (block.type === "file" && block.file && typeof block.file === "object") {
      output.push({ type: "input_file", ...(block.file as Record<string, unknown>) });
    } else if (block.type !== "thinking" && block.type !== "tool_use") {
      const text = block.text ?? block.content;
      if (typeof text === "string" && text) output.push({ type: "input_text", text });
    }
  }
  return output;
}

export class OpenAiCompatibleProvider implements ModelProvider {
  constructor(private readonly options: OpenAiProviderOptions) {}
  stream(model: Model, context: ModelContext, options: StreamOptions = {}): AsyncIterable<ModelEvent> {
    return streamFromCompletion(async (_model, _context, streamOptions, callbacks): Promise<AssistantMessage> => {
      const response = await this.complete(_context.messages as ChatMessage[], { list: () => (_context.tools ?? []).map((tool) => ({ name: tool.name, description: tool.description ?? "", schema: tool.schema })) } as ToolRegistry, streamOptions.signal, callbacks.onToken, streamOptions.invocation as ModelInvocation | undefined, callbacks.onThinking);
      return { role: "assistant", text: response.text, toolCalls: response.tool_calls, stopReason: response.stop_reason, ...(response.thinking_blocks ? { thinkingBlocks: response.thinking_blocks } : {}), ...(response.reasoning_content ? { reasoningContent: response.reasoning_content } : {}), ...(response.usage ? { usage: usageFromLegacy(response.usage) } : {}), model: { provider: model.provider, id: response.model ?? model.id } };
    }, model, context, options);
  }
  async complete(messages: ChatMessage[], tools: ToolRegistry, signal?: AbortSignal, onToken?: (token: string) => void, _invocation?: ModelInvocation, onThinking?: (thinking: string) => void): Promise<ModelResponse> {
    const timeoutMs = this.options.timeoutMs ?? 120_000;
    const controller = new AbortController();
    const abort = () => controller.abort(signal?.reason);
    signal?.addEventListener("abort", abort, { once: true });
    let timedOut = false; const timeout = createIdleTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
    try {
      const base = (this.options.baseUrl ?? "https://api.openai.com/v1").replace(/\/$/, "");
      const definitions = tools.list().map((tool, index, all) => ({ type: "function", name: tool.name, description: tool.description, parameters: tool.schema, ...(this.cacheControl && index === all.length - 1 ? { cache_control: { type: "ephemeral" } } : {}) }));
      const apiMessages = messages.map((message) => {
        const normalized = normalizeChatContent(message);
        return {
          role: message.role,
          content: normalized.content,
          ...(message.role === "tool" && message.tool_call_id ? { tool_call_id: message.tool_call_id } : {}),
          ...(message.role === "assistant" && normalized.reasoningContent ? { reasoning_content: normalized.reasoningContent } : {}),
          ...(message.role === "assistant" && message.tool_calls?.length ? { tool_calls: message.tool_calls.map((call) => ({ id: call.id, type: "function", function: { name: call.name, arguments: JSON.stringify(call.input) } })) } : {}),
          ...(message.role === "system" && this.cacheControl ? { cache_control: { type: "ephemeral" } } : {}),
        };
      });
      const responses = this.options.apiFormat === "openai_responses";
      const input: Array<Record<string, unknown>> = [];
      for (const message of messages) {
        if (message.role === "system") continue;
        if (message.role === "tool") { input.push({ type: "function_call_output", call_id: message.tool_call_id ?? "", output: typeof message.content === "string" ? message.content : JSON.stringify(message.content) }); continue; }
        if (message.role === "assistant" && message.tool_calls?.length) {
          const content = responseInputContent(message.content);
          if (typeof content === "string" ? content : content.length) input.push({ role: "assistant", content });
          for (const call of message.tool_calls) input.push({ type: "function_call", call_id: call.id, name: call.name, arguments: JSON.stringify(call.input) });
          continue;
        }
        input.push({ role: message.role, content: responseInputContent(message.content) });
      }
      const system = messages.filter((message) => message.role === "system").map((message) => {
        const content = responseInputContent(message.content);
        return typeof content === "string" ? content : content.filter((block) => block.type === "input_text").map((block) => String(block.text ?? "")).join("\n");
      }).filter(Boolean).join("\n\n");
      const reasoning = isReasoningModel(this.options.model) || Boolean(this.options.reasoningEffort);
      const body = responses ? { model: this.options.model, ...(system ? { instructions: system } : {}), input, tools: definitions.map((tool) => Object.fromEntries(Object.entries(tool).filter(([key]) => key !== "cache_control"))), max_output_tokens: this.options.maxOutputTokens, ...(this.options.stream ? { stream: true } : {}), ...this.samplingParams(), ...(this.options.reasoningEffort ? { reasoning: { effort: this.options.reasoningEffort, summary: "auto" } } : {}) } : { model: this.options.model, messages: apiMessages, tools: definitions.map((tool) => ({ type: "function", function: { name: tool.name, description: tool.description, parameters: tool.parameters }, ...(tool.cache_control ? { cache_control: tool.cache_control } : {}) })), tool_choice: "auto", ...(this.options.stream ? { stream: true, stream_options: { include_usage: true } } : {}), ...(this.options.maxOutputTokens ? (reasoning ? { max_completion_tokens: this.options.maxOutputTokens } : { max_tokens: this.options.maxOutputTokens }) : {}), ...this.samplingParams(reasoning), ...(this.options.reasoningEffort ? { reasoning_effort: this.options.reasoningEffort } : {}) };
      const response = await fetch(`${base}/${responses ? "responses" : "chat/completions"}`, { method: "POST", headers: { ...(this.options.apiKey ? { authorization: `Bearer ${this.options.apiKey}` } : {}), ...(this.options.compat?.headers ?? {}), "content-type": "application/json" }, body: JSON.stringify({ ...body, ...(this.options.compat?.extraBody ?? {}) }), signal: controller.signal });
      if (!response.ok) throw await providerHttpError(response, "OpenAI-compatible");
      timeout.reset();
      if (this.options.stream && response.body && response.headers.get("content-type")?.includes("text/event-stream")) return await this.parseStream(response, responses, onToken, onThinking, timeout.reset);
      const payload = await response.json() as OpenAiResponse & ResponsesResponse;
      if (responses) return this.parseResponses(payload, onThinking);
      const selectedChoice = payload.choices?.[0];
      const choice = selectedChoice?.message;
      if (!choice) throw new Error("LLM response did not contain a message");
      const toolCalls = (choice.tool_calls ?? []).flatMap((call) => {
        if (!call.id || !call.function?.name) return [];
        const input = parseToolArguments(call.function.arguments);
        return [{ id: call.id, name: call.function.name, input }];
      });
      if (choice.reasoning_content) onThinking?.(choice.reasoning_content);
      return { text: choice.content ?? "", ...(choice.reasoning_content ? { reasoning_content: choice.reasoning_content } : {}), tool_calls: toolCalls, stop_reason: normalizeStopReason(selectedChoice?.finish_reason, toolCalls.length > 0), model: this.options.model, usage: { input_tokens: Number(payload.usage?.input_tokens ?? payload.usage?.prompt_tokens ?? 0), output_tokens: Number(payload.usage?.output_tokens ?? payload.usage?.completion_tokens ?? 0), cache_read_input_tokens: Number(payload.usage?.prompt_tokens_details?.cached_tokens ?? payload.usage?.input_tokens_details?.cached_tokens ?? 0) } };
    } catch (error) { if (timedOut) throw new ProviderTimeoutError("OpenAI-compatible", timeoutMs); throw error; } finally { timeout.clear(); signal?.removeEventListener("abort", abort); }
  }

  private get cacheControl(): boolean { return Boolean(this.options.cacheControl) && !this.options.compat?.disableCacheControl; }
  private samplingParams(suppressSampling = false): Record<string, unknown> {
    const { temperature, topP, compat } = this.options;
    return { ...(temperature != null && !suppressSampling && !compat?.dropTemperature ? { temperature } : {}), ...(topP != null && !suppressSampling && !compat?.dropTopP ? { top_p: topP } : {}) };
  }

  private async parseStream(response: Response, responses: boolean, onToken?: (token: string) => void, onThinking?: (thinking: string) => void, onProgress?: () => void): Promise<ModelResponse> {
    const reader = response.body!.getReader(); const decoder = new TextDecoder(); let buffer = ""; let text = ""; let reasoning_content = ""; let stopReason: string | null | undefined; const calls = new Map<number, { id: string; name: string; args: string }>(); let usage: ResponsesResponse["usage"] & OpenAiResponse["usage"] = {};
    const consume = (raw: string) => {
      if (raw === "[DONE]") return;
      let event: any; try { event = JSON.parse(raw); } catch { return; }
      if (responses) {
        if (event.type === "response.output_text.delta") { const token = String(event.delta ?? ""); text += token; onToken?.(token); }
        else if (event.type === "response.reasoning_summary_text.delta" || event.type === "response.reasoning_text.delta") { const thinking = String(event.delta ?? ""); if (thinking) { reasoning_content += thinking; onThinking?.(thinking); } }
        else if (event.type === "response.function_call_arguments.delta") { const index = Number(event.output_index ?? 0); const current = calls.get(index) ?? { id: String(event.item_id ?? `call_${index}`), name: "", args: "" }; current.args += String(event.delta ?? ""); calls.set(index, current); }
        else if (event.type === "response.output_item.added" && event.item?.type === "function_call") { const index = Number(event.output_index ?? calls.size); calls.set(index, { id: String(event.item.call_id ?? event.item.id ?? `call_${index}`), name: String(event.item.name ?? ""), args: String(event.item.arguments ?? "") }); }
        else if (event.type === "response.completed" || event.type === "response.incomplete") { usage = event.response?.usage ?? {}; stopReason = responsesStopReason(event.response?.status, event.response?.incomplete_details); }
      } else {
        const chunk = event as OpenAiResponse; const choice = chunk.choices?.[0]; const delta = choice?.delta; if (choice?.finish_reason) stopReason = choice.finish_reason; const reasoning = delta?.reasoning_content ?? ""; if (reasoning) { reasoning_content += reasoning; onThinking?.(reasoning); } const token = delta?.content ?? ""; if (token) { text += token; onToken?.(token); } for (const call of delta?.tool_calls ?? []) { const index = Number(call.index ?? 0); const current = calls.get(index) ?? { id: call.id ?? `call_${index}`, name: "", args: "" }; if (call.id) current.id = call.id; if (call.function?.name) current.name += call.function.name; if (call.function?.arguments) current.args += call.function.arguments; calls.set(index, current); } if (chunk.usage) usage = chunk.usage; }
    };
    while (true) { const { value, done } = await reader.read(); if (done) break; onProgress?.(); buffer += decoder.decode(value, { stream: true }); const rows = buffer.split(/\r?\n\r?\n/); buffer = rows.pop() ?? ""; for (const row of rows) { const data = row.split(/\r?\n/).find((line) => line.startsWith("data:")); if (data) consume(data.slice(5).trim()); } }
    const tool_calls = [...calls.values()].filter((call) => call.name).map((call) => ({ id: call.id, name: call.name, input: parseToolArguments(call.args) }));
    return { text, ...(reasoning_content ? { reasoning_content } : {}), tool_calls, stop_reason: normalizeStopReason(stopReason, tool_calls.length > 0), model: this.options.model, streamed: true, usage: { input_tokens: Number((usage as any).input_tokens ?? (usage as any).prompt_tokens ?? 0), output_tokens: Number((usage as any).output_tokens ?? (usage as any).completion_tokens ?? 0), cache_read_input_tokens: Number((usage as any).input_tokens_details?.cached_tokens ?? (usage as any).prompt_tokens_details?.cached_tokens ?? 0) } };
  }

  private parseResponses(payload: ResponsesResponse, onThinking?: (thinking: string) => void): ModelResponse {
    const output = Array.isArray(payload.output) ? payload.output : [];
    const text = payload.output_text ?? output.filter((item) => item.type === "message").flatMap((item) => item.content ?? []).filter((part) => part.type === "output_text" || part.type === "text").map((part) => part.text ?? "").join("");
    const reasoning_content = output.filter((item) => item.type === "reasoning").flatMap((item) => item.summary ?? item.content ?? []).filter((part) => part.type === "summary_text" || part.type === "reasoning_text" || part.type === "text").map((part) => part.text ?? "").join("\n");
    if (reasoning_content) onThinking?.(reasoning_content);
    const tool_calls = output.filter((item) => item.type === "function_call" && item.name).map((item, index) => {
      const input = parseToolArguments(item.arguments);
      return { id: item.call_id || item.id || `call_${index}`, name: item.name!, input };
    });
    return { text, ...(reasoning_content ? { reasoning_content } : {}), tool_calls, stop_reason: normalizeStopReason(responsesStopReason(payload.status, payload.incomplete_details), tool_calls.length > 0), model: this.options.model, usage: { input_tokens: Number(payload.usage?.input_tokens ?? 0), output_tokens: Number(payload.usage?.output_tokens ?? 0), cache_read_input_tokens: Number(payload.usage?.input_tokens_details?.cached_tokens ?? 0) } };
  }
}

function responsesStopReason(status?: string, details?: { reason?: string | null }): string | undefined {
  if (details?.reason) return details.reason;
  return status === "incomplete" ? "max_output_tokens" : undefined;
}
