import type { SessionEntry, SessionSnapshot } from "./types.js";

export class SessionValidationError extends Error {
  readonly code = "SESSION_INVALID";
  constructor(message: string, readonly line?: number) { super(message); this.name = "SessionValidationError"; }
}

const isObject = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);

export function validateSessionEntry(value: unknown, line?: number): asserts value is SessionEntry {
  if (!isObject(value) || typeof value.id !== "string" || typeof value.type !== "string" || typeof value.sequence !== "number" || !Number.isInteger(value.sequence) || value.sequence < 1 || (value.parentId !== null && typeof value.parentId !== "string") || typeof value.timestamp !== "string") throw new SessionValidationError("invalid session entry", line);
  if (value.type === "message" && !isObject(value.message)) throw new SessionValidationError("message entry requires message", line);
  if (value.type === "compaction" && typeof value.summary !== "string") throw new SessionValidationError("compaction entry requires summary", line);
  if (value.type === "model_context" && !Array.isArray(value.messages)) throw new SessionValidationError("model_context entry requires messages", line);
  if (value.type === "custom" && typeof value.customType !== "string") throw new SessionValidationError("custom entry requires customType", line);
  if (!["message", "compaction", "model_context", "custom"].includes(value.type)) throw new SessionValidationError(`unknown entry type: ${value.type}`, line);
}

export function validateSessionSnapshot(snapshot: unknown): asserts snapshot is SessionSnapshot {
  if (!isObject(snapshot) || !isObject(snapshot.header) || snapshot.header.type !== "session" || snapshot.header.version !== 1 || typeof snapshot.header.id !== "string" || !Array.isArray(snapshot.entries) || (snapshot.leafId !== null && typeof snapshot.leafId !== "string")) throw new SessionValidationError("invalid session snapshot");
  const ids = new Set<string>(); let previousSequence = 0;
  for (const entry of snapshot.entries) {
    validateSessionEntry(entry);
    if (ids.has(entry.id)) throw new SessionValidationError(`duplicate entry id: ${entry.id}`);
    if (entry.sequence <= previousSequence) throw new SessionValidationError("entry sequence must increase");
    if (entry.parentId !== null && !ids.has(entry.parentId)) throw new SessionValidationError(`missing parent entry: ${entry.parentId}`);
    ids.add(entry.id); previousSequence = entry.sequence;
  }
  if (snapshot.leafId !== null && !ids.has(snapshot.leafId)) throw new SessionValidationError(`missing leaf entry: ${snapshot.leafId}`);
}
