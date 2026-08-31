import assert from "node:assert/strict";
import test from "node:test";
import fsSync from "node:fs";
import fsPromises from "node:fs/promises";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { SkillLoader } from "../src/skills.js";

// 计数 spy：统计针对 SKILL.md 的全文读取（fsPromises.readFile / fsSync.readFileSync 两条路径都计入）
function instrumentReads(): { calls: string[]; restore: () => void } {
  const calls: string[] = [];
  const promisesTarget = fsPromises as unknown as { readFile: (...args: unknown[]) => Promise<unknown> };
  const syncTarget = fsSync as unknown as { readFileSync: (...args: unknown[]) => unknown };
  const originalReadFile = promisesTarget.readFile; const originalReadFileSync = syncTarget.readFileSync;
  promisesTarget.readFile = (...args: unknown[]) => { calls.push(path.resolve(String(args[0]))); return originalReadFile(...args); };
  syncTarget.readFileSync = (...args: unknown[]) => { calls.push(path.resolve(String(args[0]))); return originalReadFileSync(...args); };
  return { calls, restore: () => { promisesTarget.readFile = originalReadFile; syncTarget.readFileSync = originalReadFileSync; } };
}
const skillReads = (calls: string[]): string[] => calls.filter((file) => file.endsWith("SKILL.md"));

test("SkillLoader.list reads only frontmatter; bodies load on demand and are cached", async () => {
  const projectRoot = await mkdtemp(path.join(os.tmpdir(), "sztu-skill-lazy-project-"));
  const configRoot = await mkdtemp(path.join(os.tmpdir(), "sztu-skill-lazy-config-"));
  const builtinRoot = await mkdtemp(path.join(os.tmpdir(), "sztu-skill-lazy-builtin-"));
  const alphaDir = path.join(projectRoot, ".sztu", "skills", "alpha");
  await mkdir(alphaDir, { recursive: true });
  const body = `Full instructions for alpha.\n${"Detail line. ".repeat(400)}`;
  await writeFile(path.join(alphaDir, "SKILL.md"), `---\nname: alpha\ndescription: Alpha skill\nallowed_tools:\n  - read_file\n---\n${body}\n`, "utf8");
  // 无 frontmatter 的文件必须被跳过且不抛错
  const brokenDir = path.join(projectRoot, ".sztu", "skills", "broken");
  await mkdir(brokenDir, { recursive: true });
  await writeFile(path.join(brokenDir, "SKILL.md"), "no frontmatter here\n", "utf8");
  const loader = new SkillLoader(projectRoot, configRoot, builtinRoot);
  const { calls, restore } = instrumentReads();
  try {
    const skills = await loader.list();
    assert.equal(skillReads(calls).length, 0); // list() 只读 frontmatter，不读任何 SKILL.md 全文
    const alpha = skills.find((item) => item.name === "alpha");
    assert.ok(alpha); // frontmatter 元数据照常可用
    assert.equal(alpha.description, "Alpha skill"); assert.deepEqual(alpha.allowed_tools, ["read_file"]); assert.equal(alpha.scope, "workspace");
    assert.equal(skills.some((item) => item.name === "broken"), false);
    assert.equal(alpha.system_prompt_template, body.trim()); // 首次访问正文才触发一次全文读取
    assert.equal(skillReads(calls).length, 1);
    assert.equal(alpha.system_prompt_template, body.trim()); // 再次访问命中缓存，不再读文件
    const again = await loader.list();
    assert.equal(skillReads(calls).length, 1); // 第二次 list() 依然不读正文
    const cached = again.find((item) => item.name === "alpha"); assert.ok(cached); assert.equal(cached.system_prompt_template, body.trim()); assert.equal(skillReads(calls).length, 1);
    const fetched = await loader.get("alpha"); assert.equal(fetched.system_prompt_template, body.trim()); assert.equal(skillReads(calls).length, 1); // get() 也命中缓存
    loader.invalidateCache(); // 清空缓存后重新读一次
    const refreshed = await loader.get("alpha"); assert.equal(refreshed.system_prompt_template, body.trim()); assert.equal(skillReads(calls).length, 2);
    await assert.rejects(loader.get("missing"), /Unknown or disabled skill/); // 原有错误语义保持
  } finally { restore(); await rm(projectRoot, { recursive: true, force: true }); await rm(configRoot, { recursive: true, force: true }); await rm(builtinRoot, { recursive: true, force: true }); }
});

test("SkillLoader.list keeps full shape and enabled overrides while staying lazy", async () => {
  const projectRoot = await mkdtemp(path.join(os.tmpdir(), "sztu-skill-lazy2-project-"));
  const configRoot = await mkdtemp(path.join(os.tmpdir(), "sztu-skill-lazy2-config-"));
  const builtinRoot = await mkdtemp(path.join(os.tmpdir(), "sztu-skill-lazy2-builtin-"));
  const skillDir = path.join(projectRoot, ".sztu", "skills", "beta");
  await mkdir(skillDir, { recursive: true });
  await writeFile(path.join(skillDir, "SKILL.md"), "---\nname: beta\ndescription: Beta skill\n---\nBeta body.\n", "utf8");
  const loader = new SkillLoader(projectRoot, configRoot, builtinRoot);
  const { calls, restore } = instrumentReads();
  try {
    const skills = await loader.list(); const beta = skills.find((item) => item.name === "beta"); assert.ok(beta);
    // 返回形状与原来一致（调用方依赖这些字段）
    assert.deepEqual(Object.keys(beta!).sort(), ["allow_implicit_invocation", "allowed_tools", "brand_color", "description", "display_name", "enabled", "icon", "id", "name", "path", "plugin", "scope", "short_description", "source", "system_prompt_template"].sort());
    const disabled = await loader.setEnabled("project:beta", false); assert.equal(disabled.enabled, false);
    await assert.rejects(loader.get("beta"), /Unknown or disabled skill/); // 禁用的技能不可 get
    assert.equal(skillReads(calls).length, 0); // setEnabled 路径也不需要读正文
  } finally { restore(); await rm(projectRoot, { recursive: true, force: true }); await rm(configRoot, { recursive: true, force: true }); await rm(builtinRoot, { recursive: true, force: true }); }
});
