"""M8-A — deterministic provenance binding: remembered case facts → calc-registry inputs.

The binder is DETERMINISTIC + DECLARED (owner-confirmed mapping table, 2026-06-10): v1 binds ONLY
wellendurchmesser→d1_mm (shaft Ø at the running surface, direct-on-shaft) and drehzahl→rpm. It
never judges: no LLM, fail-closed on absent/unitless/ambiguous/conflicting source facts. Origins
are preserved so the citation stays honest (the V1 provenance-loss lesson).
"""

from __future__ import annotations

import pytest

from sealai_v2.core.calc.binding import bind_params
from sealai_v2.core.contracts import RememberedFact


def fact(
    feld: str, wert: str, provenance: str = "distilled-from-conversation"
) -> RememberedFact:
    return RememberedFact(feld=feld, wert=wert, provenance=provenance)


def test_canonical_pair_binds_with_origins():
    """The saltwater case: d=50 mm + n=4000 U/min remembered → kern inputs present."""
    res = bind_params(
        (fact("wellendurchmesser", "50 mm"), fact("drehzahl", "4000 U/min"))
    )
    assert res.params == {"d1_mm": 50.0, "rpm": 4000.0}
    assert (
        "wellendurchmesser" in res.origins["d1_mm"] and "50 mm" in res.origins["d1_mm"]
    )
    assert "vom Nutzer" in res.origins["d1_mm"]  # user-stated, not derived
    assert "drehzahl" in res.origins["rpm"]


@pytest.mark.parametrize(
    "wert",
    ["4000 U/min", "4000 u/min", "4000 1/min", "4000 min⁻¹", "4000 min^-1", "4000 rpm"],
)
def test_drehzahl_unit_spellings(wert: str):
    res = bind_params((fact("drehzahl", wert),))
    assert res.params == {"rpm": 4000.0}


def test_german_decimal_comma_and_thousands_with_unit():
    assert bind_params((fact("wellendurchmesser", "50,5 mm"),)).params == {
        "d1_mm": 50.5
    }
    # "4.000" is 4000 ONLY with an adjoining unit token (owner decision 2)
    assert bind_params((fact("drehzahl", "4.000 U/min"),)).params == {"rpm": 4000.0}


@pytest.mark.parametrize(
    "feld,wert",
    [
        ("wellendurchmesser", "50"),  # unitless → fail-closed (owner decision 2)
        ("drehzahl", "4.000"),  # thousands WITHOUT unit → ambiguous → fail-closed
        ("drehzahl", "4000"),  # unitless → fail-closed
        ("wellendurchmesser", "50–60 mm"),  # range → fail-closed
        ("wellendurchmesser", "50 bis 60 mm"),
        ("wellendurchmesser", "groß"),  # no number
        ("wellendurchmesser", "50 zoll"),  # unknown unit (v1: mm only)
        (
            "drehzahl",
            "schnell, ca. 4000 U/min und mehr",
        ),  # extra prose → not a clean value
    ],
)
def test_fail_closed_on_unbindable_values(feld: str, wert: str):
    res = bind_params((fact(feld, wert),))
    assert res.params == {}
    assert res.notes  # the drop is visible, never silent


def test_unmapped_felder_are_ignored_silently():
    """medium/temperatur/… are not calc inputs — no params, no noise notes."""
    res = bind_params((fact("medium", "Salzwasser"), fact("temperatur", "80 °C")))
    assert res.params == {} and res.origins == {} and res.notes == ()


def test_same_feld_conflicting_values_fail_closed():
    """case-state vs durable can disagree — the binder never picks a side."""
    res = bind_params((fact("drehzahl", "4000 U/min"), fact("drehzahl", "3000 U/min")))
    assert "rpm" not in res.params
    assert any("drehzahl" in n for n in res.notes)


def test_same_feld_same_value_is_not_a_conflict():
    res = bind_params((fact("drehzahl", "4000 U/min"), fact("drehzahl", "4000 U/min")))
    assert res.params == {"rpm": 4000.0}


def test_user_edited_provenance_is_carried():
    res = bind_params((fact("wellendurchmesser", "50 mm", provenance="user-edited"),))
    assert "user-edited" in res.origins["d1_mm"] or "bestätigt" in res.origins["d1_mm"]


def test_user_form_provenance_is_carried():
    # a value entered via the parameter form binds, and its origin is named honestly (Formular).
    res = bind_params((fact("wellendurchmesser", "50 mm", provenance="user-form"),))
    assert res.params == {"d1_mm": 50.0}
    assert "Formular" in res.origins["d1_mm"] or "user-form" in res.origins["d1_mm"]


def test_empty_input_is_empty_result():
    res = bind_params(())
    assert res.params == {} and res.origins == {} and res.notes == ()


# --- origins threaded through the engine -----------------------------------------------------


def test_engine_threads_input_origins_and_marks_derived():
    from sealai_v2.core.calc.evaluator import CascadeCalcEngine

    res = CascadeCalcEngine().evaluate(
        params={"d1_mm": 50.0, "rpm": 4000.0, "p_bar": 0.5},
        param_origins={
            "d1_mm": "vom Nutzer genannt (wellendurchmesser: »50 mm«)",
            "rpm": "vom Nutzer genannt (drehzahl: »4000 U/min«)",
        },
    )
    by_id = {c.calc_id: c for c in res.computed}
    v = by_id["umfangsgeschwindigkeit"]
    assert v.input_origins == (
        "vom Nutzer genannt (wellendurchmesser: »50 mm«)",
        "vom Nutzer genannt (drehzahl: »4000 U/min«)",
    )
    # the cascade-derived v_m_s feeding pv is marked DERIVED, p_bar (no declared origin) stays Parameter
    pv = by_id["pv_wert"]
    origins = dict(zip(pv.inputs_used, pv.input_origins))
    assert origins["v_m_s"] == "abgeleitet (umfangsgeschwindigkeit)"
    assert origins["p_bar"] == "Parameter"


# --- pipeline wiring: remembered facts feed the kern -------------------------------------------


def _calc_pipeline(client):
    import sealai_v2.core.calc.evaluator as ev
    from sealai_v2.core.contracts import ModelConfig
    from sealai_v2.core.l1_generator import L1Generator
    from sealai_v2.memory.store import InProcessConversationMemory
    from sealai_v2.pipeline.pipeline import Pipeline
    from sealai_v2.prompts.assembler import PromptAssembler

    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        engine=ev.CascadeCalcEngine(),
        memory=InProcessConversationMemory(),
    )


def _seed(p, tenant_id: str, session_id: str, facts):
    p.memory.record_turn(
        tenant_id=tenant_id,
        session_id=session_id,
        question="seed",
        answer="",
        facts=facts,
    )


def test_pipeline_binds_remembered_facts_into_compute():
    """THE canonical fix: saltwater d=50/n=4000 remembered → the kern fires + the prompt carries
    the deterministic value with its user-stated origin (no more 'nicht berechenbar' beside an
    L1-computed v)."""
    import asyncio

    from sealai_v2.core.contracts import SessionContext
    from sealai_v2.security.tenant import TenantContext
    from sealai_v2.tests._fakes import FakeLlmClient

    client = FakeLlmClient("ok")
    p = _calc_pipeline(client)
    _seed(
        p,
        "t1",
        "s1",
        (fact("wellendurchmesser", "50 mm"), fact("drehzahl", "4000 U/min")),
    )
    res = asyncio.run(
        p.run("Passt das so?", tenant=TenantContext("t1"), session=SessionContext("s1"))
    )
    by_id = {c.calc_id: c for c in res.computed_values}
    assert "umfangsgeschwindigkeit" in by_id
    assert abs(by_id["umfangsgeschwindigkeit"].value - 10.472) < 0.001
    assert not any(n.calc_id == "umfangsgeschwindigkeit" for n in res.not_computed)
    system = client.calls[0]["system"]
    assert "Berechnete Werte" in system and "10.472" in system
    assert "wellendurchmesser" in system  # the origin is visible to L1 (and the render)


def test_explicit_params_take_precedence_over_bound_facts():
    import asyncio

    from sealai_v2.core.contracts import SessionContext
    from sealai_v2.security.tenant import TenantContext
    from sealai_v2.tests._fakes import FakeLlmClient

    p = _calc_pipeline(FakeLlmClient("ok"))
    _seed(
        p,
        "t1",
        "s1",
        (fact("wellendurchmesser", "50 mm"), fact("drehzahl", "4000 U/min")),
    )
    res = asyncio.run(
        p.run(
            "Passt das so?",
            tenant=TenantContext("t1"),
            session=SessionContext("s1"),
            params={"d1_mm": 80.0, "rpm": 3000.0},
        )
    )
    v = {c.calc_id: c for c in res.computed_values}["umfangsgeschwindigkeit"]
    assert abs(v.value - 12.5664) < 0.001  # fixtures/explicit params keep priority


def test_briefing_render_shows_input_origins():
    """The briefing (the canonical failure surface) carries the per-input provenance."""
    from sealai_v2.core.contracts import ComputedValue, RenderSnapshot
    from sealai_v2.render.renderer import ArtifactRenderer

    cv = ComputedValue(
        calc_id="umfangsgeschwindigkeit",
        name="v_m_s",
        value=10.472,
        unit="m/s",
        stage=1,
        derivation_depth=1,
        formula="v = π·d1·n/60000",
        source="DIN 3760",
        inputs_used=("d1_mm", "rpm"),
        input_origins=(
            "vom Nutzer genannt (wellendurchmesser: »50 mm«)",
            "vom Nutzer genannt (drehzahl: »4000 U/min«)",
        ),
    )
    art = ArtifactRenderer().briefing(
        RenderSnapshot(question="q", answer_text="a", computed=(cv,), grounded=False)
    )
    assert "Eingaben:" in art.body
    assert "wellendurchmesser: »50 mm«" in art.body
    assert "vom Nutzer genannt" in art.body


def test_binding_fail_closed_surfaces_note_and_kern_stays_honest():
    import asyncio

    from sealai_v2.core.contracts import SessionContext
    from sealai_v2.security.tenant import TenantContext
    from sealai_v2.tests._fakes import FakeLlmClient

    p = _calc_pipeline(FakeLlmClient("ok"))
    _seed(p, "t1", "s1", (fact("drehzahl", "4000"),))  # unitless → fail-closed
    res = asyncio.run(
        p.run("Passt das so?", tenant=TenantContext("t1"), session=SessionContext("s1"))
    )
    assert res.computed_values == ()
    assert any(n.calc_id == "umfangsgeschwindigkeit" for n in res.not_computed)
    assert any(
        "drehzahl" in n for n in res.calc_notes
    )  # the drop is visible, never silent
