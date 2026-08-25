export type ProviderErrorKind = "authentication" | "invalid_request" | "rate_limit" | "server" | "network" | "timeout" | "aborted" | "parse" | "unknown";

export class ProviderError extends Error {
  readonly name = "ProviderError";
  constructor(
    readonly kind: ProviderErrorKind,
    message: string,
    readonly options: { status?: number; retryable?: boolean; retryAfterMs?: number; cause?: unknown } = {},
  ) {
    super(message, { cause: options.cause });
  }
  get status(): number | undefined { return this.options.status; }
  get retryable(): boolean { return this.options.retryable ?? ["rate_limit", "server", "network", "timeout"].includes(this.kind); }
  get retryAfterMs(): number | undefined { return this.options.retryAfterMs; }
}

export function isAbortError(error: unknown): boolean {
  return error instanceof ProviderError ? error.kind === "aborted" : error instanceof DOMException && error.name === "AbortError" || error instanceof Error && error.name === "AbortError";
}

export function normalizeProviderError(error: unknown): ProviderError {
  if (error instanceof ProviderError) return error;
  if (isAbortError(error)) return new ProviderError("aborted", "Provider request was aborted", { retryable: false, cause: error });
  const message = error instanceof Error ? error.message : String(error);
  const statusMatch = message.match(/\b(400|401|403|404|408|409|429|5\d\d)\b/);
  const status = statusMatch ? Number(statusMatch[1]) : undefined;
  let kind: ProviderErrorKind = "unknown";
  if (status === 401 || status === 403) kind = "authentication";
  else if (status === 429) kind = "rate_limit";
  else if (status !== undefined && status >= 500) kind = "server";
  else if (status !== undefined && status >= 400) kind = "invalid_request";
  else if (/timeout|ETIMEDOUT/i.test(message)) kind = "timeout";
  else if (/fetch failed|network|socket|ECONN|ENOTFOUND/i.test(message)) kind = "network";
  else if (/json|parse|invalid arguments/i.test(message)) kind = "parse";
  return new ProviderError(kind, message, { status, cause: error });
}

export function isRetryableProviderError(error: unknown): boolean { return normalizeProviderError(error).retryable; }
