"""Rate-aware wrapper for eval-only LLM clients.

The replay sends many independent cases to the subject pipeline concurrently. The external judge
must not inherit that burst. This wrapper paces every request for the subject and the separate
judge client, including multi-turn re-ask checks, while leaving serving concurrency unchanged.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from sealai_v2.core.contracts import LlmClient, LlmResult, LlmStreamEvent, ModelConfig


class PacedLlmClient:
    """Bound concurrent judge calls and reserve a minimum interval between their starts."""

    def __init__(
        self,
        inner: LlmClient,
        *,
        max_concurrency: int = 1,
        min_interval_s: float = 3.0,
    ) -> None:
        self._inner = inner
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._schedule_lock = asyncio.Lock()
        self._min_interval_s = max(0.0, min_interval_s)
        self._next_start = 0.0

    async def _wait_for_turn(self) -> None:
        async with self._schedule_lock:
            now = time.monotonic()
            start_at = max(now, self._next_start)
            self._next_start = start_at + self._min_interval_s
        delay = start_at - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)

    async def generate(
        self, *, system: str, user: str, model_config: ModelConfig
    ) -> LlmResult:
        async with self._semaphore:
            await self._wait_for_turn()
            return await self._inner.generate(
                system=system, user=user, model_config=model_config
            )

    async def generate_structured(
        self,
        *,
        system: str,
        user: str,
        model_config: ModelConfig,
        schema_name: str,
        json_schema: dict,
    ) -> LlmResult:
        async with self._semaphore:
            await self._wait_for_turn()
            native = getattr(self._inner, "generate_structured", None)
            if native is None:
                return await self._inner.generate(
                    system=system, user=user, model_config=model_config
                )
            return await native(
                system=system,
                user=user,
                model_config=model_config,
                schema_name=schema_name,
                json_schema=json_schema,
            )

    async def generate_stream(
        self, *, system: str, user: str, model_config: ModelConfig
    ) -> AsyncIterator[LlmStreamEvent]:
        async with self._semaphore:
            await self._wait_for_turn()
            async for event in self._inner.generate_stream(
                system=system, user=user, model_config=model_config
            ):
                yield event
