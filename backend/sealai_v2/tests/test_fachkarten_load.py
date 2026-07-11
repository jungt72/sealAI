"""Fachkarten loader, evidence gate, and bootstrap faithfulness."""

from __future__ import annotations

import json

import pytest

from sealai_v2.knowledge.fachkarten import load_fachkarten


def _write(tmp_path, cards):
    p = tmp_path / "fk.json"
    p.write_text(json.dumps({"version": "t", "cards": cards}), encoding="utf-8")
    return p


def test_seed_quarantines_claims_without_independent_human_review():
    cat = load_fachkarten()
    assert len(cat.reviewed()) == 0
    assert cat.by_id("FK-PHARMA-SIP-VALIDIERUNG").review_state == "draft"
    assert cat.by_id("FK-ERSATZDICHTUNG-IDENTIFIKATION").review_state == "draft"
    assert len(cat.cards) == 55
    assert sum(len(card.reviewed_claims()) for card in cat.cards) == 0
    assert sum(len(card.quarantined_claims()) for card in cat.cards) == 79


def test_reviewed_seed_requires_primary_source_grounding():
    cat = load_fachkarten()
    for c in cat.reviewed():
        assert all(claim.sources for claim in c.reviewed_claims()), c.id


def test_reviewed_nbr_profile_uses_user_facing_german_orthography():
    card = load_fachkarten().by_id("FK-NBR-UEBERBLICK")
    text = " ".join(claim.text for claim in card.claims)
    for ascii_spelling in (
        "ungesaettigt",
        "hoeher",
        "Mineraloele",
        "Bestaendigkeit",
        "Schlaeuche",
        "geprueft",
    ):
        assert ascii_spelling not in text
    for german_spelling in (
        "ungesättigter",
        "Mineralöle",
        "Beständigkeit",
        "Schläuche",
    ):
        assert german_spelling in text


def test_foodgrade_carries_owner_vmq_nuance():
    fg = load_fachkarten().by_id("FK-FOODGRADE-FETT")
    nuance = [cl for cl in fg.claims if "moderate" in cl.text.lower()]
    assert nuance, "VMQ-moderate nuance missing"
    assert nuance[0].owner_grounded
    assert any(p.startswith("owner") for p in nuance[0].provenance)


def test_reviewed_claim_without_source_is_quarantined(tmp_path):
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
    claim = load_fachkarten(_write(tmp_path, bad)).by_id("FK-BAD").claims[0]
    assert claim.review_state == "quarantined"
    assert claim.quarantined


def test_owner_confirmation_without_source_is_not_authoritative(tmp_path):
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
    card = load_fachkarten(_write(tmp_path, ok)).by_id("FK-OWN")
    assert card.review_state == "draft"
    assert card.claims[0].review_state == "quarantined"


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
                    "reviewed_by": "domain-reviewer:alice",
                    "reviewed_at": "2026-07-11T10:00:00Z",
                    "review_expires_at": "2099-07-11T10:00:00Z",
                }
            ],
        }
    ]
    assert (
        load_fachkarten(_write(tmp_path, ok)).by_id("FK-RES").review_state == "reviewed"
    )


def test_model_review_marker_is_not_independent_human_review(tmp_path):
    cards = [
        {
            "id": "FK-AI",
            "review_state": "reviewed",
            "provenance": ["deep-research"],
            "scope": {"material": ["FKM"]},
            "claims": [
                {
                    "text": "Source-backed but not human-adjudicated",
                    "review_state": "reviewed",
                    "sources": ["ISO 23936-2"],
                    "provenance": ["deep-research"],
                    "reviewed_by": "review:codex",
                    "reviewed_at": "2026-07-11T10:00:00Z",
                    "review_expires_at": "2099-07-11T10:00:00Z",
                }
            ],
        }
    ]

    claim = load_fachkarten(_write(tmp_path, cards)).cards[0].claims[0]
    assert claim.quarantined


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


def test_declared_reviewed_card_without_evidenced_claim_is_downgraded(tmp_path):
    bad = [
        {
            "id": "FK-X",
            "review_state": "reviewed",
            "provenance": ["trap-correct:X"],
            "scope": {"material": ["EPDM"]},
            "claims": [{"text": "d", "review_state": "draft", "provenance": ["m"]}],
        }
    ]
    assert load_fachkarten(_write(tmp_path, bad)).by_id("FK-X").review_state == "draft"


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
