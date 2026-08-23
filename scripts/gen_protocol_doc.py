#!/usr/bin/env python3
"""Generate docs/reference/wire-protocol.md from the protocol models."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sztu_code.core.bus.commands import (
    AgentRunCommand,
    AgentRunResult,
    ChangeListCommand,
    ChangeListResult,
    ChangeRevertCommand,
    ChangeRevertResult,
    EventSubscribeCommand,
    EventSubscribeResult,
    PingCommand,
    PluginCatalogCommand,
    PluginCatalogInstallCommand,
    PluginCatalogInstallResult,
    PluginCatalogResult,
    PluginInstallCommand,
    PluginInstallResult,
    PluginListCommand,
    PluginListResult,
    PluginMarketplaceAddCommand,
    PluginMarketplaceAddResult,
    PluginMarketplaceRefreshCommand,
    PluginMarketplaceRefreshResult,
    PluginMarketplaceRemoveCommand,
    PluginMarketplaceRemoveResult,
    PluginSetEnabledCommand,
    PluginSetEnabledResult,
    PluginUninstallCommand,
    PluginUninstallResult,
    PongResult,
    ProviderCcswitchApplyCommand,
    ProviderCcswitchApplyResult,
    ProviderCcswitchListCommand,
    ProviderCcswitchListResult,
    ProviderStatusCommand,
    ProviderStatusResult,
    SessionArchiveCommand,
    SessionArchiveResult,
    SessionCloseCommand,
    SessionCloseResult,
    SessionCreateCommand,
    SessionCreateResult,
    SessionGetHistoryCommand,
    SessionGetHistoryResult,
    SessionListCommand,
    SessionListResult,
    SessionPinCommand,
    SessionPinResult,
    SessionRenameCommand,
    SessionRenameResult,
    SessionResumeCommand,
    SessionResumeResult,
    SessionSendMessageCommand,
    SessionSendMessageResult,
    SessionSteerMessageCommand,
    SessionSteerMessageResult,
    SettingsGetCommand,
    SettingsGetResult,
    SettingsUpdateCommand,
    SettingsUpdateResult,
    SkillInstallCommand,
    SkillInstallResult,
    SkillListCommand,
    SkillListResult,
    SkillSetEnabledCommand,
    SkillSetEnabledResult,
    UserQuestionPendingCommand,
    UserQuestionPendingResult,
    UserQuestionRespondCommand,
    UserQuestionRespondResult,
    WorkspaceProfileCommand,
    WorkspaceProfileResult,
)
from sztu_code.core.bus.envelope import EventPushEnvelope
from sztu_code.core.bus.events import (
    ChangeAppliedEvent,
    CoreStartedEvent,
    LlmModelSelectedEvent,
    LlmThinkingEvent,
    LlmTokenEvent,
    LlmUsageEvent,
    LogLineEvent,
    RunFinishedEvent,
    RunStartedEvent,
    SessionClosedEvent,
    SessionCreatedEvent,
    SessionMessageReceivedEvent,
    SessionMessageSteeredEvent,
    SessionResumedEvent,
    SessionWaitingForInputEvent,
    StepFinishedEvent,
    StepStartedEvent,
    ToolCallFailedEvent,
    ToolCallFinishedEvent,
    ToolCallStartedEvent,
    UserQuestionRequestedEvent,
    UserQuestionResolvedEvent,
    WorkflowFinishedEvent,
    WorkflowHandoffEvent,
    WorkflowReviewEvent,
    WorkflowStartedEvent,
    WorkflowTaskUpdatedEvent,
)

_OUTPUT_PATH = Path(__file__).parent.parent / "docs" / "reference" / "wire-protocol.md"


# 从 pydantic 模型生成一个带字段表、JSON Schema 和可选示例的 Markdown 小节
def _model_section(name: str, model: type, example: dict | None = None) -> str:  # type: ignore[type-arg]
    schema = model.model_json_schema()  # type: ignore[attr-defined]
    props = schema.get("properties", {})
    required: set[str] = set(schema.get("required", []))

    table = ""
    if props:
        table = "\n| Field | Type | Required |\n|---|---|---|\n"
        for field_name, field_info in props.items():
            ftype = field_info.get("type", "object")
            if "anyOf" in field_info:
                ftype = " | ".join(t.get("type", "?") for t in field_info["anyOf"])
            req = "yes" if field_name in required else "no"
            table += f"| `{field_name}` | `{ftype}` | {req} |\n"

    schema_block = f"\n```json\n{json.dumps(schema, indent=2)}\n```\n"

    example_block = ""
    if example:
        example_block = f"\n**Example:**\n\n```json\n{json.dumps(example, indent=2)}\n```\n"

    return f"### {name}\n{table}{schema_block}{example_block}"


# 生成完整的 Wire Protocol 文档字符串
def generate() -> str:
    run_id = "20260516-100000-abc123"
    ts = "2026-05-16T10:00:00.001Z"

    ping_req_example = {
        "jsonrpc": "2.0",
        "id": "u-1",
        "method": "core.ping",
        "params": {"client": "cli/0.0.1"},
    }
    pong_resp_example = {
        "jsonrpc": "2.0",
        "id": "u-1",
        "result": {
            "server_version": "0.2.0",
            "uptime_ms": 12,
            "received_at": ts,
        },
    }
    agent_run_req_example = {
        "jsonrpc": "2.0",
        "id": "u-2",
        "method": "agent.run",
        "params": {"goal": "总结 README.md 的主要章节"},
    }
    agent_run_resp_example = {
        "jsonrpc": "2.0",
        "id": "u-2",
        "result": {"run_id": run_id},
    }
    subscribe_req_example = {
        "jsonrpc": "2.0",
        "id": "u-3",
        "method": "event.subscribe",
        "params": {
            "topics": ["run.*", "step.*", "tool.*", "llm.token"],
            "scope": "global",
            "replay_from_run": None,
        },
    }
    subscribe_resp_example = {
        "jsonrpc": "2.0",
        "id": "u-3",
        "result": {"subscription_id": "sub-abc123", "replayed_count": 0},
    }
    session_id = "sess-abc123def456"
    session_create_req_example = {
        "jsonrpc": "2.0",
        "id": "u-4",
        "method": "session.create",
        "params": {"mode": "chat", "title": ""},
    }
    session_create_resp_example = {
        "jsonrpc": "2.0",
        "id": "u-4",
        "result": {"session_id": session_id, "status": "waiting_for_input"},
    }
    session_send_req_example = {
        "jsonrpc": "2.0",
        "id": "u-5",
        "method": "session.send_message",
        "params": {"session_id": session_id, "content": "总结 README.md"},
    }
    session_send_resp_example = {
        "jsonrpc": "2.0",
        "id": "u-5",
        "result": {"run_id": run_id},
    }
    event_push_example = {
        "kind": "event",
        "event": {
            "type": "step.started",
            "run_id": run_id,
            "step": 1,
            "ts": ts,
        },
    }

    sections = [
        "# Wire Protocol\n\n",
        "> Generated by `scripts/gen_protocol_doc.py`. **Do not edit manually.**\n\n",
        "[Back to documentation index](../README.md)\n\n",
        "## Transport\n\n",
        "- TCP loopback `127.0.0.1:7437` (override via `SZTU_HOST` / `SZTU_PORT`)\n",
        "- Each message is one `\\n`-terminated JSON line (NDJSON)\n",
        "- Commands use JSON-RPC 2.0 (client → server); Events use `kind=event` envelope (server → client)\n\n",
        "## Commands\n\n",
        "All commands are sent as JSON-RPC 2.0 requests. The `type` field inside `params` is used for routing.\n\n",
        _model_section("PingCommand", PingCommand, ping_req_example),
        "\n",
        _model_section("PongResult", PongResult, pong_resp_example),
        "\n",
        _model_section("AgentRunCommand", AgentRunCommand, agent_run_req_example),
        "\n",
        _model_section("AgentRunResult", AgentRunResult, agent_run_resp_example),
        "\n",
        _model_section("WorkspaceProfileCommand", WorkspaceProfileCommand),
        "\n",
        _model_section("WorkspaceProfileResult", WorkspaceProfileResult),
        "\n",
        _model_section("ChangeListCommand", ChangeListCommand),
        "\n",
        _model_section("ChangeListResult", ChangeListResult),
        "\n",
        _model_section("ChangeRevertCommand", ChangeRevertCommand),
        "\n",
        _model_section("ChangeRevertResult", ChangeRevertResult),
        "\n",
        _model_section("SettingsGetCommand", SettingsGetCommand),
        "\n",
        _model_section("SettingsGetResult", SettingsGetResult),
        "\n",
        _model_section("SettingsUpdateCommand", SettingsUpdateCommand),
        "\n",
        _model_section("SettingsUpdateResult", SettingsUpdateResult),
        "\n",
        _model_section("ProviderStatusCommand", ProviderStatusCommand),
        "\n",
        _model_section("ProviderStatusResult", ProviderStatusResult),
        "\n",
        _model_section("SkillListCommand", SkillListCommand),
        "\n",
        _model_section("SkillListResult", SkillListResult),
        "\n",
        _model_section("SkillInstallCommand", SkillInstallCommand),
        "\n",
        _model_section("SkillInstallResult", SkillInstallResult),
        "\n",
        _model_section("SkillSetEnabledCommand", SkillSetEnabledCommand),
        "\n",
        _model_section("SkillSetEnabledResult", SkillSetEnabledResult),
        "\n",
        _model_section("PluginListCommand", PluginListCommand),
        "\n",
        _model_section("PluginListResult", PluginListResult),
        "\n",
        _model_section("PluginInstallCommand", PluginInstallCommand),
        "\n",
        _model_section("PluginInstallResult", PluginInstallResult),
        "\n",
        _model_section("PluginSetEnabledCommand", PluginSetEnabledCommand),
        "\n",
        _model_section("PluginSetEnabledResult", PluginSetEnabledResult),
        "\n",
        _model_section("PluginUninstallCommand", PluginUninstallCommand),
        "\n",
        _model_section("PluginUninstallResult", PluginUninstallResult),
        "\n",
        _model_section("PluginCatalogCommand", PluginCatalogCommand),
        "\n",
        _model_section("PluginCatalogResult", PluginCatalogResult),
        "\n",
        _model_section("PluginMarketplaceAddCommand", PluginMarketplaceAddCommand),
        "\n",
        _model_section("PluginMarketplaceAddResult", PluginMarketplaceAddResult),
        "\n",
        _model_section("PluginMarketplaceRefreshCommand", PluginMarketplaceRefreshCommand),
        "\n",
        _model_section("PluginMarketplaceRefreshResult", PluginMarketplaceRefreshResult),
        "\n",
        _model_section("PluginMarketplaceRemoveCommand", PluginMarketplaceRemoveCommand),
        "\n",
        _model_section("PluginMarketplaceRemoveResult", PluginMarketplaceRemoveResult),
        "\n",
        _model_section("PluginCatalogInstallCommand", PluginCatalogInstallCommand),
        "\n",
        _model_section("PluginCatalogInstallResult", PluginCatalogInstallResult),
        "\n",
        _model_section("ProviderCcswitchListCommand", ProviderCcswitchListCommand),
        "\n",
        _model_section("ProviderCcswitchListResult", ProviderCcswitchListResult),
        "\n",
        _model_section("ProviderCcswitchApplyCommand", ProviderCcswitchApplyCommand),
        "\n",
        _model_section("ProviderCcswitchApplyResult", ProviderCcswitchApplyResult),
        "\n",
        _model_section("EventSubscribeCommand", EventSubscribeCommand, subscribe_req_example),
        "\n",
        _model_section("EventSubscribeResult", EventSubscribeResult, subscribe_resp_example),
        "\n",
        _model_section("SessionCreateCommand", SessionCreateCommand, session_create_req_example),
        "\n",
        _model_section("SessionCreateResult", SessionCreateResult, session_create_resp_example),
        "\n",
        _model_section("SessionListCommand", SessionListCommand),
        "\n",
        _model_section("SessionListResult", SessionListResult),
        "\n",
        _model_section("SessionRenameCommand", SessionRenameCommand),
        "\n",
        _model_section("SessionRenameResult", SessionRenameResult),
        "\n",
        _model_section("SessionArchiveCommand", SessionArchiveCommand),
        "\n",
        _model_section("SessionArchiveResult", SessionArchiveResult),
        "\n",
        _model_section("SessionPinCommand", SessionPinCommand),
        "\n",
        _model_section("SessionPinResult", SessionPinResult),
        "\n",
        _model_section("SessionResumeCommand", SessionResumeCommand),
        "\n",
        _model_section("SessionResumeResult", SessionResumeResult),
        "\n",
        _model_section("SessionSendMessageCommand", SessionSendMessageCommand, session_send_req_example),
        "\n",
        _model_section("SessionSendMessageResult", SessionSendMessageResult, session_send_resp_example),
        "\n",
        _model_section("SessionSteerMessageCommand", SessionSteerMessageCommand),
        "\n",
        _model_section("SessionSteerMessageResult", SessionSteerMessageResult),
        "\n",
        _model_section("UserQuestionRespondCommand", UserQuestionRespondCommand),
        "\n",
        _model_section("UserQuestionRespondResult", UserQuestionRespondResult),
        "\n",
        _model_section("UserQuestionPendingCommand", UserQuestionPendingCommand),
        "\n",
        _model_section("UserQuestionPendingResult", UserQuestionPendingResult),
        "\n",
        _model_section("SessionGetHistoryCommand", SessionGetHistoryCommand),
        "\n",
        _model_section("SessionGetHistoryResult", SessionGetHistoryResult),
        "\n",
        _model_section("SessionCloseCommand", SessionCloseCommand),
        "\n",
        _model_section("SessionCloseResult", SessionCloseResult),
        "\n## Server Push\n\n",
        "Events pushed from daemon to subscribed clients over the same TCP connection.\n\n",
        _model_section("EventPushEnvelope", EventPushEnvelope, event_push_example),
        "\n## IPC Events\n\n",
        "Events sent over the IPC socket (daemon → client).\n\n",
        _model_section("CoreStartedEvent", CoreStartedEvent),
        "\n## Run Events\n\n",
        "Events written to `runs/<run_id>/events.jsonl` and forwarded over IPC to subscribed clients.\n\n",
        _model_section("RunStartedEvent", RunStartedEvent,
            {"type": "run.started", "run_id": run_id, "goal": "总结 README.md", "ts": ts}),
        "\n",
        _model_section("RunFinishedEvent", RunFinishedEvent, {
            "type": "run.finished", "run_id": run_id,
            "status": "success", "reason": None, "steps": 2, "ts": ts}),
        "\n",
        _model_section("StepStartedEvent", StepStartedEvent,
            {"type": "step.started", "run_id": run_id, "step": 1, "ts": ts}),
        "\n",
        _model_section("StepFinishedEvent", StepFinishedEvent,
            {"type": "step.finished", "run_id": run_id, "step": 1, "ts": ts}),
        "\n",
        _model_section("ToolCallStartedEvent", ToolCallStartedEvent,
            {"type": "tool.call_started", "run_id": run_id, "tool_use_id": "toolu_01",
             "tool_name": "read_file", "params": {"path": "README.md", "description": "Read README.md"}, "ts": ts}),
        "\n",
        _model_section("ToolCallFinishedEvent", ToolCallFinishedEvent,
            {"type": "tool.call_finished", "run_id": run_id, "tool_use_id": "toolu_01",
             "tool_name": "read_file", "elapsed_ms": 3, "ts": ts}),
        "\n",
        _model_section("ToolCallFailedEvent", ToolCallFailedEvent,
            {"type": "tool.call_failed", "run_id": run_id, "tool_use_id": "toolu_02",
             "tool_name": "read_file", "error_class": "runtime_error",
             "error_message": "file not found", "elapsed_ms": 1, "attempt": 1, "ts": ts}),
        "\n",
        _model_section("LlmModelSelectedEvent", LlmModelSelectedEvent,
            {"type": "llm.model_selected", "run_id": run_id,
             "model": "configured-model", "strategy": "static", "ts": ts}),
        "\n",
        _model_section("LlmTokenEvent", LlmTokenEvent,
            {"type": "llm.token", "run_id": run_id, "token": "The ", "ts": ts}),
        "\n",
        _model_section("LlmThinkingEvent", LlmThinkingEvent,
            {"type": "llm.thinking", "run_id": run_id, "step": 1,
             "thinking": "Inspecting the workspace", "ts": ts}),
        "\n",
        _model_section("LlmUsageEvent", LlmUsageEvent,
            {"type": "llm.usage", "run_id": run_id, "input_tokens": 512, "output_tokens": 48,
             "cache_read_input_tokens": 490, "cache_creation_input_tokens": 0, "ts": ts}),
        "\n",
        _model_section("LogLineEvent", LogLineEvent,
            {"type": "log.line", "run_id": run_id, "level": "INFO",
             "source": "sztu_code.core.loop", "message": "step 1 started", "ts": ts}),
        "\n",
        _model_section("ChangeAppliedEvent", ChangeAppliedEvent,
            {"type": "change.applied", "run_id": run_id, "workspace_path": "/repo",
             "paths": ["src/example.py"], "ts": ts}),
        "\n## Multi-agent Workflow Events\n\n",
        _model_section("WorkflowStartedEvent", WorkflowStartedEvent),
        "\n",
        _model_section("WorkflowTaskUpdatedEvent", WorkflowTaskUpdatedEvent),
        "\n",
        _model_section("WorkflowHandoffEvent", WorkflowHandoffEvent),
        "\n",
        _model_section("WorkflowReviewEvent", WorkflowReviewEvent),
        "\n",
        _model_section("WorkflowFinishedEvent", WorkflowFinishedEvent),
        "\n## Session Events\n\n",
        _model_section("SessionCreatedEvent", SessionCreatedEvent,
            {"type": "session.created", "session_id": session_id, "mode": "chat", "ts": ts}),
        "\n",
        _model_section("SessionMessageReceivedEvent", SessionMessageReceivedEvent,
            {"type": "session.message_received", "session_id": session_id,
             "content": "总结 README.md", "ts": ts}),
        "\n",
        _model_section("SessionMessageSteeredEvent", SessionMessageSteeredEvent),
        "\n",
        _model_section("UserQuestionRequestedEvent", UserQuestionRequestedEvent),
        "\n",
        _model_section("UserQuestionResolvedEvent", UserQuestionResolvedEvent),
        "\n",
        _model_section("SessionWaitingForInputEvent", SessionWaitingForInputEvent,
            {"type": "session.waiting_for_input", "session_id": session_id,
             "last_run_id": run_id, "ts": ts}),
        "\n",
        _model_section("SessionResumedEvent", SessionResumedEvent,
            {"type": "session.resumed", "session_id": session_id, "ts": ts}),
        "\n",
        _model_section("SessionClosedEvent", SessionClosedEvent,
            {"type": "session.closed", "session_id": session_id, "ts": ts}),
        "\n## Error Codes\n\n",
        "| Code | Name | Meaning |\n",
        "|------|------|---------|\n",
        "| -32700 | Parse Error | Invalid JSON received |\n",
        "| -32600 | Invalid Request | Missing required JSON-RPC fields |\n",
        "| -32601 | Method Not Found | Unknown method |\n",
        "| -32602 | Invalid Params | Parameter validation failed |\n",
        "| -32603 | Internal Error | Handler raised an unhandled exception |\n",
        "| -32000 | Application Error | e.g. another run already in progress |\n",
    ]
    return "".join(sections)


# 解析命令行参数，写出或校验协议文档
def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the wire protocol reference")
    parser.add_argument("--check", action="store_true", help="Verify file matches generated output")
    parser.add_argument("--output", default=str(_OUTPUT_PATH))
    args = parser.parse_args()

    content = generate()

    if args.check:
        output_path = Path(args.output)
        if not output_path.exists():
            print(f"ERROR: {output_path} not found — run: make docs", file=sys.stderr)
            sys.exit(1)
        if output_path.read_text(encoding="utf-8") != content:
            print(f"ERROR: {output_path} out of sync with code — run: make docs", file=sys.stderr)
            sys.exit(1)
        print(f"OK: {output_path} is up to date.")
    else:
        output_path = Path(args.output)
        output_path.write_text(content, encoding="utf-8")
        print(f"Generated {output_path}")


if __name__ == "__main__":
    main()
