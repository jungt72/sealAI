"""Memory distiller (build-spec §7, layer 2) — conservative, STATED-facts-only extraction.

The distillation is an LLM step → a fact-corruption vector, so the load-bearing properties are:
extract only explicit user facts, and FAIL SAFE (parse failure → no fact, never a guessed one).
"""

from __future__ import annotations

import asyncio

from sealai_v2.core.contracts import ModelConfig
from sealai_v2.memory.distiller import Distiller
from sealai_v2.prompts.assembler import DistillPromptAssembler
from sealai_v2.tests._fakes import FakeLlmClient


def _distiller(text: str) -> Distiller:
    return Distiller(FakeLlmClient(text), DistillPromptAssembler(), ModelConfig("fake-helper"))


def test_distills_stated_facts_from_json():
    d = _distiller(
        '{"facts": [{"feld": "medium", "wert": "Hydrauliköl"}, '
        '{"feld": "temperatur", "wert": "120°C"}]}'
    )
    facts = asyncio.run(d.distill(question="EPDM in Hydrauliköl bei 120°C?"))
    assert {f.feld: f.wert for f in facts} == {
        "medium": "Hydrauliköl",
        "temperatur": "120°C",
    }
    # remembered-claim provenance — NOT reviewed/authoritative
    assert all(f.provenance == "distilled-from-conversation" for f in facts)


def test_empty_facts_when_nothing_stated():
    d = _distiller('{"facts": []}')
    assert asyncio.run(d.distill(question="Hallo, wie geht es dir?")) == ()


def test_parse_failure_fails_safe_to_empty():
    d = _distiller("das ist kein JSON, nur Prosa")
    assert asyncio.run(d.distill(question="irgendwas")) == ()


def test_skips_incomplete_entries():
    d = _distiller(
        '{"facts": [{"feld": "medium", "wert": ""}, {"feld": "", "wert": "x"}, '
        '{"feld": "druck", "wert": "10 bar"}]}'
    )
    facts = asyncio.run(d.distill(question="..."))
    assert {f.feld: f.wert for f in facts} == {"druck": "10 bar"}


def test_distill_prompt_is_conservative():
    p = DistillPromptAssembler().distill_prompt().lower()
    assert "explizit" in p  # only what the user explicitly stated
    assert "schlussfolgerung" in p  # no inference
    assert "empfehlung" in p  # never the assistant's recommendations
