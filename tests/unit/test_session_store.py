from __future__ import annotations

from pathlib import Path

from sztu_code.core.session.model import RunStats, Session
from sztu_code.core.session.store import SessionStore


# 功能：验证 SessionStore 初始化时自动创建 sessions 根目录
# 设计：传入 tmp_path 下不存在的目录，断言目录被创建，覆盖首次启动 daemon 的冷路径
def test_store_creates_root(tmp_path: Path) -> None:
    root = tmp_path / "sessions"
    SessionStore(root)
    assert root.exists()


# 功能：验证 session meta 写入后能完整读回
# 设计：构造含 run_ids 的 Session，经过 JSON 文件往返后断言字段保持，覆盖 meta.json 的持久化契约
def test_meta_roundtrip(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    session = Session(
        id="sess-1",
        mode="chat",
        status="waiting_for_input",
        title="hello",
        created_at="t1",
        updated_at="t2",
        run_ids=["run-1"],
        run_stats={"run-1": RunStats(input_tokens=120, output_tokens=30, cache_read_input_tokens=90, elapsed_s=2.5)},
    )
    store.write_meta(session)
    loaded = store.read_meta("sess-1")
    assert loaded == session


def test_history_preserves_run_id_without_polluting_model_messages(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    store.append_message("sess-1", "user", "hello", run_id="run-1")

    assert "run_id" not in store.read_messages("sess-1")[0]
    assert store.read_history("sess-1")[0]["run_id"] == "run-1"


def test_history_restores_messages_hidden_by_compaction(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    store.append_message("sess-1", "user", "original request", run_id="run-1")
    store.append_message("sess-1", "assistant", "original response", run_id="run-1")
    continuation = (
        "This session is being continued from a previous conversation that ran out of "
        "context. The summary below covers the earlier portion of the conversation.\n\n"
        "Summary:\n## 1. Original Goal\nKeep working\n\n"
        "Continue the conversation from where it left off without asking questions."
    )

    store.write_compacted("sess-1", [
        {"role": "user", "content": continuation},
        {"role": "assistant", "content": "Understood, I'll continue from this summary."},
    ])

    assert store.read_messages("sess-1")[0]["content"] == continuation
    history = store.read_history("sess-1")
    assert [(message["role"], message["content"]) for message in history] == [
        ("user", "original request"),
        ("assistant", "original response"),
    ]
    assert [message["run_id"] for message in history] == ["run-1", "run-1"]


def test_history_merges_sliding_compaction_backups_without_duplicates(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    first_turn = [
        {"role": "user", "content": "first request"},
        {"role": "assistant", "content": "first response"},
    ]
    second_turn = [
        {"role": "user", "content": "second request"},
        {"role": "assistant", "content": "second response"},
    ]
    third_turn = [
        {"role": "user", "content": "third request"},
        {"role": "assistant", "content": "third response"},
    ]
    for message in [*first_turn, *second_turn]:
        store.append_message("sess-1", message["role"], message["content"], run_id="run-old")

    def continuation(summary: str) -> str:
        return (
            "This session is being continued from a previous conversation that ran out of "
            "context. The summary below covers the earlier portion of the conversation.\n\n"
            f"Summary:\n{summary}\n\nContinue the conversation directly."
        )

    store.write_compacted("sess-1", [
        {"role": "user", "content": continuation("first compact")},
        {"role": "assistant", "content": "Understood, I'll continue from this summary."},
        *second_turn,
    ])
    for message in third_turn:
        store.append_message("sess-1", message["role"], message["content"], run_id="run-new")
    store.write_compacted("sess-1", [
        {"role": "user", "content": continuation("second compact")},
        {"role": "assistant", "content": [{
            "type": "text",
            "text": "Understood, I'll continue from this summary.",
            "cache_control": {"type": "ephemeral"},
        }]},
        *third_turn,
    ])

    history = store.read_history("sess-1")
    assert [(message["role"], message["content"]) for message in history] == [
        (message["role"], message["content"])
        for message in [*first_turn, *second_turn, *third_turn]
    ]


def test_backfill_run_stats_from_finished_event(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    session = Session(
        id="sess-1", mode="chat", status="waiting_for_input", title="old",
        created_at="t1", updated_at="t2", run_ids=["run-1"],
    )
    store.write_meta(session)
    events = store.runs_dir(session.id) / "run-1" / "events.jsonl"
    events.parent.mkdir(parents=True)
    events.write_text(
        '{"type":"run.finished","total_input_tokens":120,"total_output_tokens":30,'
        '"cache_read_input_tokens":90,"elapsed_s":2.5}\n',
        encoding="utf-8",
    )

    assert store.backfill_run_stats(session)
    assert session.run_stats["run-1"] == RunStats(
        input_tokens=120, output_tokens=30, cache_read_input_tokens=90, elapsed_s=2.5
    )
    assert store.read_meta(session.id).run_stats == session.run_stats


# 功能：验证多轮会话按各自 run_id 保存不同的 token 与耗时统计
# 设计：为两个 run 写入数值不同的完成事件并回填，断言统计不会复用或串写到另一轮
def test_backfill_keeps_each_run_stats_independent(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    session = Session(
        id="sess-1", mode="chat", status="waiting_for_input", title="multi-run",
        created_at="t1", updated_at="t2", run_ids=["run-1", "run-2"],
    )
    store.write_meta(session)
    finished_by_run = {
        "run-1": (120, 30, 2.5),
        "run-2": (480, 75, 8.25),
    }
    for run_id, (input_tokens, output_tokens, elapsed_s) in finished_by_run.items():
        events = store.runs_dir(session.id) / run_id / "events.jsonl"
        events.parent.mkdir(parents=True)
        events.write_text(
            '{"type":"run.finished",'
            f'"total_input_tokens":{input_tokens},'
            f'"total_output_tokens":{output_tokens},'
            f'"elapsed_s":{elapsed_s}}}\n',
            encoding="utf-8",
        )

    assert store.backfill_run_stats(session)
    assert session.run_stats == {
        "run-1": RunStats(input_tokens=120, output_tokens=30, elapsed_s=2.5),
        "run-2": RunStats(input_tokens=480, output_tokens=75, elapsed_s=8.25),
    }
    assert session.run_stats["run-1"] != session.run_stats["run-2"]


def test_read_context_injections_restores_full_text_across_runs(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    session = Session(
        id="sess-1", mode="chat", status="waiting_for_input", title="context",
        created_at="t1", updated_at="t2", run_ids=["run-1", "run-2"],
    )
    store.write_meta(session)
    events_by_run = {
        "run-1": [
            '{"type":"run.started","run_id":"run-1"}',
            '{"type":"context.injected","run_id":"run-1","source":"system",'
            '"label":"上下文注入","chars":35,"preview":"# Base",'
            '"text":"# Base\\n\\n## Project Context\\nproject rules","ts":"t1"}',
        ],
        "run-2": [
            "{broken json",
            '{"type":"llm.token","run_id":"run-2","token":"ignored"}',
            '{"type":"context.injected","run_id":"run-2","source":"system",'
            '"label":"系统提示词","chars":"invalid","preview":"legacy preview","ts":"t2"}',
        ],
    }
    for run_id, lines in events_by_run.items():
        events_path = store.runs_dir(session.id) / run_id / "events.jsonl"
        events_path.parent.mkdir(parents=True)
        events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    injections = store.read_context_injections(session.id)

    assert [item["run_id"] for item in injections] == ["run-1", "run-2"]
    assert injections[0]["text"].endswith("project rules")
    assert injections[1] == {
        "run_id": "run-2",
        "source": "system",
        "label": "上下文注入",
        "chars": 0,
        "preview": "legacy preview",
        "text": "legacy preview",
        "ts": "t2",
    }


def test_store_delete_removes_session_files(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    store.write_meta(Session(
        id="sess-1",
        mode="chat",
        status="waiting_for_input",
        title="delete me",
        created_at="t1",
        updated_at="t2",
        run_ids=["run-1"],
    ))
    store.append_message("sess-1", "user", "hello")

    store.delete("sess-1")

    assert not store.session_dir("sess-1").exists()
    assert store.list_sessions(include_archived=True) == []


# 功能：验证含 tool_use/tool_result block 的 thread 消息能按 Anthropic 格式读回
# 设计：追加 assistant tool_use 和 user tool_result，读取时应剥离 ts/run_id，只保留 API messages 所需字段
def test_thread_message_roundtrip_with_tool_blocks(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    store.append_message("sess-1", "user", "read file")
    store.append_message(
        "sess-1",
        "assistant",
        [{"type": "tool_use", "id": "t1", "name": "read_file", "input": {"path": "x"}}],
        run_id="run-1",
    )
    store.append_message(
        "sess-1",
        "user",
        [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}],
        run_id="run-1",
    )

    messages = store.read_messages("sess-1")
    # read_messages 现在会透出 ts 时间戳，比较时忽略它
    stripped = [{k: v for k, v in m.items() if k != "ts"} for m in messages]
    assert stripped == [
        {"role": "user", "content": "read file"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "t1", "name": "read_file", "input": {"path": "x"}}
            ],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}],
        },
    ]
    assert all(m["ts"] for m in messages)  # 每条消息都带时间戳


# 功能：验证 thread 尾部孤儿 tool_use 会被裁掉
# 设计：构造一条未配对 tool_result 的 assistant tool_use，读取时只返回最后一次配平之前的消息，避免 API 报 messages.invalid
def test_read_messages_trims_orphan_tool_use_tail(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    store.append_message("sess-1", "user", "hello")
    store.append_message(
        "sess-1",
        "assistant",
        [{"type": "tool_use", "id": "orphan", "name": "read_file", "input": {}}],
        run_id="run-1",
    )
    messages = store.read_messages("sess-1")
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "hello"
    assert messages[0]["ts"]


# 功能：验证 notes.md 不存在时读为空，追加笔记后能读到内容和 run_id
# 设计：先读空状态再追加，覆盖 chat 第一轮前和 note_save 调用后的两个关键状态
def test_notes_read_and_append(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    assert store.read_notes("sess-1") == ""
    store.append_note("sess-1", "Python 3.12", "run-1")
    notes = store.read_notes("sess-1")
    assert "Python 3.12" in notes
    assert "run-1" in notes


# 功能：验证 SessionStore 使用构造时传入的 tool_result 截断参数
# 设计：配置小于完整标记的 limit/keep，读取结果仍应严格受限并显式呈现截断提示
def test_read_messages_uses_configured_tool_result_budget(tmp_path: Path) -> None:
    store = SessionStore(tmp_path, tool_result_limit=20, tool_result_keep=5)
    store.append_message("sess-1", "assistant", [
        {"type": "tool_use", "id": "t1", "name": "read_file", "input": {"path": "x"}},
    ])
    store.append_message("sess-1", "user", [
        {"type": "tool_result", "tool_use_id": "t1", "content": "a" * 100},
    ])

    messages = store.read_messages("sess-1")
    result_block = messages[-1]["content"][0]
    assert len(result_block["content"]) <= 5
    assert result_block["content"].startswith("[")
