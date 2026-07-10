from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import LlmResult, LlmStreamEvent, ModelConfig
from sealai_v2.eval.judge_pacing import PacedLlmClient


class _RecordingClient:
    def __init__(self) -> None:
        self.starts: list[float] = []
        self.active = 0
        self.max_active = 0
        self.structured_calls = 0

    async def generate(
        self, *, system: str, user: str, model_config: ModelConfig
    ) -> LlmResult:
        self.starts.append(time.monotonic())
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.005)
        self.active -= 1
        return LlmResult(text="{}", model=model_config.model)

    async def generate_stream(
        self, *, system: str, user: str, model_config: ModelConfig
    ) -> AsyncIterator[LlmStreamEvent]:
        result = await self.generate(
            system=system, user=user, model_config=model_config
        )
        yield LlmStreamEvent(result=result)

    async def generate_structured(self, **kwargs) -> LlmResult:
        self.structured_calls += 1
        return await self.generate(
            system=kwargs["system"],
            user=kwargs["user"],
            model_config=kwargs["model_config"],
        )


def test_paced_judge_serializes_and_spaces_concurrent_calls() -> None:
    async def run() -> _RecordingClient:
        inner = _RecordingClient()
        judge = PacedLlmClient(inner, max_concurrency=1, min_interval_s=0.02)
        cfg = ModelConfig("judge")
        await asyncio.gather(
            *(
                judge.generate(system="s", user=str(i), model_config=cfg)
                for i in range(3)
            )
        )
        return inner

    inner = asyncio.run(run())
    assert inner.max_active == 1
    assert len(inner.starts) == 3
    assert all(
        later - earlier >= 0.015
        for earlier, later in zip(inner.starts, inner.starts[1:])
    )


def test_eval_judge_token_reservation_is_bounded() -> None:
    settings = Settings()
    assert settings.eval_judge_max_output_tokens == 512
    assert settings.eval_judge_reasoning_effort == "low"


def test_eval_subject_pacing_defaults_are_conservative() -> None:
    settings = Settings()
    assert settings.eval_subject_concurrency == 1
    assert settings.eval_subject_min_interval_s == 3.0


def test_paced_eval_client_preserves_structured_output_path() -> None:
    inner = _RecordingClient()
    client = PacedLlmClient(inner, max_concurrency=1, min_interval_s=0.0)

    result = asyncio.run(
        client.generate_structured(
            system="S",
            user="U",
            model_config=ModelConfig("structured-model"),
            schema_name="answer",
            json_schema={"type": "object"},
        )
    )

    assert result.model == "structured-model"
    assert len(inner.starts) == 1
    assert inner.structured_calls == 1
