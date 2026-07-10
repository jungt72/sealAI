"""Phase 3A (live token streaming) — OpenAiLlmClient.generate_stream unit tests.

Verifies the delta/terminal contract, that the SAME request construction as generate() is used
(model/system+user/prompt_cache_key via extra_body/stream flags), usage parsing from the final
include_usage chunk, the FIRST-attempt-only prompt_cache_key defensive unwind, and that a mid-stream
failure propagates as a failed call with NO synthetic terminal event. No real network anywhere."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from sealai_v2.core.contracts import LlmStreamEvent, ModelConfig
from sealai_v2.llm.client import OpenAiLlmClient
from sealai_v2.llm.telemetry import LlmCallTelemetry


def _delta_chunk(content: str | None, *, model: str = "fake-smalltalk", finish=None):
    choice = SimpleNamespace(
        index=0, delta=SimpleNamespace(content=content), finish_reason=finish
    )
    return SimpleNamespace(choices=[choice], model=model, usage=None)


def _usage_chunk(
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    cached_tokens: int,
    *,
    model: str = "fake-smalltalk",
):
    usage = SimpleNamespace(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        prompt_tokens_details=SimpleNamespace(cached_tokens=cached_tokens),
    )
    # the final include_usage chunk carries usage with EMPTY choices
    return SimpleNamespace(choices=[], model=model, usage=usage)


class _FakeStream:
    """An async iterator over pre-scripted chunks (stands in for openai's AsyncStream)."""

    def __init__(self, chunks: list) -> None:
        self._chunks = list(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


class _StreamingFakeOpenAI:
    """Minimal stand-in for AsyncOpenAI.chat.completions.create(stream=True). Records every call's
    kwargs; returns a fresh _FakeStream from ``chunks`` (or a factory keyed on attempt count)."""

    def __init__(self, chunks=None, *, factory=None) -> None:
        self._chunks = chunks
        self._factory = factory
        self.calls: list[dict] = []

        class _Completions:
            def __init__(self, outer: "_StreamingFakeOpenAI") -> None:
                self._outer = outer

            async def create(self, **kwargs):
                self._outer.calls.append(kwargs)
                if self._outer._factory is not None:
                    return self._outer._factory(len(self._outer.calls), kwargs)
                return _FakeStream(list(self._outer._chunks))

        class _Chat:
            def __init__(self, outer: "_StreamingFakeOpenAI") -> None:
                self.completions = _Completions(outer)

        self.chat = _Chat(self)


class _SpySink:
    def __init__(self) -> None:
        self.events: list[LlmCallTelemetry] = []

    def record(self, event: LlmCallTelemetry) -> None:
        self.events.append(event)


async def _collect(client, **kw) -> list[LlmStreamEvent]:
    out: list[LlmStreamEvent] = []
    async for ev in client.generate_stream(**kw):
        out.append(ev)
    return out


def test_streams_deltas_then_one_terminal_result_with_usage() -> None:
    chunks = [
        _delta_chunk("Hal"),
        _delta_chunk("lo"),
        _delta_chunk("!", finish="stop"),
        _usage_chunk(120, 8, 128, cached_tokens=40),
    ]
    inner = _StreamingFakeOpenAI(chunks)
    client = OpenAiLlmClient(inner, provider="mistral")
    cfg = ModelConfig(model="fake-smalltalk", cache_key="sealai:smalltalk:key")

    events = asyncio.run(_collect(client, system="STATIC", user="hi", model_config=cfg))

    deltas = [e.delta for e in events if e.delta is not None]
    terminals = [e.result for e in events if e.result is not None]
    assert deltas == ["Hal", "lo", "!"]
    assert len(terminals) == 1
    assert events[-1].result is not None  # terminal is LAST
    final = terminals[0]
    assert final.text == "Hallo!"
    assert final.finish_reason == "stop"
    assert final.usage is not None
    assert final.usage.prompt_tokens == 120
    assert final.usage.cached_tokens == 40


def test_prompt_cache_key_passed_via_extra_body_and_stream_flags_on_create() -> None:
    inner = _StreamingFakeOpenAI([_delta_chunk("x", finish="stop")])
    client = OpenAiLlmClient(inner)
    cfg = ModelConfig(model="fake-smalltalk", cache_key="sealai:smalltalk:abc")
    asyncio.run(_collect(client, system="S", user="U", model_config=cfg))
    assert len(inner.calls) == 1
    call = inner.calls[0]
    assert call["model"] == "fake-smalltalk"
    assert call["stream"] is True
    assert call["stream_options"] == {"include_usage": True}
    assert call["extra_body"] == {"prompt_cache_key": "sealai:smalltalk:abc"}
    assert call["messages"][0] == {"role": "system", "content": "S"}
    assert call["messages"][1] == {"role": "user", "content": "U"}


def test_reasoning_effort_is_forwarded_provider_natively() -> None:
    inner = _StreamingFakeOpenAI([_delta_chunk("x", finish="stop")])
    client = OpenAiLlmClient(inner)
    cfg = ModelConfig(model="mistral-small-2603", reasoning_effort="high")
    asyncio.run(_collect(client, system="S", user="U", model_config=cfg))
    assert inner.calls[0]["reasoning_effort"] == "high"


def test_prompt_cache_key_rejection_unwinds_once_before_any_delta() -> None:
    # First create() raises a prompt_cache_key rejection BEFORE yielding anything; the client must
    # strip extra_body and retry the stream from scratch (safe: no token has crossed the wire yet).
    def factory(attempt: int, kwargs: dict):
        if attempt == 1:
            assert "extra_body" in kwargs
            raise ValueError("Unsupported parameter: 'prompt_cache_key'")
        assert "extra_body" not in kwargs  # retry stripped it
        return _FakeStream([_delta_chunk("ok", finish="stop")])

    inner = _StreamingFakeOpenAI(factory=factory)
    client = OpenAiLlmClient(inner)
    cfg = ModelConfig(model="fake-smalltalk", cache_key="sealai:smalltalk:abc")
    events = asyncio.run(_collect(client, system="S", user="U", model_config=cfg))
    assert len(inner.calls) == 2  # one rejected, one clean retry
    assert [e.delta for e in events if e.delta is not None] == ["ok"]
    assert events[-1].result is not None
    assert events[-1].result.text == "ok"


def test_mid_stream_failure_propagates_with_no_synthetic_terminal() -> None:
    # A failure AFTER the first delta has been yielded must propagate (a partial stream is a failed
    # call) — no terminal LlmStreamEvent(result=...) is ever synthesized, and it is NOT retried.
    class _BoomStream:
        def __init__(self) -> None:
            self._first = True

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._first:
                self._first = False
                return _delta_chunk("par")
            raise RuntimeError("SENTINEL-MIDSTREAM-BOOM")

    class _Inner:
        def __init__(self) -> None:
            self.calls = 0

            class _C:
                async def create(_self, **kwargs):
                    self.calls += 1
                    return _BoomStream()

            self.chat = SimpleNamespace(completions=_C())

    inner = _Inner()
    sink = _SpySink()
    client = OpenAiLlmClient(inner, provider="openai", telemetry_sink=sink)
    cfg = ModelConfig(model="fake-smalltalk", stage="smalltalk_navigation")

    seen: list[LlmStreamEvent] = []

    async def driver():
        async for ev in client.generate_stream(system="S", user="U", model_config=cfg):
            seen.append(ev)

    with pytest.raises(RuntimeError, match="SENTINEL-MIDSTREAM-BOOM"):
        asyncio.run(driver())

    assert seen == [LlmStreamEvent(delta="par")]  # only the delta before the boom
    assert not [e for e in seen if e.result is not None]  # NO synthetic terminal
    assert inner.calls == 1  # not retried after a token was already streamed
    # error telemetry emitted exactly once, with no raw content on it
    assert len(sink.events) == 1
    assert sink.events[0].status == "error"
    assert sink.events[0].error_type == "RuntimeError"
    dumped = repr(sink.events[0])
    assert "SENTINEL-MIDSTREAM-BOOM" not in dumped
    assert "par" not in dumped
