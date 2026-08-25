import test from "node:test";
import assert from "node:assert/strict";
import { buildSessionTree, projectModelContext, resolveBranch, type SessionHeader } from "../src/index.js";

const header = (id = "s1"): SessionHeader => ({ type: "session", version: 1, id, parentSessionId: null, createdAt: "2025-01-01T00:00:00.000Z", updatedAt: "2025-01-01T00:00:00.000Z" });
const message = (id: string, parentId: string | null, sequence: number, text: string) => ({ type: "message" as const, id, parentId, sequence, timestamp: "2025-01-01T00:00:00.000Z", message: { role: "user" as const, content: text } });

test("projects a branch and builds a session tree", () => {
  const entries = [message("a", null, 1, "one"), message("b", "a", 2, "two"), message("c", "a", 3, "other")];
  assert.deepEqual(resolveBranch(entries, "b").map((entry) => entry.id), ["a", "b"]);
  assert.equal(buildSessionTree(entries)[0]!.children.length, 2);
  assert.deepEqual(projectModelContext({ header: header(), entries, leafId: "b" }).map((item) => item.content), ["one", "two"]);
});

test("compaction replaces the projected prefix", () => {
  const entries = [message("a", null, 1, "old"), { type: "compaction" as const, id: "c", parentId: "a", sequence: 2, timestamp: "2025-01-01T00:00:00.000Z", summary: "Goal and next steps", retainedMessages: [{ role: "assistant" as const, content: "recent" }] }];
  const projected = projectModelContext({ header: header(), entries, leafId: "c" });
  assert.match(String(projected[0]!.content), /Goal and next steps/); assert.equal(projected[1]!.content, "recent");
});
