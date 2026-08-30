export type BillingEffect = "none" | "possible" | "charged" | "unknown";

export class ProviderError extends Error {
  readonly name = "ProviderError";
  constructor(message: string, readonly details: {
    status?: number;
    requestId?: string;
    retryAfterMs?: number;
    retryable: boolean;
    billingEffect: BillingEffect;
    partialResponse?: boolean;
    retryExhausted?: boolean;
  }) { super(message); }
}

export async function providerHttpError(response: Response, provider: string): Promise<ProviderError> {
  const status = response.status;
  const requestId = response.headers.get("request-id") ?? response.headers.get("x-request-id") ?? undefined;
  const retryAfterMs = parseRetryAfter(response.headers.get("retry-after"));
  const body = (await response.text()).slice(0, 500);
  return new ProviderError(`${provider} request failed (${status})${requestId ? ` [request ${requestId}]` : ""}: ${body}`, {
    status, requestId, retryAfterMs, retryable: [408, 425, 429, 500, 502, 503, 504].includes(status), billingEffect: status >= 500 ? "unknown" : "none",
  });
}

export function parseRetryAfter(value: string | null, now = Date.now()): number | undefined {
  if (!value) return undefined;
  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) return Math.ceil(seconds * 1_000);
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? Math.max(0, timestamp - now) : undefined;
}

export function retryDelayMs(error: unknown, attempt: number, random = Math.random): number {
  if (error instanceof ProviderError && error.details.retryAfterMs !== undefined) return error.details.retryAfterMs;
  const cap = Math.min(60_000, 500 * 2 ** Math.max(0, attempt));
  return Math.floor(random() * cap);
}

export function retryableProviderError(error: unknown): boolean {
  if (error instanceof ProviderError) return error.details.retryable;
  const message = error instanceof Error ? error.message : String(error);
  return /\b(408|425|429|500|502|503|504)\b|timeout|fetch failed|network|socket|ECONN|ETIMEDOUT/i.test(message);
}

export async function abortableDelay(delayMs: number, signal?: AbortSignal): Promise<void> {
  if (delayMs <= 0) return;
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(resolve, delayMs);
    const abort = () => { clearTimeout(timer); reject(signal?.reason instanceof Error ? signal.reason : new Error("Provider retry aborted")); };
    signal?.addEventListener("abort", abort, { once: true });
  });
}
