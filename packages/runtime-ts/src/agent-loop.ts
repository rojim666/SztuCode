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
import { TaskCanvas } from "./task-canvas.js";

export type ChatMessage = ContextMessage;
export type ModelToolCall = { id: string; name: string; input: Record<string, unknown> };
export type ModelUsage = { input_tokens: number; output_tokens: number; cache_read_input_tokens: number; cache_creation_input_tokens: number };
export type ModelResponse = { text: string; tool_calls: ModelToolCall[]; stop_reason: "end_turn" | "tool_use" | "max_tokens"; thinking_blocks?: ContentBlock[]; reasoning_content?: string; usage?: Partial<ModelUsage>; model?: string; streamed?: boolean };
export type ModelInvocation = { runId: string; step: number; purpose?: "agent" | "compaction" };
export interface ModelProvider { complete(messages: ChatMessage[], tools: ToolRegistry, signal?: AbortSignal, onToken?: (token: string) => void, invocation?: ModelInvocation, onThinking?: (thinking: string) => void): Promise<ModelResponse> }
export type AgentProgress = { steps: number; usage: ModelUsage; contextPct: number };
export type AgentRunResult = { text: string; steps: number; messages: ChatMessage[]; usage: ModelUsage; contextPct: number; compacted: boolean; summaries: string[] };
export type AgentLoopOptions = { contextWindow?: number; maxOutputTokens?: number; sessionId?: string; streaming?: boolean; stuckMaxFailures?: number; stuckMaxTotal?: number; offloadEnabled?: boolean; offloadMinChars?: number; offloadMinLines?: number; offloadRoot?: string; toolMaxRetries?: number; toolRetryBaseMs?: number; toolMaxConcurrency?: number; maxWallClockMs?: number; maxLlmFailures?: number; compactThreshold?: number; slidingWindowSize?: number; compactCooldownSteps?: number; compactCircuitBreaker?: number; compactMinimumOldTokens?: number; compactBackground?: boolean; onProgress?: (progress: AgentProgress) => void; onCheckpoint?: (checkpoint: { step: number; sequence: number; phase: "tool_batch" | "completed" | "failed"; messages: ChatMessage[]; usage: ModelUsage }) => Promise<void> | void; onCompacted?: (messages: ChatMessage[], summary: string) => Promise<void>; extensions?: ExtensionRegistry; workspaceRoot?: string; telemetry?: TelemetryContext };

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
    // 墙钟时间预算
    const maxWallClockMs = this.options.maxWallClockMs ?? nonNegativeEnv("SZTU_MAX_WALL_CLOCK_MS", 0);
    const runStartTime = Date.now();
    // LLM 调用连续失败上限：达到前把错误回注对话让模型自行续跑；达到后诚实失败。0 表示首次失败即终止。
    const maxLlmFailures = this.options.maxLlmFailures ?? nonNegativeEnv("SZTU_MAX_LLM_FAILURES", 3);
    let llmFailures = 0;
    let checkpointSequence = 0;
    let currentStep = 0;
    const wallClockExceeded = (): boolean => maxWallClockMs > 0 && (Date.now() - runStartTime) >= maxWallClockMs;
    // TaskCanvas 任务画布
    const taskCanvas = new TaskCanvas();
    taskCanvas.recordStep({ label: "开始执行任务", summary: goal.slice(0, 100), toolNames: [], status: "done" });
    this.publish({ type: "log.line", run_id: runId, level: "INFO", source: "canvas", message: taskCanvas.renderMermaid(), ts: now() });
    // 后台压缩控制
    const compactBackground = this.options.compactBackground ?? booleanEnv("SZTU_COMPACT_BACKGROUND", true);
    let compactionRunning = false;
    // 熔断退路：LLM 摘要连续失败后，用无模型的硬丢弃压缩兜底，避免上下文持续膨胀到 API 报错
    const applyHardDropCompaction = async (): Promise<boolean> => {
      let fallback = context.compact(slidingWindowSize);
      // body <= 滑窗时 compact 会 deferred，但在小上下文场景这正是熔断发生的地方：
      // 退到极限窗口（只保留最近 1 个 turn），保证熔断后至少丢弃一批旧消息（body 为空才真正放弃）
      if (fallback.deferred && slidingWindowSize > 1) fallback = context.compact(1);
      if (fallback.deferred) return false;
      compacted = true;
      compactionCount += 1;
      taskCanvas.recordStep({ label: "上下文压缩（熔断退路）", summary: `硬丢弃 ${fallback.removedMessages} 条旧消息`, toolNames: [], status: "done" });
      this.publish({ type: "log.line", run_id: runId, level: "WARN", source: "context", message: `Compaction circuit breaker open after ${compactionFailures} summary failure(s); applied hard-drop compaction (${fallback.removedMessages} messages removed)`, ts: now() });
      if (this.options.sessionId) this.publish({ type: "context.compacted", session_id: this.options.sessionId, run_id: runId, original_tokens: fallback.originalTokens, summary_tokens: fallback.summaryTokens, ts: now() });
      await extensions?.dispatch("compact", { messages, summary: "", removedMessages: fallback.removedMessages }, extensionRoot, { runId, sessionId: this.options.sessionId });
      await this.options.onCompacted?.(messages, "");
      return true;
    };
    const startCompaction = async (step: number): Promise<boolean> => {
      if (pendingCompaction || compactionRunning || compactThreshold <= 0 || step - lastCompactStep < compactCooldownSteps) return false;
      // 熔断打开：LLM 摘要不可用，直接走硬丢弃退路（不消耗 LLM 调用）
      if (compactCircuitBreaker > 0 && compactionFailures >= compactCircuitBreaker) {
        lastCompactStep = step;
        return applyHardDropCompaction();
      }
      if (this.options.sessionId) this.publish({ type: "context.compacting", session_id: this.options.sessionId, run_id: runId, ts: now() });
      this.publish({ type: "log.line", run_id: runId, level: "INFO", source: "context", message: `Starting background compaction at step ${step}`, ts: now() });
      compactionRunning = true;
      // 创建快照用于压缩，避免并发修改消息数组
      const snapshotLength = messages.length;
      const messagesSnapshot = [...messages];
      pendingCompaction = safeStartSpan(this.options.telemetry ?? NOOP_TELEMETRY_CONTEXT, { name: "context.compaction", attributes: { run_id: runId, step, compaction_count: compactionCount, background: compactBackground } }, async (span) => {
        try {
          // 使用快照上下文进行压缩
          const snapshotContext = new ContextManager(messagesSnapshot, { maxTokens: context.budget.maxTokens, reservedOutputTokens: context.budget.reservedOutputTokens, maxToolResultChars: context.budget.maxToolResultChars });
          const result = await snapshotContext.compactWithProvider(this.provider, "", { slidingWindow: slidingWindowSize, minimumOldTokens: compactMinimumOldTokens, compactionCount }, signal, { runId, step, purpose: "compaction" });
          span.setAttributes({ removed_messages: result.removedMessages, summary_tokens: result.summaryTokens, failed: Boolean(result.failed) });
          // 附加快照长度信息，用于后续应用时合并
          (result as any).snapshotLength = snapshotLength;
          (result as any).compactMessages = snapshotContext.messages;
          return result;
        } catch (error) { span.recordError(error); throw error; } finally { compactionRunning = false; }
      });
      lastCompactStep = step;
      return true;
    };
    // 快速检查：后台压缩是否完成（非阻塞）
    const checkCompactionReady = (): boolean => {
      return pendingCompaction !== null;
    };
    // 应用已完成的压缩（阻塞等待）
    const applyPendingCompaction = async (blocking = false): Promise<boolean> => {
      if (!pendingCompaction) return false;
      if (!blocking && compactBackground) {
        // 非阻塞模式：检查 Promise 状态（不 await）
        // 我们通过一个微任务来检测是否已完成
        let isResolved = false;
        const check = Promise.race([
          pendingCompaction.then(() => { isResolved = true; }),
          Promise.resolve().then(() => {})
        ]);
        await check;
        if (!isResolved) return false;
      }
      const result = await pendingCompaction; pendingCompaction = null;
      if (result.failed) {
        compactionFailures += 1;
        this.publish({ type: "log.line", run_id: runId, level: "WARN", source: "context", message: `Compaction failed (${compactionFailures}/${compactCircuitBreaker || "unlimited"})`, ts: now() });
        // 熔断在本轮打开：立即硬丢弃一次，不等到下次触发才退化
        if (compactCircuitBreaker > 0 && compactionFailures >= compactCircuitBreaker) await applyHardDropCompaction();
        return false;
      }
      if (result.deferred) return false;
      // 应用压缩结果：合并快照后新增的消息
      const snapshotLength = (result as any).snapshotLength as number ?? messages.length;
      const compactMessages = (result as any).compactMessages as ContextMessage[] ?? [];
      const appendedWhileCompacting = messages.slice(snapshotLength);
      messages.splice(0, messages.length, ...compactMessages, ...appendedWhileCompacting);
      context.notifyMutated();
      compactionFailures = 0; compactionCount += 1; compacted = true;
      if (result.summaryText) summaries.push(result.summaryText);
      // 更新任务画布
      taskCanvas.recordStep({ label: "上下文压缩", summary: `压缩了 ${result.removedMessages} 条消息`, toolNames: [], status: result.failed ? "failed" : "done" });
      await extensions?.dispatch("compact", { messages, summary: result.summaryText, removedMessages: result.removedMessages }, extensionRoot, { runId, sessionId: this.options.sessionId });
      await this.options.onCompacted?.(messages, result.summaryText);
      this.publish({ type: "log.line", run_id: runId, level: "INFO", source: "context", message: `Summarized ${result.removedMessages} messages using a ${slidingWindowSize}-turn window`, ts: now() });
      if (this.options.sessionId) this.publish({ type: "context.compacted", session_id: this.options.sessionId, run_id: runId, original_tokens: result.originalTokens, summary_tokens: result.summaryTokens, ts: now() });
      return true;
    };
    const denials = new DenialTracker();
    const stuck = new StuckLoopTracker(this.options.stuckMaxFailures ?? nonNegativeEnv("SZTU_STUCK_MAX_FAILURES", 2), this.options.stuckMaxTotal ?? nonNegativeEnv("SZTU_STUCK_MAX_TOTAL", 0));
    const phases = createPhaseTracker();
    try {
    for (let step = 1; maxSteps === 0 || step <= maxSteps; step += 1) {
      currentStep = step;
      signal?.throwIfAborted();

      // 墙钟时间预算预检
      if (wallClockExceeded()) {
        this.publish({ type: "log.line", run_id: runId, level: "WARN", source: "loop", message: `Max wall clock time (${maxWallClockMs}ms) exceeded, stopping run`, ts: now() });
        const finalText = "Task stopped due to wall clock time limit exceeded.";
        taskCanvas.recordStep({ label: "超时终止", summary: `墙钟时间 ${maxWallClockMs}ms 已到`, status: "failed" });
        messages.push({ role: "assistant", content: finalText });
        return { text: finalText, steps: step - 1, messages, usage, contextPct: lastContextPct, compacted, summaries };
      }

      // 非阻塞检查后台压缩是否完成，仅在完成时应用
      await applyPendingCompaction(false);
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
      if (sanitized.length !== messages.length || sanitized.some((message, index) => message !== messages[index])) {
        messages.splice(0, messages.length, ...sanitized);
        context.notifyMutated();
      }
      await extensions?.dispatch("context", { messages, contextPct: lastContextPct }, extensionRoot, { runId, sessionId: this.options.sessionId });
      const requestTokens = context.tokenEstimate();
      let response: ModelResponse;
      try {
        const tokenBuffer = bufferedEmitter((token) => this.publish({ type: "llm.token", run_id: runId, token, ts: now() }));
        response = await this.provider.complete(messages, this.tools, signal, tokenBuffer.push, { runId, step, purpose: "agent" }, (thinking) => this.publish({ type: "llm.thinking", run_id: runId, step, thinking, ts: now() }));
        tokenBuffer.flush();
        llmFailures = 0;
      } catch (error) {
        // 用户主动取消不是故障，照常上抛
        if (signal?.aborted) throw error;
        llmFailures += 1;
        const reason = error instanceof Error ? error.message : String(error);
        if (llmFailures >= maxLlmFailures) throw error;
        // 错误回注对话：让失败成为对话的一部分而不是进程的终点，模型下一步可自行重试/续跑
        this.publish({ type: "log.line", run_id: runId, level: "ERROR", source: "llm", message: `Model call failed (${llmFailures}/${maxLlmFailures}): ${reason}`, ts: now() });
        messages.push({ role: "user", content: `The model API call failed (attempt ${llmFailures} of ${maxLlmFailures}): ${reason}\nNo output was produced for this step. Continue the task from the last completed step; do not repeat work that already finished.` });
        this.publish({ type: "step.finished", run_id: runId, step, ts: now() });
        continue;
      }
      usage.input_tokens += Number(response.usage?.input_tokens ?? 0);
      usage.output_tokens += Number(response.usage?.output_tokens ?? 0);
      usage.cache_read_input_tokens += Number(response.usage?.cache_read_input_tokens ?? 0);
      usage.cache_creation_input_tokens += Number(response.usage?.cache_creation_input_tokens ?? 0);
      const contextWindow = resolveContextWindow(this.options.contextWindow);
      const reservedOutputTokens = this.options.maxOutputTokens ?? 8_192;
      const responseInputTokens = Number(response.usage?.input_tokens ?? 0);
      lastContextPct = context.contextPct(responseInputTokens > 0 ? responseInputTokens : requestTokens);
      this.options.onProgress?.({ steps: step, usage: { ...usage }, contextPct: lastContextPct });
      const usageSnapshot = context.usageSnapshot();
      this.publish({ type: "llm.usage", run_id: runId, input_tokens: responseInputTokens, output_tokens: Number(response.usage?.output_tokens ?? 0), cache_read_input_tokens: Number(response.usage?.cache_read_input_tokens ?? 0), cache_creation_input_tokens: Number(response.usage?.cache_creation_input_tokens ?? 0), context_pct: lastContextPct, model: response.model ?? "", context_window: contextWindow, available_tokens: Math.max(0, contextWindow - reservedOutputTokens - (responseInputTokens || requestTokens)), reserved_output_tokens: reservedOutputTokens, system_tokens: usageSnapshot.system, summary_tokens: summaries.reduce((sum, summary) => sum + context.counter.count(summary), 0), conversation_tokens: usageSnapshot.conversation, tool_tokens: usageSnapshot.tool, ts: now() });
      if (response.text && (!this.options.streaming || !response.streamed)) this.publish({ type: "llm.token", run_id: runId, token: response.text, ts: now() });
      if (response.stop_reason === "end_turn") {
        const finalPhase = phases.finish();
        if (finalPhase) this.publish({ type: "phase.changed", run_id: runId, step, phase: finalPhase.to, previous: finalPhase.from, reason: finalPhase.reason, ts: now() });
        this.publish({ type: "step.finished", run_id: runId, step, ts: now() });
        messages.push({ role: "assistant", content: responseContent(response), ...(response.reasoning_content ? { reasoning_content: response.reasoning_content } : {}) });
        // 等待后台压缩完成（如果有）
        await applyPendingCompaction(true);
        await this.options.onCheckpoint?.({ step, sequence: ++checkpointSequence, phase: "completed", messages: [...messages], usage: { ...usage } });
        // TaskCanvas 记录任务完成
        taskCanvas.recordStep({ label: "任务完成", summary: response.text.slice(0, 100), status: "done" });
        this.publish({ type: "log.line", run_id: runId, level: "INFO", source: "canvas", message: taskCanvas.renderMermaid(), ts: now() });
        return { text: response.text, steps: step, messages, usage, contextPct: lastContextPct, compacted, summaries };
      }
      messages.push({ role: "assistant", content: responseContent(response), tool_calls: response.tool_calls, ...(response.reasoning_content ? { reasoning_content: response.reasoning_content } : {}) });

      // 达到阈值时启动后台压缩（利用工具执行期间的等待时间）
      if (lastContextPct >= compactThreshold && !pendingCompaction) {
        void startCompaction(step);
      }

      // TaskCanvas 记录本轮工具调用开始
      const toolNames = response.tool_calls.map(c => c.name);
      taskCanvas.recordStep({
        label: toolNames.slice(0, 3).join("; ") + (toolNames.length > 3 ? ` +${toolNames.length - 3}` : ""),
        toolNames,
        status: "running",
      });

      // 工具并发调度：只读工具批量并发执行，写工具/危险工具串行
      const toolMaxConcurrency = Math.max(1, this.options.toolMaxConcurrency ?? nonNegativeEnv("SZTU_TOOL_MAX_CONCURRENCY", 4));
      type BeforeToolCallResult = { cancel?: boolean; reason?: string; input?: Record<string, unknown> } | undefined;
      const preparedCalls: Array<{
        call: ModelToolCall;
        before: BeforeToolCallResult;
        input: Record<string, unknown>;
        tool: Tool | undefined;
        toolName: string;
        canonicalCall: ModelToolCall;
        canRunConcurrent: boolean;
      }> = [];

      for (const call of response.tool_calls) {
        signal?.throwIfAborted();
        const before = await extensions?.dispatch("before_tool_call", { toolName: call.name, input: call.input, toolCallId: call.id }, extensionRoot, { runId, sessionId: this.options.sessionId });
        const input = before?.input ?? call.input;
        const tool = this.tools.get(call.name);
        const toolName = tool?.name ?? call.name;
        const canonicalCall = tool ? { ...call, name: toolName, input } : { ...call, input };
        let canRunConcurrent = false;

        if (tool && !before?.cancel) {
          const validation = validateSchema(input, tool.schema);
          if (validation.valid) {
            const permission = tool.classifyPermission?.(input) ?? tool.permission;
            // 只读、非交互工具允许并发
            canRunConcurrent = permission === "read_only" && !(tool as any).isInteractive;
          }
        }

        preparedCalls.push({ call, before, input, tool, toolName, canonicalCall, canRunConcurrent });
      }

      // 分割为并发批次和串行序列
      const batches: Array<Array<typeof preparedCalls[0]>> = [];
      let currentBatch: Array<typeof preparedCalls[0]> = [];

      for (const prepared of preparedCalls) {
        if (prepared.canRunConcurrent && toolMaxConcurrency > 1) {
          currentBatch.push(prepared);
        } else {
          if (currentBatch.length > 0) {
            batches.push(currentBatch);
            currentBatch = [];
          }
          batches.push([prepared]);
        }
      }
      if (currentBatch.length > 0) batches.push(currentBatch);

      // 执行结果按原始顺序存储
      const toolResults = new Map<string, { result: ToolResult; elapsedMs: number; input: Record<string, unknown>; tool: Tool | undefined; toolName: string; canonicalCall: ModelToolCall }>();

      for (const batch of batches) {
        signal?.throwIfAborted();

        if (batch.length === 1 || !batch[0].canRunConcurrent) {
          // 串行执行
          const prepared = batch[0];
          const { call, before, input, tool, toolName, canonicalCall } = prepared;

          if (before?.cancel) {
            toolResults.set(call.id, { result: { ok: false, output: before.reason ?? "Tool call cancelled by extension", errorType: "runtime_error" }, elapsedMs: 0, input, tool, toolName, canonicalCall });
            continue;
          }

          this.publish({ type: "tool.call_started", run_id: runId, tool_use_id: call.id, tool_name: toolName, params: input, ts: now() });
          const phaseChange = phases.observeTool(toolName, input);
          if (phaseChange) this.publish({ type: "phase.changed", run_id: runId, step, phase: phaseChange.to, previous: phaseChange.from, reason: phaseChange.reason, ts: now() });

          if (!tool) {
            stuck.recordFailure(stuckSignature(call));
            this.publish({ type: "tool.call_failed", run_id: runId, tool_use_id: call.id, tool_name: call.name, error_class: "unknown_tool", error_message: `Unknown tool: ${call.name}`, elapsed_ms: 0, ts: now() });
            toolResults.set(call.id, { result: { ok: false, output: `Unknown tool: ${call.name}`, errorType: "runtime_error" }, elapsedMs: 0, input, tool, toolName, canonicalCall });
            continue;
          }

          const validation = validateSchema(input, tool.schema);
          if (!validation.valid) {
            stuck.recordFailure(stuckSignature(canonicalCall));
            this.publish({ type: "tool.call_failed", run_id: runId, tool_use_id: call.id, tool_name: toolName, error_class: "schema_error", error_message: validation.error, elapsed_ms: 0, ts: now() });
            toolResults.set(call.id, { result: { ok: false, output: validation.error, errorType: "schema_error" }, elapsedMs: 0, input, tool, toolName, canonicalCall });
            continue;
          }

          const permission = tool.classifyPermission?.(input) ?? tool.permission;
          const allowed = await this.permissions.check(runId, call.id, toolName, input, permission, signal, this.context.workspace.root);
          if (!allowed) {
            denials.recordDenial(toolName);
            this.publish({ type: "tool.call_failed", run_id: runId, tool_use_id: call.id, tool_name: toolName, error_class: "permission_denied", error_message: "Permission denied or approval timed out", elapsed_ms: 0, ts: now() });
            toolResults.set(call.id, { result: { ok: false, output: "Permission denied", errorType: "permission_denied" }, elapsedMs: 0, input, tool, toolName, canonicalCall });
            continue;
          }

          const started = Date.now();
          const toolContext = { ...this.context, signal, events: this.events, runId, toolUseId: call.id };
          const result = await safeStartSpan(this.options.telemetry ?? NOOP_TELEMETRY_CONTEXT, { name: "tool.execution", attributes: { run_id: runId, tool_name: toolName, tool_use_id: call.id, scheduler_mode: "serial" } }, async (span) => {
            try {
              const value = await invokeToolWithRetry(tool, input, toolContext, this.options.toolMaxRetries ?? nonNegativeEnv("SZTU_TOOL_MAX_RETRIES", 1), this.options.toolRetryBaseMs ?? nonNegativeEnv("SZTU_TOOL_RETRY_BASE_MS", 2_000), (attempt, failure) => {
                this.publish({ type: "log.line", run_id: runId, level: "WARN", source: "tool", message: `Retrying ${toolName} after attempt ${attempt}: ${failure.error ?? "Tool failed"}`, ts: now() });
              });
              span.setAttributes({ ok: value.ok, error_type: value.errorType ?? "" });
              return value;
            } catch (error) { span.recordError(error); throw error; }
          });
          const elapsedMs = Date.now() - started;
          toolResults.set(call.id, { result, elapsedMs, input, tool, toolName, canonicalCall });
        } else {
          // 并发执行只读工具批次（带信号量限流）
          const semaphore = { permits: Math.min(toolMaxConcurrency, batch.length), queue: [] as Array<() => void> };
          const acquire = async () => {
            if (semaphore.permits > 0) { semaphore.permits--; return; }
            await new Promise<void>(resolve => semaphore.queue.push(resolve));
          };
          const release = () => {
            if (semaphore.queue.length > 0) {
              const next = semaphore.queue.shift()!;
              next();
            } else {
              semaphore.permits++;
            }
          };

          // 预检查所有并发工具的权限（只读工具权限检查可批量进行）
          const permissionResults = new Map<string, boolean>();
          for (const prepared of batch) {
            const { call, input, tool, toolName } = prepared;
            if (!tool) { permissionResults.set(call.id, false); continue; }
            const permission = tool.classifyPermission?.(input) ?? tool.permission;
            const allowed = await this.permissions.check(runId, call.id, toolName, input, permission, signal, this.context.workspace.root);
            permissionResults.set(call.id, allowed);
          }

          await Promise.all(batch.map(async (prepared) => {
            const { call, before, input, tool, toolName, canonicalCall } = prepared;

            if (before?.cancel) {
              toolResults.set(call.id, { result: { ok: false, output: before.reason ?? "Tool call cancelled by extension", errorType: "runtime_error" }, elapsedMs: 0, input, tool, toolName, canonicalCall });
              return;
            }

            this.publish({ type: "tool.call_started", run_id: runId, tool_use_id: call.id, tool_name: toolName, params: input, ts: now() });
            const phaseChange = phases.observeTool(toolName, input);
            if (phaseChange) this.publish({ type: "phase.changed", run_id: runId, step, phase: phaseChange.to, previous: phaseChange.from, reason: phaseChange.reason, ts: now() });

            if (!tool) {
              stuck.recordFailure(stuckSignature(call));
              this.publish({ type: "tool.call_failed", run_id: runId, tool_use_id: call.id, tool_name: call.name, error_class: "unknown_tool", error_message: `Unknown tool: ${call.name}`, elapsed_ms: 0, ts: now() });
              toolResults.set(call.id, { result: { ok: false, output: `Unknown tool: ${call.name}`, errorType: "runtime_error" }, elapsedMs: 0, input, tool, toolName, canonicalCall });
              return;
            }

            const validation = validateSchema(input, tool.schema);
            if (!validation.valid) {
              stuck.recordFailure(stuckSignature(canonicalCall));
              this.publish({ type: "tool.call_failed", run_id: runId, tool_use_id: call.id, tool_name: toolName, error_class: "schema_error", error_message: validation.error, elapsed_ms: 0, ts: now() });
              toolResults.set(call.id, { result: { ok: false, output: validation.error, errorType: "schema_error" }, elapsedMs: 0, input, tool, toolName, canonicalCall });
              return;
            }

            const allowed = permissionResults.get(call.id) ?? false;
            if (!allowed) {
              denials.recordDenial(toolName);
              this.publish({ type: "tool.call_failed", run_id: runId, tool_use_id: call.id, tool_name: toolName, error_class: "permission_denied", error_message: "Permission denied or approval timed out", elapsed_ms: 0, ts: now() });
              toolResults.set(call.id, { result: { ok: false, output: "Permission denied", errorType: "permission_denied" }, elapsedMs: 0, input, tool, toolName, canonicalCall });
              return;
            }

            await acquire();
            const started = Date.now();
            const toolContext = { ...this.context, signal, events: this.events, runId, toolUseId: call.id };
            try {
              const result = await safeStartSpan(this.options.telemetry ?? NOOP_TELEMETRY_CONTEXT, { name: "tool.execution", attributes: { run_id: runId, tool_name: toolName, tool_use_id: call.id, scheduler_mode: "concurrent" } }, async (span) => {
                try {
                  const value = await invokeToolWithRetry(tool, input, toolContext, this.options.toolMaxRetries ?? nonNegativeEnv("SZTU_TOOL_MAX_RETRIES", 1), this.options.toolRetryBaseMs ?? nonNegativeEnv("SZTU_TOOL_RETRY_BASE_MS", 2_000), (attempt, failure) => {
                    this.publish({ type: "log.line", run_id: runId, level: "WARN", source: "tool", message: `Retrying ${toolName} after attempt ${attempt}: ${failure.error ?? "Tool failed"}`, ts: now() });
                  });
                  span.setAttributes({ ok: value.ok, error_type: value.errorType ?? "" });
                  return value;
                } catch (error) { span.recordError(error); throw error; }
              });
              const elapsedMs = Date.now() - started;
              toolResults.set(call.id, { result, elapsedMs, input, tool, toolName, canonicalCall });
            } finally {
              release();
            }
          }));
        }
      }

      // 按原始顺序处理结果并加入消息
      const toolSummaries: string[] = [];
      const refPaths: string[] = [];
      let hasFailures = false;
      for (const call of response.tool_calls) {
        const entry = toolResults.get(call.id);
        if (!entry) continue;
        const { result, elapsedMs, input, tool, toolName, canonicalCall } = entry;

        await extensions?.dispatch("after_tool_call", { toolName, input, toolCallId: call.id, result }, extensionRoot, { runId, sessionId: this.options.sessionId });
        const rawOutput = result.ok ? result.output : [result.output, result.error].filter(Boolean).join("\n") || "Tool failed";
        let contextOutput = rawOutput;
        if (offload.shouldOffload(toolName, rawOutput)) {
          try {
            const record = await offload.offload(toolName, call.id, rawOutput, runId, !result.ok);
            contextOutput = offload.placeholder(record);
            refPaths.push(record.ref_path);
          } catch { /* Context truncation remains the fallback. */ }
        }
        // 生成工具结果摘要
        const summaryText = result.ok
          ? `${toolName}: ${String(rawOutput).slice(0, 80).replace(/\n/g, " ")}`
          : `${toolName} failed: ${result.error ?? "error"}`;
        toolSummaries.push(summaryText);
        if (!result.ok) hasFailures = true;

        if (result.ok) {
          denials.recordSuccess(toolName);
          stuck.recordSuccess(stuckSignature(canonicalCall));
          this.publish({ type: "tool.call_finished", run_id: runId, tool_use_id: call.id, tool_name: toolName, elapsed_ms: elapsedMs, output: contextOutput, ts: now() });
          if (tool && isTestCommand(String(input.command ?? ""))) this.publish({ type: "test.result", run_id: runId, tool_use_id: call.id, status: "passed", summary: testSummary(String(input.command ?? ""), result.output), ts: now() });
        }
        else {
          stuck.recordFailure(stuckSignature(canonicalCall));
          this.publish({ type: "tool.call_failed", run_id: runId, tool_use_id: call.id, tool_name: toolName, error_class: result.errorType ?? "runtime_error", error_message: result.error ?? "Tool failed", elapsed_ms: elapsedMs, ts: now() });
          if (tool && isTestCommand(String(input.command ?? ""))) this.publish({ type: "test.result", run_id: runId, tool_use_id: call.id, status: "failed", summary: testSummary(String(input.command ?? ""), result.error ?? "Tool failed"), ts: now() });
        }
        messages.push({ role: "tool", tool_call_id: call.id, content: contextOutput, is_error: !result.ok });
      }

      // 更新 TaskCanvas 本轮工具执行结果
      taskCanvas.finalizeLast({
        status: hasFailures ? "failed" : "done",
        summary: toolSummaries.join("; ").slice(0, 200),
        refs: refPaths,
      });
      // 定期发布画布更新
      if (step % 3 === 0 || taskCanvas.nodeCount <= 3) {
        this.publish({ type: "log.line", run_id: runId, level: "INFO", source: "canvas", message: taskCanvas.renderMermaid(), ts: now() });
      }

      // 工具执行完毕后，如果后台压缩已完成则立即应用
      await applyPendingCompaction(false);

      this.publish({ type: "step.finished", run_id: runId, step, ts: now() });
      await this.options.onCheckpoint?.({ step, sequence: ++checkpointSequence, phase: "tool_batch", messages: [...messages], usage: { ...usage } });
      await extensions?.dispatch("turn_end", { goal, step, messages }, extensionRoot, { runId, sessionId: this.options.sessionId });
      if (maxSteps > 0 && step >= maxSteps) {
        const conclusion = await this.conclude(runId, step, messages, usage, lastContextPct, signal, taskCanvas);
        if (conclusion.complete) return { text: conclusion.text, steps: step, messages, usage, contextPct: conclusion.contextPct, compacted, summaries };
        throw new Error(`Agent exceeded max steps (${maxSteps})${conclusion.text ? `: ${conclusion.text}` : ""}`);
      }
      // 兜底：如果还没有启动压缩且需要压缩，则启动（工具执行期间可能已经启动了）
      const addedTokens = Math.max(0, context.tokenEstimate() - requestTokens);
      if (context.needsCompaction(compactThreshold, responseInputTokens || requestTokens, addedTokens) && !pendingCompaction) {
        void startCompaction(step);
      }
    }
    throw new Error("Agent stopped unexpectedly");
    } catch (error) {
      // 失败也带上已积累的对话状态：上层（RunManager）在失败路径持久化，避免多步工作成果随异常蒸发
      if (error instanceof Error && messages.length) {
        const carrier = error as Error & { partialMessages?: ChatMessage[] };
        if (!carrier.partialMessages) carrier.partialMessages = messages;
      }
      await this.options.onCheckpoint?.({ step: currentStep, sequence: ++checkpointSequence, phase: "failed", messages: [...messages], usage: { ...usage } });
      throw error;
    }
  }

  private async conclude(runId: string, step: number, messages: ChatMessage[], usage: ModelUsage, previousContextPct: number, signal?: AbortSignal, taskCanvas?: TaskCanvas): Promise<{ complete: boolean; text: string; contextPct: number }> {
    messages.push({ role: "user", content: "The agent run has reached its step limit and must stop now. Give your final answer. If the goal is fully achieved, start with [COMPLETE]. If work remains, start with [INCOMPLETE] and list it. Do not call tools." });
    const tokenBuffer = bufferedEmitter((token) => this.publish({ type: "llm.token", run_id: runId, token, ts: now() }));
    const response = await this.provider.complete(messages, new ToolRegistry(), signal, tokenBuffer.push, { runId, step, purpose: "agent" }, (thinking) => this.publish({ type: "llm.thinking", run_id: runId, step, thinking, ts: now() }));
    tokenBuffer.flush();
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
// Coalesce provider deltas into short frames to keep the event bus affordable during streaming.
function bufferedEmitter(emit: (text: string) => void, windowMs = 75): { push: (text: string) => void; flush: () => void } {
  let pending = ""; let timer: ReturnType<typeof setTimeout> | undefined;
  const flush = () => { if (timer) clearTimeout(timer); timer = undefined; if (pending) { const text = pending; pending = ""; emit(text); } };
  return { push(text) { pending += text; if (!timer) timer = setTimeout(flush, windowMs); }, flush };
}
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
    // retryable === false 的工具（如 bash）失败不自动重试：exit≠0 是业务结果而非基础设施故障，且命令可能非幂等
    if (result.ok || tool.retryable === false || !retryableToolErrors.has(errorType) || attempt >= maxRetries) return result;
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
