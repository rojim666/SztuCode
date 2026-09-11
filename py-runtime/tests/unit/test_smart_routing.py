import asyncio

from sztu_code.core.llm.smart import SmartProvider, task_requires_flagship
from sztu_code.core.llm.types import LlmResponse


def test_complexity_uses_requests_not_tool_payloads() -> None:
    assert task_requires_flagship([{"role": "user", "content": "审查跨模块架构"}])
    assert not task_requires_flagship([{"role": "user", "content": "改一下标题"}, {"role": "tool", "content": "architecture security audit"}])


def test_routing_is_stable_during_tools_and_releases_finished_runs() -> None:
    class Fake:
        def __init__(self) -> None:
            self.calls = 0
        async def chat(self, *args, **kwargs):
            self.calls += 1
            return LlmResponse(stop_reason="tool_use" if self.calls == 1 else "end_turn")
    standard, flagship = Fake(), Fake()
    provider = SmartProvider(standard, flagship)
    async def run():
        await provider.chat([{"role": "user", "content": "标题修改"}], [], None, "r")
        await provider.chat([{"role": "user", "content": "architecture"}], [], None, "r")
        assert standard.calls == 2 and flagship.calls == 0
        assert not provider._choices
        await provider.chat([{"role": "user", "content": "architecture"}], [], None, "r2")
        assert flagship.calls == 1
    asyncio.run(run())
