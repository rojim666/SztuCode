import { ServerError } from "./errors.js";
import type { ConnectionState, RpcHandler, RpcRequest, RpcResponse, RpcRouterContext } from "./types.js";

export const PARSE_ERROR = -32700;
export const INVALID_REQUEST = -32600;
export const METHOD_NOT_FOUND = -32601;
export const INVALID_PARAMS = -32602;
export const INTERNAL_ERROR = -32603;

const success = <T>(id: RpcRequest["id"], result: T): RpcResponse<T> => ({ jsonrpc: "2.0", id, result });
const failure = (id: RpcRequest["id"], code: number, message: string, data?: unknown): RpcResponse => ({
  jsonrpc: "2.0", id, error: { code, message, ...(data === undefined ? {} : { data }) },
});

export class RpcRouter {
  private readonly handlers = new Map<string, RpcHandler>();

  register(method: string, handler: RpcHandler): this {
    if (!method.trim()) throw new TypeError("RPC method must not be empty");
    this.handlers.set(method, handler);
    return this;
  }

  unregister(method: string): boolean { return this.handlers.delete(method); }

  has(method: string): boolean { return this.handlers.has(method); }

  async dispatch(request: RpcRequest, context: RpcRouterContext | ConnectionState): Promise<RpcResponse> {
    const state = "connection" in context ? context.connection : context;
    const handler = this.handlers.get(request.method);
    if (!handler) return failure(request.id, METHOD_NOT_FOUND, `Method not found: ${request.method}`);
    try {
      return success(request.id, await handler(request.params, { connection: state }));
    } catch (error) {
      if (error instanceof ServerError) {
        const code = error.code === "busy" ? -32012 : error.code === "not_found" ? -32004 : INVALID_PARAMS;
        return failure(request.id, code, error.message, error.details);
      }
      const message = error instanceof Error ? error.message : String(error);
      if (/not found|unknown session/i.test(message)) return failure(request.id, -32004, message);
      if (/required|invalid|must be/i.test(message)) return failure(request.id, INVALID_PARAMS, message);
      return failure(request.id, INTERNAL_ERROR, message);
    }
  }
}

export function isRpcRequest(value: unknown): value is RpcRequest {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return item.jsonrpc === "2.0" && (typeof item.id === "string" || typeof item.id === "number" || item.id === null) && typeof item.method === "string";
}

export { success as rpcSuccess, failure as rpcFailure };

