import type { ChatMessage, ModelInvocation, ModelProvider, ModelResponse } from "./agent-loop.js";
import type { ToolRegistry } from "./tools.js";
import { TraceWriter } from "@sztucode/telemetry";
import { NOOP_TELEMETRY_CONTEXT, safeStartSpan, type TelemetryContext } from "@sztucode/telemetry";

export { TraceWriter } from "@sztucode/telemetry";
export type { TraceDirection, TraceLayer, TraceRecord } from "@sztucode/telemetry";

/** Runtime-specific compatibility wrapper around the transport-free telemetry writer. */
export class TracingProvider implements ModelProvider {
  constructor(private readonly inner: ModelProvider, private readonly trace: TraceWriter, private readonly includePayload = true, private readonly telemetry: TelemetryContext = NOOP_TELEMETRY_CONTEXT) {}

  async complete(messages: ChatMessage[], tools: ToolRegistry, signal?: AbortSignal, onToken?: (token: string) => void, invocation?: ModelInvocation, onThinking?: (thinking: string) => void): Promise<ModelResponse> {
    const schemas = tools.list();
    this.trace.emit({ ts: now(), direction: "CORE→LLM", layer: "llm", kind: "api_call", run_id: invocation?.runId ?? null, step: invocation?.step ?? null, data: this.includePayload ? { messages, tool_schemas: schemas } : { message_count: messages.length, tool_count: schemas.length } });
    const started = Date.now();
    try {
      const result = await safeStartSpan(this.telemetry, { name: "llm.request", attributes: { run_id: invocation?.runId, step: invocation?.step, purpose: invocation?.purpose, message_count: messages.length, tool_count: schemas.length } }, async (span) => {
        try {
          const response = await this.inner.complete(messages, tools, signal, onToken, invocation, onThinking);
          span.setAttributes({ model: response.model ?? "", stop_reason: response.stop_reason, input_tokens: Number(response.usage?.input_tokens ?? 0), output_tokens: Number(response.usage?.output_tokens ?? 0) });
          return response;
        } catch (error) { span.recordError(error); throw error; }
      });
      this.trace.emit({ ts: now(), direction: "LLM→CORE", layer: "llm", kind: "api_response", run_id: invocation?.runId ?? null, step: invocation?.step ?? null, data: this.includePayload ? { stop_reason: result.stop_reason, text: result.text, thinking_blocks: result.thinking_blocks ?? [], tool_calls: result.tool_calls, usage: result.usage ?? {}, model: result.model ?? "", latency_ms: Date.now() - started } : { stop_reason: result.stop_reason, usage: result.usage ?? {}, model: result.model ?? "", latency_ms: Date.now() - started } });
      return result;
    } catch (error) {
      this.trace.emit({ ts: now(), direction: "LLM→CORE", layer: "llm", kind: "api_error", run_id: invocation?.runId ?? null, step: invocation?.step ?? null, data: { error: error instanceof Error ? error.message : String(error), latency_ms: Date.now() - started } });
      throw error;
    }
  }
}
const now = (): string => new Date().toISOString();
