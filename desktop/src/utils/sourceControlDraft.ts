type DraftStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

const DRAFT_PREFIX = "sztu.gitCommitDraft.";
const MAX_DRAFT_LENGTH = 10_000;

function draftKey(workspaceId: string): string {
  return `${DRAFT_PREFIX}${encodeURIComponent(workspaceId)}`;
}

export function loadCommitDraft(workspaceId: string, storage: DraftStorage = localStorage): string {
  if (!workspaceId) return "";
  try {
    return (storage.getItem(draftKey(workspaceId)) ?? "").slice(0, MAX_DRAFT_LENGTH);
  } catch {
    return "";
  }
}

export function saveCommitDraft(
  workspaceId: string,
  message: string,
  storage: DraftStorage = localStorage,
): void {
  if (!workspaceId) return;
  try {
    if (message) storage.setItem(draftKey(workspaceId), message.slice(0, MAX_DRAFT_LENGTH));
    else storage.removeItem(draftKey(workspaceId));
  } catch {
    // Draft persistence is best-effort and must never block Git operations.
  }
}
