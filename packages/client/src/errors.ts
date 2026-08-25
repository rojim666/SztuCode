import type { ProtocolError } from "@sztucode/protocol";

export class ClientError extends Error { constructor(message: string) { super(message); this.name = "ClientError"; } }
export class ClientDisconnectedError extends ClientError { constructor(message = "Daemon connection is closed") { super(message); this.name = "ClientDisconnectedError"; } }
export class ClientClosedError extends ClientError { constructor() { super("Daemon client is closed"); this.name = "ClientClosedError"; } }
export class ClientTimeoutError extends ClientError {
  constructor(readonly requestId: string, readonly method: string, timeoutMs: number) { super(`${method} request ${requestId} timed out after ${timeoutMs}ms`); this.name = "ClientTimeoutError"; }
}
export class ClientProtocolError extends ClientError { constructor(message: string, readonly received?: unknown) { super(message); this.name = "ClientProtocolError"; } }
export class ClientRequestError extends ClientError {
  readonly code: number;
  readonly data: unknown;
  constructor(error: ProtocolError) { super(error.message); this.name = "ClientRequestError"; this.code = error.code; this.data = error.data; }
}
