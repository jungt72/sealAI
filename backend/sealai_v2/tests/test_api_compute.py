"""M8 (trust-spine completion) — Part 3: GET /api/v2/compute, the deterministic kernel READ surface.

Reads the session's current settled case-state, recomputes the kernel (NO LLM), persists the derived
slice, and returns the kernel result + honest "nicht berechenbar" reasons. Tenant + session come ONLY
from the verified token (P0). The Berechnungen panel reads this; the answer/briefing rest on the same
persisted values.
"""

from __future__ import annotations

from sealai_v2.core.contracts import ModelConfig
from sealai_v2.core.calc.evaluator import CascadeCalcEngine
from sealai_v2.core.l1_generator import L1Generator
from sealai_v2.memory.store import (
    InProcessConversationMemory,
    InProcessCrossSessionMemory,
)
from sealai_v2.pipeline.pipeline import Pipeline
from sealai_v2.prompts.assembler import PromptAssembler
from sealai_v2.tests._apiutil import auth, make_client
from sealai_v2.tests._fakes import FakeLlmClient


def _engine_pipeline(*, engine: bool = True, memory: bool = True) -> Pipeline:
    client = FakeLlmClient("ok")
    return Pipeline(
        generator=L1Generator(client, PromptAssembler(), ModelConfig("fake-l1")),
        client=client,
        helper_model=ModelConfig("fake-helper"),
        understand_enabled=False,
        engine=CascadeCalcEngine() if engine else None,
        memory=InProcessConversationMemory() if memory else None,
        cross_session=InProcessCrossSessionMemory() if memory else None,
    )


def _seed(client, *pairs, token: str = "tok-A") -> None:
    for feld, wert in pairs:
        client.put(
            f"/api/v2/conversations/current/facts/{feld}",
            json={"wert": wert, "origin": "user-form"},
            headers=auth(token),
        )


def test_compute_settled_inputs_returns_value_with_provenance():
    client, _ = make_client(_engine_pipeline())
    _seed(client, ("wellendurchmesser", "40 mm"), ("drehzahl", "8000 U/min"))
    r = client.get("/api/v2/compute", headers=auth("tok-A"))
    assert r.status_code == 200
    body = r.json()
    by_id = {c["calc_id"]: c for c in body["computed"]}
    v = by_id["umfangsgeschwindigkeit"]
    assert abs(v["value"] - 16.755) < 0.01
    assert v["unit"] == "m/s" and v["formula"]
    assert v["provenance"] == "kernel_computed"
    assert set(v["parent_fields"]) == {"wellendurchmesser", "drehzahl"}
    assert any("Formular" in o for o in v["input_origins"])


def test_compute_persists_the_derived_slice():
    client, pipeline = make_client(_engine_pipeline())
    _seed(client, ("wellendurchmesser", "40 mm"), ("drehzahl", "8000 U/min"))
    client.get("/api/v2/compute", headers=auth("tok-A"))
    d = pipeline.memory.derived_facts(tenant_id="tenant-A", session_id="sess-A")
    assert any(x.calc_id == "umfangsgeschwindigkeit" for x in d)


def test_compute_no_inputs_is_honest_no_number():
    client, _ = make_client(_engine_pipeline())
    r = client.get("/api/v2/compute", headers=auth("tok-A"))
    assert r.status_code == 200
    body = r.json()
    assert body["computed"] == []  # no fabricated value
    assert any(n["calc_id"] == "umfangsgeschwindigkeit" for n in body["not_computed"])


def test_compute_unitless_input_fails_closed_with_note():
    client, _ = make_client(_engine_pipeline())
    _seed(client, ("wellendurchmesser", "40 mm"), ("drehzahl", "8000"))  # unitless n
    body = client.get("/api/v2/compute", headers=auth("tok-A")).json()
    assert all(c["calc_id"] != "umfangsgeschwindigkeit" for c in body["computed"])
    assert any("drehzahl" in note for note in body["notes"])


def test_compute_is_tenant_scoped_via_token():
    """P0: tenant A's compute reads A's session only — B's seeded facts never leak in."""
    client, _ = make_client(_engine_pipeline())
    _seed(
        client,
        ("wellendurchmesser", "40 mm"),
        ("drehzahl", "8000 U/min"),
        token="tok-B",
    )
    body = client.get("/api/v2/compute", headers=auth("tok-A")).json()  # A is empty
    assert body["computed"] == []


def test_compute_case_id_query_param_targets_that_case():
    """The dashboard's Fälle URL must drive the compute read surface just like memory/facts."""
    client, _ = make_client(_engine_pipeline())
    client.put(
        "/api/v2/conversations/current/facts/wellendurchmesser",
        params={"case_id": "case-2"},
        json={"wert": "40 mm", "origin": "user-form"},
        headers=auth("tok-A"),
    )
    client.put(
        "/api/v2/conversations/current/facts/drehzahl",
        params={"case_id": "case-2"},
        json={"wert": "8000 U/min", "origin": "user-form"},
        headers=auth("tok-A"),
    )
    assert client.get("/api/v2/compute", headers=auth("tok-A")).json()["computed"] == []
    body = client.get(
        "/api/v2/compute", params={"case_id": "case-2"}, headers=auth("tok-A")
    ).json()
    assert any(c["calc_id"] == "umfangsgeschwindigkeit" for c in body["computed"])


def test_compute_503_when_compute_disabled():
    client, _ = make_client(_engine_pipeline(engine=False))
    assert client.get("/api/v2/compute", headers=auth("tok-A")).status_code == 503


def test_compute_503_when_memory_disabled():
    client, _ = make_client(_engine_pipeline(memory=False))
    assert client.get("/api/v2/compute", headers=auth("tok-A")).status_code == 503


def test_chat_response_additively_carries_computed():
    """A chat turn surfaces its in-band kern result so the panel can update without a 2nd round-trip
    (the authoritative settled read is still /compute, which flushes the background distill first)."""
    pipeline = _engine_pipeline()
    pipeline.memory.edit_fact(
        tenant_id="tenant-A",
        session_id="sess-A",
        feld="wellendurchmesser",
        wert="40 mm",
        provenance="user-form",
        owner_subject="user-A",
    )
    pipeline.memory.edit_fact(
        tenant_id="tenant-A",
        session_id="sess-A",
        feld="drehzahl",
        wert="8000 U/min",
        provenance="user-form",
        owner_subject="user-A",
    )
    client, _ = make_client(pipeline)
    body = client.post(
        "/api/v2/chat", json={"message": "Wie hoch ist v?"}, headers=auth("tok-A")
    ).json()
    assert "computed" in body and "not_computed" in body
    by_id = {c["calc_id"]: c for c in body["computed"]}
    assert abs(by_id["umfangsgeschwindigkeit"]["value"] - 16.755) < 0.01
