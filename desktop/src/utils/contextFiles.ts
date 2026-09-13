import type { ToolCallEntry } from "../components/timeline/types";

const FILE_READ_TOOLS = new Set(["read_file", "read", "parse_document"]);

/** Files whose contents were returned by successful reads in this user turn. */
export function readContextFiles(calls: ToolCallEntry[], workspacePath?: string): string[] {
  const normalize = (path: string) => path.trim().replace(/\\/g, "/").replace(/^(\.\/)+/, "");
  const workspace = workspacePath ? normalize(workspacePath).replace(/\/$/, "") : "";
  const windows = /^[a-z]:\//i.test(workspace) || workspace.startsWith("//");
  const keyOf = (path: string) => windows || /^[a-z]:\//i.test(path) || path.startsWith("//") ? path.toLowerCase() : path;
  const files = new Map<string, string>();
  for (const call of calls) {
    // A path mentioned in a write, search, shell command or Git status is not
    // evidence that the model read that file. Pending/failed reads do not count.
    if (call.status !== "done" || call.error || call.output === undefined || !FILE_READ_TOOLS.has(call.name.toLowerCase())) continue;
    const value = call.params.path ?? call.params.file_path;
    if (typeof value !== "string") continue;
    let path = normalize(value);
    if (!path || path === "." || path.endsWith("/")) continue;
    if (workspace && keyOf(path).startsWith(keyOf(workspace + "/"))) path = path.slice(workspace.length + 1);
    const key = keyOf(path);
    if (!files.has(key)) files.set(key, path);
  }
  return [...files.values()];
}
