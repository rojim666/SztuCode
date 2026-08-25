# @sztucode/telemetry

Transport-free telemetry contracts for SztuCode. Runtime code passes a `TelemetryContext` explicitly and can use `startSpan`, nested child spans, attributes, events, status, and error recording without depending on an exporter.

`NOOP_TELEMETRY_CONTEXT` is the default when telemetry is disabled. `InMemoryTelemetryContext` is the reference adapter for tests. `TraceWriter` and `TraceTelemetryContext` preserve the runtime JSONL trace format; their output is best-effort and excludes sensitive attribute names such as prompts, content, API keys, paths, and file data by default.

Use `safeStartSpan` around optional adapters when adapter failures must never affect business execution.
