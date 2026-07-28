from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path


# 发送一条 JSON-RPC 请求并返回响应对象
async def _send_recv(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    method: str,
    params: dict,
    req_id: str = "1",
) -> dict:
    req = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
    writer.write((json.dumps(req) + "\n").encode())
    await writer.drain()
    line = await asyncio.wait_for(reader.readline(), timeout=5.0)
    return json.loads(line)


# 功能：验证 daemon 提供创建、列表、重命名、归档、恢复和读取历史的 session IPC 闭环。
# 设计：不触发 session.send_message，避免真实 LLM 依赖；在同一 TCP 连接串联产品协议，验证 handler 注册、持久化状态与返回摘要一致。
async def test_session_create_history_close_over_ipc(
    running_daemon: subprocess.Popen[bytes],
    free_port: int,
    tmp_path: Path,
) -> None:
    reader, writer = await asyncio.open_connection("127.0.0.1", free_port)
    project = tmp_path / "session-workspace"
    project.mkdir()
    opened = await _send_recv(
        reader,
        writer,
        "workspace.open",
        {"path": str(project)},
        req_id="open-session-workspace",
    )
    workspace_id = opened["result"]["workspace"]["workspace_id"]

    created = await _send_recv(
        reader,
        writer,
        "session.create",
        {"mode": "chat", "title": "ipc test", "workspace_id": workspace_id},
        req_id="create",
    )
    assert "result" in created, created
    session_id = created["result"]["session_id"]
    assert created["result"]["status"] == "active"

    listed = await _send_recv(
        reader,
        writer,
        "session.list",
        {"limit": 50},
        req_id="list",
    )
    summary = next(
        session for session in listed["result"]["sessions"]
        if session["session_id"] == session_id
    )
    assert summary["title"] == "ipc test"
    assert summary["archived"] is False
    assert summary["workspace_id"] == workspace_id

    renamed = await _send_recv(
        reader,
        writer,
        "session.rename",
        {"session_id": session_id, "title": "renamed task"},
        req_id="rename",
    )
    assert renamed["result"]["session"]["title"] == "renamed task"

    archived = await _send_recv(
        reader,
        writer,
        "session.archive",
        {"session_id": session_id},
        req_id="archive",
    )
    assert archived["result"]["session"]["archived"] is True

    resumed = await _send_recv(
        reader,
        writer,
        "session.resume",
        {"session_id": session_id},
        req_id="resume",
    )
    assert resumed["result"]["session"]["archived"] is False
    assert resumed["result"]["session"]["status"] == "waiting_for_input"

    history = await _send_recv(
        reader,
        writer,
        "session.get_history",
        {"session_id": session_id},
        req_id="history",
    )
    assert history["result"]["messages"] == []

    closed = await _send_recv(
        reader,
        writer,
        "session.close",
        {"session_id": session_id},
        req_id="close",
    )
    assert closed["result"]["status"] == "closed"

    writer.close()
    await writer.wait_closed()


# 功能：验证 daemon 通过 IPC 打开工作区后可列出文件树、搜索文本并读取指定文件。
# 设计：使用测试专属临时目录而非仓库本身，串联 workspace.open/tree、file.search/read 四个端点，并确认结果不依赖 Git 或真实模型。
async def test_workspace_file_commands_over_ipc(
    running_daemon: subprocess.Popen[bytes],
    free_port: int,
    tmp_path: Path,
) -> None:
    project = tmp_path / "workspace"
    project.mkdir()
    (project / "hello.py").write_text("def greet():\n    return 'hello'\n", encoding="utf-8")

    reader, writer = await asyncio.open_connection("127.0.0.1", free_port)
    opened = await _send_recv(
        reader,
        writer,
        "workspace.open",
        {"path": str(project)},
        req_id="open-workspace",
    )
    workspace = opened["result"]["workspace"]
    workspace_id = workspace["workspace_id"]
    assert workspace["name"] == "workspace"

    tree = await _send_recv(
        reader,
        writer,
        "workspace.tree",
        {"workspace_id": workspace_id},
        req_id="tree",
    )
    assert tree["result"]["nodes"][0]["path"] == "hello.py"

    search = await _send_recv(
        reader,
        writer,
        "file.search",
        {"workspace_id": workspace_id, "query": "greet"},
        req_id="search",
    )
    assert search["result"]["matches"][0]["path"] == "hello.py"

    read = await _send_recv(
        reader,
        writer,
        "file.read",
        {"workspace_id": workspace_id, "path": "hello.py"},
        req_id="read",
    )
    assert "def greet" in read["result"]["content"]

    writer.close()
    await writer.wait_closed()
