# SWE-bench 运行事件隔离设计

## 背景

SWE-bench 适配器通过全局事件订阅等待 daemon 的一次 `session.send_message` 运行完成。全局订阅可能同时收到其他运行的事件。当前 `run_instance_via_rpc` 在回调中无条件收集事件，并把任意 `run.finished` 当作当前任务的结束信号，因此其他运行可能污染 `events_log`、token 统计和状态，甚至提前结束当前等待。

Issue #33 要求适配器只消费当前运行的事件，同时保留现有单次运行流程和终止状态语义。

## 目标与验收标准

- 仅当前 `run_id` 的事件进入本次 `RunResult.events_log`。
- 仅当前 `run_id` 的 `llm.usage` 事件参与 token 统计。
- 其他运行的 `run.finished` 不得更新当前状态，也不得唤醒等待。
- 当前运行的 `success`、`failure`、`cancelled`、`max_steps` 完成事件都能结束等待，并正确写入状态和步骤数。
- 处理 `session.send_message` 返回当前 `run_id` 前已经到达的事件，不能丢失当前运行的完成事件，也不能误收集其他运行事件。
- 测试只使用内存事件和假的异步等待，不启动 daemon、模型或网络。

## 非目标

- 不实现多个 SWE-bench 实例的并行调度。
- 不修改 `SocketClient`、RPC 事件协议或 daemon 的全局订阅行为。
- 不改变 `RunResult` 或公开命令行接口。
- 不改变 token 字段的计算规则，只改变传入统计函数的事件集合。

## 方案比较

### 方案一：在现有回调中直接过滤

在 `on_event` 中增加 `run_id` 判断，并额外处理当前 run ID 尚未返回的阶段。代码改动最少，但回调会同时承担缓存、过滤和完成状态管理，难以单独验证竞态，后续修改容易重新引入提前唤醒问题。

### 方案二：等待完成后再过滤

先收集所有事件，等待任意 `run.finished`，最后按 `run_id` 过滤。这种方式无法阻止其他运行提前结束等待，违反 issue 的核心行为，予以排除。

### 方案三：提取有状态的 `_RunEventCollector`（推荐）

把事件接收、运行 ID 绑定、过滤、完成状态和待处理事件缓存集中到一个轻量对象。回调只把事件交给 collector，适配器在收到 `send_message` 返回值后绑定当前 `run_id`，再从 collector 读取过滤后的事件和最终状态。对象不依赖 daemon 或网络，可用交错事件序列直接测试。

推荐原因是它明确隔离了“事件到达时间”和“当前 run ID 可用时间”这两个状态，并能覆盖两者竞态，而不改变现有 RPC 流程。

## 详细设计

### 组件与状态

在 `eval/swebench/adapter.py` 中新增私有 `_RunEventCollector`，维护：

- `run_id: str | None`：尚未绑定时为 `None`。
- `events: list[dict[str, Any]]`：只保存已确认属于当前运行的事件。
- `finished_event: dict[str, Any] | None`：当前运行的 `run.finished`。
- `finished: asyncio.Event`：仅由当前运行的完成事件设置。
- 绑定前的待处理事件：用于暂存事件，绑定后一次性按 `run_id` 过滤。

`record(event)` 在任何时刻都不抛出异常：

1. 若事件没有 `run_id`，直接忽略，避免无法归属的全局事件污染本次结果。
2. 若当前 `run_id` 尚未绑定，暂存事件。
3. 若事件的 `run_id` 与当前 ID 不同，忽略。
4. 若匹配，追加到 `events`；匹配的 `run.finished` 更新 `finished_event` 并设置 `finished`。

`set_run_id(run_id)` 只允许绑定非空 ID，并重新处理之前暂存的事件。重新处理使用同一套过滤规则，因此当前完成事件即使先到达也会唤醒等待，其他运行事件仍会被丢弃。适配器在绑定后若 collector 已经完成，不需要额外等待。

### 适配器集成

`run_instance_via_rpc` 用 collector 替换当前的 `collected_events`、`run_finished` 和 `run_status` 回调状态：

1. 创建 collector 并把 `on_event` 注册给 `SocketClient`。
2. `session.send_message` 返回后调用 `set_run_id(send_result["run_id"])`。
3. 等待 collector 的完成事件，超时逻辑保持不变。
4. 从 collector 的 `finished_event` 读取 `status`、`steps` 和 `run_id`，从 `events` 填充 `events_log` 并汇总 token。
5. 只有状态为 `success`、`max_steps` 或 `cancelled` 时继续获取 diff，保持现有行为。

事件日志中的顺序仍按到达顺序保留；绑定前属于当前 run 的事件会在绑定时追加，因此不会改变事件相对顺序。

### 状态与异常处理

- 空的 RPC `run_id` 不被当作有效当前运行 ID；适配器保持原有结果错误处理，不会把无归属事件当作完成信号。
- 其他运行的 `run.finished` 既不写入 `finished_event`，也不设置 `finished`。
- 超时后仍尝试 `run.cancel`，随后只使用当前 run 已过滤的事件计算统计。
- `failure`、`cancelled` 和 `max_steps` 是完成状态，不改变现有 diff 获取条件。

## 测试设计

在 `tests/unit/test_swebench_adapter.py` 增加 collector 的离线单元测试：

1. 交错记录其他 run 的 `run.finished`、当前 run 的 `step.*`、`tool.*`、`llm.usage`，绑定当前 ID 后断言日志只含当前事件、token 只累计当前 usage，且其他完成事件没有设置完成事件。
2. 在绑定当前 ID 前记录当前 run 的 `run.finished`，绑定后断言该事件被恢复、状态和步骤正确、完成事件已设置。
3. 参数化验证当前 run 的 `success`、`failure`、`cancelled`、`max_steps` 都能设置完成状态；其他 run 的同名状态不能结束等待。
4. 验证缺少 `run_id` 的事件被忽略，不影响日志和完成状态。

测试直接实例化 collector 并调用 `record`/`set_run_id`，不创建 `SocketClient`，不访问网络或 daemon。现有 `summarize_token_usage` 测试继续保留，用过滤后的事件列表验证集成契约。

## 验收命令

```text
uv run pytest tests/unit/test_swebench_adapter.py -v
uv run ruff check eval/swebench/adapter.py tests/unit/test_swebench_adapter.py
```

实现完成后另外运行完整 `tests/unit`、类型检查和 `git diff --check`，并在创建 PR 前重新执行全部验证命令。
