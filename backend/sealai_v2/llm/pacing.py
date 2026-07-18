"""Shared provider admission control for online LLM traffic."""

from __future__ import annotations

import asyncio
import time


class PacedLlmClient:
    """Bound concurrent calls and space starts across every role sharing a provider."""

    def __init__(
        self,
        inner,
        *,
        max_concurrency: int,
        min_interval_s: float,
    ) -> None:
        self._inner = inner
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._start_lock = asyncio.Lock()
        self._min_interval_s = max(0.0, min_interval_s)
        self._last_start = 0.0

    async def _admit(self) -> None:
        async with self._start_lock:
            remaining = self._min_interval_s - (time.monotonic() - self._last_start)
            if remaining > 0:
                await asyncio.sleep(remaining)
            self._last_start = time.monotonic()

    async def generate(self, **kwargs):
        async with self._semaphore:
            await self._admit()
            return await self._inner.generate(**kwargs)

    async def generate_structured(self, **kwargs):
        async with self._semaphore:
            await self._admit()
            return await self._inner.generate_structured(**kwargs)

    async def generate_stream(self, **kwargs):
        async with self._semaphore:
            await self._admit()
            async for event in self._inner.generate_stream(**kwargs):
                yield event
