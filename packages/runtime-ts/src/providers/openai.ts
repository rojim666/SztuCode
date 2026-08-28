import type { ChatMessage, ModelInvocation, ModelProvider, ModelResponse } from "../agent-loop.js";
import type { ToolRegistry } from "../tools.js";
import { streamFromCompletion, usageFromLegacy, type AssistantMessage, type Model, type ModelContext, type ModelEvent, type StreamOptions } from "@sztucode/ai";

type OpenAiResponse = { choices?: Array<{ message?: { content?: string | null; reasoning_content?: string | null; tool_calls?: Array<{ id?: string; function?: { name?: string; arguments?: string } }> }; delta?: { content?: string | null; reasoning_content?: string | null; tool_calls?: Array<{ index?: number; id?: string; function?: { name?: string; arguments?: string } }> } }>; usage?: { prompt_tokens?: number; completion_tokens?: number; input_tokens?: number; output_tokens?: number; prompt_tokens_details?: { cached_tokens?: number } } };
type ResponsesOutput = { type?: string; id?: string; call_id?: string; name?: string; arguments?: string; summary?: Array<{ type?: string; text?: string }>; content?: Array<{ type?: string; text?: string }> };
type ResponsesResponse = { output_text?: string; output?: ResponsesOutput[]; usage?: { input_tokens?: number; output_tokens?: number; input_tokens_details?: { cached_tokens?: number } } };
/** 网关类与部分推理模型对标准 OpenAI 请求存在差异，compat 用于逐项修正而不影响默认行为。 */
export type ProviderCompat = { headers?: Record<string, string>; extraBody?: Record<string, unknown>; dropTemperature?: boolean; dropTopP?: boolean; disableCacheControl?: boolean };
export type OpenAiProviderOptions = { apiKey?: string; baseUrl?: string; model: string; timeoutMs?: number; apiFormat?: "openai_chat_completions" | "openai_responses"; maxOutputTokens?: number; temperature?: number | null; topP?: number | null; reasoningEffort?: string; stream?: boolean; cacheControl?: boolean; compat?: ProviderCompat };

export class OpenAiCompatibleProvider implements ModelProvider {
  constructor(private readonly options: OpenAiProviderOptions) {}
  stream(model: Model, context: ModelContext, options: StreamOptions = {}): AsyncIterable<ModelEvent> {
    return streamFromCompletion(async (_model, _context, streamOptions, callbacks): Promise<AssistantMessage> => {
      const response = await this.complete(_context.messages as ChatMessage[], { list: () => (_context.tools ?? []).map((tool) => ({ name: tool.name, description: tool.description ?? "", schema: tool.schema })) } as ToolRegistry, streamOptions.signal, callbacks.onToken, streamOptions.invocation as ModelInvocation | undefined, callbacks.onThinking);
      return { role: "assistant", text: response.text, toolCalls: response.tool_calls, stopReason: response.stop_reason, ...(response.thinking_blocks ? { thinkingBlocks: response.thinking_blocks } : {}), ...(response.reasoning_content ? { reasoningContent: response.reasoning_content } : {}), ...(response.usage ? { usage: usageFromLegacy(response.usage) } : {}), model: { provider: model.provider, id: response.model ?? model.id } };
    }, model, context, options);
  }
  async complete(messages: ChatMessage[], tools: ToolRegistry, signal?: AbortSignal, onToken?: (token: string) => void, _invocation?: ModelInvocation, onThinking?: (thinking: string) => void): Promise<ModelResponse> {
    const controller = new AbortController();
    const abort = () => controller.abort(signal?.reason);
    signal?.addEventListener("abort", abort, { once: true });
    const timeout = setTimeout(() => controller.abort(), this.options.timeoutMs ?? 120_000);
    try {
      const base = (this.options.baseUrl ?? "https://api.openai.com/v1").replace(/\/$/, "");
      const definitions = tools.list().map((tool, index, all) => ({ type: "function", name: tool.name, description: tool.description, parameters: tool.schema, ...(this.cacheControl && index === all.length - 1 ? { cache_control: { type: "ephemeral" } } : {}) }));
      const apiMessages = messages.map((message) => message.role === "assistant" && message.tool_calls?.length ? { role: "assistant", content: typeof message.content === "string" ? message.content || null : message.content, ...(message.reasoning_content ? { reasoning_content: message.reasoning_content } : {}), tool_calls: message.tool_calls.map((call) => ({ id: call.id, type: "function", function: { name: call.name, arguments: JSON.stringify(call.input) } })) } : message.role === "system" && this.cacheControl ? { ...message, cache_control: { type: "ephemeral" } } : message);
      const responses = this.options.apiFormat === "openai_responses";
      const input: Array<Record<string, unknown>> = [];
      for (const message of messages) {
        if (message.role === "system") continue;
        if (message.role === "tool") { input.push({ type: "function_call_output", call_id: message.tool_call_id ?? "", output: typeof message.content === "string" ? message.content : JSON.stringify(message.content) }); continue; }
        if (message.role === "assistant" && message.tool_calls?.length) {
          if (message.content) input.push({ role: "assistant", content: typeof message.content === "string" ? message.content : JSON.stringify(message.content) });
          for (const call of message.tool_calls) input.push({ type: "function_call", call_id: call.id, name: call.name, arguments: JSON.stringify(call.input) });
          continue;
        }
        input.push({ role: message.role, content: typeof message.content === "string" ? message.content : message.content.map((block) => ({ ...block, type: block.type === "text" ? "input_text" : block.type === "image" ? "input_image" : block.type, ...(block.text != null ? { text: block.text } : block.content != null ? { text: block.content } : {}) })) });
      }
      const system = messages.filter((message) => message.role === "system").map((message) => typeof message.content === "string" ? message.content : JSON.stringify(message.content)).join("\n\n");
      const body = responses ? { model: this.options.model, ...(system ? { instructions: system } : {}), input, tools: definitions, max_output_tokens: this.options.maxOutputTokens, ...(this.options.stream ? { stream: true } : {}), ...this.samplingParams(), ...(this.options.reasoningEffort ? { reasoning: { effort: this.options.reasoningEffort, summary: "auto" } } : {}) } : { model: this.options.model, messages: apiMessages, tools: definitions.map((tool) => ({ type: "function", function: { name: tool.name, description: tool.description, parameters: tool.parameters }, ...(tool.cache_control ? { cache_control: tool.cache_control } : {}) })), tool_choice: "auto", ...(this.options.stream ? { stream: true, stream_options: { include_usage: true } } : {}), ...(this.options.maxOutputTokens ? { max_tokens: this.options.maxOutputTokens } : {}), ...this.samplingParams(), ...(this.options.reasoningEffort ? { reasoning_effort: this.options.reasoningEffort } : {}) };
      const response = await fetch(`${base}/${responses ? "responses" : "chat/completions"}`, { method: "POST", headers: { ...(this.options.apiKey ? { authorization: `Bearer ${this.options.apiKey}` } : {}), ...(this.options.compat?.headers ?? {}), "content-type": "application/json" }, body: JSON.stringify({ ...body, ...(this.options.compat?.extraBody ?? {}) }), signal: controller.signal });
      if (!response.ok) throw new Error(`LLM request failed (${response.status}): ${(await response.text()).slice(0, 500)}`);
      if (this.options.stream && response.body && response.headers.get("content-type")?.includes("text/event-stream")) return await this.parseStream(response, responses, onToken, onThinking);
      const payload = await response.json() as OpenAiResponse & ResponsesResponse;
      if (responses) return this.parseResponses(payload, onThinking);
      const choice = payload.choices?.[0]?.message;
      if (!choice) throw new Error("LLM response did not contain a message");
      const toolCalls = (choice.tool_calls ?? []).flatMap((call) => {
        if (!call.id || !call.function?.name) return [];
        let input: Record<string, unknown> = {};
        try { input = JSON.parse(call.function.arguments || "{}"); } catch { throw new Error(`Invalid JSON arguments for tool ${call.function.name}`); }
        return [{ id: call.id, name: call.function.name, input }];
      });
      if (choice.reasoning_content) onThinking?.(choice.reasoning_content);
      return { text: choice.content ?? "", ...(choice.reasoning_content ? { reasoning_content: choice.reasoning_content } : {}), tool_calls: toolCalls, stop_reason: toolCalls.length ? "tool_use" : "end_turn", model: this.options.model, usage: { input_tokens: Number(payload.usage?.input_tokens ?? payload.usage?.prompt_tokens ?? 0), output_tokens: Number(payload.usage?.output_tokens ?? payload.usage?.completion_tokens ?? 0), cache_read_input_tokens: Number(payload.usage?.prompt_tokens_details?.cached_tokens ?? 0) } };
    } finally { clearTimeout(timeout); signal?.removeEventListener("abort", abort); }
  }

  private get cacheControl(): boolean { return Boolean(this.options.cacheControl) && !this.options.compat?.disableCacheControl; }
  private samplingParams(): Record<string, unknown> {
    const { temperature, topP, compat } = this.options;
    return { ...(temperature != null && !compat?.dropTemperature ? { temperature } : {}), ...(topP != null && !compat?.dropTopP ? { top_p: topP } : {}) };
  }

  private async parseStream(response: Response, responses: boolean, onToken?: (token: string) => void, onThinking?: (thinking: string) => void): Promise<ModelResponse> {
    const reader = response.body!.getReader(); const decoder = new TextDecoder(); let buffer = ""; let text = ""; let reasoning_content = ""; const calls = new Map<number, { id: string; name: string; args: string }>(); let usage: ResponsesResponse["usage"] & OpenAiResponse["usage"] = {};
    const consume = (raw: string) => {
      if (raw === "[DONE]") return;
      let event: any; try { event = JSON.parse(raw); } catch { return; }
      if (responses) {
        if (event.type === "response.output_text.delta") { const token = String(event.delta ?? ""); text += token; onToken?.(token); }
        else if (event.type === "response.reasoning_summary_text.delta" || event.type === "response.reasoning_text.delta") { const thinking = String(event.delta ?? ""); if (thinking) { reasoning_content += thinking; onThinking?.(thinking); } }
        else if (event.type === "response.function_call_arguments.delta") { const index = Number(event.output_index ?? 0); const current = calls.get(index) ?? { id: String(event.item_id ?? `call_${index}`), name: "", args: "" }; current.args += String(event.delta ?? ""); calls.set(index, current); }
        else if (event.type === "response.output_item.added" && event.item?.type === "function_call") { const index = Number(event.output_index ?? calls.size); calls.set(index, { id: String(event.item.call_id ?? event.item.id ?? `call_${index}`), name: String(event.item.name ?? ""), args: String(event.item.arguments ?? "") }); }
        else if (event.type === "response.completed") usage = event.response?.usage ?? {};
      } else {
        const chunk = event as OpenAiResponse; const delta = chunk.choices?.[0]?.delta; const reasoning = delta?.reasoning_content ?? ""; if (reasoning) { reasoning_content += reasoning; onThinking?.(reasoning); } const token = delta?.content ?? ""; if (token) { text += token; onToken?.(token); } for (const call of delta?.tool_calls ?? []) { const index = Number(call.index ?? 0); const current = calls.get(index) ?? { id: call.id ?? `call_${index}`, name: "", args: "" }; if (call.id) current.id = call.id; if (call.function?.name) current.name += call.function.name; if (call.function?.arguments) current.args += call.function.arguments; calls.set(index, current); } if (chunk.usage) usage = chunk.usage; }
    };
    while (true) { const { value, done } = await reader.read(); if (done) break; buffer += decoder.decode(value, { stream: true }); const rows = buffer.split(/\r?\n\r?\n/); buffer = rows.pop() ?? ""; for (const row of rows) { const data = row.split(/\r?\n/).find((line) => line.startsWith("data:")); if (data) consume(data.slice(5).trim()); } }
    const tool_calls = [...calls.values()].filter((call) => call.name).map((call) => { let input: Record<string, unknown> = {}; try { input = JSON.parse(call.args || "{}"); } catch { throw new Error(`Invalid JSON arguments for tool ${call.name}`); } return { id: call.id, name: call.name, input }; });
    return { text, ...(reasoning_content ? { reasoning_content } : {}), tool_calls, stop_reason: tool_calls.length ? "tool_use" : "end_turn", model: this.options.model, streamed: true, usage: { input_tokens: Number((usage as any).input_tokens ?? (usage as any).prompt_tokens ?? 0), output_tokens: Number((usage as any).output_tokens ?? (usage as any).completion_tokens ?? 0), cache_read_input_tokens: Number((usage as any).input_tokens_details?.cached_tokens ?? (usage as any).prompt_tokens_details?.cached_tokens ?? 0) } };
  }

  private parseResponses(payload: ResponsesResponse, onThinking?: (thinking: string) => void): ModelResponse {
    const output = Array.isArray(payload.output) ? payload.output : [];
    const text = payload.output_text ?? output.filter((item) => item.type === "message").flatMap((item) => item.content ?? []).filter((part) => part.type === "output_text" || part.type === "text").map((part) => part.text ?? "").join("");
    const reasoning_content = output.filter((item) => item.type === "reasoning").flatMap((item) => item.summary ?? item.content ?? []).filter((part) => part.type === "summary_text" || part.type === "reasoning_text" || part.type === "text").map((part) => part.text ?? "").join("\n");
    if (reasoning_content) onThinking?.(reasoning_content);
    const tool_calls = output.filter((item) => item.type === "function_call" && item.name).map((item, index) => {
      let input: Record<string, unknown> = {};
      try { input = JSON.parse(item.arguments || "{}"); } catch { throw new Error(`Invalid JSON arguments for tool ${item.name}`); }
      return { id: item.call_id || item.id || `call_${index}`, name: item.name!, input };
    });
    return { text, ...(reasoning_content ? { reasoning_content } : {}), tool_calls, stop_reason: tool_calls.length ? "tool_use" : "end_turn", model: this.options.model, usage: { input_tokens: Number(payload.usage?.input_tokens ?? 0), output_tokens: Number(payload.usage?.output_tokens ?? 0), cache_read_input_tokens: Number(payload.usage?.input_tokens_details?.cached_tokens ?? 0) } };
  }
}

