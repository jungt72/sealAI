"""Phase 2b — POST /api/v2/conversations/current/facts (batch settle) + the deterministic confirmation.

The form submits all fields at once → settle (user-form) → ONE recompute → a deterministic confirmation
that echoes the POST-BIND value (never the raw submitted string) and distinguishes übernommen
(settled+bound) from clarify-pending (a Rückfrage — never claimed as taken). No LLM in the echo.
"""

from __future__ import annotations

from sealai_v2.core.calc.evaluator import CascadeCalcEngine
from sealai_v2.core.contracts import ModelConfig
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.memory.store import (
    InProcessConversationMemory,
    InProcessCrossSessionMemory,
)
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.tests._apiutil import auth, make_client
from sealai_v2.tests._fakes import FakeLlmClient


def _engine_pipeline() -> Pipeline:
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


def _batch(client, items, token: str = "tok-A"):
    return client.post(
        "/api/v2/conversations/current/facts", json={"items": items}, headers=auth(token)
    )


def test_batch_settle_echoes_post_bind_value_and_pv_from_half_bar():
    """0,5 bar (German decimal, what the normalized form sends) → bound 0.5 → PV from 0.5, NOT 0.
    The übernommen line echoes the post-bind value, and the kern PV proves the 0.5 magnitude."""
    client, pipeline = make_client(_engine_pipeline())
    r = _batch(
        client,
        [
            {"feld": "wellendurchmesser", "wert": "50 mm", "label": "Wellendurchmesser d₁"},
            {"feld": "drehzahl", "wert": "3000 U/min", "label": "Drehzahl n"},
            {"feld": "druck", "wert": "0,5 bar", "label": "Druck p"},
            {"feld": "medium", "wert": "Öl", "label": "Medium"},
        ],
    )
    assert r.status_code == 200
    body = r.json()
    ueb = {u["feld"]: u for u in body["uebernommen"]}
    # post-bind echo: druck shows the bound 0,5 bar; the context field shows its settled value
    assert ueb["druck"]["wert"] == "0,5 bar" and ueb["druck"]["label"] == "Druck p"
    assert ueb["medium"]["wert"] == "Öl"
    assert body["rueckfragen"] == []
    # PV computed from p_bar = 0.5 (NOT 0): v = π·50·3000/60000 ≈ 7.854; PV = 0.5 · v ≈ 3.927
    by_id = {c["calc_id"]: c for c in body["computed"]}
    assert abs(by_id["umfangsgeschwindigkeit"]["value"] - 7.854) < 0.01
    assert "pv_wert" in by_id and abs(by_id["pv_wert"]["value"] - 3.927) < 0.01
    # settled with the honest user-form provenance
    facts = {
        f.feld: f
        for f in pipeline.memory.case_state(tenant_id="tenant-A", session_id="sess-A")
    }
    assert facts["druck"].provenance == "user-form"


def test_batch_clarify_pending_is_rueckfrage_not_uebernommen():
    """A clarify-triggering value (500 mbar — real pressure, wrong scale) is a Rückfrage, never
    claimed as 'übernommen', and no PV is fabricated."""
    client, _ = make_client(_engine_pipeline())
    body = _batch(client, [{"feld": "druck", "wert": "500 mbar", "label": "Druck p"}]).json()
    assert all(u["feld"] != "druck" for u in body["uebernommen"])  # NOT taken
    rf = {x["feld"]: x for x in body["rueckfragen"]}
    assert "druck" in rf and rf["druck"]["label"] == "Druck p"
    assert rf["druck"]["clarification"]["reason"] == "unit_known_other"
    assert rf["druck"]["clarification"]["one_click"] is False  # no silent rescale to bar
    by_id = {c["calc_id"]: c for c in body["computed"]}
    assert "pv_wert" not in by_id  # no fabricated PV


def test_batch_settle_is_token_scoped():
    """Tenant A's batch never writes tenant B's case-state (P0)."""
    client, pipeline = make_client(_engine_pipeline())
    _batch(client, [{"feld": "wellendurchmesser", "wert": "50 mm"}], token="tok-A")
    assert pipeline.memory.case_state(tenant_id="tenant-B", session_id="sess-B") == ()
