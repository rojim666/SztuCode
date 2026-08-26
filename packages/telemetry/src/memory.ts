import type { AttributeValue, SpanAttributes, SpanOptions, SpanStatus, TelemetryContext, TelemetrySpan } from "./index.js";

export interface RecordedTelemetryEvent { readonly name: string; readonly attributes: Readonly<SpanAttributes> }
export interface RecordedTelemetrySpan { readonly id: number; readonly parentId: number | null; readonly name: string; readonly attributes: Readonly<SpanAttributes>; readonly events: readonly RecordedTelemetryEvent[]; readonly status: SpanStatus; readonly settled: boolean; readonly endSequence?: number }
type MutableEvent = { name: string; attributes: SpanAttributes };
type MutableSpan = { id: number; parentId: number | null; name: string; attributes: SpanAttributes; events: MutableEvent[]; status: SpanStatus; explicitStatus: boolean; settled: boolean; endSequence?: number };
const copyValue = (value: AttributeValue): AttributeValue => Array.isArray(value) ? [...value] as AttributeValue : value;
const copyAttrs = (attrs?: SpanAttributes): SpanAttributes => { const result: SpanAttributes = {}; for (const [key, value] of Object.entries(attrs ?? {})) if (value !== undefined) result[key] = copyValue(value); return result; };
const copyStatus = (status: SpanStatus): SpanStatus => status.status === "ok" ? { status: "ok" } : status.error ? { status: "error", error: { ...status.error } } : { status: "error" };
const errorStatus = (error: unknown): SpanStatus => error instanceof Error ? { status: "error", error: { name: error.name, message: error.message } } : { status: "error" };

function start<T>(state: { spans: MutableSpan[]; nextId: number; nextEnd: number }, parent: MutableSpan | undefined, options: SpanOptions, callback: (span: TelemetrySpan) => T | Promise<T>): Promise<T> {
  if (parent?.settled) return startNoop(options, callback);
  let record: MutableSpan;
  try { record = { id: state.nextId++, parentId: parent?.id ?? null, name: options.name, attributes: copyAttrs(options.attributes), events: [], status: { status: "ok" }, explicitStatus: false, settled: false }; state.spans.push(record); }
  catch { return startNoop(options, callback); }
  const span: TelemetrySpan = {
    startSpan: (child, childCallback) => start(state, record, child, childCallback),
    addEvent(name, attributes) { if (!record.settled) try { record.events.push({ name, attributes: copyAttrs(attributes) }); } catch {} },
    setAttributes(attributes) { if (!record.settled) try { Object.assign(record.attributes, copyAttrs(attributes)); } catch {} },
    setStatus(status) { if (!record.settled) try { record.status = copyStatus(status); record.explicitStatus = true; } catch {} },
    recordError(error) { if (!record.settled) try { record.status = errorStatus(error); record.explicitStatus = true; } catch {} },
  };
  let result: T | Promise<T>;
  try { result = callback(span); } catch (error) { settle(record, state, true, error); return Promise.reject(error); }
  return Promise.resolve(result).then(value => { settle(record, state, false); return value; }, error => { settle(record, state, true, error); throw error; });
}
function settle(record: MutableSpan, state: { nextEnd: number }, failed: boolean, error?: unknown): void { if (record.settled) return; if (failed && !record.explicitStatus) record.status = errorStatus(error); record.settled = true; record.endSequence = state.nextEnd++; }
function startNoop<T>(_options: SpanOptions, callback: (span: TelemetrySpan) => T | Promise<T>): Promise<T> { try { return Promise.resolve(callback(NOOP_SPAN)); } catch (error) { return Promise.reject(error); } }
const NOOP_SPAN: TelemetrySpan = { startSpan: startNoop, addEvent: () => {}, setAttributes: () => {}, setStatus: () => {}, recordError: () => {} };

export class InMemoryTelemetryContext implements TelemetryContext {
  private readonly state = { spans: [] as MutableSpan[], nextId: 1, nextEnd: 1 };
  startSpan<T>(options: SpanOptions, callback: (span: TelemetrySpan) => T | Promise<T>): Promise<T> { return start(this.state, undefined, options, callback); }
  getSpans(): readonly RecordedTelemetrySpan[] { return this.state.spans.map(span => ({ id: span.id, parentId: span.parentId, name: span.name, attributes: copyAttrs(span.attributes), events: span.events.map(event => ({ name: event.name, attributes: copyAttrs(event.attributes) })), status: copyStatus(span.status), settled: span.settled, ...(span.endSequence === undefined ? {} : { endSequence: span.endSequence }) })); }
}
