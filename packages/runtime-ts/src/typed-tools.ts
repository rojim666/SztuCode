import type { AgentTool, JsonSchema, ToolExecutionMode, ToolResult } from "@sztucode/agent-core";
import type { Tool, ToolContext, ToolRegistry } from "./tools.js";

export type TypedToolContextFactory = (signal: AbortSignal, onFileChanged?: (relativePath: string) => void) => ToolContext;

/** Compatibility bridge for migrating legacy runtime tools one at a time. */
export function toTypedTool<TParams = Record<string, unknown>, TDetails = { output: string; error?: string; errorType?: string }>(tool: Tool, contextFactory: TypedToolContextFactory): AgentTool<TParams, TDetails> {
  return {
    name: tool.name,
    description: tool.description,
    parameters: tool.schema as JsonSchema<TParams>,
    aliases: tool.aliases,
    permission: tool.permission,
    classifyPermission: tool.classifyPermission as ((params: TParams) => import("@sztucode/agent-core").ToolPermission) | undefined,
    executionMode: tool.executionMode as ToolExecutionMode | undefined,
    timeoutMs: tool.timeoutMs,
    async execute(params, context): Promise<ToolResult<TDetails>> {
      const result = await tool.invoke(params as Record<string, unknown>, contextFactory(context.signal));
      const isError = !result.ok;
      return {
        content: isError ? result.error ?? result.output : result.output,
        details: { output: result.output, ...(result.error ? { error: result.error } : {}), ...(result.errorType ? { errorType: result.errorType } : {}) } as TDetails,
        isError,
        ...(isError ? { errorCode: result.errorType === "timeout" ? "TIMEOUT" as const : result.errorType === "permission_denied" ? "PERMISSION_DENIED" as const : "EXECUTION_FAILED" as const } : {}),
      };
    },
  };
}

export function toTypedTools(tools: readonly Tool[], contextFactory: TypedToolContextFactory): AgentTool<Record<string, unknown>>[] {
  return tools.map((tool) => toTypedTool(tool, contextFactory));
}

export function toTypedRegistry(registry: ToolRegistry, contextFactory: TypedToolContextFactory): AgentTool<Record<string, unknown>>[] {
  return toTypedTools(registry.list(), contextFactory);
}
