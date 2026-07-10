from __future__ import annotations

import asyncio
import time

from sealai_v2.core.contracts import LlmResult, LlmStreamEvent, ModelConfig
from sealai_v2.llm.pacing import PacedLlmClient


class _Inner:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.starts: list[float] = []

    async def generate(self, **kwargs):
        self.starts.append(time.monotonic())
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.005)
        self.active -= 1
        return LlmResult(text="ok", model=kwargs["model_config"].model)

    async def generate_structured(self, **kwargs):
        return await self.generate(**kwargs)

    async def generate_stream(self, **kwargs):
        self.starts.append(time.monotonic())
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.005)
        yield LlmStreamEvent(result=LlmResult(text="ok", model="m"))
        self.active -= 1


def test_shared_client_bounds_concurrency_and_spaces_call_starts():
    async def run():
        inner = _Inner()
        client = PacedLlmClient(inner, max_concurrency=1, min_interval_s=0.01)
        cfg = ModelConfig("m")
        await asyncio.gather(
            *(client.generate(system="s", user="u", model_config=cfg) for _ in range(3))
        )
        return inner

    inner = asyncio.run(run())
    assert inner.max_active == 1
    assert len(inner.starts) == 3
    assert all(b - a >= 0.009 for a, b in zip(inner.starts, inner.starts[1:]))


def test_stream_holds_the_same_admission_slot_until_terminal_event():
    async def run():
        inner = _Inner()
        client = PacedLlmClient(inner, max_concurrency=1, min_interval_s=0)
        cfg = ModelConfig("m")

        async def consume():
            return [
                event
                async for event in client.generate_stream(
                    system="s", user="u", model_config=cfg
                )
            ]

        stream_events, result = await asyncio.gather(
            consume(), client.generate(system="s", user="u", model_config=cfg)
        )
        return inner, stream_events, result

    inner, events, result = asyncio.run(run())
    assert inner.max_active == 1
    assert events[-1].result.text == "ok"
    assert result.text == "ok"
