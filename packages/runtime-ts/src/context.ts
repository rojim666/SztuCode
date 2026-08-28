import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { getEncoding, type Tiktoken } from "js-tiktoken";
import type { ModelInvocation } from "./agent-loop.js";

export type ContentBlock = { type: string; text?: string; content?: string; [key: string]: unknown };
export type ContextToolCall = { id: string; name: string; input: Record<string, unknown> };
export type ContextMessage = { role: "system" | "user" | "assistant" | "tool"; content: string | ContentBlock[]; tool_call_id?: string; tool_calls?: ContextToolCall[]; reasoning_content?: string; is_error?: boolean };
export type ContextCompactionProvider = { complete(messages: ContextMessage[], tools: { list(): unknown[] }, signal?: AbortSignal, onToken?: (token: string) => void, invocation?: ModelInvocation): Promise<{ text: string; usage?: { output_tokens?: number }; stop_reason?: string }> };
export type ContextCompactionResult = { originalTokens: number; summaryTokens: number; removedMessages: number; summaryText: string; usedModel: boolean; deferred?: boolean; failed?: boolean };

const CJK_RANGES: Array<[number, number]> = [[0x3400, 0x4dbf], [0x4e00, 0x9fff], [0xf900, 0xfaff], [0x20000, 0x2a6df]];
const isCjk = (char: string) => { const code = char.codePointAt(0) ?? 0; return CJK_RANGES.some(([low, high]) => code >= low && code <= high); };
const encoders = new Map<string, Tiktoken | null>();
const loadEncoder = (name: string): Tiktoken | null => { if (encoders.has(name)) return encoders.get(name)!; let encoder: Tiktoken | null = null; try { encoder = getEncoding(name as Parameters<typeof getEncoding>[0]); } catch { /* fallback below */ } encoders.set(name, encoder); return encoder; };

export class TokenCounter {
  private readonly encoder: Tiktoken | null;
  constructor(readonly encodingName = "cl100k_base") { this.encoder = loadEncoder(encodingName); }
  count(text: string): number {
    if (this.encoder) { try { return this.encoder.encode(text).length + 4; } catch { /* use the CJK-aware fallback */ } }
    if (!text) return 4;
    let cjk = 0;
    for (const char of text) if (isCjk(char)) cjk += 1;
    return Math.max(1, Math.ceil(cjk + (text.length - cjk) / 4) + 4);
  }
  countJson(value: unknown): number { return value === null || value === undefined || value === "" ? 0 : this.count(typeof value === "string" ? value : JSON.stringify(value)); }
  countMessages(messages: ContextMessage[]): number { return Math.max(1, messages.reduce((total, message) => total + (typeof message.content === "string" ? this.count(message.content) : message.content.reduce((sum, block) => sum + this.count(String(block.text ?? block.content ?? "")), 0)), 0)); }
  get preciseAvailable(): boolean { return this.encoder !== null; }
}

const OFFLOAD_MARKER = "[上下文卸载:";
const truncationMarker = (original: number, omitted: number, head: number, tail: number) => `\n[... original=${original} chars; ${omitted} chars omitted; kept=head:${head},tail:${tail} ...]\n`;

export function truncateText(text: string, budget: number, isError = false): string {
  if (text.length <= budget) return text;
  if (budget <= 0) return "";
  const ratio = isError ? 0.2 : 0.5;
  let retained = Math.min(text.length - 1, budget); let head = 0; let tail = 0; let marker = "";
  while (retained > 0) { head = Math.floor(retained * ratio); tail = retained - head; marker = truncationMarker(text.length, text.length - retained, head, tail); if (retained + marker.length <= budget) break; retained -= 1; }
  if (!retained) return truncationMarker(text.length, text.length, 0, 0).slice(0, budget);
  return text.slice(0, head) + marker + text.slice(text.length - tail);
}

export function truncateToolResults(messages: ContextMessage[], limit = 8_000, keep = 4_000): ContextMessage[] {
  const budget = Math.max(0, Math.min(limit, keep));
  return messages.map((message) => {
    if (message.role === "tool" && typeof message.content === "string" && message.content.length > limit && !message.content.includes(OFFLOAD_MARKER)) return { ...message, content: truncateText(message.content, budget) };
    if (message.role !== "user" || !Array.isArray(message.content)) return message;
    const content = message.content.map((block) => block.type === "tool_result" && typeof block.content === "string" && !block.content.includes(OFFLOAD_MARKER) && block.content.length > limit ? { ...block, content: truncateText(block.content, budget, block.is_error === true) } : block);
    return { ...message, content };
  });
}

export function sanitizeContextMessages(messages: ContextMessage[], toolResultLimit = 8_000): ContextMessage[] {
  const truncated = truncateToolResults(messages, toolResultLimit, Math.floor(toolResultLimit / 2));
  const pending = new Set<string>(); let lastBalanced = 0;
  truncated.forEach((message, index) => { if (message.role === "assistant") for (const call of message.tool_calls ?? []) pending.add(call.id); if (message.role === "tool" && message.tool_call_id) pending.delete(message.tool_call_id); if (!pending.size) lastBalanced = index + 1; });
  return pending.size ? truncated.slice(0, lastBalanced) : truncated;
}

function messagesToText(messages: ContextMessage[]): string {
  return messages.map((message) => { const content = typeof message.content === "string" ? message.content : message.content.map((block) => `${block.type}: ${String(block.text ?? block.content ?? "")}`).join("\n"); const calls = message.tool_calls?.length ? `\nTool calls: ${message.tool_calls.map((call) => `${call.name}(${JSON.stringify(call.input)})`).join(", ")}` : ""; return `[${message.role.toUpperCase()}]\n${content}${calls}`; }).join("\n\n");
}

type Turn = ContextMessage[];
function splitIntoTurns(messages: ContextMessage[]): { system: ContextMessage[]; preamble: Turn; body: Turn[] } {
  const system = messages.filter((message) => message.role === "system");
  const conversation = messages.filter((message) => message.role !== "system");
  const firstAssistant = conversation.findIndex((message) => message.role === "assistant");
  const preambleEnd = firstAssistant < 0 ? Math.min(1, conversation.length) : firstAssistant;
  const preamble = conversation.slice(0, preambleEnd); const body: Turn[] = []; let current: Turn = [];
  for (const message of conversation.slice(preambleEnd)) {
    if (message.role === "assistant" && current.length) { body.push(current); current = []; }
    if (message.role === "user" && current.length && !current.some((item) => item.role === "assistant")) { body.push(current); current = []; }
    current.push(message);
    if (message.role === "tool" && !message.tool_call_id) { body.push(current); current = []; }
  }
  if (current.length) body.push(current);
  return { system, preamble, body };
}

const continuationMessage = (summary: string) => "This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier portion of the conversation.\n\nSummary:\n" + summary + "\n\nContinue directly from where the conversation left off without acknowledging or recapping this summary.";
const continuationAck = (): ContentBlock[] => [{ type: "text", text: "Understood. I will continue from the summary without restating it.", cache_control: { type: "ephemeral" } }];
const flat = (turns: Turn[]) => turns.flatMap((turn) => turn);

export type ContextBudget = { maxTokens: number; reservedOutputTokens: number; maxToolResultChars: number };
export type CompactionOptions = { slidingWindow?: number; minimumOldTokens?: number; compactionCount?: number };

export type UsageSnapshot = { system: number; conversation: number; tool: number };

// 增量计数缓存：记录上次计数时的消息引用前缀，查询时若仍是纯追加则只对新尾部
// 编码。压缩/截断会整体替换消息对象，引用前缀失配时自动回退全量重数，保证结果
// 与全量路径一致。约束：已入列消息不得原地修改（只允许 push 追加）——agent-loop
// 与 compactWithProvider 均满足。
type UsageCache = { length: number; system: number; conversation: number; tool: number; refs: ContextMessage[] };

export class ContextManager {
  readonly counter: TokenCounter;
  private _usageCache: UsageCache | null = null;
  constructor(public messages: ContextMessage[] = [], private readonly budget: ContextBudget = { maxTokens: 128_000, reservedOutputTokens: 8_192, maxToolResultChars: 8_000 }, counter = new TokenCounter()) { this.counter = counter; }
  append(message: ContextMessage): void { this.messages.push(message); }

  // 统计单条消息的对话 token（与 TokenCounter.countMessages 的块语义一致）
  private countMessageContent(content: ContextMessage["content"]): number {
    return typeof content === "string" ? this.counter.count(content) : content.reduce((sum, block) => sum + this.counter.count(String(block.text ?? block.content ?? "")), 0);
  }

  // 分类 token 快照（system/conversation/tool），跨调用增量累积：
  // - 纯追加：仅对新尾部计数并累加，历史上下文不再重复编码
  // - 前缀失配（压缩/截断/回放）：全量重数后重建缓存
  usageSnapshot(): UsageSnapshot {
    const messages = this.messages;
    const cache = this._usageCache;
    if (cache) {
      const prev = cache.refs;
      const limit = Math.min(prev.length, messages.length);
      let overlap = 0;
      while (overlap < limit && messages[overlap] === prev[overlap]) overlap += 1;
      if (overlap === prev.length && messages.length >= prev.length) {
        let { system, conversation, tool } = cache;
        for (let i = prev.length; i < messages.length; i += 1) {
          const message = messages[i]!;
          if (message.role === "system") system += this.counter.countJson(message.content);
          else if (message.role === "tool") tool += this.counter.countJson(message.content);
          conversation += this.countMessageContent(message.content);
        }
        this._usageCache = { length: messages.length, system, conversation, tool, refs: [...messages] };
        return { system, conversation, tool };
      }
    }
    let system = 0;
    let tool = 0;
    for (const message of messages) {
      if (message.role === "system") system += this.counter.countJson(message.content);
      else if (message.role === "tool") tool += this.counter.countJson(message.content);
    }
    const conversation = this.counter.countMessages(messages);
    this._usageCache = { length: messages.length, system, conversation, tool, refs: [...messages] };
    return { system, conversation, tool };
  }

  tokenEstimate(): number { return this.usageSnapshot().conversation; }
  availableTokens(): number { return Math.max(0, this.budget.maxTokens - this.budget.reservedOutputTokens - this.tokenEstimate()); }
  budgetMaxToolResultChars(): number { return this.budget.maxToolResultChars; }
  contextPct(inputTokens?: number): number { return Math.max(0, Number(inputTokens ?? this.tokenEstimate())) / Math.max(1, this.budget.maxTokens); }
  needsCompaction(threshold = 0.70, inputTokens?: number, addedTokens = 0): boolean { return threshold > 0 && this.contextPct((inputTokens && inputTokens > 0 ? inputTokens : this.tokenEstimate()) + Math.max(0, addedTokens)) >= threshold; }
  compact(slidingWindow = 5): ContextCompactionResult {
    const originalTokens = this.tokenEstimate(); const { system, preamble, body } = splitIntoTurns(this.messages);
    if (body.length <= slidingWindow) return { originalTokens, summaryTokens: originalTokens, removedMessages: 0, summaryText: "", usedModel: false, deferred: true };
    const recent = flat(body.slice(-slidingWindow)); const old = flat(body.slice(0, -slidingWindow));
    const replacement = sanitizeContextMessages([...system, ...preamble, { role: "user", content: "[Earlier conversation compacted. Continue using the initial goal and recent turns.]" }, ...recent], this.budget.maxToolResultChars);
    this.messages.splice(0, this.messages.length, ...replacement);
    return { originalTokens, summaryTokens: this.tokenEstimate(), removedMessages: old.length, summaryText: "", usedModel: false };
  }
  async compactWithProvider(provider: ContextCompactionProvider, focus = "", slidingWindowOrOptions: number | CompactionOptions = 5, signal?: AbortSignal, invocation?: ModelInvocation): Promise<ContextCompactionResult> {
    const options = typeof slidingWindowOrOptions === "number" ? { slidingWindow: slidingWindowOrOptions, minimumOldTokens: 0, compactionCount: 0 } : slidingWindowOrOptions;
    const slidingWindow = options.slidingWindow ?? 5; const originalTokens = this.tokenEstimate(); const snapshotLength = this.messages.length; const { system, preamble, body } = splitIntoTurns(this.messages);
    const fullFallback = body.length <= slidingWindow;
    const oldTurns = fullFallback ? [] : body.slice(0, -slidingWindow); const recentTurns = fullFallback ? [] : body.slice(-slidingWindow);
    const old = fullFallback ? this.messages.filter((message) => message.role !== "system") : flat(oldTurns); const oldTokens = this.counter.countMessages(old);
    if (!old.length) return { originalTokens, summaryTokens: originalTokens, removedMessages: 0, summaryText: "", usedModel: false, deferred: true };
    if (!fullFallback && oldTokens < (options.minimumOldTokens ?? 2_000)) return { originalTokens, summaryTokens: originalTokens, removedMessages: 0, summaryText: "", usedModel: false, deferred: true };
    const prompt = ["Summarize the earlier agent conversation for continuation.", "Preserve the original goal, decisions, completed work, files and changes, failures, unresolved issues, and exact next steps.", "Be factual and compact. Do not invent information. Return plain text with headings: Goal, Progress, Decisions, Open Issues, Next Steps.", (options.compactionCount ?? 0) > 0 ? `This is compaction #${(options.compactionCount ?? 0) + 1}. Focus primarily on new information because the previous summary is already in the stable prefix.` : "", focus.trim() ? `Pay special attention to: ${focus.trim()}` : "", "\nEarlier turns:\n---\n" + messagesToText(old)].filter(Boolean).join("\n");
    try {
      const response = await provider.complete([{ role: "user", content: prompt }], { list: () => [] }, signal, undefined, invocation ? { ...invocation, purpose: "compaction" } : undefined);
      const summaryText = response.text.trim(); const summaryTokens = Number(response.usage?.output_tokens ?? this.counter.count(summaryText));
      const valid = response.stop_reason !== "max_tokens" && summaryText.length >= 40 && summaryTokens > 0 && summaryTokens < oldTokens && /goal|progress|next steps|open issues|decisions/i.test(summaryText);
      if (!valid) return { originalTokens, summaryTokens: originalTokens, removedMessages: 0, summaryText: "", usedModel: false, failed: true };
      const appendedWhileCompacting = this.messages.slice(snapshotLength);
      const replacement = sanitizeContextMessages([...system, ...(fullFallback ? [] : preamble), { role: "user", content: continuationMessage(summaryText) }, { role: "assistant", content: continuationAck() }, ...flat(recentTurns), ...appendedWhileCompacting], this.budget.maxToolResultChars);
      this.messages.splice(0, this.messages.length, ...replacement);
      return { originalTokens, summaryTokens: this.tokenEstimate(), removedMessages: old.length, summaryText, usedModel: true };
    } catch { return { originalTokens, summaryTokens: originalTokens, removedMessages: 0, summaryText: "", usedModel: false, failed: true }; }
  }
  async save(filePath: string): Promise<void> { await mkdir(path.dirname(filePath), { recursive: true }); await writeFile(filePath, `${JSON.stringify(this.messages)}\n`, "utf8"); }
  static async load(filePath: string): Promise<ContextManager> { try { return new ContextManager(JSON.parse(await readFile(filePath, "utf8")) as ContextMessage[]); } catch { return new ContextManager(); } }
}
