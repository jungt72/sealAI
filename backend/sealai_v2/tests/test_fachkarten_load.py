"""Fachkarten loader + circularity-guard (two review paths) + the bootstrap faithfulness."""

from __future__ import annotations

import json

import pytest

from sealai_v2.knowledge.fachkarten import load_fachkarten


def _write(tmp_path, cards):
    p = tmp_path / "fk.json"
    p.write_text(json.dumps({"version": "t", "cards": cards}), encoding="utf-8")
    return p


def test_seed_loads_eight_reviewed_cards():
    cat = load_fachkarten()
    assert len(cat.cards) == 8
    assert len(cat.reviewed()) == 8
    # circularity guard held: every reviewed claim is owner/trap-grounded (path i) or sourced (path ii)
    for c in cat.cards:
        for cl in c.reviewed_claims():
            assert cl.owner_grounded or cl.sources, f"{c.id}: ungrounded reviewed claim"


def test_seed_provenance_names_source_trap():
    cat = load_fachkarten()
    for c in cat.cards:
        assert any(p.startswith("trap-correct:") for p in c.provenance), c.id


def test_foodgrade_carries_owner_vmq_nuance():
    fg = load_fachkarten().by_id("FK-FOODGRADE-FETT")
    nuance = [cl for cl in fg.claims if "moderate" in cl.text.lower()]
    assert nuance, "VMQ-moderate nuance missing"
    assert nuance[0].owner_grounded
    assert any(p.startswith("owner") for p in nuance[0].provenance)


def test_reviewed_claim_without_owner_or_source_is_load_error(tmp_path):
    bad = [
        {
            "id": "FK-BAD",
            "review_state": "reviewed",
            "provenance": ["trap-correct:X"],
            "scope": {"material": ["EPDM"]},
            "claims": [
                {
                    "text": "ein vom Modell erfundener Fakt",
                    "review_state": "reviewed",
                    "provenance": ["model_knowledge:UNREVIEWED"],
                }
            ],
        }
    ]
    with pytest.raises(ValueError, match="LLM erdet LLM"):
        load_fachkarten(_write(tmp_path, bad))


def test_path_i_owner_confirmed_needs_no_source(tmp_path):
    ok = [
        {
            "id": "FK-OWN",
            "review_state": "reviewed",
            "provenance": ["owner"],
            "scope": {"material": ["EPDM"]},
            "claims": [
                {
                    "text": "owner-bestätigt",
                    "review_state": "reviewed",
                    "provenance": ["owner"],
                }
            ],
        }
    ]
    assert (
        load_fachkarten(_write(tmp_path, ok)).by_id("FK-OWN").review_state == "reviewed"
    )


def test_path_ii_deep_research_with_primary_source_is_reviewed(tmp_path):
    ok = [
        {
            "id": "FK-RES",
            "review_state": "reviewed",
            "provenance": ["deep-research"],
            "scope": {"material": ["FKM"]},
            "claims": [
                {
                    "text": "FKM nach Norm",
                    "review_state": "reviewed",
                    "sources": ["ISO 23936-2"],
                    "provenance": ["deep-research"],
                }
            ],
        }
    ]
    assert (
        load_fachkarten(_write(tmp_path, ok)).by_id("FK-RES").review_state == "reviewed"
    )


def test_draft_claim_needs_no_source(tmp_path):
    ok = [
        {
            "id": "FK-DRAFT",
            "review_state": "draft",
            "provenance": ["trap-correct:X"],
            "scope": {"material": ["EPDM"]},
            "claims": [
                {
                    "text": "unbestätigt",
                    "review_state": "draft",
                    "provenance": ["model_knowledge:UNREVIEWED"],
                }
            ],
        }
    ]
    cat = load_fachkarten(_write(tmp_path, ok))
    assert cat.by_id("FK-DRAFT").review_state == "draft"
    assert not cat.by_id("FK-DRAFT").reviewed_claims()


def test_reviewed_card_without_reviewed_claim_is_error(tmp_path):
    bad = [
        {
            "id": "FK-X",
            "review_state": "reviewed",
            "provenance": ["trap-correct:X"],
            "scope": {"material": ["EPDM"]},
            "claims": [{"text": "d", "review_state": "draft", "provenance": ["m"]}],
        }
    ]
    with pytest.raises(ValueError):
        load_fachkarten(_write(tmp_path, bad))
