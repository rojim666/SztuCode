import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { getEncoding, type Tiktoken } from "js-tiktoken";
import type { ModelInvocation } from "./agent-loop.js";

export type ContentBlock = { type: string; text?: string; content?: string; [key: string]: unknown };
export type ContextToolCall = { id: string; name: string; input: Record<string, unknown> };
export type ContextMessage = { role: "system" | "user" | "assistant" | "tool"; content: string | ContentBlock[]; tool_call_id?: string; tool_calls?: ContextToolCall[]; reasoning_content?: string; is_error?: boolean };
export type ContextCompactionProvider = { complete(messages: ContextMessage[], tools: { list(): unknown[] }, signal?: AbortSignal, onToken?: (token: string) => void, invocation?: ModelInvocation): Promise<{ text: string; usage?: { input_tokens?: number; output_tokens?: number }; stop_reason?: string }> };
export type ContextCompactionResult = { originalTokens: number; summaryTokens: number; removedMessages: number; summaryText: string; usedModel: boolean; deferred?: boolean; failed?: boolean; usage?: { input_tokens?: number; output_tokens?: number } };

const CJK_RANGES: Array<[number, number]> = [[0x3400, 0x4dbf], [0x4e00, 0x9fff], [0xf900, 0xfaff], [0x20000, 0x2a6df]];
const isCjk = (char: string) => { const code = char.codePointAt(0) ?? 0; return CJK_RANGES.some(([low, high]) => code >= low && code <= high); };
const encoders = new Map<string, Tiktoken | null>();
const loadEncoder = (name: string): Tiktoken | null => { if (encoders.has(name)) return encoders.get(name)!; let encoder: Tiktoken | null = null; try { encoder = getEncoding(name as Parameters<typeof getEncoding>[0]); } catch { /* fallback below */ } encoders.set(name, encoder); return encoder; };

export class TokenCounter {
  private readonly encoder: Tiktoken | null;
  // 默认 o200k_base：GPT-4o/5 系真实编码（js-tiktoken 支持），比 cl100k_base 更贴近现役模型分词
  constructor(readonly encodingName = "o200k_base") { this.encoder = loadEncoder(encodingName); }
  // 按 provider/模型名选择真实编码：OpenAI 系（gpt/o1/o3/o4/chatgpt）用 o200k_base；其余模型无本地真实 tokenizer，默认沿用 o200k_base 作为估算基准
  static forModel(provider?: string, model?: string): TokenCounter {
    const family = `${provider ?? ""} ${model ?? ""}`;
    const isOpenAi = /openai/i.test(provider ?? "") || /gpt|o1|o3|o4|chatgpt/i.test(family);
    return new TokenCounter(isOpenAi ? "o200k_base" : "o200k_base");
  }
  // 纯编码长度（不含每段 +4 开销），供消息级计数统一在消息层加一次开销，避免分块重复累加
  rawCount(text: string): number {
    if (this.encoder) { try { return this.encoder.encode(text).length; } catch { /* use the CJK-aware fallback */ } }
    if (!text) return 0;
    let cjk = 0;
    for (const char of text) if (isCjk(char)) cjk += 1;
    return Math.max(1, Math.ceil(cjk + (text.length - cjk) / 4));
  }
  count(text: string): number { return this.rawCount(text) + 4; }
  countJson(value: unknown): number { return value === null || value === undefined || value === "" ? 0 : this.count(typeof value === "string" ? value : JSON.stringify(value)); }
  rawCountJson(value: unknown): number { return value === null || value === undefined || value === "" ? 0 : this.rawCount(typeof value === "string" ? value : JSON.stringify(value)); }
  countMessages(messages: ContextMessage[]): number { return Math.max(1, messages.reduce((total, message) => total + 4 + (typeof message.content === "string" ? this.rawCount(message.content) : message.content.reduce((sum, block) => sum + this.rawCount(String(block.text ?? block.content ?? "")), 0)), 0)); }
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

export class IncrementalContextSanitizer {
  private sourceLength = 0; private sourceTail: ContextMessage | undefined; private limit = 0;
  private sanitized: ContextMessage[] = []; private readonly pending = new Set<string>(); private lastBalanced = 0;
  sanitize(messages: ContextMessage[], toolResultLimit = 8_000): ContextMessage[] {
    const appendOnly = this.limit === toolResultLimit && this.sourceLength <= messages.length && (this.sourceLength === 0 || messages[this.sourceLength - 1] === this.sourceTail);
    if (!appendOnly) { this.sourceLength = 0; this.sourceTail = undefined; this.sanitized = []; this.pending.clear(); this.lastBalanced = 0; }
    for (const source of messages.slice(this.sourceLength)) {
      const message = truncateToolResults([source], toolResultLimit, Math.floor(toolResultLimit / 2))[0]!;
      this.sanitized.push(message);
      if (message.role === "assistant") for (const call of message.tool_calls ?? []) this.pending.add(call.id);
      if (message.role === "tool" && message.tool_call_id) this.pending.delete(message.tool_call_id);
      if (!this.pending.size) this.lastBalanced = this.sanitized.length;
    }
    this.sourceLength = messages.length; this.sourceTail = messages.at(-1); this.limit = toolResultLimit;
    return this.pending.size ? this.sanitized.slice(0, this.lastBalanced) : this.sanitized;
  }
}

export function microcompactToolResults(messages: ContextMessage[], keepRecent = 4, limit = 1_000): ContextMessage[] {
  const toolIndexes = messages.map((message, index) => message.role === "tool" ? index : -1).filter((index) => index >= 0);
  const compact = new Set(toolIndexes.slice(0, Math.max(0, toolIndexes.length - keepRecent)));
  let changed = false;
  const result = messages.map((message, index) => {
    if (!compact.has(index) || typeof message.content !== "string" || message.content.length <= limit || message.content.includes(OFFLOAD_MARKER)) return message;
    changed = true; return { ...message, content: truncateText(message.content, limit, message.is_error === true) };
  });
  return changed ? result : messages;
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

// 增量计数缓存：记录上次计数时的消息长度和尾部消息引用。
// 由于消息数组只在压缩/截断时整体替换（splice），追加时仅需检查：
// 1. 长度是否增长
// 2. 之前长度位置的消息引用是否匹配（未被替换）
// 满足则只对新增尾部计数，否则全量重数。避免每次创建 [...messages] 浅拷贝。
type UsageCache = {
  length: number;
  system: number;
  conversation: number;
  tool: number;
  tailMessage: ContextMessage | undefined;  // 缓存时 messages[length-1] 的引用
};

export class ContextManager {
  readonly counter: TokenCounter;
  private _usageCache: UsageCache | null = null;
  // provider 服务端真实输入 token 对本地估算的校准系数（滑动平均），仅影响本地预判口径
  private calibrationFactor = 1;
  private calibrated = false;
  // 单条消息 token 缓存：避免同一条消息被重复计数（压缩/截断时清空）
  private _messageTokenCache = new WeakMap<ContextMessage, { conversation: number; category: "system" | "tool" | "other"; categoryTokens: number }>();

  constructor(public messages: ContextMessage[] = [], private readonly _budget: ContextBudget = { maxTokens: 128_000, reservedOutputTokens: 8_192, maxToolResultChars: 8_000 }, counter = new TokenCounter()) { this.counter = counter; }
  append(message: ContextMessage): void { this.messages.push(message); }

  // 通知上下文消息数组被外部修改（如 sanitize、splice 替换等），清空增量缓存
  notifyMutated(): void { this.invalidateCache(); }

  // 暴露预算配置（只读）
  get budget(): Readonly<ContextBudget> { return this._budget; }

  // 统计单条消息的完整对话 token（包含 content、tool_calls、reasoning_content）
  private countMessageTokens(message: ContextMessage): { conversation: number; category: "system" | "tool" | "other"; categoryTokens: number } {
    const cached = this._messageTokenCache.get(message);
    if (cached) return cached;

    let conversation = 0;
    // content 部分（块内用 rawCount，避免每个分块重复叠加 +4 开销）
    if (typeof message.content === "string") {
      conversation += this.counter.rawCount(message.content);
    } else {
      for (const block of message.content) {
        conversation += this.counter.rawCount(String(block.text ?? block.content ?? ""));
      }
    }
    // tool_calls 部分（assistant 消息的工具调用参数）
    if (message.tool_calls) {
      for (const call of message.tool_calls) {
        conversation += this.counter.rawCount(call.name);
        conversation += this.counter.rawCountJson(call.input);
      }
    }
    // reasoning_content 部分
    if (message.reasoning_content) {
      conversation += this.counter.rawCount(message.reasoning_content);
    }
    // 每条消息基础开销：仅在消息级计一次（修复分块 +4 双重累加导致的系统性高估）
    conversation += 4;

    // 分类计数（system/tool 用于单独统计）
    let category: "system" | "tool" | "other" = "other";
    let categoryTokens = 0;
    if (message.role === "system") {
      category = "system";
      categoryTokens = this.counter.countJson(message.content);
    } else if (message.role === "tool") {
      category = "tool";
      categoryTokens = this.counter.countJson(message.content);
    }

    const result = { conversation, category, categoryTokens };
    this._messageTokenCache.set(message, result);
    return result;
  }

  // 清空增量缓存（压缩/截断/整体替换后调用）
  private invalidateCache(): void {
    this._usageCache = null;
    // WeakMap 无需手动清理，消息对象被 GC 时自动清除
  }

  // 分类 token 快照（system/conversation/tool），跨调用增量累积：
  // - 纯追加：仅对新尾部计数并累加，历史上下文不再重复编码
  // - 前缀失配（压缩/截断/回放）：全量重数后重建缓存
  usageSnapshot(): UsageSnapshot {
    const messages = this.messages;
    const len = messages.length;
    const cache = this._usageCache;

    // 快速路径：检查是否纯追加（长度增长且之前位置的消息未变）
    if (cache && len >= cache.length) {
      // 如果长度相同且尾部消息引用相同，直接返回缓存
      if (len === cache.length && messages[len - 1] === cache.tailMessage) {
        return { system: cache.system, conversation: cache.conversation, tool: cache.tool };
      }
      // 验证前缀未变：检查旧长度位置的消息是否仍是旧尾部（说明是追加而非替换）
      if (len > cache.length && messages[cache.length - 1] === cache.tailMessage) {
        let { system, conversation, tool } = cache;
        for (let i = cache.length; i < len; i += 1) {
          const message = messages[i]!;
          const counted = this.countMessageTokens(message);
          conversation += counted.conversation;
          if (counted.category === "system") system += counted.categoryTokens;
          else if (counted.category === "tool") tool += counted.categoryTokens;
        }
        this._usageCache = { length: len, system, conversation, tool, tailMessage: messages[len - 1] };
        return { system, conversation, tool };
      }
    }

    // 慢路径：全量重数
    let system = 0;
    let conversation = 0;
    let tool = 0;
    for (const message of messages) {
      const counted = this.countMessageTokens(message);
      conversation += counted.conversation;
      if (counted.category === "system") system += counted.categoryTokens;
      else if (counted.category === "tool") tool += counted.categoryTokens;
    }
    this._usageCache = { length: len, system, conversation, tool, tailMessage: messages[len - 1] };
    return { system, conversation, tool };
  }

  tokenEstimate(): number { return Math.ceil(this.usageSnapshot().conversation * this.calibrationFactor); }
  // 用服务端返回的真实输入 token 校准本地估算：系数钳制在 [0.5, 2]，滑动平均（0.7 旧 + 0.3 新），首次直接采用
  calibrate(serverInputTokens: number): void {
    if (!(serverInputTokens > 0)) return;
    const local = this.usageSnapshot().conversation;
    if (!(local > 0)) return;
    const ratio = Math.min(2, Math.max(0.5, serverInputTokens / local));
    this.calibrationFactor = this.calibrated ? 0.7 * this.calibrationFactor + 0.3 * ratio : ratio;
    this.calibrated = true;
  }
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
    this.invalidateCache();
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
      // 摘要合法性：不强制关键词格式（模板关键词仅是建议），长度与截断性足够即放行；相等也放行避免边界误杀
      const valid = response.stop_reason !== "max_tokens" && summaryText.length >= 40 && summaryTokens > 0 && summaryTokens <= oldTokens;
      const usage = response.usage?.input_tokens !== undefined || response.usage?.output_tokens !== undefined ? { input_tokens: response.usage?.input_tokens, output_tokens: response.usage?.output_tokens } : undefined;
      if (!valid) return { originalTokens, summaryTokens: originalTokens, removedMessages: 0, summaryText: "", usedModel: false, failed: true, usage };
      const appendedWhileCompacting = this.messages.slice(snapshotLength);
      const replacement = sanitizeContextMessages([...system, ...(fullFallback ? [] : preamble), { role: "user", content: continuationMessage(summaryText) }, { role: "assistant", content: continuationAck() }, ...flat(recentTurns), ...appendedWhileCompacting], this.budget.maxToolResultChars);
      this.messages.splice(0, this.messages.length, ...replacement);
      this.invalidateCache();
      return { originalTokens, summaryTokens: this.tokenEstimate(), removedMessages: old.length, summaryText, usedModel: true, usage };
    } catch { return { originalTokens, summaryTokens: originalTokens, removedMessages: 0, summaryText: "", usedModel: false, failed: true }; }
  }
  async save(filePath: string): Promise<void> { await mkdir(path.dirname(filePath), { recursive: true }); await writeFile(filePath, `${JSON.stringify(this.messages)}\n`, "utf8"); }
  static async load(filePath: string): Promise<ContextManager> { try { return new ContextManager(JSON.parse(await readFile(filePath, "utf8")) as ContextMessage[]); } catch { return new ContextManager(); } }
}
