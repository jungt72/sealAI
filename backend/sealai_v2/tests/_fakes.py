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


class DistillRoutingFakeLlmClient:
    """Routes by the system prompt: a memory-distill call (its prompt opens with "extrahierst
    strukturierte Fakten") returns a fixed facts-JSON; any other call returns a fixed prose answer.
    Lets ONE fake drive the full chat path (L1 answer + background distill) in a pipeline run."""

    _DISTILL_MARKER = "extrahierst strukturierte Fakten"

    def __init__(self, distill_json: str, answer: str = "ok") -> None:
        self.distill_json = distill_json
        self.answer = answer
        self.calls: list[dict] = []

    async def generate(
        self, *, system: str, user: str, model_config: ModelConfig
    ) -> LlmResult:
        self.calls.append({"system": system, "user": user, "model": model_config.model})
        text = self.distill_json if self._DISTILL_MARKER in system else self.answer
        return LlmResult(
            text=text, model=model_config.model, finish_reason="stop"
        )


class ScriptedFakeLlmClient:
    """Returns a fixed SEQUENCE of responses across successive ``generate`` calls — e.g. the
    L1 draft, then the L3 verdict, then a regeneration, then the re-verify. Records every call;
    raises if the script is exhausted (so an unexpected extra LLM call is caught, not masked)."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []
        self._i = 0

    async def generate(
        self, *, system: str, user: str, model_config: ModelConfig
    ) -> LlmResult:
        self.calls.append({"system": system, "user": user, "model": model_config.model})
        if self._i >= len(self.responses):
            raise AssertionError(
                "ScriptedFakeLlmClient: more LLM calls than scripted responses"
            )
        text = self.responses[self._i]
        self._i += 1
        return LlmResult(text=text, model=model_config.model, finish_reason="stop")
