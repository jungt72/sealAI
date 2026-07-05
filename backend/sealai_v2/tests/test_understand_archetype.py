"""G4 (V2.1 Inc 1) — the understand stage ALSO annotates a soft ``archetype`` (one call, no second
classifier — owner decision 3). The recognised key is SERVER-SIDE validated against the store's keys
(an invented/out-of-store key never survives) and stays annotate-only (it guides the prompt in G4,
it never gates/routes). RED before ``understand`` accepts ``archetype_keys`` / ``Understanding`` has
``archetype``.
"""

from __future__ import annotations

import asyncio

from sealai_v2.core.contracts import ModelConfig
from sealai_v2.pipeline import stages
from sealai_v2.prompts.assembler import UnderstandPromptAssembler
from sealai_v2.tests._fakes import FakeLlmClient

_KEYS = ("getriebe", "ruehrwerk")
_PROMPT_ASSEMBLER = UnderstandPromptAssembler()


def _understand(text, keys=_KEYS):
    client = FakeLlmClient(text)
    return asyncio.run(
        stages.understand(
            client,
            ModelConfig("fake-helper"),
            "Frage?",
            prompt_assembler=_PROMPT_ASSEMBLER,
            archetype_keys=keys,
        )
    )


def test_recognizes_known_archetype():
    u = _understand('{"intent":"fallarbeit","rationale":"x","archetype":"getriebe"}')
    assert u.archetype == "getriebe"
    assert u.intent.value == "fallarbeit"  # intent annotation still lands


def test_null_archetype_when_absent():
    u = _understand('{"intent":"wissensfrage","rationale":"x"}')
    assert u.archetype is None


def test_unknown_archetype_is_dropped():
    # server-side validation: an invented / out-of-store key never survives (no LLM-invented key)
    u = _understand('{"intent":"fallarbeit","rationale":"x","archetype":"auto"}')
    assert u.archetype is None


def test_archetype_is_case_insensitive():
    u = _understand('{"intent":"fallarbeit","rationale":"x","archetype":"Getriebe"}')
    assert u.archetype == "getriebe"


def test_no_keys_means_no_archetype():
    # catalog absent → no archetype requested/parsed; intent still works (back-compat path)
    client = FakeLlmClient('{"intent":"faktfrage","rationale":"x"}')
    u = asyncio.run(
        stages.understand(
            client,
            ModelConfig("fake-helper"),
            "Frage?",
            prompt_assembler=_PROMPT_ASSEMBLER,
        )
    )
    assert u.archetype is None
    assert u.intent.value == "faktfrage"


_SEAL_TYPES = ("rwdr", "hydraulik")


def _understand_pack(text, known_seal_types=_SEAL_TYPES, medium_already_known=True):
    client = FakeLlmClient(text)
    return asyncio.run(
        stages.understand(
            client,
            ModelConfig("fake-helper"),
            "Frage?",
            prompt_assembler=_PROMPT_ASSEMBLER,
            known_seal_types=known_seal_types,
            medium_already_known=medium_already_known,
        )
    )


def test_recognizes_known_pack_suggestion():
    u = _understand_pack(
        '{"intent":"fallarbeit","rationale":"x","suggested_seal_type":"hydraulik"}'
    )
    assert u.suggested_seal_type == "hydraulik"


def test_null_pack_suggestion_when_absent():
    u = _understand_pack('{"intent":"wissensfrage","rationale":"x"}')
    assert u.suggested_seal_type is None


def test_unknown_pack_suggestion_is_dropped():
    # server-side validation, same discipline as archetype: an invented/out-of-list value never survives
    u = _understand_pack(
        '{"intent":"fallarbeit","rationale":"x","suggested_seal_type":"gleitringdichtung"}'
    )
    assert u.suggested_seal_type is None


def test_pack_suggestion_is_case_insensitive():
    u = _understand_pack(
        '{"intent":"fallarbeit","rationale":"x","suggested_seal_type":"Hydraulik"}'
    )
    assert u.suggested_seal_type == "hydraulik"


def test_no_known_seal_types_means_no_suggestion_even_if_llm_returns_one():
    # mirrors test_no_keys_means_no_archetype: an empty allowlist (e.g. seal_type already committed)
    # means the field is never even requested/parsed, regardless of what the LLM says
    u = _understand_pack(
        '{"intent":"fallarbeit","rationale":"x","suggested_seal_type":"hydraulik"}',
        known_seal_types=(),
    )
    assert u.suggested_seal_type is None


def test_recognizes_medium_hint_when_medium_not_already_known():
    u = _understand_pack(
        '{"intent":"fallarbeit","rationale":"x","medium_hint":"Teig"}',
        medium_already_known=False,
    )
    assert u.medium_hint == "Teig"


def test_medium_hint_is_ignored_when_medium_already_known():
    # even if the LLM (mistakenly) returns one, it must never surface once medium is already settled
    u = _understand_pack(
        '{"intent":"fallarbeit","rationale":"x","medium_hint":"Teig"}',
        medium_already_known=True,
    )
    assert u.medium_hint is None


def test_null_medium_hint_when_absent():
    u = _understand_pack(
        '{"intent":"wissensfrage","rationale":"x"}', medium_already_known=False
    )
    assert u.medium_hint is None


def test_medium_hint_is_length_capped():
    long_text = "x" * 500
    u = _understand_pack(
        '{"intent":"fallarbeit","rationale":"x","medium_hint":"' + long_text + '"}',
        medium_already_known=False,
    )
    assert u.medium_hint is not None
    assert len(u.medium_hint) <= 80


def test_pack_suggestion_and_medium_hint_prompt_text_only_appears_when_requested():
    # precise prompt-construction check (not just parsing) — the LLM is only ASKED for these
    # fields when the caller actually wants them, mirroring archetype_keys' own on/off behaviour
    client = FakeLlmClient('{"intent":"fallarbeit","rationale":"x"}')
    asyncio.run(
        stages.understand(
            client,
            ModelConfig("fake-helper"),
            "Frage?",
            prompt_assembler=_PROMPT_ASSEMBLER,
            known_seal_types=_SEAL_TYPES,
            medium_already_known=False,
        )
    )
    system = client.calls[0]["system"]
    assert "suggested_seal_type" in system
    assert "medium_hint" in system

    client2 = FakeLlmClient('{"intent":"fallarbeit","rationale":"x"}')
    asyncio.run(
        stages.understand(
            client2,
            ModelConfig("fake-helper"),
            "Frage?",
            prompt_assembler=_PROMPT_ASSEMBLER,
        )
    )
    system2 = client2.calls[0]["system"]
    assert "suggested_seal_type" not in system2
    assert "medium_hint" not in system2
