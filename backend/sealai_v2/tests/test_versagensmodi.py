"""Versagensmodi (Dim. 5) loader + store — schema, circularity guard, symptom retrieval.

Deterministic, offline, no LLM. The seed is CC-drafted (review_state=draft) → flag-only,
provisional, owner-review pending. The circularity guard forbids a model-generated REVIEWED
mode (build-spec §8 "no LLM erdet LLM").
"""

from __future__ import annotations

import pytest

from sealai_v2.knowledge.versagensmodi import (
    InProcessVersagensmodiStore,
    _mode,
    load_versagensmodi,
)


def test_seed_loads_and_is_all_draft():
    cat = load_versagensmodi()
    assert len(cat.modes) == 6
    # the whole seed is provisional until the owner reviews it
    assert all(m.review_state == "draft" for m in cat.modes)
    assert cat.reviewed == ()  # nothing authoritative yet


def test_every_mode_has_symptom_ursache_fix():
    for m in load_versagensmodi().modes:
        assert m.symptom and m.ursache and m.fix
        assert m.scope.get("symptom")  # retrievable by symptom


def test_query_retrieves_by_symptom():
    store = InProcessVersagensmodiStore()
    hits = store.query(
        tenant_id="t1",
        query_text="Meine Dichtlippe ist hart und rissig geworden, sie leckt",
    )
    assert any(m.id == "VM-RWDR-LIPPE-VERHAERTET" for m in hits)


def test_query_quellung_with_medium_context():
    store = InProcessVersagensmodiStore()
    hits = store.query(
        tenant_id="t1", query_text="die Dichtung quillt auf und wird weich in Mineralöl"
    )
    assert any(m.id == "VM-ELASTOMER-QUELLUNG" for m in hits)


def test_draft_quelle_marks_provisional():
    m = load_versagensmodi().by_id("VM-OZONRISSE")
    assert m is not None
    assert "vorläufig" in m.quelle().lower()
    assert m.reviewed is False


def test_circularity_guard_rejects_modelgenerated_reviewed():
    # A reviewed mode with neither owner/trap provenance nor a primary source is a load error.
    bad = {
        "id": "VM-BAD",
        "symptom": "x",
        "ursache": "y",
        "fix": "z",
        "review_state": "reviewed",
        "scope": {"symptom": ["x"]},
        "provenance": ["draft:CC"],  # not a reviewed-prefix
        "sources": [],
    }
    with pytest.raises(ValueError, match="no LLM erdet LLM|reviewed mode"):
        _mode(bad)


def test_reviewed_with_owner_provenance_loads():
    ok = {
        "id": "VM-OK",
        "symptom": "x",
        "ursache": "y",
        "fix": "z",
        "review_state": "reviewed",
        "scope": {"symptom": ["x"]},
        "provenance": ["owner:review-note"],
        "sources": [],
    }
    m = _mode(ok)
    assert m.reviewed is True


def test_tenant_gate_enforced():
    store = InProcessVersagensmodiStore()
    with pytest.raises(Exception):
        store.query(tenant_id="", query_text="rissig")
