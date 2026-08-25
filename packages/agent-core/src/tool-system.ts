import type { ContentBlock, Usage } from "@sztucode/ai";

/** JSON Schema subset used by tools. The phantom generic keeps parameters typed at compile time. */
export type JsonSchema<T = unknown> = {
  type?: "object" | "array" | "string" | "number" | "integer" | "boolean" | "null" | (string & {}) | Array<string>;
  properties?: Record<string, JsonSchema<unknown>>;
  required?: string[];
  items?: JsonSchema<unknown>;
  enum?: unknown[];
  const?: unknown;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  minItems?: number;
  maxItems?: number;
  additionalProperties?: boolean | JsonSchema<unknown>;
  allOf?: JsonSchema<unknown>[];
  anyOf?: JsonSchema<unknown>[];
  oneOf?: JsonSchema<unknown>[];
  pattern?: string;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
  description?: string;
  readonly __params?: T;
};

export type ToolPermission = "read_only" | "workspace_write" | "danger_full_access" | (string & {});
export type ToolExecutionMode = "sequential" | "parallel";
export type ToolContent = string | ContentBlock[];
export type ToolErrorCode = "INVALID_ARGUMENTS" | "PERMISSION_DENIED" | "EXECUTION_FAILED" | "TIMEOUT" | "ABORTED" | "NOT_FOUND";

export interface ToolUpdate<TDetails = unknown> {
  content?: ToolContent;
  details?: TDetails;
}

export interface ToolResult<TDetails = unknown> {
  content: ToolContent;
  details?: TDetails;
  isError?: boolean;
  errorCode?: ToolErrorCode;
  terminate?: boolean;
  usage?: Usage;
}

export interface ToolExecutionContext<TDetails = unknown> {
  callId: string;
  signal: AbortSignal;
  onUpdate: (update: ToolUpdate<TDetails>) => void;
}

export interface AgentTool<TParams = unknown, TDetails = unknown> {
  name: string;
  description: string;
  parameters: JsonSchema<TParams>;
  aliases?: readonly string[];
  permission?: ToolPermission;
  classifyPermission?: (params: TParams) => ToolPermission;
  executionMode?: ToolExecutionMode;
  timeoutMs?: number;
  execute: (params: TParams, context: ToolExecutionContext<TDetails>) => Promise<ToolResult<TDetails>>;
}

export interface ValidationResult<T = unknown> {
  valid: boolean;
  value?: T;
  error?: string;
}

export function validateToolParameters<T>(value: unknown, schema: JsonSchema<T>, path = "$", root = value): ValidationResult<T> {
  void root;
  for (const child of schema.allOf ?? []) { const result = validateToolParameters(value, child, path); if (!result.valid) return result as ValidationResult<T>; }
  if (schema.anyOf?.length && !schema.anyOf.some((child) => validateToolParameters(value, child, path).valid)) return invalid(`${path} does not match any allowed schema`);
  if (schema.oneOf?.length && schema.oneOf.filter((child) => validateToolParameters(value, child, path).valid).length !== 1) return invalid(`${path} must match exactly one allowed schema`);
  if (schema.const !== undefined && !Object.is(value, schema.const)) return invalid(`${path} must equal ${JSON.stringify(schema.const)}`);
  if (schema.enum && !schema.enum.some((candidate) => Object.is(candidate, value))) return invalid(`${path} must be one of ${schema.enum.map((candidate) => JSON.stringify(candidate)).join(", ")}`);
  const type = Array.isArray(schema.type) ? schema.type : schema.type ? [schema.type] : [];
  if (type.length && !type.some((candidate) => matchesType(value, candidate))) return invalid(`${path} must be ${type.join(" or ")}`);
  const primaryType = type.find((candidate) => matchesType(value, candidate));
  if (primaryType === "object") {
    if (!isRecord(value)) return invalid(`${path} must be an object`);
    for (const key of schema.required ?? []) if (!(key in value)) return invalid(`${path}.${key} is required`);
    for (const [key, child] of Object.entries(schema.properties ?? {})) if (key in value) { const result = validateToolParameters(value[key], child, `${path}.${key}`); if (!result.valid) return result as ValidationResult<T>; }
    for (const key of Object.keys(value)) if (!(key in (schema.properties ?? {})) && schema.additionalProperties === false) return invalid(`${path}.${key} is not allowed`); else if (!(key in (schema.properties ?? {})) && schema.additionalProperties && typeof schema.additionalProperties === "object") { const result = validateToolParameters(value[key], schema.additionalProperties, `${path}.${key}`); if (!result.valid) return result as ValidationResult<T>; }
  } else if (primaryType === "array") {
    if (!Array.isArray(value)) return invalid(`${path} must be an array`);
    if (schema.minItems !== undefined && value.length < schema.minItems) return invalid(`${path} must contain at least ${schema.minItems} item(s)`);
    if (schema.maxItems !== undefined && value.length > schema.maxItems) return invalid(`${path} must contain at most ${schema.maxItems} item(s)`);
    if (schema.items) for (let index = 0; index < value.length; index += 1) { const result = validateToolParameters(value[index], schema.items, `${path}[${index}]`); if (!result.valid) return result as ValidationResult<T>; }
  } else if (primaryType === "string") {
    if (typeof value !== "string") return invalid(`${path} must be a string`);
    if (schema.minLength !== undefined && value.length < schema.minLength) return invalid(`${path} must contain at least ${schema.minLength} character(s)`);
    if (schema.maxLength !== undefined && value.length > schema.maxLength) return invalid(`${path} must contain at most ${schema.maxLength} character(s)`);
    if (schema.pattern) { try { if (!new RegExp(schema.pattern).test(value)) return invalid(`${path} does not match the required pattern`); } catch { return invalid(`${path} has an invalid schema pattern`); } }
  } else if (primaryType === "number" || primaryType === "integer") {
    if (typeof value !== "number" || !Number.isFinite(value) || primaryType === "integer" && !Number.isInteger(value)) return invalid(`${path} must be a ${primaryType}`);
    if (schema.minimum !== undefined && value < schema.minimum) return invalid(`${path} must be >= ${schema.minimum}`);
    if (schema.maximum !== undefined && value > schema.maximum) return invalid(`${path} must be <= ${schema.maximum}`);
    if (schema.exclusiveMinimum !== undefined && value <= schema.exclusiveMinimum) return invalid(`${path} must be > ${schema.exclusiveMinimum}`);
    if (schema.exclusiveMaximum !== undefined && value >= schema.exclusiveMaximum) return invalid(`${path} must be < ${schema.exclusiveMaximum}`);
  }
  return { valid: true, value: value as T };
}

export type AgentToolResult<TDetails = unknown> = ToolResult<TDetails>;

function invalid<T>(error: string): ValidationResult<T> { return { valid: false, error }; }
function isRecord(value: unknown): value is Record<string, unknown> { return typeof value === "object" && value !== null && !Array.isArray(value); }
function matchesType(value: unknown, type: string): boolean {
  if (type === "object") return isRecord(value);
  if (type === "array") return Array.isArray(value);
  if (type === "integer") return typeof value === "number" && Number.isInteger(value);
  if (type === "number") return typeof value === "number" && Number.isFinite(value);
  if (type === "null") return value === null;
  return typeof value === type;
}
