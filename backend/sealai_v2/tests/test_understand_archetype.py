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
from sealai_v2.tests._fakes import FakeLlmClient

_KEYS = ("getriebe", "ruehrwerk")


def _understand(text, keys=_KEYS):
    client = FakeLlmClient(text)
    return asyncio.run(
        stages.understand(
            client, ModelConfig("fake-helper"), "Frage?", archetype_keys=keys
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
    u = asyncio.run(stages.understand(client, ModelConfig("fake-helper"), "Frage?"))
    assert u.archetype is None
    assert u.intent.value == "faktfrage"
