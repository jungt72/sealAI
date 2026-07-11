"""Fachkarten loader + circularity-guard (two review paths) + the bootstrap faithfulness."""

from __future__ import annotations

import json

import pytest

from sealai_v2.knowledge.fachkarten import load_fachkarten


def _write(tmp_path, cards):
    p = tmp_path / "fk.json"
    p.write_text(json.dumps({"version": "t", "cards": cards}), encoding="utf-8")
    return p


def test_seed_loads_twelve_reviewed_cards():
    # The original 11 reviewed cards are joined by the primary-source-reviewed NBR overview;
    # the remaining research cards stay draft.
    cat = load_fachkarten()
    assert len(cat.reviewed()) == 12
    assert cat.by_id("FK-PHARMA-SIP-VALIDIERUNG").review_state == "reviewed"
    assert cat.by_id("FK-ERSATZDICHTUNG-IDENTIFIKATION").review_state == "reviewed"
    assert len(cat.cards) == 50
    # circularity guard held: every reviewed claim is owner/trap-grounded (path i) or sourced (path ii)
    # — checked across ALL cards (a draft card's reviewed_claims() is always empty by construction, so
    # this is equivalent to iterating cat.reviewed(), just doesn't assume which cards are reviewed).
    for c in cat.cards:
        for cl in c.reviewed_claims():
            assert cl.owner_grounded or cl.sources, f"{c.id}: ungrounded reviewed claim"


def test_reviewed_seed_uses_owner_or_primary_source_grounding():
    # Reviewed claims may use path (i), owner/trap grounding, or path (ii), verified primary sources.
    # This mirrors the loader's circularity guard instead of incorrectly requiring every reviewed
    # card to use the older owner-only path.
    grounding = ("owner", "eval:", "trap-correct:")
    cat = load_fachkarten()
    for c in cat.reviewed():
        card_owner_grounded = any(p.startswith(grounding) for p in c.provenance)
        assert card_owner_grounded or all(
            claim.owner_grounded or claim.sources for claim in c.reviewed_claims()
        ), c.id


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


def test_claim_kind_defaults_to_family_tendency(tmp_path):
    ok = [
        {
            "id": "FK-K",
            "review_state": "draft",
            "provenance": ["claude-research:x"],
            "scope": {"material": ["NBR"]},
            "claims": [
                {
                    "text": "NBR tendiert zu Oelbestaendigkeit",
                    "review_state": "draft",
                    "provenance": ["x"],
                }
            ],
        }
    ]
    assert (
        load_fachkarten(_write(tmp_path, ok)).by_id("FK-K").claims[0].kind
        == "family_tendency"
    )


def test_claim_kind_is_carried(tmp_path):
    ok = [
        {
            "id": "FK-K2",
            "review_state": "draft",
            "provenance": ["claude-research:x"],
            "scope": {"material": ["FKM"]},
            "claims": [
                {
                    "text": "70 Shore A (Compound XY, Datenblatt)",
                    "review_state": "draft",
                    "kind": "example_value",
                    "provenance": ["x"],
                },
                {
                    "text": "FKM in Glykol-Bremsfluessigkeit ungeeignet",
                    "review_state": "draft",
                    "kind": "safety_nogo",
                    "provenance": ["x"],
                },
            ],
        }
    ]
    claims = load_fachkarten(_write(tmp_path, ok)).by_id("FK-K2").claims
    assert claims[0].kind == "example_value"
    assert claims[1].kind == "safety_nogo"


def test_invalid_claim_kind_is_load_error(tmp_path):
    bad = [
        {
            "id": "FK-KBAD",
            "review_state": "draft",
            "provenance": ["claude-research:x"],
            "scope": {"material": ["NBR"]},
            "claims": [
                {
                    "text": "x",
                    "review_state": "draft",
                    "kind": "nonsense",
                    "provenance": ["x"],
                }
            ],
        }
    ]
    with pytest.raises(ValueError, match="kind"):
        load_fachkarten(_write(tmp_path, bad))


def test_extended_claim_kinds_load(tmp_path):
    # the re-challenge 4→8 additions: definition / regulatory_status / qualification_required / safety_caution
    ok = [
        {
            "id": "FK-K8",
            "review_state": "draft",
            "provenance": ["claude-research:x"],
            "scope": {"material": ["FKM"], "medium": ["Bremsfluessigkeit"]},
            "claims": [
                {
                    "text": "FKM ist nach ISO 1629 genormt",
                    "review_state": "draft",
                    "kind": "definition",
                    "provenance": ["x"],
                },
                {
                    "text": "EU 1935/2004 ist die Rahmenverordnung fuer Lebensmittelkontakt",
                    "review_state": "draft",
                    "kind": "regulatory_status",
                    "provenance": ["x"],
                },
                {
                    "text": "RGD-Eignung nur nach ISO 23936-2 / Herstellerqualifikation",
                    "review_state": "draft",
                    "kind": "qualification_required",
                    "provenance": ["x"],
                },
                {
                    "text": "Amine im Kuehlmittel koennen FKM angreifen",
                    "review_state": "draft",
                    "kind": "safety_caution",
                    "provenance": ["x"],
                },
            ],
        }
    ]
    kinds = [
        cl.kind for cl in load_fachkarten(_write(tmp_path, ok)).by_id("FK-K8").claims
    ]
    assert kinds == [
        "definition",
        "regulatory_status",
        "qualification_required",
        "safety_caution",
    ]
