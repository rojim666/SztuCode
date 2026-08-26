import type { AssistantMessage, ContentBlock, Model, ModelMessage, ModelToolCall, StreamFn, ThinkingLevel, Usage } from "@sztucode/ai";
import type { AgentTool, AgentToolResult, ToolExecutionMode, ToolPermission } from "./tool-system.js";

export type AgentMessage = ModelMessage & { timestamp?: number; details?: unknown };
export type QueueMode = "all" | "one-at-a-time";
export type { AgentTool, AgentToolResult, ToolExecutionMode, ToolPermission } from "./tool-system.js";

export interface AgentState {
  systemPrompt: string;
  model: Model;
  thinkingLevel: ThinkingLevel;
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
  args: unknown;
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
  args: unknown;
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
  thinkingLevel?: ThinkingLevel;
  systemPrompt?: string;
  messages?: AgentMessage[];
  tools?: AgentTool[];
  toolExecution?: ToolExecutionMode;
  steeringMode?: QueueMode;
  followUpMode?: QueueMode;
  checkToolPermission?: (context: { tool: AgentTool; args: unknown; permission?: string; signal: AbortSignal }) => boolean | Promise<boolean>;
}

export type PromptInput = string | AgentMessage;
