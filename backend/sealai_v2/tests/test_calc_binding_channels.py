"""M8 (trust-spine completion) — Part 1: prod input-binding reliability across BOTH channels.

The binder logic itself is covered by ``test_calc_binding.py`` (which seeds case-state directly,
bypassing the distiller). These tests close the prod gap the request names — they exercise the two
REAL channels end-to-end and lock the contract:

  • CHAT channel — user message → real ``Distiller`` (FakeLlmClient JSON) → store → recall →
    ``bind_params`` → kern. Unit-bearing → the kern fires; unitless → fail-closed, surfaced note,
    NO number (the chip surface then settles it). This is where the unit-fidelity gap lived.
  • FORM channel — the canonical holdout ``CALC-USERFORM-PROV-01`` seed facts bind deterministically
    (offline; the multi-turn LLM run is the post-arc eval).

The binder is NEVER weakened here (doctrine): reliability comes from distiller unit-fidelity +
the chip-settling surface, not from loosening the number+unit grammar.
"""

from __future__ import annotations

import asyncio

from sealai_v2.core.calc.binding import bind_params
from sealai_v2.core.calc.evaluator import CascadeCalcEngine
from sealai_v2.core.contracts import LlmResult, ModelConfig, SessionContext
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.eval.multiturn import load_multiturn_cases
from sealai_v2.memory.distiller import Distiller
from sealai_v2.memory.store import InProcessConversationMemory
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import DistillPromptAssembler, PromptAssembler
from sealai_v2.security.tenant import TenantContext

_DISTILL_MARKER = "extrahierst strukturierte Fakten"  # distill.jinja's opening line


class _ChatFake:
    """Routes by system prompt: a distill call → a fixed facts-JSON; any other call → a fixed prose
    answer. Lets one fake drive the full chat path (distill + L1) in a pipeline run."""

    def __init__(self, distill_json: str, answer: str = "ok") -> None:
        self.distill_json = distill_json
        self.answer = answer
        self.calls: list[dict] = []

    async def generate(
        self, *, system: str, user: str, model_config: ModelConfig
    ) -> LlmResult:
        self.calls.append({"system": system, "user": user, "model": model_config.model})
        text = self.distill_json if _DISTILL_MARKER in system else self.answer
        return LlmResult(text=text, model=model_config.model, finish_reason="stop")


def _chat_pipeline(client: _ChatFake) -> Pipeline:
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        engine=CascadeCalcEngine(),
        memory=InProcessConversationMemory(),
        distiller=Distiller(
            client, DistillPromptAssembler(), ModelConfig("fake-helper")
        ),
    )


async def _two_turns(client: _ChatFake, first: str, second: str):
    """Turn 1 states facts (distilled in the background remember); flush so they land; turn 2 is
    where the kern can read them back — the CALC-MEM-01 two-turn shape, the real prod flow."""
    p = _chat_pipeline(client)
    tenant, session = TenantContext("t1"), SessionContext("s1")
    await p.run(first, tenant=tenant, session=session)
    await p.flush_memory(tenant_id="t1", session_id="s1")
    return await p.run(second, tenant=tenant, session=session)


# --- CHAT channel ---------------------------------------------------------------------------------


def test_chat_channel_unit_bearing_facts_bind_and_kern_fires():
    """The fixed gap: chat-given d + n WITH units survive distillation → bind → the kern computes v
    and the prompt carries it with a user-stated origin (no L1 self-compute needed)."""
    client = _ChatFake(
        '{"facts": [{"feld": "wellendurchmesser", "wert": "40 mm"}, '
        '{"feld": "drehzahl", "wert": "8000 U/min"}]}'
    )
    res = asyncio.run(
        _two_turns(client, "Welle 40 mm, dreht mit 8000 U/min", "Passt das?")
    )
    by_id = {c.calc_id: c for c in res.computed_values}
    assert "umfangsgeschwindigkeit" in by_id
    assert abs(by_id["umfangsgeschwindigkeit"].value - 16.755) < 0.01
    assert not any(n.calc_id == "umfangsgeschwindigkeit" for n in res.not_computed)
    # origin is honest: distilled-from-conversation reads as "vom Nutzer genannt"
    assert any(
        "vom Nutzer genannt" in o for o in by_id["umfangsgeschwindigkeit"].input_origins
    )


def test_chat_channel_unitless_value_fails_closed_and_is_visible():
    """Unitless chat input (»8000«, no unit token) stays unbound — fail-closed, the kern stays
    honest, the drop is a visible note. The binder is NOT loosened to rescue it."""
    client = _ChatFake(
        '{"facts": [{"feld": "wellendurchmesser", "wert": "40 mm"}, '
        '{"feld": "drehzahl", "wert": "8000"}]}'  # unitless drehzahl
    )
    res = asyncio.run(_two_turns(client, "Welle 40 mm, 8000", "Passt das?"))
    assert not any(c.calc_id == "umfangsgeschwindigkeit" for c in res.computed_values)
    assert any(n.calc_id == "umfangsgeschwindigkeit" for n in res.not_computed)
    assert any("drehzahl" in n for n in res.calc_notes)  # the drop is never silent


# --- FORM channel (the canonical holdout) ---------------------------------------------------------


def test_form_channel_holdout_seed_facts_bind_deterministically():
    """CALC-USERFORM-PROV-01: parameter-form inputs (user-form provenance) bind to the kern inputs
    and the citation stays honest (Formular). Deterministic, offline — the multi-turn LLM behaviour
    is the post-arc owner-gated eval."""
    cases = {c.id: c for c in load_multiturn_cases()}
    holdout = cases["CALC-USERFORM-PROV-01"]
    res = bind_params(holdout.seed_facts)
    assert res.params == {"d1_mm": 40.0, "rpm": 8000.0}
    assert all("Formular" in o or "user-form" in o for o in res.origins.values())
    # and the kern then computes the holdout's ~16,76 m/s from those bound inputs
    calc = CascadeCalcEngine().evaluate(params=res.params, param_origins=res.origins)
    v = {c.calc_id: c for c in calc.computed}["umfangsgeschwindigkeit"]
    assert abs(v.value - 16.755) < 0.01
