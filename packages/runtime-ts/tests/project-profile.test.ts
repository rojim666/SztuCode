import test from "node:test";
import assert from "node:assert/strict";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { profileProject, type ProjectComponent, type ValidationCategory } from "../src/project-profile.js";

const names = (items: Array<{ name: string }>) => new Set(items.map((item) => item.name));
const commands = (project: ProjectComponent, category: ValidationCategory) => project.validation_plan.filter((item) => item.category === category).map((item) => item.command);

test("project profile scans a mixed monorepo and creates advisory validation plans", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-profile-"));
  try {
    await mkdir(path.join(root, "apps", "web"), { recursive: true });
    await mkdir(path.join(root, "services", "api", "tests", "integration"), { recursive: true });
    await writeFile(path.join(root, "package.json"), JSON.stringify({ workspaces: ["apps/*", "services/*"] }), "utf8");
    await writeFile(path.join(root, "apps", "web", "package.json"), JSON.stringify({
      packageManager: "pnpm@9.0.0",
      scripts: { format: "prettier --check .", lint: "eslint .", test: "vitest run", "test:e2e": "playwright test", build: "vite build" },
      dependencies: { react: "^19.0.0" }, devDependencies: { typescript: "^5.6.0", vite: "^6.0.0" },
    }), "utf8");
    await writeFile(path.join(root, "apps", "web", "tsconfig.json"), "{}", "utf8");
    await writeFile(path.join(root, "services", "api", "pyproject.toml"), "[project]\ndependencies=['fastapi','pytest','ruff','mypy']\n[build-system]\nbuild-backend='hatchling.build'\n", "utf8");
    await writeFile(path.join(root, "services", "api", "uv.lock"), "version = 1\n", "utf8");

    const profile = await profileProject(root);
    const web = profile.projects.find((project) => project.path === "apps/web");
    const api = profile.projects.find((project) => project.path === "services/api");
    assert.equal(profile.monorepo, true); assert.ok(web); assert.ok(api);
    assert.deepEqual(names(web.languages), new Set(["Node.js", "TypeScript"])); assert.ok(names(web.frameworks).has("React")); assert.ok(names(web.build_tools).has("Vite"));
    assert.deepEqual(commands(web, "static_check"), ["pnpm run lint"]); assert.deepEqual(commands(web, "integration_test"), ["pnpm run test:e2e"]); assert.deepEqual(commands(web, "build"), ["pnpm run build"]);
    assert.ok(names(api.languages).has("Python")); assert.ok(names(api.frameworks).has("FastAPI")); assert.ok(names(api.package_managers).has("uv")); assert.ok(names(api.build_tools).has("Hatchling"));
    assert.ok(commands(api, "static_check").includes("uv run ruff check .")); assert.ok(commands(api, "unit_test").includes("uv run pytest")); assert.ok(commands(api, "integration_test").includes("uv run pytest tests/integration")); assert.ok(api.validation_plan.every((item) => item.recommendation_only));
  } finally { await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});

test("project profile detects Rust, Maven and CMake validation capabilities", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-profile-languages-"));
  try {
    await mkdir(path.join(root, "rust"), { recursive: true }); await writeFile(path.join(root, "rust", "Cargo.toml"), "[package]\nname='core'\n", "utf8");
    await mkdir(path.join(root, "java"), { recursive: true }); await writeFile(path.join(root, "java", "pom.xml"), "<project><artifactId>spring-boot-starter-web</artifactId><plugin>spotless</plugin><plugin>checkstyle</plugin><plugin>failsafe</plugin></project>", "utf8");
    await mkdir(path.join(root, "native"), { recursive: true }); await writeFile(path.join(root, "native", "CMakeLists.txt"), "project(native LANGUAGES C CXX)\nenable_testing()\n", "utf8");
    const profile = await profileProject(root); const rust = profile.projects.find((project) => project.path === "rust")!; const java = profile.projects.find((project) => project.path === "java")!; const native = profile.projects.find((project) => project.path === "native")!;
    assert.ok(names(rust.languages).has("Rust")); assert.ok(commands(rust, "static_check").some((command) => command.startsWith("cargo clippy")));
    assert.ok(names(java.frameworks).has("Spring Boot")); assert.ok(commands(java, "integration_test").includes("mvn verify")); assert.ok(commands(java, "format").includes("mvn spotless:check"));
    assert.ok(names(native.languages).has("C")); assert.ok(names(native.languages).has("C++")); assert.ok(commands(native, "unit_test").includes("ctest --test-dir build"));
  } finally { await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});

test("project profile tolerates an unreadable or malformed package manifest", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "sztu-profile-malformed-"));
  try {
    await writeFile(path.join(root, "package.json"), "{not-json", "utf8");
    const profile = await profileProject(root);
    assert.equal(profile.projects.length, 1); assert.ok(names(profile.projects[0].languages).has("Node.js")); assert.ok(names(profile.projects[0].package_managers).has("npm"));
  } finally { await rm(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 20 }); }
});
