# SWE-bench 运行事件隔离 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 SWE-bench 适配器只消费当前 RPC run 的事件，避免其他 run 的完成事件、日志和 token 统计污染当前结果。

**Architecture:** 在 `eval/swebench/adapter.py` 中提取私有 `_RunEventCollector`，先缓存尚未绑定 run ID 的事件，绑定后按 run ID 接受事件；只有匹配的 `run.finished` 更新最终状态并唤醒等待。`run_instance_via_rpc` 使用 collector 的过滤结果，并显式注册事件回调，不改变 SocketClient 或事件协议。

**Tech Stack:** Python 3.11+, `asyncio.Event`, `dataclasses`, pytest, Ruff。

---

### Task 1: 添加事件隔离的失败测试

**Files:**
- Modify: `tests/unit/test_swebench_adapter.py`，在现有适配器测试导入和 token 测试附近增加 collector 行为测试

- [ ] **Step 1: 导入适配器模块而不依赖尚不存在的类**

在现有 `from eval.swebench.adapter import (...)` 导入旁增加：

```python
from eval.swebench import adapter as swebench_adapter  # noqa: E402
```

测试通过模块属性访问 `_RunEventCollector`，这样 RED 阶段可以完成收集并因缺少行为失败，而不是因导入语法错误失败。

- [ ] **Step 2: 写交错事件过滤和 token 统计测试**

```python
def test_run_event_collector_filters_interleaved_events() -> None:
    collector = swebench_adapter._RunEventCollector()
    collector.record({"type": "run.finished", "run_id": "other", "status": "success", "steps": 99})
    collector.record({"type": "step.started", "run_id": "current", "step": 1})
    collector.record({"type": "llm.usage", "run_id": "other", "input_tokens": 900})
    collector.record({"type": "tool.call_started", "run_id": "current", "tool_name": "bash"})
    collector.record({"type": "llm.usage", "run_id": "current", "input_tokens": 12, "output_tokens": 3})

    collector.set_run_id("current")
    assert not collector.finished.is_set()

    collector.record({"type": "run.finished", "run_id": "other", "status": "failure", "steps": 100})
    assert not collector.finished.is_set()

    collector.record({"type": "run.finished", "run_id": "current", "status": "success", "steps": 2})

    assert collector.finished.is_set()
    assert collector.finished_event == {
        "type": "run.finished", "run_id": "current", "status": "success", "steps": 2,
    }
    assert [event["run_id"] for event in collector.events] == ["current"] * 4
    usage = summarize_token_usage(collector.events)
    assert usage.input_tokens == 12
    assert usage.output_tokens == 3
```

- [ ] **Step 3: 写绑定前完成事件的竞态测试**

```python
def test_run_event_collector_replays_current_finished_event_after_binding() -> None:
    collector = swebench_adapter._RunEventCollector()
    current_finished = {"type": "run.finished", "run_id": "current", "status": "failure", "steps": 4}
    collector.record(current_finished)
    collector.record({"type": "run.finished", "run_id": "other", "status": "success", "steps": 8})

    assert not collector.finished.is_set()
    collector.set_run_id("current")

    assert collector.finished.is_set()
    assert collector.finished_event == current_finished
    assert collector.events == [current_finished]
```

- [ ] **Step 4: 覆盖四种终止状态和无 run ID 事件**

```python
@pytest.mark.parametrize("status", ["success", "failure", "cancelled", "max_steps"])
def test_run_event_collector_accepts_all_terminal_statuses(status: str) -> None:
    collector = swebench_adapter._RunEventCollector()
    collector.set_run_id("current")

    collector.record({"type": "run.finished", "run_id": "other", "status": status, "steps": 8})
    assert not collector.finished.is_set()

    collector.record({"type": "run.finished", "run_id": "current", "status": status, "steps": 3})

    assert collector.finished.is_set()
    assert collector.finished_event["status"] == status
    assert collector.finished_event["steps"] == 3


def test_run_event_collector_ignores_events_without_run_id() -> None:
    collector = swebench_adapter._RunEventCollector()
    collector.set_run_id("current")

    collector.record({"type": "run.finished", "status": "success", "steps": 1})
    collector.record({"type": "llm.usage", "input_tokens": 50})

    assert collector.events == []
    assert not collector.finished.is_set()
```

- [ ] **Step 5: 运行 RED 测试并确认失败原因是缺少 collector**

Run:

```text
python -m uv run --offline pytest tests/unit/test_swebench_adapter.py -k run_event_collector -v
```

Expected: collection succeeds, then the new tests fail with `AttributeError: module ... has no attribute '_RunEventCollector'`. No daemon, model, or network is started.

### Task 2: 实现最小的 `_RunEventCollector`

**Files:**
- Modify: `eval/swebench/adapter.py`，在 `TokenUsage` 定义后增加私有 collector

- [ ] **Step 1: 添加 collector 状态和过滤方法**

```python
@dataclass
class _RunEventCollector:
    run_id: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    finished_event: dict[str, Any] | None = None
    finished: asyncio.Event = field(default_factory=asyncio.Event)
    _pending_events: list[dict[str, Any]] = field(default_factory=list)

    def record(self, event: dict[str, Any]) -> None:
        event_run_id = str(event.get("run_id", ""))
        if not event_run_id:
            return
        if self.run_id is None:
            self._pending_events.append(event)
            return
        self._accept(event, event_run_id)

    def set_run_id(self, run_id: str) -> None:
        normalized_run_id = str(run_id)
        if not normalized_run_id:
            raise ValueError("run_id must be non-empty")
        self.run_id = normalized_run_id
        pending_events, self._pending_events = self._pending_events, []
        for event in pending_events:
            self._accept(event, str(event.get("run_id", "")))

    def _accept(self, event: dict[str, Any], event_run_id: str) -> None:
        if event_run_id != self.run_id:
            return
        self.events.append(event)
        if event.get("type") == "run.finished":
            self.finished_event = event
            self.finished.set()
```

- [ ] **Step 2: 运行 RED 测试确认最小实现方向**

Run:

```text
python -m uv run --offline pytest tests/unit/test_swebench_adapter.py -k run_event_collector -v
```

Expected: all collector tests pass.

### Task 3: 将 collector 接入 RPC 适配器

**Files:**
- Modify: `eval/swebench/adapter.py:205-300`，替换临时事件状态并绑定当前 run

- [ ] **Step 1: 用 collector 替换三个局部状态**

将 `collected_events`、`run_finished`、`run_status` 替换为：

```python
    collector = _RunEventCollector()

    async def on_event(event: dict[str, Any]) -> None:
        collector.record(event)
        event_type = event.get("type", "")
        if collector.run_id != str(event.get("run_id", "")):
            return
```

保留已有 step/tool 日志分支，但只对 collector 当前 run 的事件执行。连接成功后、创建 `loop_task` 前注册：

```python
    client.on_event(on_event)
```

- [ ] **Step 2: 绑定 RPC 返回的 run ID 并使用过滤结果**

将发送消息后的等待和结果提取改为：

```python
        run_id = str(send_result.get("run_id", ""))
        collector.set_run_id(run_id)
        logger.info(f"  Run started: {run_id}")

        try:
            await asyncio.wait_for(collector.finished.wait(), timeout=timeout)
        except TimeoutError:
            result.error = f"Timeout after {timeout}s"
            try:
                await client.send_command("run.cancel", {"run_id": run_id})
            except Exception:
                pass

        finished_event = collector.finished_event or {}
        result.status = finished_event.get("status", "")
        result.steps = finished_event.get("steps", 0)
        result.events_log = collector.events

        usage = summarize_token_usage(collector.events)
```

保留现有 diff 条件，但改为检查 `result.status`。这样其他 run 的完成事件不能提前唤醒，当前 run 在 `set_run_id` 前完成时会由 collector 立即设置等待事件。

- [ ] **Step 3: 运行专项测试和静态检查**

Run:

```text
python -m uv run --offline pytest tests/unit/test_swebench_adapter.py -v
python -m uv run --offline ruff check eval/swebench/adapter.py tests/unit/test_swebench_adapter.py
```

Expected: the adapter unit test file passes and Ruff exits with code 0.

### Task 4: 全量验证并准备提交

**Files:**
- Modify: no additional files

- [ ] **Step 1: 运行完整单元测试和类型/差异检查**

Run:

```text
python -m uv run --offline pytest tests/unit -q
python -m uv run --offline mypy eval/swebench/adapter.py
git diff --check
```

Expected: full unit tests report only the known unrelated Windows path-separator assertion; compare Mypy output with the unchanged `upstream/main` adapter and ensure no new errors are introduced. `git diff --check` exits with code 0.

- [ ] **Step 2: 检查变更范围和工作树**

Run:

```text
git status --short
git diff --stat upstream/main...HEAD
git diff -- eval/swebench/adapter.py tests/unit/test_swebench_adapter.py
```

Expected: only the adapter, its unit tests, and the two process documents are changed; no generated cache or unrelated source changes appear.

- [ ] **Step 3: 提交实现**

Run:

```text
git add eval/swebench/adapter.py tests/unit/test_swebench_adapter.py
git commit -s -m "fix: 隔离 SWE-bench 运行事件"
```

Expected: commit contains the implementation and regression tests with a `Signed-off-by` trailer.
