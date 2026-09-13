import assert from "node:assert/strict";
import test from "node:test";
import type { ToolCallEntry } from "../src/components/timeline/types";
import { readContextFiles } from "../src/utils/contextFiles";

function call(name: string, path: string, patch: Partial<ToolCallEntry> = {}): ToolCallEntry {
  return { id: path, name, params: { path }, status: "done", output: "contents", ...patch };
}

test("context files include successful reads, excluding changes, searches and pending or failed reads", () => {
  const calls = [
    call("read_file", "src/read.ts"),
    call("write_file", "src/changed.ts"),
    call("edit_file", "src/edited.ts"),
    call("list_dir", "src"),
    call("glob_search", "src/found.ts"),
    call("grep_search", "src/match.ts"),
    call("bash", "src/shell.ts", { output: " M src/unstaged.ts\n?? src/untracked.ts" }),
    call("read_file", "pending.ts", { status: "running" }),
    call("read_file", "denied.ts", { status: "awaiting_permission" }),
    call("read_file", "failed.ts", { status: "failed" }),
    call("read_file", "error.ts", { error: "File not found" }),
    call("read_file", "unfinished-history.ts", { output: undefined }),
    call("read_file", "empty.txt", { output: "" }),
    call("parse_document", "report.pdf"),
  ];
  assert.deepEqual(readContextFiles(calls), ["src/read.ts", "empty.txt", "report.pdf"]);
});

test("read aliases and Windows paths deduplicate within the workspace", () => {
  assert.deepEqual(readContextFiles([
    call("Read", "", { params: { file_path: "F:\\Repo\\src\\App.vue" } }),
    call("read_file", "./src/App.vue"),
    call("read", "src/app.vue"),
    call("read_file", "F:/Repo-other/external.txt"),
  ], "F:/Repo"), ["src/App.vue", "F:/Repo-other/external.txt"]);
});

test("POSIX paths preserve case and invalid paths do not create file entries", () => {
  assert.deepEqual(readContextFiles([
    call("read_file", "src/A.ts"), call("read_file", "src/a.ts"),
    call("read_file", " "), call("read_file", "."), call("read_file", "src/"),
  ], "/repo"), ["src/A.ts", "src/a.ts"]);
});

test("new turns and session switches start with their own reads; tool completion updates the list", () => {
  const previousTurn = [call("read_file", "previous.ts")];
  const currentTurn = [call("read_file", "current.ts", { status: "running" })];
  assert.deepEqual(readContextFiles(previousTurn), ["previous.ts"]);
  assert.deepEqual(readContextFiles(currentTurn), []);
  currentTurn[0].status = "done";
  assert.deepEqual(readContextFiles(currentTurn), ["current.ts"]);
  assert.deepEqual(readContextFiles([]), []);
  assert.deepEqual(readContextFiles(previousTurn), ["previous.ts"]);
});
