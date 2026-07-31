from __future__ import annotations

import pytest
from pydantic import ValidationError

from sztu_code.core.bus.commands import (
    PermissionRespondCommand,
    PingCommand,
    PongResult,
    SessionPinCommand,
    SettingsUpdateCommand,
)
from sztu_code.core.bus.events import CoreStartedEvent, LlmThinkingEvent


# 功能：验证 PingCommand 序列化后再反序列化，client 和 type 字段完整保留
# 设计：JSON 往返测试确认 wire 协议的序列化正确性，type 字段是 discriminated union 的判别键
def test_ping_command_roundtrip() -> None:
    cmd = PingCommand(client="cli/0.0.1")
    cmd2 = PingCommand.model_validate_json(cmd.model_dump_json())
    assert cmd2.client == "cli/0.0.1"
    assert cmd2.type == "core.ping"


# 功能：验证 PingCommand 的 type 字段默认值为 "core.ping"
# 设计：Literal 默认值测试，type 是 Command union 的判别键，必须与 union 定义完全一致，否则反序列化时会路由到错误类型
def test_ping_command_default_type() -> None:
    cmd = PingCommand(client="x")
    assert cmd.type == "core.ping"


# 功能：验证缺少必填 client 字段时 pydantic 校验失败
# 设计：传入空 dict 触发校验，确认 client 是必填字段，防止 daemon 收到不完整的 ping 命令进入 handler
def test_ping_command_missing_client_raises() -> None:
    with pytest.raises(ValidationError):
        PingCommand.model_validate({})


# 功能：验证 PongResult 序列化往返后所有字段完整保留
# 设计：与 PingCommand 对称，测试命令-响应对的两端序列化，确认 int 和 str 字段类型在往返中不变
def test_pong_result_roundtrip() -> None:
    pong = PongResult(server_version="0.0.1", uptime_ms=42, received_at="2026-05-11T00:00:00Z")
    pong2 = PongResult.model_validate(pong.model_dump())
    assert pong2.server_version == "0.0.1"
    assert pong2.uptime_ms == 42


# 功能：验证 CoreStartedEvent 序列化往返后 listen_addr 和 type 字段正确保留
# 设计：CoreStartedEvent 是 daemon 启动通知，往返测试确认 type 的 Literal 约束在反序列化后保持（不被字段名覆盖）
def test_core_started_event_roundtrip() -> None:
    evt = CoreStartedEvent(listen_addr="127.0.0.1:7437", version="0.0.1")
    evt2 = CoreStartedEvent.model_validate_json(evt.model_dump_json())
    assert evt2.listen_addr == "127.0.0.1:7437"
    assert evt2.type == "core.started"


# 功能：验证权限响应只接受 daemon 支持的四种决策值。
# 设计：直接以旧客户端曾发送的 approve 作为反例，确保协议边界在进入 PermissionManager 前拒绝无效决策。
def test_permission_response_rejects_legacy_decision_name() -> None:
    with pytest.raises(ValidationError):
        PermissionRespondCommand.model_validate({
            "tool_use_id": "tool-1",
            "decision": "approve",
        })


def test_settings_update_accepts_only_the_exposed_runtime_fields() -> None:
    command = SettingsUpdateCommand.model_validate(
        {"provider": "openai", "model": "gpt-4o", "permission_mode": "plan"}
    )
    assert command.type == "settings.update"
    assert command.provider == "openai"

    with pytest.raises(ValidationError):
        SettingsUpdateCommand.model_validate({"provider": "unsupported"})


def test_session_pin_command_requires_an_explicit_boolean_state() -> None:
    command = SessionPinCommand.model_validate({"session_id": "sess-1", "pinned": True})
    assert command.type == "session.pin"
    assert command.pinned is True

    with pytest.raises(ValidationError):
        SessionPinCommand.model_validate({"session_id": "sess-1"})

# 功能：验证 llm.thinking 事件可经由 wire 格式完整往返。
# 设计：思考文本会被桌面端用于增量时间线，必须保留 run、步骤与原始内容。
def test_llm_thinking_event_roundtrip() -> None:
    event = LlmThinkingEvent(
        run_id="run-1", step=2, thinking="inspect context", ts="2026-07-30T00:00:00Z"
    )
    restored = LlmThinkingEvent.model_validate_json(event.model_dump_json())
    assert restored.type == "llm.thinking"
    assert restored.run_id == "run-1"
    assert restored.step == 2
    assert restored.thinking == "inspect context"