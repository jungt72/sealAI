"""Fachkarten loader, evidence gate, and bootstrap faithfulness."""

from __future__ import annotations

import json

import pytest

from sealai_v2.knowledge.fachkarten import load_fachkarten


def _write(tmp_path, cards):
    p = tmp_path / "fk.json"
    p.write_text(json.dumps({"version": "t", "cards": cards}), encoding="utf-8")
    return p


def test_seed_carries_the_independent_owner_review_without_promoting_drafts():
    cat = load_fachkarten()
    assert len(cat.reviewed()) == 17
    assert cat.by_id("FK-PHARMA-SIP-VALIDIERUNG").review_state == "reviewed"
    assert cat.by_id("FK-ERSATZDICHTUNG-IDENTIFIKATION").review_state == "reviewed"
    assert len(cat.cards) == 55
    assert sum(len(card.reviewed_claims()) for card in cat.cards) == 79
    assert sum(len(card.draft_claims()) for card in cat.cards) == 522
    assert sum(len(card.quarantined_claims()) for card in cat.cards) == 0


def test_reviewed_seed_requires_explicit_evidence_grounding():
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


def test_source_refresh_binds_high_risk_claims_to_exact_primary_evidence():
    cat = load_fachkarten()

    ptfe = cat.by_id("FK-PTFE-ENGINEERING-PROFILE")
    temperature = next(claim for claim in ptfe.claims if "Turcon T01" in claim.text)
    assert "Edition June 2026" in temperature.sources[0]
    assert "Table 3, page 7" in temperature.sources[0]
    assert (
        "171d5881149e03a5592b0497b6f4d77356dee96bf8e805fe2d91e570f49e5f93"
        in temperature.sources[0]
    )

    rwdr = cat.by_id("FK-RWDR-ENGINEERING-PROFILE")
    shaft = next(claim for claim in rwdr.claims if "mindestens 45 HRC" in claim.text)
    assert "Laboroptimum von Rt 2 Mikrometer" in shaft.text
    assert "Ra 0,2 bis 0,5 Mikrometer" in shaft.text
    assert "page 41, Edition April 2026" in shaft.sources[0]
    assert (
        "9b1d5310574e8da4726c7f0406bd9a10685cd4ce0c71c2b9962520b76ae1fd38"
        in shaft.sources[0]
    )


def test_oring_gland_fill_uses_parker_section_3_7_contract():
    card = load_fachkarten().by_id("FK-ORING-VERPRESSUNG")
    claim = next(item for item in card.claims if "Nutfüllung" in item.text)
    assert "60 bis 85 Prozent" in claim.text
    assert "75 Prozent als Optimum" in claim.text
    assert "mindestens 10 Prozent freien Nutraum" in claim.text
    assert "Section 3.7 Gland Fill, page 3-9" in claim.sources[0]
    assert "75–90" not in claim.text


def test_active_fkm_steam_claim_uses_correct_orthography():
    card = load_fachkarten().by_id("FK-FKM-DAMPF")
    text = " ".join(claim.text for claim in card.claims)
    assert "versprödet" in text
    assert "verspröttet" not in text


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


def test_release_bootstrap_is_not_independent_human_review(tmp_path):
    cards = [
        {
            "id": "FK-BOOTSTRAP",
            "review_state": "reviewed",
            "provenance": ["release-bootstrap"],
            "scope": {"material": ["FKM"]},
            "claims": [
                {
                    "text": "Source-backed but only release-imported",
                    "review_state": "reviewed",
                    "sources": ["ISO 23936-2"],
                    "provenance": ["release-bootstrap"],
                    "reviewed_by": "release-bootstrap",
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
