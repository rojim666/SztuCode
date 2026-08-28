import type { RuntimeEvent } from "@sztucode/protocol";
import { EventBus } from "./event-bus.js";
import { ToolRegistry, type Tool, type ToolContext, type ToolResult } from "./tools.js";
import type { PermissionGate } from "./permissions.js";
import { ContextManager, sanitizeContextMessages, type ContentBlock, type ContextMessage } from "./context.js";
import { DenialTracker } from "./denial-tracker.js";
import { StuckLoopTracker, stuckSignature } from "./stuck-tracker.js";
import { createPhaseTracker } from "./phase.js";
import path from "node:path";
import { createReadRefTool, OffloadManager } from "./offload.js";
import { validateSchema } from "./schema-validator.js";
import type { ExtensionRegistry } from "./extensions/registry.js";
import { NOOP_TELEMETRY_CONTEXT, safeStartSpan, type TelemetryContext } from "@sztucode/telemetry";

export type ChatMessage = ContextMessage;
export type ModelToolCall = { id: string; name: string; input: Record<string, unknown> };
export type ModelUsage = { input_tokens: number; output_tokens: number; cache_read_input_tokens: number; cache_creation_input_tokens: number };
export type ModelResponse = { text: string; tool_calls: ModelToolCall[]; stop_reason: "end_turn" | "tool_use"; thinking_blocks?: ContentBlock[]; reasoning_content?: string; usage?: Partial<ModelUsage>; model?: string; streamed?: boolean };
export type ModelInvocation = { runId: string; step: number; purpose?: "agent" | "compaction" };
export interface ModelProvider { complete(messages: ChatMessage[], tools: ToolRegistry, signal?: AbortSignal, onToken?: (token: string) => void, invocation?: ModelInvocation, onThinking?: (thinking: string) => void): Promise<ModelResponse> }
export type AgentProgress = { steps: number; usage: ModelUsage; contextPct: number };
export type AgentRunResult = { text: string; steps: number; messages: ChatMessage[]; usage: ModelUsage; contextPct: number; compacted: boolean; summaries: string[] };
export type AgentLoopOptions = { contextWindow?: number; maxOutputTokens?: number; sessionId?: string; streaming?: boolean; stuckMaxFailures?: number; stuckMaxTotal?: number; offloadEnabled?: boolean; offloadMinChars?: number; offloadMinLines?: number; offloadRoot?: string; toolMaxRetries?: number; toolRetryBaseMs?: number; compactThreshold?: number; slidingWindowSize?: number; compactCooldownSteps?: number; compactCircuitBreaker?: number; compactMinimumOldTokens?: number; onProgress?: (progress: AgentProgress) => void; onCompacted?: (messages: ChatMessage[], summary: string) => Promise<void>; extensions?: ExtensionRegistry; workspaceRoot?: string; telemetry?: TelemetryContext };

// 上下文窗口：0（自动）或未配置时回退到默认窗口。绝不能把 0 直接当窗口用——
// 否则 contextPct = inputTokens / max(1, 0) 会把占用算成天文数字，前端钳制后恒显 100%。
const resolveContextWindow = (value: number | undefined, fallback = 128_000): number =>
  value && value > 0 ? value : fallback;

export class EchoProvider implements ModelProvider {
  async complete(messages: ChatMessage[]): Promise<ModelResponse> {
    const last = messages.at(-1)?.content ?? "";
    return { text: `TypeScript agent: ${last}`, tool_calls: [], stop_reason: "end_turn" };
  }
}

export class AgentLoop {
  constructor(private readonly provider: ModelProvider, private readonly tools: ToolRegistry, private readonly context: ToolContext, private readonly events: EventBus, private readonly permissions: PermissionGate, private readonly options: AgentLoopOptions = {}) {}

  async run(runId: string, goal: string, maxSteps = 100, history: ChatMessage[] = [], signal?: AbortSignal, takeSteering?: () => ChatMessage[]): Promise<AgentRunResult> {
    const extensionRoot = this.options.workspaceRoot ?? this.context.workspace.root;
    const extensions = this.options.extensions;
    await extensions?.dispatch("before_agent_start", { goal, messages: history }, extensionRoot, { runId, sessionId: this.options.sessionId });
    await extensions?.dispatch("agent_start", { goal, messages: history }, extensionRoot, { runId, sessionId: this.options.sessionId });
    const offload = new OffloadManager(this.options.offloadRoot ?? path.join(dataRoot(), "runs", safeRunId(runId)), { enabled: this.options.offloadEnabled ?? booleanEnv("SZTU_OFFLOAD_ENABLED", true), minChars: this.options.offloadMinChars ?? nonNegativeEnv("SZTU_OFFLOAD_MIN_CHARS", 2_000), minLines: this.options.offloadMinLines ?? nonNegativeEnv("SZTU_OFFLOAD_MIN_LINES", 50) });
    this.tools.replace(createReadRefTool(offload));
    const context = new ContextManager([...history, { role: "user", content: goal }], { maxTokens: resolveContextWindow(this.options.contextWindow), reservedOutputTokens: this.options.maxOutputTokens ?? 8_192, maxToolResultChars: 8_000 });
    const messages = context.messages;
    const initialSystem = messages.find((message) => message.role === "system");
    if (initialSystem) { const text = typeof initialSystem.content === "string" ? initialSystem.content : JSON.stringify(initialSystem.content); this.publish({ type: "context.injected", run_id: runId, source: "system", label: "上下文注入", chars: text.length, preview: text.slice(0, 160), text, ts: now() }); }
    const usage: ModelUsage = { input_tokens: 0, output_tokens: 0, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 };
    const compactThreshold = this.options.compactThreshold ?? numberEnv("SZTU_COMPACT_THRESHOLD", 0.70, 0, 1);
    const slidingWindowSize = this.options.slidingWindowSize ?? nonNegativeEnv("SZTU_SLIDING_WINDOW_SIZE", 5);
    const compactCooldownSteps = this.options.compactCooldownSteps ?? nonNegativeEnv("SZTU_COMPACT_COOLDOWN", 3);
    const compactCircuitBreaker = this.options.compactCircuitBreaker ?? nonNegativeEnv("SZTU_COMPACT_CIRCUIT_BREAKER", 3);
    const compactMinimumOldTokens = this.options.compactMinimumOldTokens ?? nonNegativeEnv("SZTU_COMPACT_MIN_OLD_TOKENS", 2_000);
    let pendingCompaction: Promise<import("./context.js").ContextCompactionResult> | null = null;
    let lastCompactStep = -compactCooldownSteps;
    let compactionFailures = 0;
    let compactionCount = 0;
    let compacted = false;
    let lastContextPct = context.contextPct();
    const summaries: string[] = [];
    const startCompaction = (step: number): boolean => {
      if (pendingCompaction || compactThreshold <= 0 || compactCircuitBreaker > 0 && compactionFailures >= compactCircuitBreaker || step - lastCompactStep < compactCooldownSteps) return false;
      if (this.options.sessionId) this.publish({ type: "context.compacting", session_id: this.options.sessionId, run_id: runId, ts: now() });
      pendingCompaction = safeStartSpan(this.options.telemetry ?? NOOP_TELEMETRY_CONTEXT, { name: "context.compaction", attributes: { run_id: runId, step, compaction_count: compactionCount } }, async (span) => {
        try {
          const result = await context.compactWithProvider(this.provider, "", { slidingWindow: slidingWindowSize, minimumOldTokens: compactMinimumOldTokens, compactionCount }, signal, { runId, step, purpose: "compaction" });
          span.setAttributes({ removed_messages: result.removedMessages, summary_tokens: result.summaryTokens, failed: Boolean(result.failed) });
          return result;
        } catch (error) { span.recordError(error); throw error; }
      });
      lastCompactStep = step;
      return true;
    };
    const applyPendingCompaction = async () => {
      if (!pendingCompaction) return;
      const result = await pendingCompaction; pendingCompaction = null;
      if (result.failed) { compactionFailures += 1; this.publish({ type: "log.line", run_id: runId, level: "WARN", source: "context", message: `Compaction failed (${compactionFailures}/${compactCircuitBreaker || "unlimited"})`, ts: now() }); return; }
      if (result.deferred) return;
      compactionFailures = 0; compactionCount += 1; compacted = true;
      if (result.summaryText) summaries.push(result.summaryText);
      await extensions?.dispatch("compact", { messages, summary: result.summaryText, removedMessages: result.removedMessages }, extensionRoot, { runId, sessionId: this.options.sessionId });
      await this.options.onCompacted?.(messages, result.summaryText);
      this.publish({ type: "log.line", run_id: runId, level: "INFO", source: "context", message: `Summarized ${result.removedMessages} messages using a ${slidingWindowSize}-turn window`, ts: now() });
      if (this.options.sessionId) this.publish({ type: "context.compacted", session_id: this.options.sessionId, run_id: runId, original_tokens: result.originalTokens, summary_tokens: result.summaryTokens, ts: now() });
    };
    const denials = new DenialTracker();
    const stuck = new StuckLoopTracker(this.options.stuckMaxFailures ?? nonNegativeEnv("SZTU_STUCK_MAX_FAILURES", 2), this.options.stuckMaxTotal ?? nonNegativeEnv("SZTU_STUCK_MAX_TOTAL", 0));
    const phases = createPhaseTracker();
    for (let step = 1; maxSteps === 0 || step <= maxSteps; step += 1) {
      signal?.throwIfAborted();
      await applyPendingCompaction();
      await extensions?.dispatch("turn_start", { goal, step, messages }, extensionRoot, { runId, sessionId: this.options.sessionId });
      this.publish({ type: "step.started", run_id: runId, step, ts: now() });
      const intervention = denials.intervention();
      if (intervention) {
        messages.push({ role: "user", content: intervention.message });
        this.publish({ type: "denial.intervention", run_id: runId, tool_name: intervention.toolName, consecutive_count: intervention.consecutiveCount, total_denials: intervention.totalDenials, message: intervention.message, ts: now() });
      }
      const stuckIntervention = stuck.intervention();
      if (stuckIntervention) {
        messages.push({ role: "user", content: stuckIntervention.message });
        this.publish({ type: "stuck.loop", run_id: runId, signature: stuckIntervention.signature, consecutive_count: stuckIntervention.consecutiveCount, total_interventions: stuckIntervention.totalInterventions, message: stuckIntervention.message, ts: now() });
        if (stuckIntervention.hardStop) throw new Error(`Agent stopped after ${stuckIntervention.totalInterventions} stuck-loop intervention(s)`);
      }
      const steering = takeSteering?.() ?? [];
      if (steering.length) {
        messages.push(...steering);
        this.publish({ type: "log.line", run_id: runId, level: "INFO", source: "session", message: `Injected ${steering.length} steering message(s)`, ts: now() });
      }
      const sanitized = sanitizeContextMessages(messages, context.budgetMaxToolResultChars());
      if (sanitized.length !== messages.length || sanitized.some((message, index) => message !== messages[index])) { messages.splice(0, messages.length, ...sanitized); }
      await extensions?.dispatch("context", { messages, contextPct: lastContextPct }, extensionRoot, { runId, sessionId: this.options.sessionId });
      const requestTokens = context.tokenEstimate();
      const response = await this.provider.complete(messages, this.tools, signal, (token) => this.publish({ type: "llm.token", run_id: runId, token, ts: now() }), { runId, step, purpose: "agent" }, (thinking) => this.publish({ type: "llm.thinking", run_id: runId, step, thinking, ts: now() }));
      usage.input_tokens += Number(response.usage?.input_tokens ?? 0);
      usage.output_tokens += Number(response.usage?.output_tokens ?? 0);
      usage.cache_read_input_tokens += Number(response.usage?.cache_read_input_tokens ?? 0);
      usage.cache_creation_input_tokens += Number(response.usage?.cache_creation_input_tokens ?? 0);
      const contextWindow = resolveContextWindow(this.options.contextWindow);
      const reservedOutputTokens = this.options.maxOutputTokens ?? 8_192;
      const responseInputTokens = Number(response.usage?.input_tokens ?? 0);
      lastContextPct = context.contextPct(responseInputTokens > 0 ? responseInputTokens : requestTokens);
      this.options.onProgress?.({ steps: step, usage: { ...usage }, contextPct: lastContextPct });
      this.publish({ type: "llm.usage", run_id: runId, input_tokens: responseInputTokens, output_tokens: Number(response.usage?.output_tokens ?? 0), cache_read_input_tokens: Number(response.usage?.cache_read_input_tokens ?? 0), cache_creation_input_tokens: Number(response.usage?.cache_creation_input_tokens ?? 0), context_pct: lastContextPct, model: response.model ?? "", context_window: contextWindow, available_tokens: Math.max(0, contextWindow - reservedOutputTokens - (responseInputTokens || requestTokens)), reserved_output_tokens: reservedOutputTokens, system_tokens: messages.filter((message) => message.role === "system").reduce((sum, message) => sum + context.counter.countJson(message.content), 0), summary_tokens: summaries.reduce((sum, summary) => sum + context.counter.count(summary), 0), conversation_tokens: context.counter.countMessages(messages), tool_tokens: messages.filter((message) => message.role === "tool").reduce((sum, message) => sum + context.counter.countJson(message.content), 0), ts: now() });
      if (response.text && (!this.options.streaming || !response.streamed)) this.publish({ type: "llm.token", run_id: runId, token: response.text, ts: now() });
      if (response.stop_reason === "end_turn" || response.tool_calls.length === 0) {
        const finalPhase = phases.finish();
        if (finalPhase) this.publish({ type: "phase.changed", run_id: runId, step, phase: finalPhase.to, previous: finalPhase.from, reason: finalPhase.reason, ts: now() });
        this.publish({ type: "step.finished", run_id: runId, step, ts: now() });
        messages.push({ role: "assistant", content: responseContent(response), ...(response.reasoning_content ? { reasoning_content: response.reasoning_content } : {}) });
        return { text: response.text, steps: step, messages, usage, contextPct: lastContextPct, compacted, summaries };
      }
      messages.push({ role: "assistant", content: responseContent(response), tool_calls: response.tool_calls, ...(response.reasoning_content ? { reasoning_content: response.reasoning_content } : {}) });
      for (const call of response.tool_calls) {
        signal?.throwIfAborted();
        const before = await extensions?.dispatch("before_tool_call", { toolName: call.name, input: call.input, toolCallId: call.id }, extensionRoot, { runId, sessionId: this.options.sessionId });
        if (before?.cancel) { messages.push({ role: "tool", tool_call_id: call.id, content: before.reason ?? "Tool call cancelled by extension", is_error: true }); continue; }
        const input = before?.input ?? call.input;
        const tool = this.tools.get(call.name);
        const toolName = tool?.name ?? call.name;
        const canonicalCall = tool ? { ...call, name: toolName, input } : { ...call, input };
        this.publish({ type: "tool.call_started", run_id: runId, tool_use_id: call.id, tool_name: toolName, params: input, ts: now() });
        const phaseChange = phases.observeTool(toolName, input);
        if (phaseChange) this.publish({ type: "phase.changed", run_id: runId, step, phase: phaseChange.to, previous: phaseChange.from, reason: phaseChange.reason, ts: now() });
        if (!tool) {
          stuck.recordFailure(stuckSignature(call));
          this.publish({ type: "tool.call_failed", run_id: runId, tool_use_id: call.id, tool_name: call.name, error_class: "unknown_tool", error_message: `Unknown tool: ${call.name}`, elapsed_ms: 0, ts: now() });
          messages.push({ role: "tool", tool_call_id: call.id, content: `Unknown tool: ${call.name}`, is_error: true });
          continue;
        }
        const validation = validateSchema(input, tool.schema);
        if (!validation.valid) {
          stuck.recordFailure(stuckSignature(canonicalCall));
          this.publish({ type: "tool.call_failed", run_id: runId, tool_use_id: call.id, tool_name: toolName, error_class: "schema_error", error_message: validation.error, elapsed_ms: 0, ts: now() });
          messages.push({ role: "tool", tool_call_id: call.id, content: validation.error, is_error: true });
          continue;
        }
        const permission = tool.classifyPermission?.(input) ?? tool.permission;
        const allowed = await this.permissions.check(runId, call.id, toolName, input, permission, signal);
        if (!allowed) {
          denials.recordDenial(toolName);
          this.publish({ type: "tool.call_failed", run_id: runId, tool_use_id: call.id, tool_name: toolName, error_class: "permission_denied", error_message: "Permission denied or approval timed out", elapsed_ms: 0, ts: now() });
          messages.push({ role: "tool", tool_call_id: call.id, content: "Permission denied", is_error: true });
          continue;
        }
        const started = Date.now();
        const result = await safeStartSpan(this.options.telemetry ?? NOOP_TELEMETRY_CONTEXT, { name: "tool.execution", attributes: { run_id: runId, tool_name: toolName, tool_use_id: call.id } }, async (span) => {
          try {
            const value = await invokeToolWithRetry(tool, input, { ...this.context, signal }, this.options.toolMaxRetries ?? nonNegativeEnv("SZTU_TOOL_MAX_RETRIES", 1), this.options.toolRetryBaseMs ?? nonNegativeEnv("SZTU_TOOL_RETRY_BASE_MS", 2_000), (attempt, failure) => {
              this.publish({ type: "log.line", run_id: runId, level: "WARN", source: "tool", message: `Retrying ${toolName} after attempt ${attempt}: ${failure.error ?? "Tool failed"}`, ts: now() });
            });
            span.setAttributes({ ok: value.ok, error_type: value.errorType ?? "" });
            return value;
          } catch (error) { span.recordError(error); throw error; }
        });
        const elapsedMs = Date.now() - started;
        await extensions?.dispatch("after_tool_call", { toolName, input, toolCallId: call.id, result }, extensionRoot, { runId, sessionId: this.options.sessionId });
        const rawOutput = result.ok ? result.output : [result.output, result.error].filter(Boolean).join("\n") || "Tool failed";
        let contextOutput = rawOutput;
        if (offload.shouldOffload(toolName, rawOutput)) {
          try { contextOutput = offload.placeholder(await offload.offload(toolName, call.id, rawOutput, runId, !result.ok)); } catch { /* Context truncation remains the fallback. */ }
        }
        if (result.ok) {
          denials.recordSuccess(toolName);
          stuck.recordSuccess(stuckSignature(canonicalCall));
          this.publish({ type: "tool.call_finished", run_id: runId, tool_use_id: call.id, tool_name: toolName, elapsed_ms: elapsedMs, output: contextOutput, ts: now() });
          if (isTestCommand(String(input.command ?? ""))) this.publish({ type: "test.result", run_id: runId, tool_use_id: call.id, status: "passed", summary: testSummary(String(input.command ?? ""), result.output), ts: now() });
        }
        else { stuck.recordFailure(stuckSignature(canonicalCall)); this.publish({ type: "tool.call_failed", run_id: runId, tool_use_id: call.id, tool_name: toolName, error_class: result.errorType ?? "runtime_error", error_message: result.error ?? "Tool failed", elapsed_ms: elapsedMs, ts: now() }); if (isTestCommand(String(input.command ?? ""))) this.publish({ type: "test.result", run_id: runId, tool_use_id: call.id, status: "failed", summary: testSummary(String(input.command ?? ""), result.error ?? "Tool failed"), ts: now() }); }
        messages.push({ role: "tool", tool_call_id: call.id, content: contextOutput, is_error: !result.ok });
      }
      this.publish({ type: "step.finished", run_id: runId, step, ts: now() });
      await extensions?.dispatch("turn_end", { goal, step, messages }, extensionRoot, { runId, sessionId: this.options.sessionId });
      if (maxSteps > 0 && step >= maxSteps) {
        const conclusion = await this.conclude(runId, step, messages, usage, lastContextPct, signal);
        if (conclusion.complete) return { text: conclusion.text, steps: step, messages, usage, contextPct: conclusion.contextPct, compacted, summaries };
        throw new Error(`Agent exceeded max steps (${maxSteps})${conclusion.text ? `: ${conclusion.text}` : ""}`);
      }
      const addedTokens = Math.max(0, context.tokenEstimate() - requestTokens);
      if (context.needsCompaction(compactThreshold, responseInputTokens || requestTokens, addedTokens)) startCompaction(step);
    }
    throw new Error("Agent stopped unexpectedly");
  }

  private async conclude(runId: string, step: number, messages: ChatMessage[], usage: ModelUsage, previousContextPct: number, signal?: AbortSignal): Promise<{ complete: boolean; text: string; contextPct: number }> {
    messages.push({ role: "user", content: "The agent run has reached its step limit and must stop now. Give your final answer. If the goal is fully achieved, start with [COMPLETE]. If work remains, start with [INCOMPLETE] and list it. Do not call tools." });
    const response = await this.provider.complete(messages, new ToolRegistry(), signal, (token) => this.publish({ type: "llm.token", run_id: runId, token, ts: now() }), { runId, step, purpose: "agent" }, (thinking) => this.publish({ type: "llm.thinking", run_id: runId, step, thinking, ts: now() }));
    usage.input_tokens += Number(response.usage?.input_tokens ?? 0);
    usage.output_tokens += Number(response.usage?.output_tokens ?? 0);
    usage.cache_read_input_tokens += Number(response.usage?.cache_read_input_tokens ?? 0);
    usage.cache_creation_input_tokens += Number(response.usage?.cache_creation_input_tokens ?? 0);
    const inputTokens = Number(response.usage?.input_tokens ?? 0); const contextPct = inputTokens > 0 ? inputTokens / resolveContextWindow(this.options.contextWindow) : previousContextPct;
    this.options.onProgress?.({ steps: step, usage: { ...usage }, contextPct });
    if (response.text && (!this.options.streaming || !response.streamed)) this.publish({ type: "llm.token", run_id: runId, token: response.text, ts: now() });
    messages.push({ role: "assistant", content: responseContent(response) });
    const text = response.text.trim();
    if (response.stop_reason !== "end_turn" || response.tool_calls.length > 0 || /^\[INCOMPLETE\]/i.test(text)) return { complete: false, text, contextPct };
    return { complete: true, text: text.replace(/^\[COMPLETE\]\s*/i, "") || text, contextPct };
  }

  private publish(event: RuntimeEvent): void { this.events.publish(event); }
}

const now = () => new Date().toISOString();
const nonNegativeEnv = (name: string, fallback: number): number => { const value = Number(process.env[name]); return Number.isInteger(value) && value >= 0 ? value : fallback; };
const numberEnv = (name: string, fallback: number, minimum: number, maximum: number): number => { const value = Number(process.env[name]); return Number.isFinite(value) && value >= minimum && value <= maximum ? value : fallback; };
const booleanEnv = (name: string, fallback: boolean): boolean => process.env[name] === undefined ? fallback : !/^(0|false|no)$/i.test(process.env[name] ?? "");
const dataRoot = () => process.env.SZTU_DATA_DIR ?? path.join(process.env.USERPROFILE ?? process.env.HOME ?? process.cwd(), ".sztu");
const safeRunId = (runId: string) => runId.replace(/[^A-Za-z0-9_.-]/g, "_") || "run";
const isTestCommand = (command: string): boolean => /(^|\s)(pytest|vitest|jest|npm\s+test|pnpm\s+test|yarn\s+test|cargo\s+test)(\s|$)/i.test(command);
const testSummary = (command: string, output: string): string => { const lines = output.split(/\r?\n/).map((line) => line.trim()).filter(Boolean); const relevant = lines.filter((line) => /passed|failed|error|test/i.test(line)); return (relevant.at(-1) ?? lines.at(-1) ?? command).slice(0, 300); };
const retryableToolErrors = new Set<ToolResult["errorType"]>(["runtime_error", "rate_limited"]);
const responseContent = (response: ModelResponse): ChatMessage["content"] => response.thinking_blocks?.length ? [...response.thinking_blocks, ...(response.text ? [{ type: "text", text: response.text }] : [])] : response.text;

async function invokeToolWithRetry(tool: Tool, input: Record<string, unknown>, context: ToolContext, maxRetries: number, retryBaseMs: number, onRetry: (attempt: number, failure: ToolResult) => void): Promise<ToolResult> {
  for (let attempt = 0; ; attempt += 1) {
    context.signal?.throwIfAborted();
    let result: ToolResult;
    try { result = await tool.invoke(input, context); }
    catch (error) {
      context.signal?.throwIfAborted();
      result = { ok: false, output: "", error: error instanceof Error ? error.message : String(error), errorType: "runtime_error" };
    }
    const errorType = result.errorType ?? "runtime_error";
    if (result.ok || !retryableToolErrors.has(errorType) || attempt >= maxRetries) return result;
    onRetry(attempt + 1, result);
    await abortableDelay(retryBaseMs * 2 ** attempt, context.signal);
  }
}

function abortableDelay(ms: number, signal?: AbortSignal): Promise<void> {
  signal?.throwIfAborted();
  if (ms <= 0) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const finish = () => { signal?.removeEventListener("abort", abort); resolve(); };
    const abort = () => { clearTimeout(timer); signal?.removeEventListener("abort", abort); reject(signal?.reason ?? new Error("Run cancelled")); };
    const timer = setTimeout(finish, ms);
    signal?.addEventListener("abort", abort, { once: true });
  });
}
