from __future__ import annotations

from app.agent.domain.compatibility_precheck import (
    build_material_medium_compatibility_precheck,
)
from app.agent.domain.checks_registry import build_registered_check_results
from app.agent.runtime.clarification_priority import select_clarification_priority
from app.agent.state.models import (
    AssertedClaim,
    AssertedState,
    GovernedSessionState,
    MediumCaptureState,
    MediumClassificationState,
)
from app.agent.v92.contracts import FinalAnswerContext
from app.agent.v92.final_guard import validate_final_output
from app.api.v1.projections.case_workspace import project_case_workspace


def _state(
    assertions: dict[str, object],
    *,
    medium_status: str = "recognized",
    medium_family: str = "chemisch_aggressiv",
    raw_medium: str | None = None,
) -> GovernedSessionState:
    return GovernedSessionState(
        asserted=AssertedState(
            assertions={
                key: AssertedClaim(field_name=key, asserted_value=value)
                for key, value in assertions.items()
            }
        ),
        medium_capture=MediumCaptureState(
            raw_mentions=[raw_medium or str(assertions.get("medium") or "")],
            primary_raw_text=raw_medium or str(assertions.get("medium") or ""),
        ),
        medium_classification=MediumClassificationState(
            canonical_label=str(assertions.get("medium") or "") or None,
            family=medium_family,  # type: ignore[arg-type]
            confidence="medium",
            status=medium_status,  # type: ignore[arg-type]
        ),
    )


def _workspace(profile: dict[str, object]) -> dict[str, object]:
    return {
        "conversation": {"thread_id": "patch6-compatibility"},
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


def _support_card() -> dict[str, object]:
    return {
        "schema_version": "material_evidence_card.v1",
        "card_id": "compat-fkm-hlp",
        "material": "FKM",
        "medium": "HLP",
        "claim_level": "L2",
        "claim_type": "compatibility_precheck",
        "source_type": "fact_card",
        "source_title": "Curated FKM/HLP orientation card",
        "source_hash": "sha256:patch6-fkm-hlp",
        "limitations": [],
        "final_approval_claim_allowed": False,
        "compliance_claim_allowed": False,
        "compatibility_status": "supported_precheck",
        "excerpt_short": "FKM/HLP orientation under bounded precheck conditions.",
        "statement_short": "Evidence-backed precheck context only.",
    }


def test_unknown_medium_blocks_compatibility_claim() -> None:
    item = build_material_medium_compatibility_precheck(
        {"medium": "das medium", "material": "FKM", "temperature_c": 80}
    )

    assert item.status == "missing_input"
    assert item.compatibility_claim_type == "missing_medium"
    assert "medium" in item.missing_fields
    assert item.final_approval_claim_allowed is False
    assert "eindeutig benannt" in item.allowed_user_wording


def test_unknown_material_blocks_compatibility_claim() -> None:
    item = build_material_medium_compatibility_precheck(
        {"medium": "Wasser", "temperature_c": 80}
    )

    assert item.status == "missing_input"
    assert item.compatibility_claim_type == "missing_material"
    assert "material" in item.missing_fields
    assert item.final_approval_claim_allowed is False


def test_generic_chemical_requires_more_detail() -> None:
    item = build_material_medium_compatibility_precheck(
        {"medium": "Reiniger", "material": "FKM", "temperature_c": 40}
    )

    assert item.status == "ambiguous_input"
    assert item.compatibility_claim_type == "ambiguous_medium"
    assert "medium" in item.ambiguous_fields
    assert "genaue Spezifikation offen" in item.allowed_user_wording


def test_acid_or_base_without_concentration_is_caution_or_missing() -> None:
    check = _compat_check(
        {"medium": "Natronlauge", "material": "EPDM", "temperature_c": 50}
    )

    assert check["status"] == "blocked"
    assert check["compatibility_status"] == "missing_input"
    assert check["compatibility_claim_type"] == "missing_concentration"
    assert "concentration" in check["missing_fields"]
    assert check["value"] is None


def test_material_medium_precheck_requires_temperature_when_temperature_dependent() -> (
    None
):
    item = build_material_medium_compatibility_precheck(
        {"medium": "HLP", "material": "FKM"}
    )

    assert item.status == "missing_input"
    assert item.compatibility_claim_type == "missing_temperature"
    assert "temperature_c" in item.missing_fields
    assert "Betriebstemperatur fehlt" in item.allowed_user_wording


def test_supported_precheck_is_not_final_approval() -> None:
    check = _compat_check(
        {
            "medium": "HLP",
            "material": "FKM",
            "temperature_c": 80,
            "compatibility_evidence_cards": [_support_card()],
        }
    )

    assert check["status"] == "passed"
    assert check["compatibility_status"] == "supported_precheck"
    assert check["evidence_status"] == "evidence_found"
    assert check["evidence_refs"]
    assert check["final_approval_claim_allowed"] is False
    wording = str(check["allowed_user_wording"]).casefold()
    assert "precheck" in wording
    assert "kandidat" in wording
    assert "geeignet" not in wording
    assert "freigegeben" not in wording


def test_compliance_claim_requires_explicit_evidence() -> None:
    item = build_material_medium_compatibility_precheck(
        {
            "medium": "Wasser",
            "material": "EPDM",
            "temperature_c": 60,
            "compliance": "FDA Food",
        }
    )

    assert item.status == "blocked_claim"
    assert item.compatibility_claim_type == "compliance_evidence_required"
    assert "compliance_evidence" in item.missing_fields
    assert item.final_approval_claim_allowed is False


def test_final_guard_blocks_absolute_compatibility_wording_without_evidence() -> None:
    context = FinalAnswerContext(
        turn_id="turn-patch6",
        case_id="case-patch6",
        case_revision=1,
        route="engineering_recommendation",
        intent="engineering_recommendation",
        is_technical=True,
        user_message="Ist FKM kompatibel?",
    )

    result = validate_final_output("FKM ist bestaendig gegen HLP.", context=context)

    assert result.decision == "block"
    assert result.final_stream_allowed is False
    assert "absolute_material_medium_compatibility" in result.detected_forbidden_claims


def test_question_planner_asks_exact_medium_for_compatibility() -> None:
    priority = select_clarification_priority(
        _state(
            {"medium": "Reiniger", "material": "FKM"},
            medium_status="family_only",
            raw_medium="Reiniger",
        ),
        ["medium"],
    )

    assert priority is not None
    assert priority.focus_key == "medium"
    assert "reinigungsloesung" in priority.question.casefold()
    assert "konzentration" in priority.question.casefold()
    assert priority.reason


def test_compatibility_check_metrics_backend_derived() -> None:
    projection = project_case_workspace(
        _workspace(
            {
                "medium": "Natronlauge",
                "material": "EPDM",
                "temperature_c": 50,
                "pressure_at_seal_bar": 1,
                "shaft_diameter_mm": 50,
                "speed_rpm": 1500,
            }
        )
    )
    checks = {check.calc_id: check for check in projection.cockpit_view.checks}
    check = checks["material_medium_compatibility_precheck"]

    assert check.status == "blocked"
    assert check.compatibility_status == "missing_input"
    assert check.compatibility_claim_type == "missing_concentration"
    assert "concentration" in check.missing_fields
    assert projection.cockpit_view.check_metrics.check_blocked_count >= 1
    assert check.status not in {"passed", "failed"}
