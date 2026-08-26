export type AttributeValue = string | number | boolean | readonly string[] | readonly number[] | readonly boolean[];
export type SpanAttributes = Record<string, AttributeValue | undefined>;
export type SpanStatus = { status: "ok" } | { status: "error"; error?: { name: string; message: string } };
export interface SpanOptions { name: string; attributes?: SpanAttributes }

export interface TelemetrySpan {
  startSpan<T>(options: SpanOptions, callback: (span: TelemetrySpan) => T | Promise<T>): Promise<T>;
  addEvent(name: string, attributes?: SpanAttributes): void;
  setAttributes(attributes: SpanAttributes): void;
  setStatus(status: SpanStatus): void;
  recordError(error: unknown): void;
}

export interface TelemetryContext {
  startSpan<T>(options: SpanOptions, callback: (span: TelemetrySpan) => T | Promise<T>): Promise<T>;
}

import { NOOP_TELEMETRY_CONTEXT } from "./noop.js";

/** Runs business code even when a third-party telemetry adapter fails. */
export function safeStartSpan<T>(context: TelemetryContext | undefined, options: SpanOptions, callback: (span: TelemetrySpan) => T | Promise<T>): Promise<T> {
  const fallback = () => {
    try { return Promise.resolve(callback(NOOP_TELEMETRY_CONTEXT as unknown as TelemetrySpan)); }
    catch (error) { return Promise.reject(error); }
  };
  if (!context) return fallback();
  let businessResult: Promise<T> | undefined;
  try {
    const admitted = context.startSpan(options, (span) => {
      try { businessResult = Promise.resolve(callback(span)); return businessResult; }
      catch (error) { businessResult = Promise.reject(error); return businessResult; }
    });
    return Promise.resolve(admitted).catch(() => businessResult ?? fallback());
  } catch { return businessResult ?? fallback(); }
}

export { NOOP_TELEMETRY_CONTEXT } from "./noop.js";
export { InMemoryTelemetryContext } from "./memory.js";
export type { RecordedTelemetryEvent, RecordedTelemetrySpan } from "./memory.js";
export { TraceTelemetryContext, TraceWriter } from "./trace.js";
export type { TraceDirection, TraceLayer, TraceRecord } from "./trace.js";
