"""SztuCode 的 Terminal-Bench (Harbor) 接入包。

- agent.py: host 端 Harbor 自定义 agent（SztuCodeAgent）
- runner.py: 容器内 runner（拉起 daemon 并走 JSON-RPC 完成任务）
"""

from eval.terminalbench.agent import SztuCodeAgent

__all__ = ["SztuCodeAgent"]
