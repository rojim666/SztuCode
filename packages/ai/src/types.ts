export type ThinkingLevel = "off" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max";

export interface ModelRef {
  provider: string;
  id: string;
}

export interface Model extends ModelRef {
  name?: string;
  api: string;
  contextWindow: number;
  maxTokens: number;
  reasoning: boolean;
  [key: string]: unknown;
}

export interface Usage {
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  cacheWriteTokens: number;
  totalTokens?: number;
}

export type MessageRole = "system" | "user" | "assistant" | "tool";
export interface ContentBlock {
  type: string;
  [key: string]: unknown;
}

export interface ModelToolCall {
  id: string;
  name: string;
  input: Record<string, unknown>;
}

export interface ModelMessage {
  role: MessageRole;
  content: string | ContentBlock[];
  tool_call_id?: string;
  tool_calls?: ModelToolCall[];
  reasoning_content?: string;
  is_error?: boolean;
}

export interface ToolDefinition {
  name: string;
  description?: string;
  schema: Record<string, unknown>;
}

export interface ModelContext {
  messages: ModelMessage[];
  tools?: ToolDefinition[];
  system?: string;
}

export interface StreamOptions {
  signal?: AbortSignal;
  thinkingLevel?: ThinkingLevel;
  maxTokens?: number;
  temperature?: number;
  invocation?: { runId?: string; step?: number; purpose?: string };
}

export interface AssistantMessage {
  role: "assistant";
  text: string;
  toolCalls: ModelToolCall[];
  stopReason: "end_turn" | "tool_use" | "max_tokens" | string;
  thinking?: string;
  thinkingBlocks?: ContentBlock[];
  reasoningContent?: string;
  usage?: Usage;
  model?: ModelRef;
}

export type AssistantMessageEvent =
  | { type: "token"; text: string }
  | { type: "thinking"; text: string }
  | { type: "tool_call"; call: ModelToolCall }
  | { type: "usage"; usage: Usage }
  | { type: "completed"; message: AssistantMessage }
  | { type: "error"; error: import("./errors.js").ProviderError };

export type ModelEvent = AssistantMessageEvent | { type: "aborted"; reason?: string };

export type StreamFn = (model: Model, context: ModelContext, options?: StreamOptions) => AsyncIterable<ModelEvent>;

export interface ProviderStream {
  stream: StreamFn;
}
