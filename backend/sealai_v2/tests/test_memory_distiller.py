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
    return Distiller(
        FakeLlmClient(text), DistillPromptAssembler(), ModelConfig("fake-helper")
    )


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
    facts = asyncio.run(d.distill(question="System läuft bei 10 bar"))
    assert {f.feld: f.wert for f in facts} == {"druck": "10 bar"}


def test_distill_prompt_is_conservative():
    p = DistillPromptAssembler().distill_prompt().lower()
    assert "explizit" in p  # only what the user explicitly stated
    assert "schlussfolgerung" in p  # no inference
    assert "empfehlung" in p  # never the assistant's recommendations


def test_distill_prompt_instructs_unit_fidelity():
    """M8 chat-channel binding reliability: the fail-closed binder needs number+unit, so the
    distiller must KEEP the user's unit token with the number (»8000 U/min«, not »8000«) — while
    never INVENTING a unit the user did not state (unitless stays unitless → fail-closed → the chip
    surface settles it). Offline proof that the instruction is present; the real LLM behaviour is
    validated by the post-arc eval REPLAY."""
    p = DistillPromptAssembler().distill_prompt().lower()
    assert "einheit" in p  # instructs keeping the unit with the number
    assert "erfinde keine einheit" in p or "keine einheit" in p  # never fabricate a unit
    # names a canonical bindable shape so chat-given drehzahl survives to the kern
    assert "u/min" in p


# --- (c)(i) runtime numeric-trace fail-closed: a distilled number must trace to the user turn ---


def test_drops_fact_with_fabricated_number():
    # the user said 150 °C; the LLM "distills" 1500 °C → untraceable number → DROP (fail-closed)
    d = _distiller('{"facts": [{"feld": "temperatur", "wert": "1500°C"}]}')
    assert asyncio.run(d.distill(question="FKM bei 150°C in Heißöl?")) == ()


def test_keeps_fact_with_traceable_number():
    d = _distiller('{"facts": [{"feld": "temperatur", "wert": "150 °C"}]}')
    facts = asyncio.run(d.distill(question="FKM bei 150°C in Heißöl?"))
    assert {f.feld: f.wert for f in facts} == {"temperatur": "150 °C"}


def test_keeps_qualitative_fact_without_numbers():
    # no numerics to trace → the runtime numeric guard does not apply (qualitative = judge/human-final)
    d = _distiller('{"facts": [{"feld": "medium", "wert": "Hydrauliköl"}]}')
    facts = asyncio.run(d.distill(question="Womit dichte ich gegen Öl ab?"))
    assert {f.feld: f.wert for f in facts} == {"medium": "Hydrauliköl"}


def test_drops_only_the_offending_fact_keeps_the_rest():
    d = _distiller(
        '{"facts": [{"feld": "medium", "wert": "Hydrauliköl"}, '
        '{"feld": "temperatur", "wert": "1500°C"}, '
        '{"feld": "drehzahl", "wert": "3000 U/min"}]}'
    )
    facts = asyncio.run(
        d.distill(question="Hydrauliköl, 150°C, Welle dreht 3000 U/min")
    )
    # medium (no number) kept; drehzahl 3000 traces; temperatur 1500 fabricated → dropped
    assert {f.feld: f.wert for f in facts} == {
        "medium": "Hydrauliköl",
        "drehzahl": "3000 U/min",
    }


# --- drop observability (owner addition 1): the numeric guard is also a MEASUREMENT instrument.
# drop_rate ≈ 0 ⇒ the conservative distiller works; high ⇒ it fabricates and is only being rescued.


def test_stats_count_a_dropped_fabricated_number():
    d = _distiller('{"facts": [{"feld": "temperatur", "wert": "1500°C"}]}')
    asyncio.run(d.distill(question="FKM bei 150°C?"))
    assert (d.stats.proposed, d.stats.dropped) == (1, 1)
    assert d.stats.drop_rate == 1.0


def test_stats_clean_distill_has_zero_drop_rate():
    d = _distiller('{"facts": [{"feld": "temperatur", "wert": "150 °C"}]}')
    asyncio.run(d.distill(question="FKM bei 150°C?"))
    assert (d.stats.proposed, d.stats.dropped) == (1, 0)
    assert d.stats.drop_rate == 0.0


def test_stats_no_proposed_facts_is_zero_not_division_error():
    d = _distiller('{"facts": []}')
    asyncio.run(d.distill(question="Hallo"))
    assert (d.stats.proposed, d.stats.dropped, d.stats.drop_rate) == (0, 0, 0.0)


def test_stats_accumulate_across_calls():
    # qualitative facts (no numerics) count as proposed-but-not-dropped; the rate is over all proposed
    d = _distiller(
        '{"facts": [{"feld": "medium", "wert": "Öl"}, {"feld": "temperatur", "wert": "1500°C"}]}'
    )
    asyncio.run(d.distill(question="Öl bei 150°C"))
    asyncio.run(d.distill(question="Öl bei 150°C"))
    assert (d.stats.proposed, d.stats.dropped) == (4, 2)
    assert d.stats.drop_rate == 0.5
