export type ServerErrorCode = "busy" | "session_locked" | "not_found" | "invalid_request" | "not_implemented";

export class ServerError extends Error {
  constructor(readonly code: ServerErrorCode, message: string, readonly details?: unknown) {
    super(message);
    this.name = "ServerError";
  }
}

export class SessionBusyError extends ServerError {
  constructor(message = "Session is busy", details?: unknown) {
    super("busy", message, details);
    this.name = "SessionBusyError";
  }
}

export class SessionLockedError extends ServerError {
  constructor(message = "Session is locked", details?: unknown) {
    super("session_locked", message, details);
    this.name = "SessionLockedError";
  }
}

export class SessionNotFoundError extends ServerError {
  constructor(message = "Session was not found", details?: unknown) {
    super("not_found", message, details);
    this.name = "SessionNotFoundError";
  }
}
