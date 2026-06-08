"""Test doubles. ``FakeLlmClient`` satisfies the ``LlmClient`` Protocol without any network."""

from __future__ import annotations

from sealai_v2.core.contracts import LlmResult, ModelConfig


class FakeLlmClient:
    def __init__(self, response_text: str = "FAKE-ANSWER") -> None:
        self.response_text = response_text
        self.calls: list[dict] = []

    async def generate(
        self, *, system: str, user: str, model_config: ModelConfig
    ) -> LlmResult:
        self.calls.append({"system": system, "user": user, "model": model_config.model})
        return LlmResult(
            text=self.response_text, model=model_config.model, finish_reason="stop"
        )
