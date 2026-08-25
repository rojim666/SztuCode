import type { SpanOptions, SpanStatus, SpanAttributes, TelemetryContext, TelemetrySpan } from "./index.js";

function startNoopSpan<T>(_options: SpanOptions, callback: (span: TelemetrySpan) => T | Promise<T>): Promise<T> {
  try { return Promise.resolve(callback(noopSpan)); }
  catch (error) { return Promise.reject(error); }
}

const noopSpan: TelemetrySpan = {
  startSpan: startNoopSpan,
  addEvent: (_name: string, _attributes?: SpanAttributes) => {},
  setAttributes: (_attributes: SpanAttributes) => {},
  setStatus: (_status: SpanStatus) => {},
  recordError: (_error: unknown) => {},
};
Object.freeze(noopSpan);
export const NOOP_TELEMETRY_CONTEXT: TelemetryContext = noopSpan;
