import assert from "node:assert/strict";
import test from "node:test";
import { createProjectProfileController } from "../src/components/Inspector/project-profile";
import type { ProjectProfile } from "../src/services/sztu-runtime";

function profile(rootPath: string): ProjectProfile {
  return {
    root_path: rootPath,
    monorepo: false,
    projects: [{
      path: ".",
      languages: [{ name: "Python", confidence: "confirmed", evidence: [] }],
      frameworks: [],
      package_managers: [],
      build_tools: [],
      evidence: [],
      validation_plan: [],
    }],
    scan_limited: false,
  };
}

function deferred<T>(): { promise: Promise<T>; resolve(value: T): void } {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((nextResolve) => { resolve = nextResolve; });
  return { promise, resolve };
}

test("loads a workspace profile on first selection", async () => {
  const calls: Array<{ workspaceId: string; refresh: boolean }> = [];
  const controller = createProjectProfileController(async (workspaceId, refresh) => {
    calls.push({ workspaceId, refresh });
    return profile("C:/projects/alpha");
  });

  const loading = controller.setWorkspace("workspace-alpha");
  assert.equal(controller.state.loading, true);
  assert.equal(controller.state.profile, null);
  await loading;

  assert.deepEqual(calls, [{ workspaceId: "workspace-alpha", refresh: false }]);
  assert.equal(controller.state.profile?.root_path, "C:/projects/alpha");
  assert.equal(controller.state.error, null);
});

test("refreshes the current workspace profile with a new result", async () => {
  const results = [profile("C:/projects/alpha"), profile("C:/projects/alpha-updated")];
  const calls: Array<{ workspaceId: string; refresh: boolean }> = [];
  const controller = createProjectProfileController(async (workspaceId, refresh) => {
    calls.push({ workspaceId, refresh });
    return results.shift()!;
  });

  await controller.setWorkspace("workspace-alpha");
  await controller.refresh();

  assert.deepEqual(calls, [
    { workspaceId: "workspace-alpha", refresh: false },
    { workspaceId: "workspace-alpha", refresh: true },
  ]);
  assert.equal(controller.state.profile?.root_path, "C:/projects/alpha-updated");
});

test("keeps the previous profile when an explicit refresh fails", async () => {
  const previous = profile("C:/projects/alpha");
  let request = 0;
  const controller = createProjectProfileController(async () => {
    request += 1;
    if (request === 1) return previous;
    throw new Error("profile service unavailable");
  });

  await controller.setWorkspace("workspace-alpha");
  await controller.refresh();

  assert.equal(controller.state.profile, previous);
  assert.equal(controller.state.loading, false);
  assert.equal(controller.state.error, "profile service unavailable");
});

test("ignores stale responses after switching workspaces", async () => {
  const first = deferred<ProjectProfile>();
  const second = deferred<ProjectProfile>();
  const controller = createProjectProfileController((workspaceId) => workspaceId === "workspace-alpha" ? first.promise : second.promise);

  const alpha = controller.setWorkspace("workspace-alpha");
  const beta = controller.setWorkspace("workspace-beta");
  second.resolve(profile("C:/projects/beta"));
  await beta;
  first.resolve(profile("C:/projects/alpha"));
  await alpha;

  assert.equal(controller.state.workspaceId, "workspace-beta");
  assert.equal(controller.state.profile?.root_path, "C:/projects/beta");
  assert.equal(controller.state.error, null);
});
