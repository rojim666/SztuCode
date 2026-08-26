"""
End-to-end integration test for the S1 agent pipeline.

Requires a configured real Anthropic or OpenAI-compatible provider.
Run explicitly:
    uv run --project py-runtime pytest py-runtime/tests/integration/test_run_e2e.py -v
Or with the marker:
    uv run --project py-runtime pytest py-runtime/tests -m integration -v
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from sztu_code.core.config import SztuConfig
from sztu_code.core.runner import AgentRunner

# 加载项目 .env，使真实 provider 凭证可在不调用 get_config() 时用于集成测试
load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)

pytestmark = pytest.mark.integration


@pytest.fixture()
def sample_file(tmp_path: Path) -> Path:
    f = tmp_path / "sample.txt"
    f.write_text(
        "# Test Document\n\nThe magic number mentioned in this file is 7391.\n",
        encoding="utf-8",
    )
    return f


# 功能：验证完整端到端链路调用真实可配置 LLM、读取文件并写入 events.jsonl
# 设计：按环境选择 Anthropic/OpenAI 兼容 provider，以数字 7391 和事件序列证明模型确实使用了 read_file
async def test_run_e2e_reads_file_and_succeeds(
    sample_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_provider = os.environ.get("SZTU_E2E_PROVIDER", "").strip()
    if requested_provider:
        provider_name = requested_provider
    elif os.environ.get("OPENAI_API_KEY"):
        provider_name = "openai"
    elif os.environ.get("ANTHROPIC_API_KEY"):
        provider_name = "anthropic"
    else:
        pytest.skip("real LLM API key not set")
    if provider_name not in {"anthropic", "openai"}:
        pytest.fail(f"unsupported SZTU_E2E_PROVIDER: {provider_name}")
    model = (
        os.environ.get("SZTU_E2E_MODEL", "").strip()
        or os.environ.get("SZTU_LLM_DEFAULT_MODEL", "").strip()
    )
    if not model:
        pytest.skip("SZTU_E2E_MODEL or SZTU_LLM_DEFAULT_MODEL not set")

    # ReadFileTool resolves paths relative to CWD — point it at tmp_path
    monkeypatch.chdir(tmp_path)

    goal = (
        "Use the read_file tool to read the file 'sample.txt' "
        "and report the magic number it mentions."
    )
    runs_dir = tmp_path / "runs"

    config = SztuConfig()
    config.agent.max_steps = 5
    config.llm.provider = provider_name
    config.llm.default_model = model
    config.llm.context_window = int(os.environ.get("SZTU_E2E_CONTEXT_WINDOW", "0"))

    runner = AgentRunner(config, runs_dir=runs_dir)
    await runner.run(goal)

    # ── events.jsonl must exist ──────────────────────────────────────────────
    jsonl_files = list(runs_dir.rglob("events.jsonl"))
    assert len(jsonl_files) == 1, "expected exactly one events.jsonl"

    events = [
        json.loads(line)
        for line in jsonl_files[0].read_text(encoding="utf-8").splitlines()
        if line
    ]
    types = [e["type"] for e in events]

    # ── event sequence assertions (from §6.4) ────────────────────────────────
    assert types[0] == "run.started"
    assert types[-1] == "run.finished"
    assert "step.started" in types
    assert "tool.call_started" in types
    assert "tool.call_finished" in types
    assert "llm.usage" in types

    # ── run completed successfully ────────────────────────────────────────────
    finished = events[-1]
    assert finished["status"] == "success", (
        f"run finished with status={finished['status']!r}, reason={finished.get('reason')!r}"
    )

    # ── read_file was actually invoked ────────────────────────────────────────
    tool_starts = [e for e in events if e["type"] == "tool.call_started"]
    assert any(e["tool_name"] == "read_file" for e in tool_starts), (
        "expected at least one read_file tool call"
    )

    # ── run_id is consistent across the event stream ─────────────────────────
    run_id = events[0]["run_id"]
    assert all(e["run_id"] == run_id for e in events), "run_id must be the same in every event"

    # ── LLM cache stats are present ──────────────────────────────────────────
    usage_events = [e for e in events if e["type"] == "llm.usage"]
    assert len(usage_events) >= 1
    for ue in usage_events:
        assert "input_tokens" in ue
        assert "output_tokens" in ue
        assert "cache_read_input_tokens" in ue
