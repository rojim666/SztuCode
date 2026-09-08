import { existsSync, type Dirent } from "node:fs";
import { access, readdir, readFile } from "node:fs/promises";
import path from "node:path";

export type DetectionEvidence = { path: string; rule: string; detail?: string; strength: "confirmed" | "supporting" | "weak" };
export type Finding = { name: string; confidence: "confirmed" | "likely"; evidence: DetectionEvidence[] };
export type ValidationCategory = "format" | "static_check" | "unit_test" | "integration_test" | "build";
export type ValidationCommand = { category: ValidationCategory; command: string; working_directory: string; reason: string; evidence: DetectionEvidence[]; recommendation_only: true };
export type ProjectComponent = { path: string; languages: Finding[]; frameworks: Finding[]; package_managers: Finding[]; build_tools: Finding[]; evidence: DetectionEvidence[]; validation_plan: ValidationCommand[] };
export type ProjectProfile = { root_path: string; monorepo: boolean; projects: ProjectComponent[]; scan_limited: boolean };

const MANIFESTS = new Set(["package.json", "pyproject.toml", "setup.py", "Cargo.toml", "pom.xml", "build.gradle", "build.gradle.kts", "CMakeLists.txt"]);
const IGNORED_DIRECTORIES = new Set([".git", ".hg", ".svn", ".idea", ".vscode", "node_modules", ".venv", "venv", "dist", "build", "target", "coverage", ".cache", ".pytest_cache", "__pycache__"]);
const MAX_SCAN_DEPTH = 3;
const MAX_SCAN_ENTRIES = 2_000;

const exists = async (file: string) => access(file).then(() => true, () => false);
const portable = (value: string) => value.split(path.sep).join("/") || ".";
const relative = (root: string, file: string) => portable(path.relative(root, file));
const readText = async (file: string) => readFile(file, "utf8").catch(() => "");
const readJson = async (file: string): Promise<Record<string, unknown>> => {
  try { const value = JSON.parse(await readFile(file, "utf8")); return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {}; }
  catch { return {}; }
};

async function discoverComponents(root: string): Promise<{ roots: string[]; scanLimited: boolean }> {
  const roots = new Set<string>(); let entries = 0; let scanLimited = false;
  const visit = async (directory: string, depth: number): Promise<void> => {
    if (entries >= MAX_SCAN_ENTRIES) { scanLimited = true; return; }
    let children: Dirent[];
    try { children = await readdir(directory, { withFileTypes: true }); } catch { return; }
    children.sort((left, right) => left.name.localeCompare(right.name));
    if (children.some((entry) => entry.isFile() && MANIFESTS.has(entry.name))) roots.add(directory);
    for (const entry of children) {
      entries += 1;
      if (entries >= MAX_SCAN_ENTRIES) { scanLimited = true; break; }
      if (depth >= MAX_SCAN_DEPTH || !entry.isDirectory() || IGNORED_DIRECTORIES.has(entry.name) || entry.isSymbolicLink()) continue;
      await visit(path.join(directory, entry.name), depth + 1);
    }
  };
  await visit(root, 0);
  if (roots.size === 0) roots.add(root);
  return { roots: [...roots].sort((left, right) => relative(root, left).localeCompare(relative(root, right))), scanLimited };
}

async function detectComponent(workspaceRoot: string, componentRoot: string): Promise<ProjectComponent> {
  const componentPath = relative(workspaceRoot, componentRoot);
  const languages: Finding[] = []; const frameworks: Finding[] = []; const packageManagers: Finding[] = []; const buildTools: Finding[] = [];
  const evidence: DetectionEvidence[] = []; const validationPlan: ValidationCommand[] = [];
  const findingKeys = new Set<string>(); const evidenceKeys = new Set<string>(); const commandKeys = new Set<string>();
  const evidenceFor = (file: string, rule: string, detail?: string): DetectionEvidence => ({ path: relative(workspaceRoot, file), rule, ...(detail ? { detail } : {}), strength: "confirmed" });
  const addFinding = (target: Finding[], name: string, item: DetectionEvidence, confidence: Finding["confidence"] = "confirmed") => {
    const key = `${name}:${target === languages ? "language" : target === frameworks ? "framework" : target === packageManagers ? "manager" : "build"}`;
    if (!findingKeys.has(key)) { target.push({ name, confidence, evidence: [item] }); findingKeys.add(key); }
    if (!evidenceKeys.has(`${item.path}:${item.rule}`)) { evidence.push(item); evidenceKeys.add(`${item.path}:${item.rule}`); }
  };
  const addValidation = (category: ValidationCategory, command: string, reason: string, item: DetectionEvidence) => {
    const key = `${category}:${command}`; if (commandKeys.has(key)) return; commandKeys.add(key);
    validationPlan.push({ category, command, working_directory: componentPath, reason, evidence: [item], recommendation_only: true });
  };
  const file = (name: string) => path.join(componentRoot, name);

  const packageFile = file("package.json");
  if (await exists(packageFile)) {
    const item = evidenceFor(packageFile, "Node project manifest"); const manifest = await readJson(packageFile);
    const dependencies = { ...asStringRecord(manifest.dependencies), ...asStringRecord(manifest.devDependencies) };
    const scripts = asStringRecord(manifest.scripts);
    addFinding(languages, "Node.js", item);
    const tsconfig = file("tsconfig.json");
    if (dependencies.typescript || await exists(tsconfig)) addFinding(languages, "TypeScript", evidenceFor(await exists(tsconfig) ? tsconfig : packageFile, "TypeScript configuration or dependency"));
    for (const [dependency, name] of [["react", "React"], ["vue", "Vue"], ["next", "Next.js"], ["nuxt", "Nuxt"], ["svelte", "Svelte"], ["@angular/core", "Angular"], ["express", "Express"], ["@nestjs/core", "NestJS"]] as const) if (dependencies[dependency]) addFinding(frameworks, name, evidenceFor(packageFile, `${dependency} dependency`));
    for (const [dependency, name] of [["vite", "Vite"], ["webpack", "Webpack"], ["tsup", "tsup"], ["rollup", "Rollup"]] as const) if (dependencies[dependency]) addFinding(buildTools, name, evidenceFor(packageFile, `${dependency} dependency`));
    const manager = packageManager(manifest, componentRoot); addFinding(packageManagers, manager.name, evidenceFor(manager.file, manager.rule));
    const run = (script: string) => `${manager.command} run ${script}`;
    for (const name of Object.keys(scripts).sort()) {
      if (/^(format|format:check|prettier)$/.test(name)) addValidation("format", run(name), `package.json script ${name}`, item);
      else if (/^(lint|typecheck|check|check:types)$/.test(name)) addValidation("static_check", run(name), `package.json script ${name}`, item);
      else if (/^(test:integration|test:e2e|e2e|integration)$/.test(name)) addValidation("integration_test", run(name), `package.json script ${name}`, item);
      else if (name === "test" || name === "test:unit") addValidation("unit_test", run(name), `package.json script ${name}`, item);
      else if (name === "build") addValidation("build", run(name), "package.json build script", item);
    }
  }

  const pyproject = file("pyproject.toml"); const setupPy = file("setup.py"); const requirements = file("requirements.txt");
  const pythonManifest = await exists(pyproject) ? pyproject : await exists(setupPy) ? setupPy : await exists(requirements) ? requirements : null;
  if (pythonManifest) {
    const text = [await readText(pyproject), await readText(setupPy), await readText(requirements)].join("\n").toLowerCase();
    const item = evidenceFor(pythonManifest, "Python project manifest"); addFinding(languages, "Python", item);
    for (const [token, name] of [["fastapi", "FastAPI"], ["django", "Django"], ["flask", "Flask"]] as const) if (text.includes(token)) addFinding(frameworks, name, evidenceFor(pythonManifest, `${name} dependency`));
    const uv = await exists(file("uv.lock")); const poetry = await exists(file("poetry.lock")); const prefix = uv ? "uv run " : poetry ? "poetry run " : "";
    addFinding(packageManagers, uv ? "uv" : poetry ? "Poetry" : "pip", evidenceFor(uv ? file("uv.lock") : poetry ? file("poetry.lock") : pythonManifest, "Python package manager"));
    if (text.includes("hatchling")) addFinding(buildTools, "Hatchling", evidenceFor(pyproject, "hatchling build backend")); else if (await exists(setupPy) || text.includes("setuptools")) addFinding(buildTools, "Setuptools", item); else addFinding(buildTools, "PyPA", item, "likely");
    if (/ruff/.test(text)) { addValidation("format", `${prefix}ruff format --check .`, "ruff is configured", item); addValidation("static_check", `${prefix}ruff check .`, "ruff is configured", item); }
    if (/mypy/.test(text)) addValidation("static_check", `${prefix}mypy .`, "mypy is configured", item);
    if (/pyright/.test(text)) addValidation("static_check", `${prefix}pyright`, "pyright is configured", item);
    if (/pytest/.test(text) || await exists(file("tests"))) addValidation("unit_test", `${prefix}pytest`, "pytest or tests directory detected", item);
    if (await exists(file("tests/integration"))) addValidation("integration_test", `${prefix}pytest tests/integration`, "integration test directory detected", item);
    if (await exists(pyproject)) addValidation("build", uv ? "uv build" : "python -m build", "Python build manifest detected", item);
  }

  const cargo = file("Cargo.toml");
  if (await exists(cargo)) {
    const item = evidenceFor(cargo, "Cargo manifest"); addFinding(languages, "Rust", item); addFinding(packageManagers, "Cargo", item); addFinding(buildTools, "Cargo", item);
    addValidation("format", "cargo fmt --check", "Cargo project detected", item); addValidation("static_check", "cargo clippy --all-targets --all-features -- -D warnings", "Cargo project detected", item); addValidation("unit_test", "cargo test", "Cargo project detected", item); addValidation("build", "cargo build", "Cargo project detected", item);
  }

  const pom = file("pom.xml"); const gradle = await exists(file("build.gradle.kts")) ? file("build.gradle.kts") : file("build.gradle");
  if (await exists(pom)) {
    const text = (await readText(pom)).toLowerCase(); const item = evidenceFor(pom, "Maven manifest"); addFinding(languages, "Java", item); if (text.includes("spring-boot")) addFinding(frameworks, "Spring Boot", item); addFinding(packageManagers, "Maven", item); addFinding(buildTools, "Maven", item);
    const mvn = await exists(file("mvnw.cmd")) ? "mvnw.cmd" : await exists(file("mvnw")) ? "./mvnw" : "mvn";
    if (text.includes("spotless")) addValidation("format", `${mvn} spotless:check`, "Spotless plugin detected", item); if (text.includes("checkstyle")) addValidation("static_check", `${mvn} checkstyle:check`, "Checkstyle plugin detected", item);
    addValidation("unit_test", `${mvn} test`, "Maven project detected", item); if (text.includes("failsafe")) addValidation("integration_test", `${mvn} verify`, "Maven Failsafe detected", item); addValidation("build", `${mvn} package`, "Maven project detected", item);
  } else if (await exists(gradle)) {
    const text = (await readText(gradle)).toLowerCase(); const item = evidenceFor(gradle, "Gradle manifest"); addFinding(languages, "Java", item); if (text.includes("spring")) addFinding(frameworks, "Spring", item); addFinding(packageManagers, "Gradle", item); addFinding(buildTools, "Gradle", item);
    const gradlew = await exists(file("gradlew.bat")) ? "gradlew.bat" : await exists(file("gradlew")) ? "./gradlew" : "gradle";
    addValidation("unit_test", `${gradlew} test`, "Gradle project detected", item); addValidation("build", `${gradlew} build`, "Gradle project detected", item);
  }

  const cmake = file("CMakeLists.txt");
  if (await exists(cmake)) {
    const text = (await readText(cmake)).toLowerCase(); const item = evidenceFor(cmake, "CMake project manifest");
    if (/\bcxx\b|c\+\+|\.cpp/.test(text)) addFinding(languages, "C++", item); if (/\bc\b/.test(text)) addFinding(languages, "C", item); if (!languages.some((finding) => finding.name === "C" || finding.name === "C++")) addFinding(languages, "C/C++", item, "likely");
    addFinding(buildTools, "CMake", item); addValidation("build", "cmake -S . -B build && cmake --build build", "CMake project detected", item); if (text.includes("enable_testing") || text.includes("ctest")) addValidation("unit_test", "ctest --test-dir build", "CTest configuration detected", item);
  }

  return { path: componentPath, languages, frameworks, package_managers: packageManagers, build_tools: buildTools, evidence, validation_plan: validationPlan };
}

function asStringRecord(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(Object.entries(value).filter((entry): entry is [string, string] => typeof entry[1] === "string"));
}

function packageManager(manifest: Record<string, unknown>, root: string): { name: string; command: string; file: string; rule: string } {
  const declared = typeof manifest.packageManager === "string" ? manifest.packageManager.split("@")[0] : "";
  if (declared === "pnpm" || declared === "yarn" || declared === "npm" || declared === "bun") return { name: declared, command: declared, file: path.join(root, "package.json"), rule: "packageManager declaration" };
  for (const candidate of [{ file: "pnpm-lock.yaml", name: "pnpm" }, { file: "yarn.lock", name: "yarn" }, { file: "bun.lockb", name: "bun" }, { file: "package-lock.json", name: "npm" }]) if (existsSync(path.join(root, candidate.file))) return { name: candidate.name, command: candidate.name, file: path.join(root, candidate.file), rule: "package manager lockfile" };
  return { name: "npm", command: "npm", file: path.join(root, "package.json"), rule: "default Node package manager" };
}

export async function profileProject(root: string): Promise<ProjectProfile> {
  const resolvedRoot = path.resolve(root); const discovered = await discoverComponents(resolvedRoot);
  const projects = await Promise.all(discovered.roots.map((componentRoot) => detectComponent(resolvedRoot, componentRoot)));
  const rootManifest = await readJson(path.join(resolvedRoot, "package.json"));
  const workspaceDeclared = Array.isArray(rootManifest.workspaces) || Boolean(rootManifest.workspaces && typeof rootManifest.workspaces === "object");
  return { root_path: resolvedRoot, monorepo: projects.length > 1 || workspaceDeclared || await exists(path.join(resolvedRoot, "packages")), projects, scan_limited: discovered.scanLimited };
}
