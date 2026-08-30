import type { ModelResponse } from "../agent-loop.js";

// Keep malformed model output in-band so the agent can return a schema_error instead of aborting the run.
export function parseToolArguments(raw: string | undefined): Record<string, unknown> {
  try {
    const parsed = JSON.parse(raw || "{}");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

export function normalizeStopReason(raw: string | null | undefined, hasToolCalls: boolean): ModelResponse["stop_reason"] {
  if (raw === "length" || raw === "max_tokens" || raw === "max_output_tokens") return "max_tokens";
  if (hasToolCalls) return "tool_use";
  return "end_turn";
}
