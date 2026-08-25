import type { AssistantMessage, ModelContext, ModelEvent, ModelToolCall, Model, ThinkingLevel } from "@sztucode/ai";
import type { AgentEvent, AgentListener, AgentMessage, AgentOptions, AgentState, AgentTool, AgentToolResult, PromptInput, QueueMode, TurnHookContext } from "./types.js";
import { validateToolParameters, type ToolExecutionContext } from "./tool-system.js";

class MessageQueue {
  private items: AgentMessage[] = [];
  constructor(public mode: QueueMode) {}
  push(message: AgentMessage): void { this.items.push(message); }
  drain(): AgentMessage[] { return this.mode === "all" ? this.takeAll() : this.items.splice(0, 1); }
  private takeAll(): AgentMessage[] { const values = this.items; this.items = []; return values; }
  clear(): void { this.items = []; }
  get size(): number { return this.items.length; }
}

type MutableState = {
  systemPrompt: string;
  model: AgentState["model"];
  thinkingLevel: ThinkingLevel;
  tools: AgentTool[];
  messages: AgentMessage[];
  isStreaming: boolean;
  streamingMessage?: AssistantMessage;
  pendingToolCalls: Set<string>;
  errorMessage?: string;
  steeringQueueSize: number;
  followUpQueueSize: number;
};

const copyState = (state: MutableState): AgentState => ({
  get systemPrompt() { return state.systemPrompt; },
  set systemPrompt(value) { state.systemPrompt = value; },
  get model() { return state.model; },
  set model(value) { state.model = value; },
  get thinkingLevel() { return state.thinkingLevel; },
  set thinkingLevel(value) { state.thinkingLevel = value; },
  get tools() { return state.tools.slice(); },
  set tools(value) { state.tools = value.slice(); },
  get messages() { return state.messages.slice(); },
  set messages(value) { state.messages = value.slice(); },
  get isStreaming() { return state.isStreaming; },
  get streamingMessage() { return state.streamingMessage; },
  get pendingToolCalls() { return new Set(state.pendingToolCalls); },
  get errorMessage() { return state.errorMessage; },
  get steeringQueueSize() { return state.steeringQueueSize; },
  get followUpQueueSize() { return state.followUpQueueSize; },
});

export class Agent {
  private readonly mutable: MutableState;
  private readonly listeners = new Set<AgentListener>();
  private readonly steeringQueue: MessageQueue;
  private readonly followUpQueue: MessageQueue;
  private active?: { promise: Promise<void>; controller: AbortController };
  readonly options: AgentOptions;

  constructor(options: AgentOptions) {
    this.options = options;
    this.mutable = { systemPrompt: options.systemPrompt ?? "", model: options.model, thinkingLevel: options.thinkingLevel ?? "off", tools: options.tools?.slice() ?? [], messages: options.messages?.slice() ?? [], isStreaming: false, pendingToolCalls: new Set(), steeringQueueSize: 0, followUpQueueSize: 0 };
    this.steeringQueue = new MessageQueue(options.steeringMode ?? "one-at-a-time");
    this.followUpQueue = new MessageQueue(options.followUpMode ?? "one-at-a-time");
  }

  get state(): AgentState { return copyState(this.mutable); }
  setModel(model: Model): void { if (this.active) throw new Error("Cannot change model while agent is processing"); this.mutable.model = model; }
  setThinkingLevel(level: ThinkingLevel): void { if (this.active) throw new Error("Cannot change thinking level while agent is processing"); this.mutable.thinkingLevel = level; }
  replaceMessages(messages: AgentMessage[]): void { if (this.active) throw new Error("Cannot replace messages while agent is processing"); this.mutable.messages = messages.slice(); }
  get signal(): AbortSignal | undefined { return this.active?.controller.signal; }
  get steeringMode(): QueueMode { return this.steeringQueue.mode; }
  set steeringMode(mode: QueueMode) { this.steeringQueue.mode = mode; }
  get followUpMode(): QueueMode { return this.followUpQueue.mode; }
  set followUpMode(mode: QueueMode) { this.followUpQueue.mode = mode; }

  subscribe(listener: AgentListener): () => void { this.listeners.add(listener); return () => this.listeners.delete(listener); }
  steer(message: PromptInput): void { this.steeringQueue.push(normalizeMessage(message)); this.syncQueueState(); }
  followUp(message: PromptInput): void { this.followUpQueue.push(normalizeMessage(message)); this.syncQueueState(); }
  abort(): void { this.active?.controller.abort(new Error("Agent aborted")); }
  waitForIdle(): Promise<void> { return this.active?.promise ?? Promise.resolve(); }
  hasQueuedMessages(): boolean { return this.steeringQueue.size > 0 || this.followUpQueue.size > 0; }
  reset(): void {
    if (this.active) throw new Error("Agent is already processing. Wait for completion before resetting.");
    this.mutable.messages = []; this.mutable.streamingMessage = undefined; this.mutable.pendingToolCalls.clear(); this.mutable.errorMessage = undefined; this.steeringQueue.clear(); this.followUpQueue.clear(); this.syncQueueState();
  }

  async prompt(input: PromptInput | PromptInput[]): Promise<void> {
    if (this.active) throw new Error("Agent is already processing a prompt. Use steer() or followUp() to queue messages.");
    const messages = (Array.isArray(input) ? input : [input]).map(normalizeMessage);
    await this.start(messages, false);
  }

  async continue(): Promise<void> {
    if (this.active) throw new Error("Agent is already processing. Wait for completion before continuing.");
    const last = this.mutable.messages.at(-1);
    if (!last) throw new Error("No messages to continue from");
    if (last.role === "assistant") {
      const queued = this.steeringQueue.drain();
      if (queued.length) return this.start(queued, true);
      const follow = this.followUpQueue.drain();
      if (follow.length) return this.start(follow, false);
      throw new Error("Cannot continue from message role: assistant");
    }
    await this.start([], true);
  }

  private async start(initial: AgentMessage[], continuation: boolean): Promise<void> {
    const controller = new AbortController();
    const active = { promise: Promise.resolve(), controller };
    this.active = active; this.mutable.isStreaming = true; this.mutable.errorMessage = undefined;
    const promise = this.run(initial, continuation, controller).finally(() => {
      if (this.active === active) this.active = undefined;
      this.mutable.isStreaming = false; this.mutable.streamingMessage = undefined; this.mutable.pendingToolCalls.clear();
    });
    active.promise = promise;
    return promise;
  }

  private async run(initial: AgentMessage[], continuation: boolean, controller: AbortController): Promise<void> {
    const newMessages: AgentMessage[] = [];
    try {
      await this.emit({ type: "agent_start", messages: initial.slice() });
      for (const message of initial) { this.mutable.messages.push(message); newMessages.push(message); await this.emit({ type: "message_start", message }); await this.emit({ type: "message_end", message }); }
      let pending = initial.length ? initial.slice() : [];
      let turn = 0;
      while (true) {
        if (controller.signal.aborted) throw controller.signal.reason ?? new Error("Agent aborted");
        const steering = pending.length ? pending : this.steeringQueue.drain(); this.syncQueueState();
        if (steering.length) { for (const message of steering) { if (!initial.includes(message)) { this.mutable.messages.push(message); newMessages.push(message); await this.emit({ type: "message_start", message }); await this.emit({ type: "message_end", message }); } } }
        turn += 1; await this.emit({ type: "turn_start", turn });
        let assistant: AssistantMessage;
        try {
          assistant = await this.requestAssistant(controller.signal);
        } catch (error) {
          const aborted = controller.signal.aborted || error instanceof Error && /aborted|cancelled/i.test(error.message);
          const failed: AssistantMessage = { role: "assistant", text: "", toolCalls: [], stopReason: aborted ? "aborted" : "error" };
          await this.emit({ type: "message_start", message: failed }); await this.emit({ type: "message_end", message: failed }); await this.emit({ type: "turn_end", turn, message: failed, toolResults: [] });
          throw error;
        }
        const assistantMessage = toAgentMessage(assistant); newMessages.push(assistantMessage); this.mutable.messages.push(assistantMessage);
        const toolResults = await this.executeTools(assistant, controller.signal);
        for (const result of toolResults) {
          this.mutable.messages.push(result); newMessages.push(result);
          await this.emit({ type: "message_start", message: result });
          await this.emit({ type: "message_end", message: result });
        }
        const hookContext: TurnHookContext = { message: assistant, toolResults, messages: this.mutable.messages.slice(), newMessages: newMessages.slice() };
        await this.emit({ type: "turn_end", turn, message: assistant, toolResults });
        await this.options.prepareNextTurn?.(hookContext, controller.signal);
        if (await this.options.shouldStopAfterTurn?.(hookContext, controller.signal)) return await this.finish(newMessages, "completed");
        const nextSteering = this.steeringQueue.drain(); this.syncQueueState();
        if (nextSteering.length || toolResults.length) { pending = nextSteering; continue; }
        const follow = this.followUpQueue.drain(); this.syncQueueState();
        if (follow.length) { pending = follow; continue; }
        return await this.finish(newMessages, "completed");
      }
    } catch (error) {
      const aborted = controller.signal.aborted || error instanceof Error && error.message === "Agent aborted";
      this.mutable.errorMessage = aborted ? "Agent aborted" : error instanceof Error ? error.message : String(error);
      await this.finish(newMessages, aborted ? "aborted" : "error", this.mutable.errorMessage);
    }
  }

  private async requestAssistant(signal: AbortSignal): Promise<AssistantMessage> {
    this.mutable.streamingMessage = undefined;
    const contextMessages = this.mutable.systemPrompt ? [{ role: "system" as const, content: this.mutable.systemPrompt }, ...this.mutable.messages] : this.mutable.messages;
    const context: ModelContext = { messages: contextMessages, tools: this.mutable.tools.map(({ name, description, parameters }) => ({ name, description, schema: parameters })), system: this.mutable.systemPrompt };
    let final: AssistantMessage | undefined;
    let started = false;
    for await (const event of this.options.streamFn(this.mutable.model, context, { signal, thinkingLevel: this.mutable.thinkingLevel })) {
      if (event.type === "token" || event.type === "thinking" || event.type === "tool_call") {
        const current: AssistantMessage = this.mutable.streamingMessage ?? { role: "assistant", text: "", toolCalls: [], stopReason: "end_turn" };
        if (!started) { started = true; await this.emit({ type: "message_start", message: snapshotAssistant(current) }); }
        if (event.type === "token") current.text += event.text;
        if (event.type === "thinking") current.thinking = `${current.thinking ?? ""}${event.text}`;
        if (event.type === "tool_call") current.toolCalls.push(event.call);
        this.mutable.streamingMessage = current;
        await this.emit({ type: "message_update", message: snapshotAssistant(current), event: event.type === "tool_call" ? "tool_call" : event.type, ...(event.type === "token" || event.type === "thinking" ? { text: event.text } : { call: event.call }) });
      } else if (event.type === "completed") { final = event.message; }
      else if (event.type === "error") throw event.error;
      else if (event.type === "aborted") throw new Error(event.reason ?? "Agent aborted");
    }
    if (!final) throw new Error("Provider stream ended without a completed message");
    this.mutable.streamingMessage = final; if (!started) await this.emit({ type: "message_start", message: final }); await this.emit({ type: "message_end", message: final }); this.mutable.streamingMessage = undefined;
    return final;
  }

  private async executeTools(assistant: AssistantMessage, signal: AbortSignal): Promise<AgentMessage[]> {
    const calls = assistant.toolCalls ?? [];
    if (this.options.toolExecution === "sequential" || calls.some((call) => this.findTool(call.name)?.executionMode === "sequential") || calls.length < 2) {
      const results: AgentMessage[] = []; for (const call of calls) results.push(await this.executeTool(assistant, call, signal)); return results;
    }
    const results = await Promise.all(calls.map((call) => this.executeTool(assistant, call, signal)));
    return results;
  }

  private async executeTool(assistant: AssistantMessage, call: ModelToolCall, signal: AbortSignal): Promise<AgentMessage> {
    const tool = this.findTool(call.name); this.mutable.pendingToolCalls.add(call.id); this.syncQueueState();
    await this.emit({ type: "tool_execution_start", toolCallId: call.id, toolName: call.name, args: call.input });
    let result: AgentToolResult = { content: `Tool ${call.name} not found`, isError: true, errorCode: "NOT_FOUND" };
    let isError = true;
    let hookArgs: unknown = call.input;
    const updateEvents: Promise<void>[] = [];
    try {
      if (tool) {
        const validation = validateToolParameters(call.input, tool.parameters);
        if (!validation.valid) result = { content: validation.error ?? "Invalid tool arguments", isError: true, errorCode: "INVALID_ARGUMENTS" };
        else if (this.options.checkToolPermission && !await this.options.checkToolPermission({ tool, args: validation.value, permission: tool.classifyPermission?.(validation.value as never) ?? tool.permission, signal })) result = { content: `Permission denied for tool ${tool.name}`, isError: true, errorCode: "PERMISSION_DENIED" };
        else {
          hookArgs = validation.value;
          const before = await this.options.beforeToolCall?.({ assistantMessage: assistant, toolCall: call, args: hookArgs, messages: this.mutable.messages.slice() }, signal);
          if (!before?.block) {
            result = await this.executeWithTimeout(tool, validation.value, call.id, signal, updateEvents);
            isError = result.isError === true;
          } else result = { content: before.reason ?? "Tool execution was blocked", isError: true, errorCode: "PERMISSION_DENIED", terminate: before.terminate };
        }
        const after = await this.options.afterToolCall?.({ assistantMessage: assistant, toolCall: call, args: hookArgs, result, isError, messages: this.mutable.messages.slice() }, signal);
        if (after) {
          result = { ...result, ...(after.content === undefined ? {} : { content: after.content }), ...(after.details === undefined ? {} : { details: after.details }), ...(after.terminate === undefined ? {} : { terminate: after.terminate }), ...(after.usage === undefined ? {} : { usage: after.usage }), isError: after.isError ?? isError };
          isError = result.isError === true;
        }
      }
    } catch (error) { result = { content: error instanceof Error ? error.message : String(error), isError: true, errorCode: "EXECUTION_FAILED" }; }
    this.mutable.pendingToolCalls.delete(call.id); this.syncQueueState();
    await this.emit({ type: "tool_execution_end", toolCallId: call.id, toolName: call.name, result, isError });
    return { role: "tool", tool_call_id: call.id, content: result.content, ...(result.details === undefined ? {} : { details: result.details }), is_error: isError };
  }

  private findTool(name: string): AgentTool | undefined { return this.mutable.tools.find((tool) => tool.name === name || tool.aliases?.includes(name)); }

  private async executeWithTimeout(tool: AgentTool, args: unknown, callId: string, parentSignal: AbortSignal, updateEvents: Promise<void>[]): Promise<AgentToolResult> {
    const controller = new AbortController();
    const abort = () => controller.abort(parentSignal.reason);
    parentSignal.addEventListener("abort", abort, { once: true });
    let timer: ReturnType<typeof setTimeout> | undefined;
    const updates = (update: { content?: string | readonly unknown[]; details?: unknown }) => { updateEvents.push(this.emit({ type: "tool_execution_update", toolCallId: callId, toolName: tool.name, args: args as Record<string, unknown>, partialResult: update })); };
    try {
      const execution = tool.execute(args as never, { callId, signal: controller.signal, onUpdate: updates } as ToolExecutionContext);
      if (!tool.timeoutMs || tool.timeoutMs <= 0) return await execution;
      return await new Promise<AgentToolResult>((resolve) => {
        let settled = false;
        const finish = (result: AgentToolResult) => { if (settled) return; settled = true; parentSignal.removeEventListener("abort", parentAbort); resolve(result); };
        const parentAbort = () => { controller.abort(parentSignal.reason); finish({ content: `Tool ${tool.name} was aborted`, isError: true, errorCode: "ABORTED" }); };
        parentSignal.addEventListener("abort", parentAbort, { once: true });
        timer = setTimeout(() => { controller.abort(new Error("Tool execution timed out")); finish({ content: `Tool ${tool.name} timed out after ${tool.timeoutMs}ms`, isError: true, errorCode: "TIMEOUT" }); }, tool.timeoutMs);
        execution.then((result) => finish(result), (error) => finish({ content: error instanceof Error ? error.message : String(error), isError: true, errorCode: "EXECUTION_FAILED" }));
      });
    } finally { if (timer) clearTimeout(timer); parentSignal.removeEventListener("abort", abort); }
  }

  private async finish(messages: AgentMessage[], reason: "completed" | "aborted" | "error", error?: string): Promise<void> { await this.emit({ type: "agent_end", messages: messages.slice(), reason, ...(error ? { error } : {}) }); }
  private syncQueueState(): void { this.mutable.steeringQueueSize = this.steeringQueue.size; this.mutable.followUpQueueSize = this.followUpQueue.size; }
  private async emit(event: AgentEvent): Promise<void> { for (const listener of [...this.listeners]) await listener(event, this.signal ?? new AbortController().signal); }
}

function normalizeMessage(input: PromptInput): AgentMessage {
  return typeof input === "string" ? { role: "user", content: input, timestamp: Date.now() } : { ...input, timestamp: input.timestamp ?? Date.now() };
}

function toAgentMessage(message: AssistantMessage): AgentMessage {
  const blocks = message.thinkingBlocks?.slice() ?? [];
  if (message.text) blocks.push({ type: "text", text: message.text });
  return { role: "assistant", content: blocks.length ? blocks : message.text, ...(message.toolCalls.length ? { tool_calls: message.toolCalls } : {}), ...(message.reasoningContent ? { reasoning_content: message.reasoningContent } : {}), timestamp: Date.now() };
}

function snapshotAssistant(message: AssistantMessage): AssistantMessage {
  return { ...message, toolCalls: message.toolCalls.map((call) => ({ ...call, input: { ...call.input } })), ...(message.thinkingBlocks ? { thinkingBlocks: message.thinkingBlocks.slice() } : {}) };
}
