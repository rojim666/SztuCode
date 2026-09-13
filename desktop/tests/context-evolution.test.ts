import assert from "node:assert/strict";
import test from "node:test";
import { contextLines, contextSource, diffContext, previousContextIndex } from "../src/utils/contextEvolution";
import type { ContextInjectionEntry } from "../src/components/timeline/types";

test("ordered diff detects reordering and preserves duplicate line counts", () => {
  const result = diffContext("a\nb\na", "a\na\nb");
  assert.equal(result.added, 1);
  assert.equal(result.removed, 1);
  assert.deepEqual(result.rows.filter(r => r.kind !== "added").map(r => r.text), ["a", "b", "a"]);
  assert.deepEqual(result.rows.filter(r => r.kind !== "removed").map(r => r.text), ["a", "a", "b"]);
});

test("empty snapshots, unchanged snapshots and replacement retain accurate counts", () => {
  assert.deepEqual(diffContext("", "").rows, []);
  assert.equal(diffContext("a\nb", "a\nb").added, 0);
  assert.equal(diffContext("a\nb", "a\nb").removed, 0);
  assert.equal(diffContext("", "a\nb").added, 2);
  assert.equal(diffContext("a\nb", "").removed, 2);
  assert.deepEqual(diffContext("a\nb\nc", "a\nx\nc").rows, [
    { kind: "unchanged", text: "a" }, { kind: "removed", text: "b" },
    { kind: "added", text: "x" }, { kind: "unchanged", text: "c" },
  ]);
});

test("message JSON is readable and malformed JSON remains intact", () => {
  assert.deepEqual(contextLines('assistant: [{"text":"hello"}]'), ["assistant:", "[", "  {", '    "text": "hello"', "  }", "]"]);
  assert.deepEqual(contextLines("[broken\r\ntext"), ["[broken", "text"]);
});

test("large comparisons fall back to explicit replacement without losing counts or content", () => {
  const before = Array.from({ length: 1500 }, (_, i) => "old-" + i);
  const after = Array.from({ length: 1500 }, (_, i) => "new-" + i);
  const result = diffContext(["prefix", ...before, "suffix"].join("\n"), ["prefix", ...after, "suffix"].join("\n"));
  assert.equal(result.coarse, true);
  assert.equal(result.added, 1500);
  assert.equal(result.removed, 1500);
  assert.equal(result.rows.at(-1)?.text, "suffix");
});

test("interventions do not become the baseline for a system snapshot", () => {
  const entries = ["system", "intervention", "system", "compaction"].map((source, index) => ({
    id: String(index), source, label: "", text: "", preview: "", chars: 0,
  })) as ContextInjectionEntry[];
  assert.equal(previousContextIndex(entries, 2), 0);
  assert.equal(previousContextIndex(entries, 3), -1);
  assert.equal(previousContextIndex(entries, -1), -1);
  assert.equal(contextSource("project"), "system");
  assert.equal(contextSource("compaction"), "compaction");
});
