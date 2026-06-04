from __future__ import annotations

from app.agent.domain.checks_registry import (
    build_check_metrics,
    build_registered_check_results,
)
from app.agent.domain.compatibility_precheck import (
    build_material_medium_compatibility_precheck,
)
from app.agent.v92.contracts import FinalAnswerContext
from app.agent.v92.final_guard import validate_final_output
from app.api.v1.projections.case_workspace import project_case_workspace


def _card(
    *,
    card_id: str = "compat-fkm-hlp",
    material: str = "FKM",
    medium: str = "HLP",
    status: str = "supported_precheck",
    claim_level: str = "L2",
    source_type: str = "fact_card",
    **extra: object,
) -> dict[str, object]:
    return {
        "schema_version": "material_evidence_card.v1",
        "card_id": card_id,
        "material": material,
        "medium": medium,
        "compatibility_status": status,
        "claim_level": claim_level,
        "claim_type": "compatibility_precheck",
        "source_type": source_type,
        "source_title": "Curated compatibility orientation",
        "source_hash": f"sha256:{card_id}",
        "excerpt_short": "Evidence-backed precheck context only.",
        "statement_short": "Evidence-backed precheck context only.",
        "limitations": [],
        "final_approval_claim_allowed": False,
        "compliance_claim_allowed": False,
        **extra,
    }


def _profile(**extra: object) -> dict[str, object]:
    return {
        "sealing_type": "rwdr",
        "medium": "HLP",
        "material": "FKM",
        "temperature_c": 80,
        **extra,
    }


def _workspace(profile: dict[str, object]) -> dict[str, object]:
    return {
        "conversation": {"thread_id": "patch7-evidence"},
        "working_profile": {
            "engineering_profile": {
                "movement_type": "rotary",
                "installation": "Radialwellendichtring",
                "sealing_type": "RWDR",
                **profile,
            },
            "completeness": {"missing_critical_parameters": []},
        },
        "reasoning": {"phase": "clarification", "state_revision": 1},
        "system": {
            "governance_metadata": {"release_status": "precheck_only"},
            "rfq_admissibility": {
                "release_status": "precheck_only",
                "status": "precheck_only",
            },
            "matching_state": {},
            "rfq_state": {},
            "manufacturer_state": {},
        },
    }


def _compat_check(profile: dict[str, object]) -> dict[str, object]:
    return next(
        item
        for item in build_registered_check_results(
            profile={"sealing_type": "rwdr", **profile},
            engineering_path="rwdr",
            technical_derivations=[],
        )
        if item["calc_id"] == "material_medium_compatibility_precheck"
    )


def _final_context() -> FinalAnswerContext:
    return FinalAnswerContext(
        turn_id="turn-patch7",
        case_id="case-patch7",
        case_revision=1,
        route="engineering_recommendation",
        intent="engineering_recommendation",
        is_technical=True,
        user_message="Ist FKM gegen HLP geeignet?",
    )


def test_compatibility_precheck_no_evidence_remains_insufficient() -> None:
    item = build_material_medium_compatibility_precheck(_profile())

    assert item.status == "insufficient_evidence"
    assert item.evidence_status == "no_evidence"
    assert item.evidence_refs == []
    assert "compatibility_evidence" in item.missing_fields
    assert item.final_approval_claim_allowed is False


def test_evidence_card_supports_precheck_without_final_approval() -> None:
    item = build_material_medium_compatibility_precheck(
        _profile(compatibility_evidence_cards=[_card()])
    )

    assert item.status == "supported_precheck"
    assert item.evidence_status == "evidence_found"
    assert item.evidence_refs[0].card_id == "compat-fkm-hlp"
    assert item.final_approval_claim_allowed is False
    wording = item.allowed_user_wording.casefold()
    assert "precheck" in wording
    assert "kandidat" in wording
    assert "geeignet" not in wording
    assert "kompatibel" not in wording


def test_family_level_card_is_only_orientation() -> None:
    item = build_material_medium_compatibility_precheck(
        _profile(
            compatibility_evidence_cards=[
                {
                    "card_id": "compat-family-oil",
                    "schema_version": "material_evidence_card.v1",
                    "material_family": "FKM",
                    "medium_family": "oelhaltig",
                    "compatibility_status": "supported_precheck",
                    "claim_level": "L2",
                    "claim_type": "compatibility_precheck",
                    "source_type": "fact_card",
                    "source_title": "Curated family orientation",
                    "source_hash": "sha256:compat-family-oil",
                    "statement_short": "Evidence-backed family orientation only.",
                    "limitations": ["family_level_only"],
                    "final_approval_claim_allowed": False,
                    "compliance_claim_allowed": False,
                }
            ]
        )
    )

    assert item.status == "caution_zone"
    assert item.evidence_status == "evidence_found"
    assert item.evidence_refs
    assert item.final_approval_claim_allowed is False
    assert "geeignet" not in item.allowed_user_wording.casefold()


def test_temperature_outside_card_range_creates_caution() -> None:
    item = build_material_medium_compatibility_precheck(
        _profile(
            temperature_c=140,
            compatibility_evidence_cards=[
                _card(temperature_min_c=0, temperature_max_c=100)
            ],
        )
    )

    assert item.status == "insufficient_evidence"
    assert item.evidence_status == "insufficient_evidence"
    assert any("temperature" in item.casefold() for item in item.evidence_limitations)
    assert item.final_approval_claim_allowed is False


def test_missing_concentration_limits_acid_base_evidence() -> None:
    item = build_material_medium_compatibility_precheck(
        {
            "medium": "Natronlauge",
            "material": "EPDM",
            "temperature_c": 50,
            "compatibility_evidence_cards": [
                _card(
                    card_id="compat-epdm-naoh",
                    material="EPDM",
                    medium="Natronlauge",
                    requires_concentration=True,
                )
            ],
        }
    )

    assert item.status == "missing_input"
    assert item.compatibility_claim_type == "missing_concentration"
    assert item.evidence_status == "insufficient_evidence"
    assert "concentration" in item.missing_fields
    assert any("concentration" in item for item in item.evidence_limitations)


def test_conflicting_cards_block_strong_claim() -> None:
    item = build_material_medium_compatibility_precheck(
        _profile(
            compatibility_evidence_cards=[
                _card(card_id="compat-positive", status="supported_precheck"),
                _card(card_id="compat-negative", status="not_supported"),
            ]
        )
    )

    assert item.status == "caution_zone"
    assert item.evidence_status == "conflicting_evidence"
    assert len(item.evidence_refs) == 2
    assert item.final_approval_claim_allowed is False


def test_compliance_requires_certificate_evidence() -> None:
    item = build_material_medium_compatibility_precheck(
        _profile(compliance="FDA Food", compatibility_evidence_cards=[_card()])
    )

    assert item.status == "blocked_claim"
    assert item.compatibility_claim_type == "compliance_evidence_required"
    assert item.evidence_status == "compliance_evidence_required"
    assert "compliance_evidence" in item.missing_fields
    assert item.final_approval_claim_allowed is False


def test_final_guard_blocks_compatibility_claim_without_evidence_ref() -> None:
    result = validate_final_output("FKM geeignet fuer HLP.", context=_final_context())

    assert result.decision == "block"
    assert result.final_stream_allowed is False
    assert "absolute_material_medium_compatibility" in result.detected_forbidden_claims


def test_workspace_projection_exposes_evidence_refs() -> None:
    projection = project_case_workspace(
        _workspace(
            _profile(
                pressure_at_seal_bar=1,
                shaft_diameter_mm=50,
                speed_rpm=1500,
                compatibility_evidence_cards=[_card()],
            )
        )
    )
    check = {
        item.calc_id: item for item in projection.cockpit_view.checks
    }["material_medium_compatibility_precheck"]

    assert check.status == "passed"
    assert check.evidence_status == "evidence_found"
    assert check.evidence_refs[0].card_id == "compat-fkm-hlp"
    assert check.evidence_refs[0].source_type == "fact_card"
    assert check.final_approval_claim_allowed is False


def test_check_metrics_count_evidence_backed_precheck_correctly() -> None:
    evidence_backed = _compat_check(
        _profile(compatibility_evidence_cards=[_card()])
    )
    no_evidence = _compat_check(_profile())
    metrics = build_check_metrics([evidence_backed, no_evidence])

    assert evidence_backed["status"] == "passed"
    assert no_evidence["status"] == "blocked"
    assert metrics["check_passed_count"] == 1
    assert metrics["check_blocked_count"] == 1
    assert metrics["check_available_count"] == 1
