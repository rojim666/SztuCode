import assert from "node:assert/strict";
import test from "node:test";
import { classifyBashPermission } from "../src/bash-permission.js";

const classify = (command: string) => classifyBashPermission({ command });

test("bash permission downgrades only local read-only command chains", () => {
  for (const command of ["ls -la", "cat src/main.ts", "rg needle .", "git status --short", "git diff -- src/main.ts", "rg needle . | head -20", "git status && git diff"]) {
    assert.equal(classify(command), "workspace_write", command);
  }
});

test("bash permission keeps state-changing and ambiguous commands at full access", () => {
  for (const command of ["", "rm file", "npm test", "python script.py", "node script.js", "git clean -fd", "git reset --hard", "git checkout main", "cat file; rm file", "rg needle & rm file", "FOO=bar rg needle"]) {
    assert.equal(classify(command), "danger_full_access", command);
  }
});

test("bash permission rejects path, expansion, substitution, and redirection escapes", () => {
  for (const command of ["cat /etc/passwd", "cat ../../secret", "cat src/../../secret", "ls ~/private", "cat C:\\secrets.txt", "cat \\\\server\\share", "git --git-dir=/outside status", "cat $HOME/secret", "cat ${HOME}/secret", "type %USERPROFILE%\\secret", "Get-Content $env:USERPROFILE", "echo $(cat secret)", "echo `cat secret`", "cat file > copy", "cat < file", "sudo cat file"]) {
    assert.equal(classify(command), "danger_full_access", command);
  }
});

test("bash permission treats git diff --no-index as full access (arbitrary file read)", () => {
  for (const command of ["git diff --no-index a b", "git diff --binary --no-index a b", "git --no-index diff a b", "git diff --no-index ../outside/secret.txt copy"]) {
    assert.equal(classify(command), "danger_full_access", command);
  }
});
