import assert from "node:assert/strict";
import test from "node:test";
import { loadComposerDraft, saveComposerDraft } from "../src/utils/composerDraft";

function memoryStorage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
  };
}

test("composer drafts persist independently for each project", () => {
  const storage = memoryStorage();
  saveComposerDraft("project-a", "npm test", storage);
  saveComposerDraft("project-b", "git status", storage);

  assert.equal(loadComposerDraft("project-a", storage), "npm test");
  assert.equal(loadComposerDraft("project-b", storage), "git status");
});

test("clearing a composer draft removes the cached command", () => {
  const storage = memoryStorage();
  saveComposerDraft("project-a", "npm run build", storage);
  saveComposerDraft("project-a", "", storage);

  assert.equal(loadComposerDraft("project-a", storage), "");
});
