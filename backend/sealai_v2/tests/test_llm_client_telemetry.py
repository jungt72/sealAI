"""Phase 1 (LangGraph-suitability audit) — cached_tokens extraction, cache_ratio, and safe
per-call telemetry emission tests. Verifies the telemetry structure never carries raw prompt text
and that a failing/absent sink can never break a real LLM call."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from sealai_v2.core.contracts import ModelConfig, TokenUsage
from sealai_v2.llm.client import OpenAiLlmClient, _parse_usage
from sealai_v2.llm.telemetry import LlmCallTelemetry


def _fake_usage(
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    cached_tokens: int | None,
) -> SimpleNamespace:
    details = (
        SimpleNamespace(cached_tokens=cached_tokens)
        if cached_tokens is not None
        else None
    )
    return SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        prompt_tokens_details=details,
    )


def _fake_response(
    text: str, model: str, usage: SimpleNamespace | None
) -> SimpleNamespace:
    choice = SimpleNamespace(
        message=SimpleNamespace(content=text), finish_reason="stop"
    )
    return SimpleNamespace(choices=[choice], model=model, usage=usage)


class TestParseUsageCachedTokens:
    def test_extracts_cached_tokens_when_present(self) -> None:
        resp = _fake_response(
            "hi", "gpt-5.1", _fake_usage(1000, 50, 1050, cached_tokens=400)
        )
        usage = _parse_usage(resp)
        assert usage is not None
        assert usage.cached_tokens == 400
        assert usage.prompt_tokens == 1000

    def test_missing_prompt_tokens_details_defaults_cached_to_zero(self) -> None:
        resp = _fake_response(
            "hi", "gpt-5.1", _fake_usage(1000, 50, 1050, cached_tokens=None)
        )
        usage = _parse_usage(resp)
        assert usage is not None
        assert usage.cached_tokens == 0

    def test_no_usage_at_all_returns_none(self) -> None:
        resp = _fake_response("hi", "gpt-5.1", usage=None)
        assert _parse_usage(resp) is None


class TestCacheRatio:
    def test_basic_ratio(self) -> None:
        u = TokenUsage(prompt_tokens=1000, cached_tokens=400)
        assert u.cache_ratio == pytest.approx(0.4)

    def test_zero_prompt_tokens_is_safe_zero(self) -> None:
        u = TokenUsage(prompt_tokens=0, cached_tokens=0)
        assert u.cache_ratio == 0.0

    def test_default_cached_tokens_is_zero(self) -> None:
        u = TokenUsage(prompt_tokens=500)
        assert u.cached_tokens == 0
        assert u.cache_ratio == 0.0


class _FakeAsyncOpenAI:
    """Minimal stand-in for the AsyncOpenAI client's chat.completions.create surface."""

    def __init__(self, response: SimpleNamespace) -> None:
        self._response = response
        self.calls: list[dict] = []

        class _Completions:
            def __init__(self, outer: "_FakeAsyncOpenAI") -> None:
                self._outer = outer

            async def create(self, **kwargs):
                self._outer.calls.append(kwargs)
                return self._outer._response

        class _Chat:
            def __init__(self, outer: "_FakeAsyncOpenAI") -> None:
                self.completions = _Completions(outer)

        self.chat = _Chat(self)


class _SpySink:
    def __init__(self) -> None:
        self.events: list[LlmCallTelemetry] = []

    def record(self, event: LlmCallTelemetry) -> None:
        self.events.append(event)


class _RaisingSink:
    def record(self, event: LlmCallTelemetry) -> None:
        raise RuntimeError("sink boom")


def test_telemetry_emitted_on_success_with_safe_fields_only() -> None:
    resp = _fake_response(
        "the answer", "gpt-5.1", _fake_usage(1000, 50, 1050, cached_tokens=400)
    )
    inner = _FakeAsyncOpenAI(resp)
    sink = _SpySink()
    client = OpenAiLlmClient(inner, provider="mistral", telemetry_sink=sink)
    cfg = ModelConfig(
        model="gpt-5.1", cache_key="sealai:global:l1:gpt-5.1:abc123", stage="l1"
    )

    result = asyncio.run(
        client.generate(
            system="STATIC DOCTRINE", user="raw user question", model_config=cfg
        )
    )

    assert result.text == "the answer"
    assert len(sink.events) == 1
    ev = sink.events[0]
    assert ev.provider == "mistral"
    assert ev.model == "gpt-5.1"
    assert ev.stage == "l1"
    assert ev.prompt_cache_key == "sealai:global:l1:gpt-5.1:abc123"
    assert ev.prompt_tokens == 1000
    assert ev.cached_tokens == 400
    assert ev.cache_ratio == pytest.approx(0.4)
    assert ev.status == "ok"
    assert ev.error_type is None
    assert ev.latency_ms >= 0

    # No raw content anywhere on the telemetry event.
    dumped = repr(ev)
    assert "STATIC DOCTRINE" not in dumped
    assert "raw user question" not in dumped
    assert "the answer" not in dumped
    assert not hasattr(ev, "prompt")
    assert not hasattr(ev, "messages")


def test_no_sink_is_fully_inert() -> None:
    resp = _fake_response("ok", "gpt-5.1", _fake_usage(10, 5, 15, cached_tokens=0))
    client = OpenAiLlmClient(_FakeAsyncOpenAI(resp))  # no telemetry_sink → default None
    result = asyncio.run(
        client.generate(system="s", user="u", model_config=ModelConfig(model="gpt-5.1"))
    )
    assert result.text == "ok"  # behaves exactly as before Phase 1


def test_a_raising_sink_never_breaks_the_real_call() -> None:
    resp = _fake_response("ok", "gpt-5.1", _fake_usage(10, 5, 15, cached_tokens=0))
    client = OpenAiLlmClient(_FakeAsyncOpenAI(resp), telemetry_sink=_RaisingSink())
    result = asyncio.run(
        client.generate(system="s", user="u", model_config=ModelConfig(model="gpt-5.1"))
    )
    assert (
        result.text == "ok"
    )  # telemetry sink raised internally — the real call still succeeded


def test_telemetry_emitted_on_error_path() -> None:
    class _AlwaysFails:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs):
                    raise RuntimeError("transient upstream failure")

    sink = _SpySink()
    client = OpenAiLlmClient(
        _AlwaysFails(), provider="openai", max_retries=1, telemetry_sink=sink
    )
    with pytest.raises(RuntimeError):
        asyncio.run(
            client.generate(
                system="s",
                user="u",
                model_config=ModelConfig(model="gpt-5.1", stage="l1"),
            )
        )

    assert len(sink.events) == 1
    ev = sink.events[0]
    assert ev.status == "error"
    assert ev.error_type == "RuntimeError"
    assert ev.prompt_tokens == 0
    assert ev.cached_tokens == 0
