import assert from "node:assert/strict";
import test from "node:test";
import { needsAttachmentStaging } from "../src/utils/attachmentSource.js";

test("pasted screenshots bypass disk staging when a project is selected", () => {
  assert.equal(needsAttachmentStaging({ source: "inline" }, "project"), false);
  assert.equal(needsAttachmentStaging({ source: "inline", workspaceRoot: "old" }, "new"), false);
});

test("disk attachments still stage on first send and after project switches", () => {
  assert.equal(needsAttachmentStaging({}, "project"), true);
  assert.equal(needsAttachmentStaging({ workspaceRoot: "project", workspacePath: ".sztu/attachments/a.png" }, "project"), false);
  assert.equal(needsAttachmentStaging({ workspaceRoot: "old", workspacePath: ".sztu/attachments/a.png" }, "new"), true);
});
