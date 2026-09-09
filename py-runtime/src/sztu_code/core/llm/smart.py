"""Opt-in model routing with stable choices throughout a tool execution run."""
from collections import OrderedDict
from typing import Any

from sztu_code.core.llm.base import LLMProvider


def task_requires_flagship(messages: list[dict[str, object]]) -> bool:
    # Classify user requests only; retrieved pages and tool results are not routing directives.
    texts: list[str] = []
    for message in messages:
        if message.get("role") != "user":
            continue
        content = message.get("content", "")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            texts.extend(str(block.get("text", "")) for block in content if isinstance(block, dict) and block.get("type") == "text")
    task = "\n".join(texts[-3:]).lower()
    signals = ("architecture", "migration", "security audit", "distributed", "root cause", "架构", "迁移", "安全审计", "分布式", "根因", "跨模块", "复杂", "多agent", "多个 agent")
    return len(task) > 6000 or any(signal in task for signal in signals)


class SmartProvider:
    def __init__(self, standard: LLMProvider, flagship: LLMProvider) -> None:
        self.standard = standard
        self.flagship = flagship
        self._choices: OrderedDict[str, bool] = OrderedDict()

    async def chat(self, messages: list[dict[str, object]], tool_schemas: list[dict[str, object]], bus: Any, run_id: str, **kwargs: Any) -> Any:
        # Keep tool/thinking continuations on the original model and preserve its cache prefix.
        if run_id not in self._choices:
            self._choices[run_id] = task_requires_flagship(messages)
        self._choices.move_to_end(run_id)
        selected = self.flagship if self._choices[run_id] else self.standard
        try:
            response = await selected.chat(messages, tool_schemas, bus, run_id, **kwargs)
        except BaseException:
            self._choices.pop(run_id, None)
            raise
        if response.stop_reason != "tool_use":
            self._choices.pop(run_id, None)
        return response
