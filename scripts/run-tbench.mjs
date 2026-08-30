// Terminal-Bench 运行入口：包装 harbor CLI，补齐 Windows/Linux 都可用的
// PYTHONPATH（harbor 是 console script，启动时 cwd 不在 sys.path，自定义
// agent 模块 eval.terminalbench.agent 必须靠 PYTHONPATH 才能被导入）。
//
// 用法：
//   npm run bench:tbench                            # py runtime，全量数据集
//   npm run bench:tbench -- -d harbor/hello-world   # py runtime 冒烟测试
//   npm run bench:tbench:ts -- -d harbor/hello-world # ts runtime 冒烟测试
//   npm run bench:tbench -- -d terminal-bench/terminal-bench -l 10 -m anthropic/claude-sonnet-4-6
//
// --ts 等价于 bench:tbench:ts（选择 SztuCodeTsAgent）。
// 其余透传参数附加到 `harbor run --agent ...` 之后。
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const pyRuntimeDir = path.join(repoRoot, "py-runtime");

const extra = process.argv.slice(2).filter((arg) => arg !== "--ts");
const useTs = process.argv.includes("--ts");
const agentClass = useTs ? "SztuCodeTsAgent" : "SztuCodeAgent";
const AGENT_ARGS = ["--agent", `eval.terminalbench.agent:${agentClass}`];

// ts 模式 setup = host npm build + 容器装 Node + npm install，
// 超过 harbor 默认 360s 的 agent setup 超时，需要显式放宽（用户已传则不覆盖）
const SETUP_TIMEOUT_ARGS = useTs && !extra.includes("--agent-setup-timeout-multiplier")
  ? ["--agent-setup-timeout-multiplier", "5"]
  : [];

const args =
  extra.length > 0
    ? ["run", ...AGENT_ARGS, ...SETUP_TIMEOUT_ARGS, ...extra]
    : ["run", "-d", "terminal-bench/terminal-bench", ...AGENT_ARGS, ...SETUP_TIMEOUT_ARGS];

const child = spawn("harbor", args, {
  cwd: pyRuntimeDir,
  env: { ...process.env, PYTHONPATH: process.env.PYTHONPATH || "." },
  stdio: "inherit",
  shell: true,
});

child.on("error", (err) => {
  console.error(`[bench:tbench] 无法启动 harbor：${err.message}`);
  console.error("请先安装：uv tool install harbor");
  process.exit(1);
});
child.on("exit", (code) => process.exit(code ?? 1));
