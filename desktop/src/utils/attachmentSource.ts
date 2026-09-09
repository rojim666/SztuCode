/** Browser/clipboard files have an in-memory payload, not a filesystem path. */
export function needsAttachmentStaging(file: { source?: "inline" | "disk"; workspaceRoot?: string; workspacePath?: string }, root: string): boolean {
  return file.source !== "inline" && (file.workspaceRoot !== root || !file.workspacePath);
}
