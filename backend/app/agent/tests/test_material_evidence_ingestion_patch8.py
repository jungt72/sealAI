from __future__ import annotations

from app.agent.domain.compatibility_precheck import (
    build_material_medium_compatibility_precheck,
)
from app.agent.domain.material_evidence_cards import (
    validate_material_evidence_card,
    validate_material_evidence_cards,
)


def _card(**extra: object) -> dict[str, object]:
    card: dict[str, object] = {
        "schema_version": "material_evidence_card.v1",
        "card_id": "compat-fkm-hlp",
        "material": "FKM",
        "medium": "HLP",
        "temperature_min_c": -20,
        "temperature_max_c": 100,
        "claim_level": "L2",
        "claim_type": "compatibility_precheck",
        "statement_short": "Evidence-backed precheck context only.",
        "source_title": "Curated compatibility orientation",
        "source_type": "fact_card",
        "source_hash": "sha256:compat-fkm-hlp",
        "limitations": [],
        "final_approval_claim_allowed": False,
        "compliance_claim_allowed": False,
    }
    card.update(extra)
    return card


def test_valid_exact_card_passes_validation() -> None:
    result = validate_material_evidence_card(
        _card(
            card_id="compat-fkm-water",
            material="FKM",
            medium="water",
            temperature_min_c=0,
            temperature_max_c=80,
        )
    )

    assert result.valid is True
    assert result.support_allowed is True
    assert result.normalized_card is not None
    assert result.normalized_card["material"] == "FKM"
    assert result.normalized_card["medium"] == "water"
    assert result.normalized_card["medium_canonical"] == "Wasser"
    assert result.normalized_card["final_approval_claim_allowed"] is False


def test_missing_source_is_invalid_or_insufficient() -> None:
    raw = _card()
    raw.pop("source_title")
    raw.pop("source_hash")

    result = validate_material_evidence_card(raw)

    assert result.valid is False
    assert result.status == "invalid"
    assert "missing_source_metadata" in result.reasons


def test_unknown_schema_version_rejected() -> None:
    result = validate_material_evidence_card(_card(schema_version="material_evidence_card.v9"))

    assert result.valid is False
    assert "unsupported_schema_version" in result.reasons


def test_final_approval_wording_is_rejected_or_downgraded() -> None:
    overclaim = _card(statement_short="FKM ist freigegeben, approved und suitable.")
    result = validate_material_evidence_card(overclaim)
    item = build_material_medium_compatibility_precheck(
        {
            "medium": "HLP",
            "material": "FKM",
            "temperature_c": 80,
            "compatibility_evidence_cards": [overclaim],
        }
    )

    assert result.valid is False
    assert result.status == "downgraded"
    assert any("overclaim_wording" in claim for claim in result.blocked_claims)
    assert item.status == "insufficient_evidence"
    assert item.evidence_refs == []
    assert any("invalid_evidence_card" in item for item in item.evidence_limitations)


def test_compliance_claim_requires_certificate_metadata() -> None:
    compliance_card = _card(
        card_id="fda-without-source",
        claim_type="compliance_certificate",
        statement_short="FDA-konform.",
        compliance_claim_allowed=True,
        source_hash="",
        source_url="",
        doi="",
        manufacturer="",
    )
    result = validate_material_evidence_card(compliance_card)
    item = build_material_medium_compatibility_precheck(
        {
            "medium": "Wasser",
            "material": "EPDM",
            "temperature_c": 60,
            "compliance": "FDA Food",
            "compatibility_evidence_cards": [compliance_card],
        }
    )

    assert result.valid is False
    assert "missing_source_metadata" in result.reasons
    assert item.status == "blocked_claim"
    assert item.evidence_status == "compliance_evidence_required"
    assert item.final_approval_claim_allowed is False


def test_family_level_card_cannot_create_exact_support() -> None:
    item = build_material_medium_compatibility_precheck(
        {
            "medium": "HLP",
            "material": "FKM",
            "temperature_c": 80,
            "compatibility_evidence_cards": [
                _card(
                    card_id="compat-family-oil",
                    material="",
                    medium="",
                    material_family="FKM",
                    medium_family="oil",
                    limitations=["family_level_only"],
                )
            ],
        }
    )

    assert item.status == "caution_zone"
    assert item.evidence_status == "evidence_found"
    assert item.evidence_refs
    assert item.final_approval_claim_allowed is False


def test_temperature_outside_card_range_adds_limitation() -> None:
    item = build_material_medium_compatibility_precheck(
        {
            "medium": "HLP",
            "material": "FKM",
            "temperature_c": 140,
            "compatibility_evidence_cards": [_card(temperature_max_c=100)],
        }
    )

    assert item.status == "insufficient_evidence"
    assert item.evidence_status == "insufficient_evidence"
    assert any("temperature" in limitation for limitation in item.evidence_limitations)


def test_acid_base_card_without_concentration_has_limitation() -> None:
    result = validate_material_evidence_card(
        _card(
            card_id="compat-epdm-naoh",
            material="EPDM",
            medium="Natronlauge",
            temperature_min_c=0,
            temperature_max_c=80,
        )
    )

    assert result.valid is True
    assert result.support_allowed is False
    assert "missing_concentration" in result.limitations


def test_invalid_card_not_consumed_by_compatibility_precheck() -> None:
    invalid = _card(source_title="", source_hash="")
    item = build_material_medium_compatibility_precheck(
        {
            "medium": "HLP",
            "material": "FKM",
            "temperature_c": 80,
            "compatibility_evidence_cards": [invalid],
        }
    )

    assert item.status == "insufficient_evidence"
    assert item.evidence_status == "no_evidence"
    assert item.evidence_refs == []
    assert any("invalid_evidence_card" in item for item in item.evidence_limitations)


def test_valid_card_becomes_evidence_ref_for_precheck() -> None:
    item = build_material_medium_compatibility_precheck(
        {
            "medium": "HLP",
            "material": "FKM",
            "temperature_c": 80,
            "compatibility_evidence_cards": [_card()],
        }
    )

    assert item.status == "supported_precheck"
    assert item.evidence_status == "evidence_found"
    assert item.evidence_refs[0].card_id == "compat-fkm-hlp"
    assert item.final_approval_claim_allowed is False
    assert "precheck" in item.allowed_user_wording.casefold()


def test_conflicting_exact_duplicate_card_id_rejected() -> None:
    results = validate_material_evidence_cards([_card(), _card(statement_short="Second card.")])

    assert results[0].valid is True
    assert results[1].valid is False
    assert "duplicate_card_id" in results[1].reasons
