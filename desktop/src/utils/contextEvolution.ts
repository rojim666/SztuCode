import type { ContextInjectionEntry } from "../components/timeline/types";

export type ContextDiffRow = { kind: "added" | "removed" | "unchanged"; text: string };

export function contextSource(value: unknown): ContextInjectionEntry["source"] {
  return value === "compaction" || value === "canvas" || value === "intervention" || value === "steering" ? value : "system";
}

// JSON message arrays otherwise become one enormous changed line per request.
export function contextLines(text: string): string[] {
  if (!text) return [];
  return text.split(/\r?\n/).flatMap((line) => {
    const match = line.match(/^(?:(system|user|assistant|tool):\s*)?([\[{].*)$/);
    if (!match) return [line];
    try {
      const formatted = JSON.stringify(JSON.parse(match[2]), null, 2).split("\n");
      return match[1] ? [match[1] + ":", ...formatted] : formatted;
    } catch { return [line]; }
  });
}

/** Compare like sources: an intervention is not a replacement system prompt. */
export function previousContextIndex(entries: ContextInjectionEntry[], index: number): number {
  for (let i = index - 1; i >= 0; i--) {
    if (entries[i].source === entries[index]?.source) return i;
  }
  return -1;
}

export function diffContext(previous: string, current: string) {
  const before = contextLines(previous), after = contextLines(current);
  const rows: ContextDiffRow[] = [];
  const push = (kind: ContextDiffRow["kind"], text: string) => rows.push({ kind, text });
  let start = 0;
  while (start < before.length && start < after.length && before[start] === after[start]) {
    push("unchanged", before[start++]);
  }
  let oldEnd = before.length, newEnd = after.length;
  while (oldEnd > start && newEnd > start && before[oldEnd - 1] === after[newEnd - 1]) { oldEnd--; newEnd--; }
  const n = oldEnd - start, m = newEnd - start;
  // Bound CPU and memory; large unrelated middles are replaced as a block.
  const coarse = n * m > 1_000_000;
  if (coarse) {
    for (let i = start; i < oldEnd; i++) push("removed", before[i]);
    for (let j = start; j < newEnd; j++) push("added", after[j]);
  } else {
    const width = m + 1;
    const lcs = new Uint32Array((n + 1) * width);
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) {
      lcs[i * width + j] = before[start + i] === after[start + j]
        ? lcs[(i + 1) * width + j + 1] + 1
        : Math.max(lcs[(i + 1) * width + j], lcs[i * width + j + 1]);
    }
    let i = 0, j = 0;
    while (i < n || j < m) {
      if (i < n && j < m && before[start + i] === after[start + j]) {
        push("unchanged", before[start + i]); i++; j++;
      } else if (i < n && (j === m || lcs[(i + 1) * width + j] >= lcs[i * width + j + 1])) {
        push("removed", before[start + i++]);
      } else { push("added", after[start + j++]); }
    }
  }
  for (let i = oldEnd; i < before.length; i++) push("unchanged", before[i]);
  return { rows, coarse, added: rows.filter(r => r.kind === "added").length, removed: rows.filter(r => r.kind === "removed").length };
}
