export const REASONING_EFFORTS = ["", "low", "medium", "high", "xhigh", "max"] as const;
export type ReasoningEffort = typeof REASONING_EFFORTS[number];

export function validateReasoningEffort(value: unknown): asserts value is ReasoningEffort {
  if (!REASONING_EFFORTS.includes(value as ReasoningEffort)) {
    throw new Error(`reasoning_effort must be one of: ${REASONING_EFFORTS.join(", ")}`);
  }
}

/** Application presets for manual Anthropic thinking, shared by probes and runs. */
export function anthropicReasoningParams(effort: string | undefined, maxTokens: number) {
  validateReasoningEffort(effort ?? "");
  if (!effort) return { max_tokens: maxTokens };
  const budgets: Record<string, number> = { low: 2048, medium: 8192, high: 24576, xhigh: 32768, max: 65536 };
  const budget = budgets[effort];
  return {
    max_tokens: maxTokens <= budget ? budget + 4096 : maxTokens,
    thinking: { type: "enabled", budget_tokens: budget },
  };
}

export function openaiReasoningParams(effort: string | undefined, responses: boolean, model = "") {
  validateReasoningEffort(effort ?? "");
  if (!effort) return {};
  const deepseek = /^deepseek/i.test(model);
  const effective = deepseek && (effort === "medium" || effort === "xhigh") ? "high" : effort;
  return responses ? { reasoning: { effort: effective, ...(!deepseek ? { summary: "auto" } : {}) } } : { reasoning_effort: effective, ...(deepseek ? { thinking: { type: "enabled" } } : {}) };
}
