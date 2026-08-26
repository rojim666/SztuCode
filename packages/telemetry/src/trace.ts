import { appendFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { NOOP_TELEMETRY_CONTEXT } from "./noop.js";
import type { SpanAttributes, SpanOptions, SpanStatus, TelemetryContext, TelemetrySpan } from "./index.js";

export type TraceDirection = "CLIENT→CORE" | "CORE→CLIENT" | "CORE" | "CORE→LLM" | "LLM→CORE";
export type TraceLayer = "ipc" | "event" | "llm" | "telemetry";
export type TraceRecord = { ts: string; direction: TraceDirection; layer: TraceLayer; kind: string; run_id?: string | null; step?: number | null; client_id?: string | null; data: Record<string, unknown> };

/** Compatibility JSONL writer. I/O errors are swallowed so tracing cannot fail work. */
export class TraceWriter {
  private pending: Promise<void> = Promise.resolve();
  constructor(readonly filePath: string) {}
  emit(record: TraceRecord): void { let row: string; try { row = `${JSON.stringify(record)}\n`; } catch { return; } this.pending = this.pending.then(async () => { try { await mkdir(path.dirname(this.filePath), { recursive: true }); await appendFile(this.filePath, row, "utf8"); } catch {} }); }
  async flush(): Promise<void> { await this.pending; }
}

export interface TraceTelemetryOptions { runId?: string | null; step?: number | null; includeAttributes?: boolean }
export class TraceTelemetryContext implements TelemetryContext {
  constructor(private readonly writer: TraceWriter, private readonly options: TraceTelemetryOptions = {}) {}
  startSpan<T>(options: SpanOptions, callback: (span: TelemetrySpan) => T | Promise<T>): Promise<T> {
    const started = Date.now(); const data = this.options.includeAttributes === false ? {} : sanitizeAttributes(options.attributes);
    emitSafe(this.writer, { ts: new Date().toISOString(), direction: "CORE", layer: "telemetry", kind: "span.start", run_id: this.options.runId ?? null, step: this.options.step ?? null, data: { name: options.name, attributes: data } });
    const state = new TraceSpan(this.writer, options.name, this.options, started);
    let result: T | Promise<T>;
    try { result = callback(state); } catch (error) { state.recordError(error); state.finish(); return Promise.reject(error); }
    return Promise.resolve(result).then(value => { state.finish(); return value; }, error => { state.recordError(error); state.finish(); throw error; });
  }
}
class TraceSpan implements TelemetrySpan {
  private status: SpanStatus = { status: "ok" }; private settled = false;
  constructor(private readonly writer: TraceWriter, private readonly name: string, private readonly options: TraceTelemetryOptions, private readonly started: number) {}
  startSpan<T>(options: SpanOptions, callback: (span: TelemetrySpan) => T | Promise<T>): Promise<T> { return new TraceTelemetryContext(this.writer, this.options).startSpan(options, callback); }
  addEvent(name: string, attributes?: SpanAttributes): void { if (!this.settled) emitSafe(this.writer, { ts: new Date().toISOString(), direction: "CORE", layer: "telemetry", kind: "span.event", run_id: this.options.runId ?? null, step: this.options.step ?? null, data: { name: this.name, event: name, attributes: sanitizeAttributes(attributes) } }); }
  setAttributes(attributes: SpanAttributes): void { if (!this.settled) emitSafe(this.writer, { ts: new Date().toISOString(), direction: "CORE", layer: "telemetry", kind: "span.attributes", run_id: this.options.runId ?? null, step: this.options.step ?? null, data: { name: this.name, attributes: sanitizeAttributes(attributes) } }); }
  setStatus(status: SpanStatus): void { if (!this.settled) this.status = status; }
  recordError(error: unknown): void { if (!this.settled) this.status = { status: "error", error: error instanceof Error ? { name: error.name, message: error.message } : undefined }; }
  finish(): void { if (this.settled) return; this.settled = true; emitSafe(this.writer, { ts: new Date().toISOString(), direction: "CORE", layer: "telemetry", kind: "span.end", run_id: this.options.runId ?? null, step: this.options.step ?? null, data: { name: this.name, status: this.status, latency_ms: Date.now() - this.started } }); }
}
const emitSafe = (writer: TraceWriter, record: TraceRecord): void => { try { writer.emit(record); } catch {} };
const sanitizeAttributes = (attributes?: SpanAttributes): Record<string, unknown> => { const output: Record<string, unknown> = {}; try { for (const [key, value] of Object.entries(attributes ?? {})) if (value !== undefined && !/(prompt|content|message|secret|token|key|api|path|file|input|output)/i.test(key)) output[key] = value; } catch {} return output; };
export { NOOP_TELEMETRY_CONTEXT };
