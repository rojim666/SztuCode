import assert from "node:assert/strict";
import test from "node:test";
import { loadCommitDraft, saveCommitDraft } from "../src/utils/sourceControlDraft";

function memoryStorage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
  };
}

test("commit drafts persist independently for each workspace", () => {
  const storage = memoryStorage();
  saveCommitDraft("workspace-a", "feat: keep draft", storage);
  saveCommitDraft("workspace-b", "fix: another project", storage);

  assert.equal(loadCommitDraft("workspace-a", storage), "feat: keep draft");
  assert.equal(loadCommitDraft("workspace-b", storage), "fix: another project");
});

test("clearing a commit message removes its saved draft", () => {
  const storage = memoryStorage();
  saveCommitDraft("workspace-a", "temporary message", storage);
  saveCommitDraft("workspace-a", "", storage);

  assert.equal(loadCommitDraft("workspace-a", storage), "");
});
