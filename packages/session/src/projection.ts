import type { ModelMessage } from "@sztucode/ai";
import { resolveBranch } from "./tree.js";
import type { SessionEntry, SessionSnapshot } from "./types.js";

const continuation = (summary: string): ModelMessage => ({ role: "user", content: `This session is being continued from a previous conversation.\n\nSummary:\n${summary}\n\nContinue directly from where the conversation left off.` });

export function projectModelContext(source: SessionSnapshot | SessionEntry[], leafId?: string | null): ModelMessage[] {
  const entries = Array.isArray(source) ? source : source.entries; const leaf = leafId === undefined && !Array.isArray(source) ? source.leafId : leafId ?? entries.at(-1)?.id ?? null; const output: ModelMessage[] = [];
  for (const entry of resolveBranch(entries, leaf)) {
    if (entry.type === "message") output.push(entry.message);
    else if (entry.type === "model_context") { output.splice(0, output.length, ...entry.messages); }
    else if (entry.type === "compaction") { output.splice(0, output.length, continuation(entry.summary), ...(entry.retainedMessages ?? [])); }
  }
  return output;
}
