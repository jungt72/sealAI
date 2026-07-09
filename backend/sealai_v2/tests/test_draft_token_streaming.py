"""Phase 3B (draft-token streaming) -- draft-only preview streaming for the FULL L1 engineering
generator (``core.l1_generator.L1Generator``), for EVERY route that uses it (engineering_case,
leakage_troubleshooting, rfq_manufacturer_brief, material_comparison, general_sealing_knowledge,
material_knowledge -- every route except smalltalk_navigation, which keeps its own independent
Phase 3A path, see test_smalltalk_token_streaming.py, completely unchanged).

Flag OFF by default (``SEALAI_V2_DRAFT_TOKEN_STREAMING_ENABLED`` / ``draft_token_streaming_enabled``).
Additive to test_output_guard_wiring.py (the regenerate-on-BLOCK flow this reuses verbatim, unchanged)
and test_stream_trace_hide_gate.py (the LangSmith hide-gate, extended there for this path). Proves:

- L1Generator.generate_stream is output-equivalent to generate() for the same completion (items 1, 8);
- deltas fire via the token sink DURING generation; the terminal event's answer is never itself sent
  through the sink -- draft and final are structurally distinct return paths (item 2);
- strip_sourcing is applied to the FULL accumulated text ONCE -- raw deltas are never stripped or
  mangled (item 3);
- representative non-smalltalk routes (an engineering-shaped and a knowledge-shaped turn) stream
  draft=true tokens with the flag on, but the eventual `result` is byte-identical to the non-streaming
  path for the same script (item 4);
- the regenerate-after-guard-BLOCK path streams draft tokens for BOTH attempts, with the EXISTING
  stage=regenerate progress event marking the reset point between them, and still ships the
  regenerated (corrected) answer exactly as before this PR (item 5);
- flag OFF (default), even with a token sink wired, is byte-identical to pre-Phase-3B: zero draft
  events, non-streaming generate() is used (item 6 -- the hard merge gate);
- flag ON but no sink wired is ALSO byte-identical (no sink -> draft_stream_active is False);
- a mid-stream failure propagates as a real error -- no partial/synthetic Answer is ever produced
  (item 8);
- draft token frames (SSE wire shape) carry only {"text": ..., "draft": ...} -- nothing else, no
  ids/tenant/case/PII (item 10).
"""

from __future__ import annotations

import asyncio
import json

import pytest

from sealai_v2.core.contracts import (
    Flags,
    GroundingFact,
    LlmResult,
    LlmStreamEvent,
    ModelConfig,
)
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.knowledge.matrix import InProcessCompatibilityMatrix
from sealai_v2.memory.store import (
    InProcessConversationMemory,
    InProcessCrossSessionMemory,
)
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._apiutil import auth, make_client

_T = TenantContext("phase-3b-tenant")


# ── items 1 / 2 / 3 / 8: L1Generator.generate_stream unit-level contract ------------------------


class _DeltaScriptClient:
    """Minimal LlmClient double: generate() returns a fixed LlmResult; generate_stream() yields the
    SAME text as caller-supplied raw deltas + one terminal LlmStreamEvent(result=...). Lets a test
    assert deltas fire exactly as scripted and the terminal Answer matches generate()'s output for
    the same completion."""

    def __init__(self, text: str, *, deltas: tuple[str, ...] | None = None) -> None:
        self.text = text
        self.deltas = deltas if deltas is not None else (text,)

    async def generate(
        self, *, system: str, user: str, model_config: ModelConfig
    ) -> LlmResult:
        return LlmResult(text=self.text, model=model_config.model, finish_reason="stop")

    async def generate_stream(
        self, *, system: str, user: str, model_config: ModelConfig
    ):
        for d in self.deltas:
            yield LlmStreamEvent(delta=d)
        yield LlmStreamEvent(
            result=LlmResult(
                text=self.text, model=model_config.model, finish_reason="stop"
            )
        )


class _RaisingStreamClient:
    """generate_stream yields a couple of deltas then raises -- NO terminal result event, mirroring
    LlmStreamEvent's documented failure contract (a failed stream is a failed call; no partial/
    synthetic Answer is ever produced)."""

    def __init__(self, deltas: tuple[str, ...]) -> None:
        self.deltas = deltas

    async def generate(
        self, *, system, user, model_config
    ):  # pragma: no cover - unused here
        raise AssertionError("generate() should not be called in this test")

    async def generate_stream(self, *, system, user, model_config):
        for d in self.deltas:
            yield LlmStreamEvent(delta=d)
        raise RuntimeError("simulated mid-stream provider failure")


def _gen(client) -> L1Generator:
    return L1Generator(client, PromptAssembler(), ModelConfig("fake-l1"))


async def _collect_stream(gen: L1Generator, question: str, **kwargs):
    deltas: list[str] = []
    answer = None
    async for ev in gen.generate_stream(question, **kwargs):
        if ev.delta is not None:
            deltas.append(ev.delta)
        elif ev.answer is not None:
            answer = ev.answer
    return deltas, answer


def test_generate_stream_is_output_equivalent_to_generate_for_the_same_completion():
    text = "RWDR 45x62x8 mit FKM ist für diese Kombination geeignet."
    deltas = ("RWDR 45x62x8 ", "mit FKM ist ", "für diese Kombination geeignet.")
    facts = (GroundingFact(text="Fact.", quelle="Q", card_id="C-1", kind="card"),)

    streamed_deltas, streamed_answer = asyncio.run(
        _collect_stream(
            _gen(_DeltaScriptClient(text, deltas=deltas)),
            "Frage?",
            flags=Flags(),
            grounding_facts=facts,
        )
    )
    plain_answer = asyncio.run(
        _gen(_DeltaScriptClient(text)).generate(
            "Frage?", flags=Flags(), grounding_facts=facts
        )
    )

    assert streamed_deltas == list(deltas)
    assert streamed_answer is not None
    assert streamed_answer.text == plain_answer.text
    assert streamed_answer.model == plain_answer.model
    assert streamed_answer.finish_reason == plain_answer.finish_reason
    assert streamed_answer.grounding_facts == plain_answer.grounding_facts == facts


def test_deltas_are_a_structurally_separate_channel_from_the_terminal_answer():
    client = _DeltaScriptClient("Antwort.", deltas=("Ant", "wort."))
    deltas, answer = asyncio.run(_collect_stream(_gen(client), "Frage?", flags=Flags()))
    assert deltas == ["Ant", "wort."]
    assert answer is not None and answer.text == "Antwort."
    # the terminal answer never itself arrives as one of the delta events -- a distinct return path
    assert answer.text not in deltas


def test_strip_sourcing_applies_once_to_the_full_text_never_per_delta():
    raw = "Normaler Satz. Bitte fordern Sie ein Angebot bei Hersteller X an."
    # the sourcing sentence is fully contained in delta 2 -- so a (hypothetical, wrong) per-delta
    # strip would ALSO catch it there; this proves the RAW delta is never touched regardless, only
    # the FINAL accumulated text is.
    d1, d2 = "Normaler Satz. ", "Bitte fordern Sie ein Angebot bei Hersteller X an."
    client = _DeltaScriptClient(raw, deltas=(d1, d2))
    deltas, answer = asyncio.run(_collect_stream(_gen(client), "Frage?", flags=Flags()))
    assert deltas == [d1, d2]  # RAW, unstripped
    assert answer is not None
    assert (
        answer.text == "Normaler Satz."
    )  # the FULL accumulated text was stripped exactly once
    assert "Angebot" not in answer.text
    assert "Angebot" in deltas[1]  # the raw delta itself was never touched


def test_mid_stream_failure_propagates_no_partial_answer():
    client = _RaisingStreamClient(("Teil-satz ", "noch mehr Text"))
    gen = _gen(client)

    async def _run():
        seen = []
        async for ev in gen.generate_stream("Frage?", flags=Flags()):
            seen.append(ev)
        return seen

    with pytest.raises(RuntimeError):
        asyncio.run(_run())


# ── items 4 / 5 / 6 / 10: Pipeline-level wiring --------------------------------------------------


class _PipelineStreamClient:
    """A scripted LlmClient for full Pipeline runs: each successive .generate()/.generate_stream()
    call (whichever pipeline.py takes, per the draft-streaming flag) consumes the NEXT scripted
    response, in order -- so the SAME script drives a streaming and a non-streaming run identically,
    letting a test assert their results are byte-identical. Deltas for a scripted response default to
    a single delta equal to the whole text; override via `deltas_for`. Records calls separately per
    method so a test can prove which path pipeline.py actually took."""

    def __init__(
        self,
        responses: list[str],
        *,
        deltas_for: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.responses = list(responses)
        self._i = 0
        self._deltas_for = deltas_for or {}
        self.calls: list[dict] = []
        self.stream_calls: list[dict] = []

    def _next(self) -> str:
        if self._i >= len(self.responses):
            raise AssertionError(
                "script exhausted -- more LLM calls than scripted responses"
            )
        text = self.responses[self._i]
        self._i += 1
        return text

    async def generate(
        self, *, system: str, user: str, model_config: ModelConfig
    ) -> LlmResult:
        text = self._next()
        self.calls.append({"system": system, "user": user, "model": model_config.model})
        return LlmResult(text=text, model=model_config.model, finish_reason="stop")

    async def generate_stream(
        self, *, system: str, user: str, model_config: ModelConfig
    ):
        text = self._next()
        self.stream_calls.append(
            {"system": system, "user": user, "model": model_config.model}
        )
        for d in self._deltas_for.get(text, (text,)):
            yield LlmStreamEvent(delta=d)
        yield LlmStreamEvent(
            result=LlmResult(text=text, model=model_config.model, finish_reason="stop")
        )


class _TokenSinkSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def __call__(self, delta: str, draft: bool) -> None:
        self.calls.append((delta, draft))


class _OrderedEventLog:
    """Records token + progress events in the ONE true call order, so a test can assert the exact
    interleaving: first attempt's draft tokens, THEN the regenerate stage-start, THEN the second
    attempt's draft tokens."""

    def __init__(self) -> None:
        self.events: list[tuple[str, tuple]] = []

    def token(self, delta: str, draft: bool) -> None:
        self.events.append(("token", (delta, draft)))

    def progress(self, stage: str, status: str) -> None:
        self.events.append(("stage", (stage, status)))


def _plain_pipeline(client, *, draft_streaming: bool) -> Pipeline:
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        retriever=None,
        matrix=InProcessCompatibilityMatrix(),
        draft_token_streaming_enabled=draft_streaming,
    )


def _guard_pipeline(client, *, draft_streaming: bool) -> Pipeline:
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        retriever=None,
        matrix=InProcessCompatibilityMatrix(),
        response_contract_enabled=True,
        draft_token_streaming_enabled=draft_streaming,
    )


def _run(p: Pipeline, question: str, *, token_sink=None, progress=None):
    return asyncio.run(
        p.run(
            question, tenant=_T, flags=Flags(), token_sink=token_sink, progress=progress
        )
    )


_ENGINEERING_ANSWER = "RWDR 45x62x8 mit FKM: geeignet für Hydrauliköl bis 100 °C."
_ENGINEERING_DELTAS = ("RWDR 45x62x8 mit FKM: ", "geeignet für Hydrauliköl bis 100 °C.")
_KNOWLEDGE_ANSWER = (
    "FKM ist ein fluoriertes Elastomer mit hoher Öl- und Temperaturbeständigkeit."
)
_KNOWLEDGE_DELTAS = (
    "FKM ist ein fluoriertes Elastomer ",
    "mit hoher Öl- und Temperaturbeständigkeit.",
)


def test_engineering_route_streams_draft_tokens_but_result_is_unchanged():
    question = "RWDR 45x62x8, welches Material bei Hydrauliköl 100 °C?"

    streamed_client = _PipelineStreamClient(
        [_ENGINEERING_ANSWER], deltas_for={_ENGINEERING_ANSWER: _ENGINEERING_DELTAS}
    )
    sink = _TokenSinkSpy()
    streamed = _run(
        _plain_pipeline(streamed_client, draft_streaming=True),
        question,
        token_sink=sink,
    )

    assert (
        streamed_client.stream_calls and not streamed_client.calls
    )  # generate_stream path taken
    assert [c[0] for c in sink.calls] == list(_ENGINEERING_DELTAS)
    assert all(
        draft is True for _, draft in sink.calls
    )  # every Phase 3B token is draft=true
    assert "".join(c[0] for c in sink.calls) == _ENGINEERING_ANSWER

    plain_client = _PipelineStreamClient([_ENGINEERING_ANSWER])
    plain = _run(_plain_pipeline(plain_client, draft_streaming=False), question)
    assert (
        plain_client.calls and not plain_client.stream_calls
    )  # non-streaming generate() taken

    assert streamed.answer.text == plain.answer.text == _ENGINEERING_ANSWER
    assert streamed.answer.model == plain.answer.model
    assert streamed.answer.finish_reason == plain.answer.finish_reason
    assert streamed.guard == plain.guard


def test_knowledge_route_streams_draft_tokens_but_result_is_unchanged():
    question = "Was ist FKM und wo wird es eingesetzt?"

    streamed_client = _PipelineStreamClient(
        [_KNOWLEDGE_ANSWER], deltas_for={_KNOWLEDGE_ANSWER: _KNOWLEDGE_DELTAS}
    )
    sink = _TokenSinkSpy()
    streamed = _run(
        _plain_pipeline(streamed_client, draft_streaming=True),
        question,
        token_sink=sink,
    )
    assert [c[0] for c in sink.calls] == list(_KNOWLEDGE_DELTAS)
    assert all(draft is True for _, draft in sink.calls)

    plain_client = _PipelineStreamClient([_KNOWLEDGE_ANSWER])
    plain = _run(_plain_pipeline(plain_client, draft_streaming=False), question)

    assert streamed.answer.text == plain.answer.text == _KNOWLEDGE_ANSWER


def test_flag_off_is_byte_identical_zero_draft_events():
    question = "RWDR 45x62x8, welches Material bei Hydrauliköl 100 °C?"
    client = _PipelineStreamClient([_ENGINEERING_ANSWER])
    sink = _TokenSinkSpy()
    # flag OFF, even WITH a token sink wired -> zero draft events, generate() (not generate_stream)
    result = _run(
        _plain_pipeline(client, draft_streaming=False), question, token_sink=sink
    )
    assert sink.calls == []
    assert client.stream_calls == []
    assert client.calls  # the ordinary non-streaming generate() ran
    assert result.answer.text == _ENGINEERING_ANSWER


def test_flag_on_but_no_sink_is_also_byte_identical():
    question = "RWDR 45x62x8, welches Material bei Hydrauliköl 100 °C?"
    client = _PipelineStreamClient([_ENGINEERING_ANSWER])
    result = _run(
        _plain_pipeline(client, draft_streaming=True), question, token_sink=None
    )
    assert (
        client.stream_calls == []
    )  # no sink -> draft_stream_active is False -> non-streaming path
    assert client.calls
    assert result.answer.text == _ENGINEERING_ANSWER


# ── item 5: regenerate-after-guard-BLOCK -- reuses test_output_guard_wiring.py's fixture shape ---

_GUARD_Q = "Wir verwenden FKM in Heißdampf, passt das?"
_GUARD_LEAKY = "FKM ist bis 250 °C in Heißdampf bestens geeignet und freigegeben."
_GUARD_CLEAN = (
    "FKM ist hier kritisch — bitte den Werkstoff für diesen Anwendungsfall beim Hersteller absichern. "
    "Die finale Compound-/Werkstofffreigabe trifft der Hersteller."
)


def _halves(text: str) -> tuple[str, str]:
    mid = len(text) // 2
    return text[:mid], text[mid:]


def test_regenerate_after_guard_block_streams_both_attempts_in_order_and_resets_via_existing_event():
    client = _PipelineStreamClient(
        [_GUARD_LEAKY, _GUARD_CLEAN],
        deltas_for={
            _GUARD_LEAKY: _halves(_GUARD_LEAKY),
            _GUARD_CLEAN: _halves(_GUARD_CLEAN),
        },
    )
    log = _OrderedEventLog()
    result = _run(
        _guard_pipeline(client, draft_streaming=True),
        _GUARD_Q,
        token_sink=log.token,
        progress=log.progress,
    )

    assert (
        client.stream_calls and len(client.stream_calls) == 2
    )  # BOTH attempts streamed
    assert (
        not client.calls
    )  # non-streaming generate() never used while streaming is active

    # the EXISTING "regenerate" stage-start progress event (pre-Phase-3B) -- reused verbatim, no new
    # event type -- is what the frontend uses to reset its draft buffer between the two attempts.
    regenerate_idx = next(
        i
        for i, (kind, payload) in enumerate(log.events)
        if kind == "stage" and payload == ("regenerate", "start")
    )
    before = [
        payload for kind, payload in log.events[:regenerate_idx] if kind == "token"
    ]
    after = [
        payload for kind, payload in log.events[regenerate_idx + 1 :] if kind == "token"
    ]

    assert (
        "".join(d for d, _ in before) == _GUARD_LEAKY
    )  # first attempt, IN FULL, before the reset
    assert (
        "".join(d for d, _ in after) == _GUARD_CLEAN
    )  # second attempt, IN FULL, after the reset
    assert all(draft is True for _, draft in before + after)

    # the final result reflects the REGENERATED (corrected) answer -- exactly as before this PR
    assert result.answer.text == _GUARD_CLEAN
    assert result.guard is not None and result.guard["action"] == "PASS"


def test_regenerate_after_guard_block_flag_off_matches_test_output_guard_wiring_exactly():
    # regression lock: the draft-streaming flag being off must reproduce test_output_guard_wiring.py's
    # test_guard_regenerates_once_on_block byte-for-byte, proving Phase 3B changed nothing about the
    # guard/regenerate mechanism itself.
    client = _PipelineStreamClient([_GUARD_LEAKY, _GUARD_CLEAN])
    result = _run(_guard_pipeline(client, draft_streaming=False), _GUARD_Q)
    assert len(client.calls) == 2 and not client.stream_calls
    assert result.answer.text == _GUARD_CLEAN
    assert result.guard is not None and result.guard["action"] == "PASS"


# ── item 10: SSE wire shape -- draft frames carry only {"text", "draft"} -------------------------


def _frames(raw: str) -> list[dict]:
    out = []
    for block in raw.split("\n\n"):
        if not block.strip() or block.startswith(":"):
            continue
        event, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                event = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        out.append({"event": event, "data": data})
    return out


def _stream(client, body):
    with client.stream(
        "POST", "/api/v2/chat/stream", json=body, headers=auth("tok-A")
    ) as r:
        return "".join(r.iter_text())


def test_sse_draft_token_frames_carry_only_text_and_draft_no_extra_metadata():
    question = "RWDR 45x62x8, welches Material bei Hydrauliköl 100 °C?"
    client = _PipelineStreamClient(
        [_ENGINEERING_ANSWER], deltas_for={_ENGINEERING_ANSWER: _ENGINEERING_DELTAS}
    )
    pipeline = Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        retriever=None,
        memory=InProcessConversationMemory(),
        cross_session=InProcessCrossSessionMemory(),
        matrix=InProcessCompatibilityMatrix(),
        draft_token_streaming_enabled=True,
    )
    test_client, _ = make_client(pipeline)
    raw = _stream(test_client, {"message": question})
    frames = _frames(raw)
    token_frames = [f for f in frames if f["event"] == "token"]
    result_frames = [f for f in frames if f["event"] == "result"]

    assert [f["data"]["text"] for f in token_frames] == list(_ENGINEERING_DELTAS)
    for f in token_frames:
        assert set(f["data"].keys()) == {
            "text",
            "draft",
        }  # nothing else -- no ids/tenant/case/PII
        assert f["data"]["draft"] is True
    assert len(result_frames) == 1
    assert frames[-1]["event"] == "result"  # the gated answer is still the LAST frame
    assert result_frames[0]["data"]["answer"] == _ENGINEERING_ANSWER


def test_sse_emits_zero_draft_frames_when_flag_off():
    question = "RWDR 45x62x8, welches Material bei Hydrauliköl 100 °C?"
    client = _PipelineStreamClient([_ENGINEERING_ANSWER])
    pipeline = Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        retriever=None,
        memory=InProcessConversationMemory(),
        cross_session=InProcessCrossSessionMemory(),
        matrix=InProcessCompatibilityMatrix(),
        draft_token_streaming_enabled=False,
    )
    test_client, _ = make_client(pipeline)
    raw = _stream(test_client, {"message": question})
    frames = _frames(raw)
    assert [f for f in frames if f["event"] == "token"] == []  # ZERO token frames
    result_frames = [f for f in frames if f["event"] == "result"]
    assert len(result_frames) == 1
    assert result_frames[0]["data"]["answer"] == _ENGINEERING_ANSWER
