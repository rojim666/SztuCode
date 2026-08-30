# Terminal-Bench 评测指南

[返回文档中心](../README.md)

Terminal-Bench 是评测终端 Agent 能力的公开基准。SztuCode 通过官方 harness
[Harbor](https://github.com/harbor-framework/harbor) 的自定义 agent 机制接入，任务在
Docker 容器内执行，由独立 verifier 判分。

## 架构

```text
host (npm run bench:tbench[:ts])
└── harbor run --agent eval.terminalbench.agent:SztuCode[|Ts]Agent
    └── SztuCodeAgent            py-runtime/eval/terminalbench/agent.py
        ├── setup: 打包 runtime 上传容器 → 安装工具链 → 建依赖环境
        └── run:   上传任务指令 → 容器内执行 runner → 回收结果 JSON
            └── runner             eval/terminalbench/{runner.py | runner.mjs}
                ├── 容器内拉起 SztuCode daemon（JSON-RPC over TCP）
                ├── permission auto + event.subscribe + session.create(one_shot)
                ├── session.send_message(任务指令) → 等待 run.finished
                └── 汇总 token 用量与状态 → 写结果 JSON → agent 填充 AgentContext
```

daemon 必须运行在任务容器里：bash 工具在 daemon 所在环境 spawn shell，只有这样
agent 的文件修改和命令执行才会落在任务环境中被 verifier 检查。

## 两个 runtime

py（默认）与 ts（`SztuCodeTsAgent`）走同一套 JSON-RPC 协议与结果 schema，差异只在
容器内部署方式：

| | py (`bench:tbench`) | ts (`bench:tbench:ts`) |
| --- | --- | --- |
| 部署内容 | py-runtime 源码 | host 上 `npm run build` 后的 packages dist + prompts/agents 资源 |
| 工具链 | uv（容器内安装） | Node ≥ 18 + npm（容器内安装，多数镜像自带） |
| 依赖安装 | `uv sync --no-dev` | `npm install --omit=dev`（外部依赖仅 js-tiktoken） |
| daemon | `.venv/bin/python -m sztu_code.core` | `node packages/runtime-ts/dist/main.js` |
| runner | `runner.py`（走 py venv） | `runner.mjs`（零依赖 Node 脚本） |
| 第三方端点配置 | 容器内 `llm.toml`（SZTU_CONFIG） | `OPENAI_BASE_URL`/`OPENAI_API_KEY` 环境变量 |

ts 模式 host 端首次 setup 会执行完整 TS 构建（多 trial 共享一次，进程内 memo）。
容器内 Node.js 缺失时，agent 在 host 上下载官方二进制 tarball（v22.14.0，自带 npm，
缓存于系统临时目录）后上传进容器解压，不依赖容器内 apt/curl。
ts 的 setup 含 host 构建 + 容器安装两段，超过 Harbor 默认 360s，npm script 已自动
附加 `--agent-setup-timeout-multiplier 5`（放宽到 1800s）。

## 环境准备

- Docker Desktop（Linux 容器模式）已启动；
- Harbor CLI：`uv tool install harbor`；
- 模型 API key（见下节）。

Python 端无需额外安装：agent 每次运行会把 `py-runtime` 源码打包进容器并在容器内
用 uv 同步依赖（首次约 2 分钟，之后命中容器层缓存更快）。TS runtime 同理由
agent 自动构建部署。

## 快速开始

冒烟测试（1 个任务，验证部署链路）：

```bash
npm run bench:tbench -- -d harbor/hello-world        # py runtime
npm run bench:tbench:ts -- -d harbor/hello-world     # ts runtime
```

跑 Terminal-Bench 4.0 全量数据集（66 个任务，成本见下节）：

```bash
npm run bench:tbench
```

小样本（推荐先跑 10 个任务控制成本）：

```bash
npm run bench:tbench -- -d terminal-bench/terminal-bench -l 10 -m anthropic/claude-sonnet-4-6
```

透传参数等价于 `harbor run --agent eval.terminalbench.agent:SztuCodeAgent <参数>`，
所有 [harbor run flags](https://harborframework.com/docs/cli/run/) 均可用，例如
`-i`/`-x` 按任务名筛选、`--n-tasks` 限制数量、`--multiprocess` 并行。

等价的原始命令（理解 `scripts/run-tbench.mjs` 在做什么时参考）：

```bash
cd py-runtime
PYTHONPATH=. harbor run -d terminal-bench/terminal-bench \
    --agent eval.terminalbench.agent:SztuCodeAgent \
    -m anthropic/claude-sonnet-4-6
```

`PYTHONPATH=.` 不可省略：harbor 是 console script，启动时 cwd 不在 `sys.path`，
自定义 agent 模块 `eval.terminalbench.agent` 靠它才能被导入。npm script 已自动设置。

## 模型配置

三种方式，按优先级：

| 方式 | 用法 | 说明 |
| --- | --- | --- |
| 官方 provider | `-m anthropic/<model>` + `ANTHROPIC_API_KEY` | 透传官方环境变量给容器内 daemon |
| 官方 provider | `-m openai/<model>` + `OPENAI_API_KEY` | 同上 |
| OpenAI 兼容端点 | `SZTU_TB_BASE_URL` + `SZTU_TB_API_KEY` + `-m <provider>/<model>` | py: 写容器内 `llm.toml`；ts: 注入 `OPENAI_BASE_URL`/`OPENAI_API_KEY`。`<model>` 为端点上的模型名 |

OpenAI 兼容端点示例（GLM）：

```bash
SZTU_TB_BASE_URL=https://open.bigmodel.cn/api/paas/v4 \
SZTU_TB_API_KEY=xxx \
npm run bench:tbench -- -m zhipu/glm-4.6 -l 10        # 换成 bench:tbench:ts 即为 ts runtime
```

密钥不进命令行参数，只通过环境变量传递。

## 对比两个 runtime

跑同一个固定任务子集两次（不同 agent、相同数据集与模型），比较
`py-runtime/jobs/` 两个 job 的 `result.json`：

```bash
npm run bench:tbench -- -d terminal-bench/terminal-bench -l 10 -m <provider>/<model>
npm run bench:tbench:ts -- -d terminal-bench/terminal-bench -l 10 -m <provider>/<model>
```

`-l 10` 固定取前 10 个任务，两个 run 的任务集合一致，verdict / steps /
token 可直接对比。py 与 ts 的 agent name 分别为 `sztu-code` / `sztu-code-ts`，
在 result.json 中可区分。

## 成本控制

Terminal-Bench 4.0 全量 66 个任务，Claude Sonnet 级别模型单任务约 100K–600K
token（多数任务 20+ 步骤、长上下文累积），全量预计 $50–150。预算只有几十刀时：

- 先 `-l 5` 跑 5 个任务校准单任务成本，再决定样本量；
- `-l 10` 固定子集 + 便宜模型（GLM、DeepSeek 等国产模型按官方价格计）是
  几十刀内完成一轮评测的推荐配置；
- 用 `--skip-unlock-solutions` 避免提前解锁答案（默认即锁定）；
- 结果里 `n_input_tokens` 含 cache 命中，跨模型对比时注意各家计费口径。

## 结果

结果写入 `py-runtime/jobs/<时间戳>/`：

```text
jobs/2026-08-30__03-04-41/
├── result.json                 # job 级汇总
└── hello-world__5cPta7q/
    ├── result.json             # trial 详情：agent info、token 用量、verdict
    ├── exception.txt           # 失败时的完整 traceback
    ├── trial.log               # harbor 侧日志
    └── artifacts/              # 同步回 host 的容器产物
```

查看汇总：`cd py-runtime && harbor view jobs`。`result.json` 的
`context.metadata` 包含 `sztu_status`/`sztu_steps`/`sztu_run_id` 等 agent 上报字段，
token 口径与 [评测指南](evaluation.md) 的指标定义一致。

上榜单（可选）：`harbor upload <job 目录>` 把结果上传 Harbor Hub 获得分享链接。

## 评测旁路

容器内 daemon 的 bash 工具默认拦截依赖安装命令（本地会话防浪费），Terminal-Bench
任务本身常要求安装依赖，agent 已自动注入 `SZTU_EVAL_ALLOW_INSTALL=1` 放开此限制，
无需手工配置。

## 故障排查

| 症状 | 原因与处理 |
| --- | --- |
| `Failed to import module 'eval.terminalbench.agent'` | 未设置 `PYTHONPATH`（用 npm script 或参考原始命令） |
| `setup step 'install uv' failed` | 容器无网络或 apt 源不可达，检查 Docker 网络与代理 |
| `setup step 'uv sync' failed` | 依赖源不可达，或 `pyproject.toml` 新增了本地路径引用 |
| `host-side TS runtime build failed`（ts） | host 上手动跑 `npm run build --workspace @sztucode/runtime-ts` 看具体编译错误 |
| `Node.js tarball download ...`（ts） | host 无法访问 nodejs.org，检查本机网络/代理后重跑（下载失败不落缓存） |
| `setup step 'install node' failed`（ts） | 容器内解压失败；镜像自带 node 但版本 < 18 也会触发安装 |
| `Agent setup timed out`（ts） | host 构建或容器安装过慢，调大 `--agent-setup-timeout-multiplier`（script 默认 5） |
| `setup step 'npm install' failed`（ts） | npm registry 不可达，检查 Docker 网络与代理 |
| `ValueError: SztuCode[Ts]Agent 需要模型配置` | 未提供模型/密钥，见模型配置一节 |
| trial 一直 timeout | 任务超时上限由 agent 的 `run_timeout`（默认 6h）控制，可用 `--ak run_timeout=...` 覆盖 |
| daemon 启动失败 | 查看 trial `exception.txt` 与容器内 `/tmp/sztu-daemon.log`（随 artifacts 同步） |

调试单个 trial 时可进容器复现：`docker exec -it <container> bash`，runtime 部署
在 `/opt/sztucode`，指令与结果文件在 `/tmp/sztu-*`。
