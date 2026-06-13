"""M8 (trust-spine completion) — Part 2: the derived-fact model.

Kernel outputs are persisted as ``kernel_computed`` DerivedFacts (a SEPARATE slice from the input
case-state — Option B, owner-confirmed) and recomputed-and-REPLACED on every input-mutation channel
(form / chip edit / chat re-statement / forget). The invariant — a stale derived value never
persists — holds structurally: every recompute replaces the whole slice from current inputs, so
removing the last parent yields an empty slice. ``kernel_computed`` is backend-only: not a
case-state input, not in the FactEdit origin allowlist.

All offline, no LLM (fakes only).
"""

from __future__ import annotations

import asyncio

from sealai_v2.core.calc.binding import bind_params
from sealai_v2.core.calc.derived import recompute_derived
from sealai_v2.core.calc.evaluator import CascadeCalcEngine
from sealai_v2.core.contracts import (
    DerivedFact,
    ModelConfig,
    RememberedFact,
    SessionContext,
)
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.memory.distiller import Distiller
from sealai_v2.memory.store import InProcessConversationMemory
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import DistillPromptAssembler, PromptAssembler
from sealai_v2.security.tenant import TenantContext
from sealai_v2.tests._apiutil import auth, make_client
from sealai_v2.tests._fakes import DistillRoutingFakeLlmClient, FakeLlmClient


def _rf(feld: str, wert: str, provenance: str = "user-form") -> RememberedFact:
    return RememberedFact(feld=feld, wert=wert, provenance=provenance)


# --- pure recompute_derived ----------------------------------------------------------------------


def test_recompute_derived_maps_value_with_parents_and_origins():
    comp = recompute_derived(
        (_rf("wellendurchmesser", "40 mm"), _rf("drehzahl", "8000 U/min")),
        CascadeCalcEngine(),
    )
    by_id = {d.calc_id: d for d in comp.derived}
    v = by_id["umfangsgeschwindigkeit"]
    assert v.provenance == "kernel_computed"
    assert abs(v.value - 16.755) < 0.01
    assert v.unit == "m/s" and v.formula  # cited formula carried for the panel
    assert set(v.parent_fields) == {"wellendurchmesser", "drehzahl"}  # input-dependencies tagged
    assert any("Formular" in o for o in v.input_origins)  # provenance honest


def test_recompute_derived_no_inputs_is_empty_but_surfaces_reason():
    comp = recompute_derived((), CascadeCalcEngine())
    assert comp.derived == ()  # no fabricated derived fact
    assert any(n.calc_id == "umfangsgeschwindigkeit" for n in comp.calc.not_computed)


def test_recompute_derived_unitless_input_fails_closed_with_note():
    comp = recompute_derived(
        (_rf("wellendurchmesser", "40 mm"), _rf("drehzahl", "8000")),  # unitless n
        CascadeCalcEngine(),
    )
    assert all(d.calc_id != "umfangsgeschwindigkeit" for d in comp.derived)
    assert any("drehzahl" in n for n in comp.calc.notes)  # drop is visible


# --- binder guard (deferred from Part 1): kernel_computed is NEVER an input ----------------------


def test_binder_skips_kernel_computed_provenance():
    """Defensive boundary: even a kernel value that somehow appeared in case-state is never treated
    as a calc input (no feedback loop / no stale-derived-feeds-cascade)."""
    res = bind_params((_rf("drehzahl", "8000 U/min", provenance="kernel_computed"),))
    assert res.params == {} and res.notes == ()  # silently skipped, not an input, no noise


# --- store derived slice (a separate channel) ----------------------------------------------------


def test_store_derived_slice_is_separate_from_case_state_and_recall():
    m = InProcessConversationMemory()
    df = DerivedFact(
        calc_id="umfangsgeschwindigkeit",
        name="v_m_s",
        value=16.755,
        unit="m/s",
        formula="v = π·d1·n/60000",
        parent_fields=("wellendurchmesser", "drehzahl"),
    )
    m.edit_fact(
        tenant_id="t",
        session_id="s",
        feld="wellendurchmesser",
        wert="40 mm",
        provenance="user-form",
    )
    m.set_derived(tenant_id="t", session_id="s", derived=(df,))
    assert m.derived_facts(tenant_id="t", session_id="s") == (df,)
    # the kernel value is NOT a case-state input and NOT in recall (recall stays byte-identical)
    assert all(
        f.feld != "umfangsgeschwindigkeit"
        for f in m.case_state(tenant_id="t", session_id="s")
    )
    assert (
        m.recall(tenant_id="t", session_id="s").case_state
        == m.case_state(tenant_id="t", session_id="s")
    )
    # clear drops derived with the inputs
    m.clear(tenant_id="t", session_id="s")
    assert m.derived_facts(tenant_id="t", session_id="s") == ()


# --- pipeline.recompute_derived_for: persist + invalidate, all channels --------------------------


def _engine_pipeline(distiller: Distiller | None = None) -> Pipeline:
    client = FakeLlmClient("ok")
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        engine=CascadeCalcEngine(),
        memory=InProcessConversationMemory(),
        distiller=distiller,
    )


def test_recompute_persists_then_forget_evicts_then_edit_recomputes():
    p = _engine_pipeline()
    m = p.memory

    def edit(feld, wert, prov="user-form"):
        m.edit_fact(tenant_id="t", session_id="s", feld=feld, wert=wert, provenance=prov)

    edit("wellendurchmesser", "40 mm")
    edit("drehzahl", "8000 U/min")
    p.recompute_derived_for(tenant_id="t", session_id="s")
    d = {x.calc_id: x for x in m.derived_facts(tenant_id="t", session_id="s")}
    assert abs(d["umfangsgeschwindigkeit"].value - 16.755) < 0.01

    # forget a parent → child evicted (no stale value survives)
    m.delete_fact(tenant_id="t", session_id="s", feld="drehzahl")
    p.recompute_derived_for(tenant_id="t", session_id="s")
    assert all(
        x.calc_id != "umfangsgeschwindigkeit"
        for x in m.derived_facts(tenant_id="t", session_id="s")
    )

    # restate n + correct d → recompute to a NEW value (π·80·8000/60000 = 33.51), old value gone
    edit("drehzahl", "8000 U/min")
    edit("wellendurchmesser", "80 mm", prov="user-edited")
    p.recompute_derived_for(tenant_id="t", session_id="s")
    d2 = {x.calc_id: x for x in m.derived_facts(tenant_id="t", session_id="s")}
    assert abs(d2["umfangsgeschwindigkeit"].value - 33.51) < 0.05


def test_chat_restatement_recomputes_after_background_remember():
    """The chat channel: stated facts distilled in the background remember → recompute persists the
    derived slice once the remember has landed (flush)."""
    fake = DistillRoutingFakeLlmClient(
        '{"facts": [{"feld": "wellendurchmesser", "wert": "40 mm"}, '
        '{"feld": "drehzahl", "wert": "8000 U/min"}]}'
    )
    p = Pipeline(
        generator=L1Generator(fake, PromptAssembler(), ModelConfig("fake-l1")),
        client=fake,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        engine=CascadeCalcEngine(),
        memory=InProcessConversationMemory(),
        distiller=Distiller(fake, DistillPromptAssembler(), ModelConfig("fake-helper")),
    )
    asyncio.run(
        p.run("Welle 40 mm, 8000 U/min", tenant=TenantContext("t"), session=SessionContext("s"))
    )
    asyncio.run(p.flush_memory(tenant_id="t", session_id="s"))
    d = {x.calc_id: x for x in p.memory.derived_facts(tenant_id="t", session_id="s")}
    assert abs(d["umfangsgeschwindigkeit"].value - 16.755) < 0.01


# --- route-level invalidation (edit + forget channels through the real handlers) -----------------


def _engine_api_pipeline() -> Pipeline:
    from sealai_v2.memory.store import InProcessCrossSessionMemory

    client = FakeLlmClient("ok")
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        engine=CascadeCalcEngine(),
        memory=InProcessConversationMemory(),
        cross_session=InProcessCrossSessionMemory(),
    )


def test_route_edit_and_forget_invalidate_derived_via_token():
    client, pipeline = make_client(_engine_api_pipeline())
    for feld, wert in (("wellendurchmesser", "40 mm"), ("drehzahl", "8000 U/min")):
        client.put(
            f"/api/v2/conversations/current/facts/{feld}",
            json={"wert": wert, "origin": "user-form"},
            headers=auth("tok-A"),
        )
    d = {
        x.calc_id: x
        for x in pipeline.memory.derived_facts(tenant_id="tenant-A", session_id="sess-A")
    }
    assert "umfangsgeschwindigkeit" in d  # form edits triggered the recompute

    client.delete(
        "/api/v2/conversations/current/facts/drehzahl", headers=auth("tok-A")
    )
    assert all(
        x.calc_id != "umfangsgeschwindigkeit"
        for x in pipeline.memory.derived_facts(tenant_id="tenant-A", session_id="sess-A")
    )  # forget evicted it


def test_route_rejects_kernel_computed_origin():
    """``kernel_computed`` is backend-only — it is NOT in the FactEdit origin allowlist, so a client
    PUT claiming it falls back to user-edited (no provenance spoofing of a kernel value)."""
    client, pipeline = make_client(_engine_api_pipeline())
    client.put(
        "/api/v2/conversations/current/facts/wellendurchmesser",
        json={"wert": "40 mm", "origin": "kernel_computed"},
        headers=auth("tok-A"),
    )
    (f,) = pipeline.memory.case_state(tenant_id="tenant-A", session_id="sess-A")
    assert f.provenance == "user-edited"
