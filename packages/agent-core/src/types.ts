import type { AssistantMessage, ContentBlock, Model, ModelMessage, ModelToolCall, StreamFn, Usage } from "@sztucode/ai";

export type AgentMessage = ModelMessage & { timestamp?: number };
export type ToolExecutionMode = "sequential" | "parallel";
export type QueueMode = "all" | "one-at-a-time";

export interface AgentToolResult {
  content: string | ContentBlock[];
  details?: unknown;
  isError?: boolean;
  terminate?: boolean;
  usage?: Usage;
}

export interface AgentTool {
  name: string;
  description?: string;
  schema: Record<string, unknown>;
  execute: (callId: string, args: Record<string, unknown>, signal: AbortSignal, onUpdate: (partialResult: unknown) => void) => Promise<AgentToolResult>;
}

export interface AgentState {
  systemPrompt: string;
  model: Model;
  tools: AgentTool[];
  messages: AgentMessage[];
  readonly isStreaming: boolean;
  readonly streamingMessage?: AssistantMessage;
  readonly pendingToolCalls: ReadonlySet<string>;
  readonly errorMessage?: string;
  readonly steeringQueueSize: number;
  readonly followUpQueueSize: number;
}

export interface BeforeToolCallContext {
  assistantMessage: AssistantMessage;
  toolCall: ModelToolCall;
  args: Record<string, unknown>;
  messages: readonly AgentMessage[];
}

export interface BeforeToolCallResult {
  block?: boolean;
  reason?: string;
  terminate?: boolean;
}

export interface AfterToolCallContext {
  assistantMessage: AssistantMessage;
  toolCall: ModelToolCall;
  args: Record<string, unknown>;
  result: AgentToolResult;
  isError: boolean;
  messages: readonly AgentMessage[];
}

export interface AfterToolCallResult {
  content?: string | ContentBlock[];
  details?: unknown;
  isError?: boolean;
  terminate?: boolean;
  usage?: Usage;
}

export interface TurnHookContext {
  message: AssistantMessage;
  toolResults: AgentMessage[];
  messages: readonly AgentMessage[];
  newMessages: AgentMessage[];
}

export interface AgentHooks {
  beforeToolCall?: (context: BeforeToolCallContext, signal: AbortSignal) => BeforeToolCallResult | void | Promise<BeforeToolCallResult | void>;
  afterToolCall?: (context: AfterToolCallContext, signal: AbortSignal) => AfterToolCallResult | void | Promise<AfterToolCallResult | void>;
  shouldStopAfterTurn?: (context: TurnHookContext, signal: AbortSignal) => boolean | Promise<boolean>;
  prepareNextTurn?: (context: TurnHookContext, signal: AbortSignal) => void | Promise<void>;
}

export type AgentEvent =
  | { type: "agent_start"; messages: AgentMessage[] }
  | { type: "agent_end"; messages: AgentMessage[]; reason?: "completed" | "aborted" | "error"; error?: string }
  | { type: "turn_start"; turn: number }
  | { type: "turn_end"; turn: number; message: AssistantMessage; toolResults: AgentMessage[] }
  | { type: "message_start"; message: AgentMessage | AssistantMessage }
  | { type: "message_update"; message: AssistantMessage; event: "token" | "thinking" | "tool_call"; text?: string; call?: ModelToolCall }
  | { type: "message_end"; message: AgentMessage | AssistantMessage }
  | { type: "tool_execution_start"; toolCallId: string; toolName: string; args: Record<string, unknown> }
  | { type: "tool_execution_update"; toolCallId: string; toolName: string; args: Record<string, unknown>; partialResult: unknown }
  | { type: "tool_execution_end"; toolCallId: string; toolName: string; result: AgentToolResult; isError: boolean };

export type AgentListener = (event: AgentEvent, signal: AbortSignal) => void | Promise<void>;

export interface AgentOptions extends AgentHooks {
  model: Model;
  streamFn: StreamFn;
  systemPrompt?: string;
  messages?: AgentMessage[];
  tools?: AgentTool[];
  toolExecution?: ToolExecutionMode;
  steeringMode?: QueueMode;
  followUpMode?: QueueMode;
}

export type PromptInput = string | AgentMessage;
