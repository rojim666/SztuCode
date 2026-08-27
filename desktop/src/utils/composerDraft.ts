const DRAFT_PREFIX = "sztu.composerDraft.";
const MAX_DRAFT_LENGTH = 50_000;

type DraftStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

function draftKey(workspaceId: string | null): string {
  return `${DRAFT_PREFIX}${workspaceId ?? "temporary"}`;
}

export function loadComposerDraft(workspaceId: string | null, storage: DraftStorage = localStorage): string {
  try {
    return (storage.getItem(draftKey(workspaceId)) ?? "").slice(0, MAX_DRAFT_LENGTH);
  } catch {
    return "";
  }
}

export function saveComposerDraft(workspaceId: string | null, value: string, storage: DraftStorage = localStorage): void {
  try {
    if (value) storage.setItem(draftKey(workspaceId), value.slice(0, MAX_DRAFT_LENGTH));
    else storage.removeItem(draftKey(workspaceId));
  } catch {
    // localStorage can be unavailable in private or restricted webviews.
  }
}
