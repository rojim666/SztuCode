import type { RuntimeEvent } from "@sztucode/protocol";
import type { ChatMessage } from "../agent-loop.js";
import type { Tool, ToolResult } from "../tools.js";

export type ExtensionScope = "global" | "workspace";
export type ExtensionHook =
  | "session_start" | "session_shutdown" | "before_agent_start" | "agent_start"
  | "turn_start" | "turn_end" | "before_tool_call" | "after_tool_call"
  | "context" | "compact" | "agent_end";

export interface ExtensionContext {
  readonly extensionId: string;
  readonly scope: ExtensionScope;
  readonly workspaceRoot: string;
  readonly sessionId?: string;
  readonly runId?: string;
}

export interface ToolCallHookPayload { toolName: string; input: Record<string, unknown>; toolCallId?: string; }
export interface BeforeToolCallResult { input?: Record<string, unknown>; cancel?: boolean; reason?: string; }
export interface AfterToolCallPayload extends ToolCallHookPayload { result: ToolResult; }
export interface ContextHookPayload { messages: readonly ChatMessage[]; contextPct?: number; }
export interface CompactHookPayload { messages: readonly ChatMessage[]; summary?: string; removedMessages?: number; }
export interface AgentHookPayload { goal: string; step?: number; messages?: readonly ChatMessage[]; error?: unknown; result?: unknown; }
export type ExtensionHookPayload = ToolCallHookPayload | AfterToolCallPayload | ContextHookPayload | CompactHookPayload | AgentHookPayload | { event?: RuntimeEvent; [key: string]: unknown };
export type ExtensionHookHandler<T = ExtensionHookPayload> = (payload: T, context: ExtensionContext) => void | BeforeToolCallResult | Promise<void | BeforeToolCallResult>;

export interface SlashCommand { name: string; description?: string; execute: (args: string, context: ExtensionContext) => string | Promise<string>; }
export interface PromptTemplate { name: string; description?: string; template: string | ((input: Record<string, unknown>, context: ExtensionContext) => string | Promise<string>); }
export interface ExtensionResource { name: string; description?: string; content: string | (() => string | Promise<string>); }
export interface ToolPromptContribution { toolName?: string; content: string | ((context: ExtensionContext) => string | Promise<string>); }
export type SessionEventListener = (event: RuntimeEvent, context: ExtensionContext) => void | Promise<void>;
export type Unregister = () => void;

export interface ExtensionAPI {
  readonly context: ExtensionContext;
  on(hook: ExtensionHook, handler: ExtensionHookHandler): Unregister;
  registerTool(tool: Tool): Unregister;
  registerSlashCommand(command: SlashCommand): Unregister;
  registerPromptTemplate(template: PromptTemplate): Unregister;
  registerResource(resource: ExtensionResource): Unregister;
  registerToolPromptContribution(contribution: ToolPromptContribution): Unregister;
  onSessionEvent(listener: SessionEventListener): Unregister;
}

export interface ExtensionDefinition {
  readonly id: string;
  readonly version?: string;
  readonly scope: ExtensionScope;
  readonly root: string;
  readonly activate: (api: ExtensionAPI) => void | Promise<void>;
  readonly deactivate?: (api: ExtensionAPI) => void | Promise<void>;
}

export type ExtensionDiagnosticPhase = "load" | "activate" | "deactivate" | "hook" | "register";
export interface ExtensionDiagnostic {
  extensionId: string;
  path: string;
  scope: ExtensionScope;
  phase: ExtensionDiagnosticPhase;
  hook?: ExtensionHook;
  message: string;
  error?: unknown;
}
