"""
SztuCode 的 Harbor agent：把 SztuCode 接入 Harbor / Terminal-Bench。

架构说明:
    SztuCode daemon 的 bash 工具在 daemon 进程所在环境内 spawn shell，
    没有 remote terminal 接口。因此 daemon 必须运行在 Harbor 的任务容器里，
    agent 的文件编辑/命令执行才会落在任务环境中。

    本类是 Harbor external agent（运行在 host 的 harbor 进程内），职责:
      setup(): 打包运行时 → environment.upload_file 传入容器 → 解包 →
               安装工具链 → 建立依赖环境
      run():   上传任务指令文件 → 容器内 exec runner（runner 拉起 daemon 并
               走 JSON-RPC 完成任务） → 下载结果 JSON → 填充 AgentContext

    两个 runtime（协议兼容，结果 JSON schema 一致）:
      - py（默认）: 打包 py-runtime 源码，容器内 uv sync 建离线 venv，
        daemon = .venv/bin/python -m sztu_code.core，runner = runner.py
      - ts: host 上先 npm build，打包 packages/* 的 dist 与运行时资源，
        容器内 npm install，daemon = node packages/runtime-ts/dist/main.js，
        runner = runner.mjs（零依赖 Node 脚本）
        使用 SztuCodeTsAgent 或 --ak runtime=ts 选择。

模型配置（三种方式，按优先级）:
    1. kwargs: base_url + api_key —— OpenAI 兼容第三方端点
       （py: 写容器内 llm.toml，经 SZTU_CONFIG 指定；
        ts: 直接注入 OPENAI_BASE_URL / OPENAI_API_KEY 环境变量）
    2. host 环境变量: SZTU_TB_BASE_URL + SZTU_TB_API_KEY —— 同上，密钥不进命令行
    3. ``-m anthropic/xxx`` 或 ``-m openai/xxx`` —— 直接透传
       ANTHROPIC_API_KEY / OPENAI_API_KEY 给容器内 daemon

用法:
    cd py-runtime
    harbor run -d terminal-bench/terminal-bench@4.0.0 \
        --agent eval.terminalbench.agent:SztuCodeAgent \
        -m anthropic/claude-sonnet-4-6 -n 2

    # TS runtime:
    harbor run ... --agent eval.terminalbench.agent:SztuCodeTsAgent

    # 第三方 OpenAI 兼容模型（如 GLM）:
    SZTU_TB_BASE_URL=https://open.bigmodel.cn/api/paas/v4 \
    SZTU_TB_API_KEY=xxx \
    harbor run ... -m zhipu/glm-4.6
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

# 容器内固定布局
_REMOTE_RUNTIME_DIR = "/opt/sztucode"
_REMOTE_TARBALL = "/tmp/sztu-runtime.tar.gz"
_REMOTE_INSTRUCTION = "/tmp/sztu-instruction.txt"
_REMOTE_RESULT = "/tmp/sztu-result.json"
_REMOTE_LLM_CONFIG = "/opt/sztucode/llm.toml"

# host 端 py-runtime 根目录（eval/terminalbench/agent.py 上两级）
_RUNTIME_ROOT = Path(__file__).resolve().parents[2]
# host 端仓库根目录（py-runtime 的上级，TS runtime 部署用它）
_REPO_ROOT = _RUNTIME_ROOT.parent

# 打包排除项：虚拟环境/缓存/评测产物
_TAR_EXCLUDES = {".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
_TAR_EXCLUDED_DIRS = ("eval/reports",)

# TS runtime 需要的 workspace 包（packages/ 下相对名）
_TS_PACKAGES = (
    "ai",
    "agent-core",
    "protocol",
    "session",
    "session-fs",
    "server",
    "telemetry",
    "runtime-ts",
)
# runtime-ts 运行时从 dist 上级目录读取的非编译资源
_TS_RUNTIME_RESOURCES = ("prompts", "agents")

# setup 期间各阶段超时（秒）：解包 / 工具链安装 / 依赖同步
_SETUP_EXTRACT_TIMEOUT = 120
_SETUP_UV_TIMEOUT = 300
_SETUP_SYNC_TIMEOUT = 900
_SETUP_NODE_TIMEOUT = 600
_SETUP_NPM_TIMEOUT = 900
# host 端 TS runtime 构建（tsc 全链路）
_TS_BUILD_TIMEOUT = 1800
# run() 单次 exec 的超时上限，需覆盖 runner 的 --timeout 加上 daemon 启停
_RUN_EXEC_GRACE = 300

# 进程级 memo：一次 harbor run 多个 trial 共享一次 host 构建
_ts_build_done: dict[str, bool] = {}

# 容器内 Node.js 安装：多数 Terminal-Bench 镜像自带 node，缺失时用官方
# 二进制 tarball（自带 npm）。tarball 在 host 上下载后 upload_file 传入容器，
# 不依赖容器内网络与 curl/wget/xz 等工具（apt 装链路慢且易受镜像源抖动影响）。
_NODE_VERSION = "22.14.0"
_REMOTE_NODE_TARBALL = "/tmp/sztu-node.tar.gz"
_NODE_ARCH_MAP = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}
# 进程级 memo：一次 harbor run 多个 trial 共享同一份 host 下载
_node_tarball_cache: dict[str, Path] = {}


class SztuCodeAgent(BaseAgent):
    """把 SztuCode daemon 部署进任务容器并驱动其完成任务的 Harbor agent"""

    def __init__(
        self,
        *args: Any,
        daemon_port: int = 7457,
        run_timeout: int = 21600,
        max_steps: int | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        runtime: str = "py",
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if runtime not in ("py", "ts"):
            raise ValueError(f"unknown runtime: {runtime!r} (expected 'py' or 'ts')")
        self.daemon_port = daemon_port
        self.run_timeout = run_timeout
        self.max_steps = max_steps
        self.base_url = base_url
        self.api_key = api_key
        self.runtime = runtime

    @staticmethod
    def name() -> str:
        return "sztu-code"

    def version(self) -> str | None:
        return "0.1.0"

    # ──────────────────── setup: 部署运行时 ────────────────────

    async def setup(self, environment: BaseEnvironment) -> None:
        if self.runtime == "ts":
            await self._setup_ts(environment)
        else:
            await self._setup_py(environment)

    async def _setup_py(self, environment: BaseEnvironment) -> None:
        tar_path = self._build_runtime_tar()
        try:
            await environment.upload_file(str(tar_path), _REMOTE_TARBALL)
        finally:
            tar_path.unlink(missing_ok=True)

        # tarball 内的 LICENSE 放到 runtime 上级，满足 hatchling 的
        # license = { file = "../LICENSE" } 相对路径解析。
        # 注意不能用 pathlib：host 是 Windows 时会把 POSIX 路径转成反斜杠。
        runtime_parent = _REMOTE_RUNTIME_DIR.rsplit("/", 1)[0]
        await self._exec_checked(
            environment,
            f"mkdir -p {_REMOTE_RUNTIME_DIR} "
            f"&& tar xzf {_REMOTE_TARBALL} -C {_REMOTE_RUNTIME_DIR} "
            f"&& mv {_REMOTE_RUNTIME_DIR}/LICENSE {runtime_parent}/LICENSE "
            f"&& rm -f {_REMOTE_TARBALL}",
            timeout_sec=_SETUP_EXTRACT_TIMEOUT,
            what="extract runtime",
        )
        await self._exec_checked(
            environment,
            "set -e\n"
            'export PATH="$HOME/.local/bin:$PATH"\n'
            'if command -v uv >/dev/null 2>&1; then echo "uv already installed"; exit 0; fi\n'
            # 最小镜像（ubuntu:24.04 等）无 curl/wget/pip；apt 装一个下载器。
            # 注意 `curl|sh` 在 curl 缺失时仍返回 0（exit code 取 sh），
            # 因此末尾必须显式校验 uv 存在，避免静默失败。
            "command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1 "
            "|| (apt-get update -qq && apt-get install -y -qq curl)\n"
            "curl -LsSf https://astral.sh/uv/install.sh | sh\n"
            'command -v uv >/dev/null 2>&1 || { echo "uv install failed" >&2; exit 1; }',
            timeout_sec=_SETUP_UV_TIMEOUT,
            what="install uv",
        )
        await self._exec_checked(
            environment,
            f'export PATH="$HOME/.local/bin:$PATH"\ncd {_REMOTE_RUNTIME_DIR} && uv sync --no-dev',
            timeout_sec=_SETUP_SYNC_TIMEOUT,
            what="uv sync",
        )
        self.logger.info("[%s] runtime ready at %s", self.name(), _REMOTE_RUNTIME_DIR)

    async def _setup_ts(self, environment: BaseEnvironment) -> None:
        # host 端先构建 dist（一次 harbor run 内 memo，多 trial 共享）
        await self._ensure_ts_build()

        tar_path = self._build_runtime_tar()
        try:
            await environment.upload_file(str(tar_path), _REMOTE_TARBALL)
        finally:
            tar_path.unlink(missing_ok=True)

        await self._exec_checked(
            environment,
            f"mkdir -p {_REMOTE_RUNTIME_DIR} "
            f"&& tar xzf {_REMOTE_TARBALL} -C {_REMOTE_RUNTIME_DIR} "
            f"&& rm -f {_REMOTE_TARBALL}",
            timeout_sec=_SETUP_EXTRACT_TIMEOUT,
            what="extract runtime",
        )
        await self._install_node(environment)
        # workspaces 为裁剪过的包子集，不带根 package-lock（npm 现场解析，
        # 外部依赖只有 js-tiktoken，网络开销可忽略）
        await self._exec_checked(
            environment,
            f"cd {_REMOTE_RUNTIME_DIR} && npm install --omit=dev --no-audit "
            "--no-fund --loglevel=error",
            timeout_sec=_SETUP_NPM_TIMEOUT,
            what="npm install",
        )
        self.logger.info("[%s] ts runtime ready at %s", self.name(), _REMOTE_RUNTIME_DIR)

    async def _install_node(self, environment: BaseEnvironment) -> None:
        """容器内确保 Node.js ≥ 18 + npm 可用，缺失则从 host 上传官方 tarball"""
        check = await environment.exec(
            "node -e \"if (Number(process.versions.node.split('.')[0]) < 18) "
            'process.exit(1)" && npm -v >/dev/null 2>&1 && echo sztu-node-ok',
            timeout_sec=30,
        )
        if "sztu-node-ok" in (check.stdout or ""):
            self.logger.info("[%s] node already available", self.name())
            return

        arch_out = await environment.exec("uname -m", timeout_sec=30)
        machine = (arch_out.stdout or "").strip().splitlines()[-1] if arch_out.stdout else ""
        node_arch = _NODE_ARCH_MAP.get(machine)
        if node_arch is None:
            raise RuntimeError(f"unsupported container arch for Node.js: {machine!r}")

        tar_path = self._fetch_node_tarball(node_arch)
        await environment.upload_file(str(tar_path), _REMOTE_NODE_TARBALL)
        await self._exec_checked(
            environment,
            f"tar -xzf {_REMOTE_NODE_TARBALL} -C /usr/local --strip-components=1"
            f" && rm -f {_REMOTE_NODE_TARBALL}"
            " && node -v && npm -v",
            timeout_sec=_SETUP_NODE_TIMEOUT,
            what="install node",
        )

    def _fetch_node_tarball(self, node_arch: str) -> Path:
        """host 端下载 Node.js 官方 tarball（缓存于系统临时目录，跨 trial 复用）"""
        cached = _node_tarball_cache.get(node_arch)
        if cached and cached.is_file():
            return cached
        url = (
            f"https://nodejs.org/dist/v{_NODE_VERSION}/"
            f"node-v{_NODE_VERSION}-linux-{node_arch}.tar.gz"
        )
        dest = Path(tempfile.gettempdir()) / (
            f"sztu-node-v{_NODE_VERSION}-linux-{node_arch}.tar.gz"
        )
        if not dest.is_file():
            self.logger.info(
                "[%s] downloading Node.js v%s (%s) on host...",
                self.name(),
                _NODE_VERSION,
                node_arch,
            )
            try:
                with urllib.request.urlopen(url, timeout=180) as resp, open(dest, "wb") as fh:
                    expected = int(resp.headers.get("Content-Length", 0) or 0)
                    shutil.copyfileobj(resp, fh, length=1024 * 1024)
            except BaseException:
                dest.unlink(missing_ok=True)
                raise
            actual = dest.stat().st_size if dest.exists() else 0
            if expected and actual != expected:
                dest.unlink(missing_ok=True)
                raise RuntimeError(
                    f"Node.js tarball download incomplete: {dest.name} ({actual}/{expected} bytes)"
                )
        _node_tarball_cache[node_arch] = dest
        return dest

    async def _ensure_ts_build(self) -> None:
        """host 端构建 TS runtime（runtime-ts build 会连带构建其依赖包）"""
        if _ts_build_done.get("ok"):
            return
        self.logger.info("[%s] building TS runtime on host...", self.name())
        # Windows 下 npm 是 npm.cmd，create_subprocess_exec 无法直接执行，
        # 统一走 shell（命令为固定字符串，无注入面）
        proc = await asyncio.create_subprocess_shell(  # noqa: S602
            "npm run build --workspace @sztucode/runtime-ts",
            cwd=str(_REPO_ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_TS_BUILD_TIMEOUT)
        except TimeoutError:
            proc.kill()
            raise RuntimeError("host-side TS runtime build timed out") from None
        if proc.returncode != 0:
            tail = (stdout or b"")[-4000:].decode("utf-8", "replace")
            raise RuntimeError(
                f"host-side TS runtime build failed (exit {proc.returncode}):\n{tail}"
            )
        _ts_build_done["ok"] = True
        self.logger.info("[%s] TS runtime built", self.name())

    # ──────────────────── run: 执行任务 ────────────────────

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        # 容器默认工作目录作为 agent workspace（Terminal-Bench 惯例为 $HOME）
        pwd = await environment.exec("pwd", timeout_sec=30)
        workspace = (pwd.stdout or "/root").strip().splitlines()[-1]

        await self._upload_text(environment, instruction, _REMOTE_INSTRUCTION)

        exec_env, config_files = self._build_model_config()
        for remote_path, content in config_files:
            await self._upload_text(environment, content, remote_path)

        if self.runtime == "ts":
            runner_cmd = (
                f"cd {_REMOTE_RUNTIME_DIR} && node eval/terminalbench/runner.mjs "
                f"--instruction-file {_REMOTE_INSTRUCTION} "
                f"--workspace {workspace} "
                f"--port {self.daemon_port} "
                f"--result-file {_REMOTE_RESULT} "
                f"--timeout {self.run_timeout}"
            )
        else:
            runner_cmd = (
                f"cd {_REMOTE_RUNTIME_DIR} && .venv/bin/python -m eval.terminalbench.runner "
                f"--instruction-file {_REMOTE_INSTRUCTION} "
                f"--workspace {workspace} "
                f"--port {self.daemon_port} "
                f"--result-file {_REMOTE_RESULT} "
                f"--timeout {self.run_timeout}"
            )
        result = await environment.exec(
            runner_cmd,
            env=exec_env,
            timeout_sec=self.run_timeout + _RUN_EXEC_GRACE,
        )
        if result.stdout:
            self.logger.info("[%s] runner stdout:\n%s", self.name(), result.stdout)
        if result.return_code not in (0, 1):
            # runner 自身约定 0=success / 1=任务失败，其他为部署/协议错误
            self.logger.error(
                "[%s] runner exited with %d: %s",
                self.name(),
                result.return_code,
                result.stderr,
            )

        payload = await self._download_result(environment)
        self._populate_context(context, payload)

    # ──────────────────── 内部工具 ────────────────────

    async def _exec_checked(
        self,
        environment: BaseEnvironment,
        command: str,
        timeout_sec: int,
        what: str,
    ) -> None:
        result = await environment.exec(command, timeout_sec=timeout_sec)
        if result.return_code != 0:
            raise RuntimeError(
                f"setup step '{what}' failed with exit code {result.return_code}: "
                f"{result.stderr or result.stdout}"
            )
        self.logger.debug("[%s] %s ok", self.name(), what)

    def _build_runtime_tar(self) -> Path:
        """打包运行时源码为 tar.gz（按 runtime 分支）"""
        if self.runtime == "ts":
            return self._build_runtime_tar_ts()
        return self._build_runtime_tar_py()

    def _build_runtime_tar_py(self) -> Path:
        """把 py-runtime 源码打包为 tar.gz（排除 venv/缓存/评测产物）"""
        fd, name = tempfile.mkstemp(prefix="sztu-runtime-", suffix=".tar.gz")
        os.close(fd)
        with tarfile.open(name, "w:gz") as tar:
            for path in (_RUNTIME_ROOT / "src", _RUNTIME_ROOT / "eval"):
                tar.add(str(path), arcname=path.name, filter=self._tar_filter)
            # hatchling 校验 pyproject.toml 声明的 readme/license 文件必须存在
            for filename in ("pyproject.toml", "uv.lock", ".python-version", "README.md"):
                file_path = _RUNTIME_ROOT / filename
                if file_path.is_file():
                    tar.add(str(file_path), arcname=filename)
            # license = { file = "../LICENSE" } → 解压后放到 runtime 上级目录
            license_path = _RUNTIME_ROOT / ".." / "LICENSE"
            if license_path.is_file():
                tar.add(str(license_path), arcname="LICENSE")
        return Path(name)

    def _build_runtime_tar_ts(self) -> Path:
        """
        把 TS runtime 打包为 tar.gz。

        内容:
          - 生成的精简根 package.json（workspaces 只保留 runtime-ts 依赖链，
            排除 cli/client/evaluation 等无关包，避免容器内安装无关依赖）
          - 各包的 package.json + dist/（host 上 _ensure_ts_build 的产物）
          - runtime-ts 的 prompts/ 与 agents/（运行时从 dist 上级目录读取）
          - eval/terminalbench/runner.mjs（容器内零依赖 runner）
        """
        missing = [
            pkg
            for pkg in _TS_PACKAGES
            if not (_REPO_ROOT / "packages" / pkg / "package.json").is_file()
        ]
        if missing:
            raise FileNotFoundError(
                f"TS packages missing under {_REPO_ROOT / 'packages'}: {missing} — "
                "先在仓库根执行 npm run build --workspace @sztucode/runtime-ts"
            )
        dist_missing = [
            pkg for pkg in _TS_PACKAGES if not (_REPO_ROOT / "packages" / pkg / "dist").is_dir()
        ]
        if dist_missing:
            raise FileNotFoundError(
                f"dist not built for packages {dist_missing} — host 端 TS runtime 构建未完成"
            )

        fd, name = tempfile.mkstemp(prefix="sztu-runtime-ts-", suffix=".tar.gz")
        os.close(fd)
        with tarfile.open(name, "w:gz") as tar:
            root_manifest = {
                "name": "sztucode-ts-runtime",
                "private": True,
                "type": "module",
                "workspaces": [f"packages/{pkg}" for pkg in _TS_PACKAGES],
            }
            payload = json.dumps(root_manifest, indent=2).encode("utf-8") + b"\n"
            info = tarfile.TarInfo("package.json")
            info.size = len(payload)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(payload))

            for pkg in _TS_PACKAGES:
                pkg_dir = _REPO_ROOT / "packages" / pkg
                tar.add(str(pkg_dir / "package.json"), arcname=f"packages/{pkg}/package.json")
                tar.add(
                    str(pkg_dir / "dist"),
                    arcname=f"packages/{pkg}/dist",
                    filter=self._tar_filter,
                )
            # 编译产物之外，运行时按 dist 上级目录相对路径读取的资源
            for resource in _TS_RUNTIME_RESOURCES:
                resource_path = _REPO_ROOT / "packages" / "runtime-ts" / resource
                if resource_path.is_dir():
                    tar.add(
                        str(resource_path),
                        arcname=f"packages/runtime-ts/{resource}",
                        filter=self._tar_filter,
                    )
            tar.add(
                str(_RUNTIME_ROOT / "eval" / "terminalbench" / "runner.mjs"),
                arcname="eval/terminalbench/runner.mjs",
            )
        return Path(name)

    @staticmethod
    def _tar_filter(member: tarfile.TarInfo) -> tarfile.TarInfo | None:
        parts = Path(member.name).parts
        if any(part in _TAR_EXCLUDES for part in parts):
            return None
        rel = str(Path(*parts))
        if any(rel == excl or rel.startswith(excl + "/") for excl in _TAR_EXCLUDED_DIRS):
            return None
        if member.isfile() and (member.name.endswith(".pyc") or member.name.endswith(".log")):
            return None
        member.uid = member.gid = 0
        member.uname = member.gname = "root"
        return member

    async def _upload_text(
        self,
        environment: BaseEnvironment,
        content: str,
        remote_path: str,
    ) -> None:
        fd, name = tempfile.mkstemp(prefix="sztu-upload-")
        os.close(fd)
        try:
            Path(name).write_text(content, encoding="utf-8")
            await environment.upload_file(name, remote_path)
        finally:
            Path(name).unlink(missing_ok=True)

    async def _download_result(self, environment: BaseEnvironment) -> dict[str, Any]:
        try:
            fd, name = tempfile.mkstemp(prefix="sztu-result-")
            os.close(fd)
            try:
                await environment.download_file(_REMOTE_RESULT, name)
                return json.loads(Path(name).read_text(encoding="utf-8"))
            finally:
                Path(name).unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001 - 结果缺失时仍要给出可读错误
            self.logger.warning("[%s] cannot read result file: %s", self.name(), exc)
            return {"status": "error", "error": f"result unavailable: {exc}"}

    def _build_model_config(self) -> tuple[dict[str, str], list[tuple[str, str]]]:
        """
        组装容器内执行 env 与需要上传的额外文件。

        返回 (exec_env, [(remote_path, content), ...])。
        - anthropic/openai: 直接透传官方 API key 环境变量
        - 其他 provider（OpenAI 兼容）:
            py: 写 llm.toml 并用 SZTU_CONFIG 指向它
            ts: 注入 OPENAI_BASE_URL / OPENAI_API_KEY（TS settings 默认值
                直接读这两个环境变量，无需配置文件）
        """
        if self.runtime == "ts":
            return self._build_model_config_ts(), []
        return self._build_model_config_py()

    def _base_exec_env(self) -> dict[str, str]:
        exec_env: dict[str, str] = {
            "SZTU_HOST": "127.0.0.1",
            "SZTU_PORT": str(self.daemon_port),
            # Terminal-Bench 任务常需在容器内安装依赖，放开 bash 工具的安装拦截
            "SZTU_EVAL_ALLOW_INSTALL": "1",
        }
        if self.max_steps is not None:
            exec_env["SZTU_MAX_STEPS"] = str(self.max_steps)
        return exec_env

    def _resolve_model_endpoint(self) -> tuple[str, str, str, str]:
        """返回 (provider, model, base_url, api_key)"""
        provider = self._parsed_model_provider or ""
        model = self._parsed_model_name or self.model_name or ""
        base_url = self.base_url or self._get_env("SZTU_TB_BASE_URL")
        api_key = self.api_key or self._get_env("SZTU_TB_API_KEY")
        return provider, model, base_url, api_key

    def _build_model_config_py(self) -> tuple[dict[str, str], list[tuple[str, str]]]:
        exec_env = self._base_exec_env()
        provider, model, base_url, api_key = self._resolve_model_endpoint()

        if provider in ("anthropic", "openai") and not base_url:
            exec_env["SZTU_LLM_PROVIDER"] = provider
            if model:
                exec_env["SZTU_LLM_DEFAULT_MODEL"] = model
            # 官方 provider 的密钥从 host 环境透传（daemon 进程继承）
            prefix = provider.upper()
            for suffix in ("API_KEY", "BASE_URL"):
                value = self._get_env(f"{prefix}_{suffix}")
                if value:
                    exec_env[f"{prefix}_{suffix}"] = value
            return exec_env, []

        # OpenAI 兼容第三方端点：写容器内 llm.toml
        if not (base_url and api_key and model):
            raise ValueError(
                "SztuCodeAgent 需要模型配置：使用 -m anthropic/<model>（或 openai/<model>）"
                "并提供对应 API key，或通过 kwargs / SZTU_TB_BASE_URL + SZTU_TB_API_KEY"
                "提供 OpenAI 兼容端点（此时 -m 写 <provider>/<model>，model 为"
                "端点上的模型名）"
            )
        toml = (
            "[llm]\n"
            'provider = "openai"\n'
            'api_format = "openai_chat_completions"\n'
            f'default_model = "{model}"\n'
            f'base_url = "{base_url}"\n'
            f'api_key = "{api_key}"\n'
        )
        exec_env["SZTU_CONFIG"] = _REMOTE_LLM_CONFIG
        return exec_env, [(_REMOTE_LLM_CONFIG, toml)]

    def _build_model_config_ts(self) -> dict[str, str]:
        exec_env = self._base_exec_env()
        # TS runtime 的 trace 默认开启且逐 token 写盘，长任务会撑爆容器磁盘
        exec_env["SZTU_TRACE_ENABLED"] = "0"
        provider, model, base_url, api_key = self._resolve_model_endpoint()

        if provider in ("anthropic", "openai") and not base_url:
            exec_env["SZTU_LLM_PROVIDER"] = provider
            if model:
                exec_env["SZTU_LLM_DEFAULT_MODEL"] = model
            prefix = provider.upper()
            for suffix in ("API_KEY", "BASE_URL"):
                value = self._get_env(f"{prefix}_{suffix}")
                if value:
                    exec_env[f"{prefix}_{suffix}"] = value
            return exec_env

        # OpenAI 兼容第三方端点：TS settings 的 base_url/api_key 默认值
        # 分别取自 OPENAI_BASE_URL / OPENAI_API_KEY 环境变量
        if not (base_url and api_key and model):
            raise ValueError(
                "SztuCodeTsAgent 需要模型配置：使用 -m anthropic/<model>（或"
                " openai/<model>）并提供对应 API key，或通过 kwargs /"
                " SZTU_TB_BASE_URL + SZTU_TB_API_KEY 提供 OpenAI 兼容端点"
                "（此时 -m 写 <provider>/<model>，model 为端点上的模型名）"
            )
        exec_env["SZTU_LLM_PROVIDER"] = "openai"
        exec_env["SZTU_LLM_DEFAULT_MODEL"] = model
        exec_env["OPENAI_BASE_URL"] = base_url
        exec_env["OPENAI_API_KEY"] = api_key
        return exec_env

    def _populate_context(self, context: AgentContext, payload: dict[str, Any]) -> None:
        # Harbor 语义：n_input_tokens 含 cache，n_cache_tokens 为其中缓存命中部分
        input_tokens = int(payload.get("input_tokens", 0) or 0)
        cache_read = int(payload.get("cache_read_input_tokens", 0) or 0)
        cache_creation = int(payload.get("cache_creation_input_tokens", 0) or 0)
        context.n_input_tokens = input_tokens + cache_read + cache_creation
        context.n_cache_tokens = cache_read
        context.n_output_tokens = int(payload.get("output_tokens", 0) or 0)
        context.metadata = {
            "sztu_status": payload.get("status"),
            "sztu_reason": payload.get("reason"),
            "sztu_steps": payload.get("steps", 0),
            "sztu_run_id": payload.get("run_id"),
            "sztu_elapsed_s": payload.get("elapsed_s"),
            "sztu_error": payload.get("error"),
            "sztu_raw_input_tokens": input_tokens,
        }
        self.logger.info(
            "[%s] task finished: status=%s steps=%s elapsed=%ss tokens=%s",
            self.name(),
            payload.get("status"),
            payload.get("steps", 0),
            payload.get("elapsed_s"),
            context.n_input_tokens,
        )


class SztuCodeTsAgent(SztuCodeAgent):
    """
    SztuCodeAgent 的 TS runtime 变体。

    部署 packages/*（host 上先 build）+ Node.js，daemon 为
    ``node packages/runtime-ts/dist/main.js``，runner 为 runner.mjs。
    协议与结果 schema 与 py 版完全一致，用于对比两个 runtime 的能力。
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("runtime", "ts")
        super().__init__(*args, **kwargs)

    @staticmethod
    def name() -> str:
        return "sztu-code-ts"
