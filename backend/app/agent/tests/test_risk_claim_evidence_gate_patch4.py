from __future__ import annotations

from app.agent.domain.challenge_engine import build_challenge_state
from app.agent.domain.risk_readiness import evaluate_risks
from app.agent.state.models import AssertedClaim, AssertedState, GovernedSessionState
from app.agent.v92.contracts import FinalAnswerContext
from app.agent.v92.final_guard import validate_final_output


def _risk_payloads(
    profile: dict[str, object], *, engineering_path: str = "rwdr"
) -> list[dict[str, object]]:
    return [
        risk.to_dict()
        for risk in evaluate_risks(profile, engineering_path=engineering_path)
    ]


def _risk_by_name(payloads: list[dict[str, object]], name: str) -> dict[str, object]:
    return next(item for item in payloads if item["risk_name"] == name)


def _state(assertions: dict[str, object]) -> GovernedSessionState:
    return GovernedSessionState(
        asserted=AssertedState(
            assertions={
                key: AssertedClaim(field_name=key, asserted_value=value)
                for key, value in assertions.items()
            }
        )
    )


def _final_context(
    *, risk_findings: list[dict[str, object]] | None = None
) -> FinalAnswerContext:
    return FinalAnswerContext(
        turn_id="turn-patch4",
        case_id="case-patch4",
        case_revision=1,
        route="engineering_recommendation",
        intent="engineering_recommendation",
        is_technical=True,
        user_message="Bitte bewerte die Risiken.",
        risk_findings=list(risk_findings or []),
    )


def test_no_high_runout_claim_without_runout_value() -> None:
    payloads = _risk_payloads({"sealing_type": "rwdr"})
    surface = _risk_by_name(payloads, "surface_risk")

    assert surface["claim_type"] == "missing_input_risk"
    assert "runout_mm" in surface["missing_fields"]
    assert (
        "offen" in str(surface["allowed_user_wording"]).casefold()
        or "nicht angegeben" in str(surface["allowed_user_wording"]).casefold()
    )
    assert "Der Wellenschlag ist hoch." in surface["forbidden_user_wording"]
    assert all(
        not (
            item["risk_name"] == "runout_risk" and item["claim_type"] == "measured_risk"
        )
        for item in payloads
    )


def test_high_runout_claim_requires_measured_value() -> None:
    payloads = _risk_payloads({"sealing_type": "rwdr", "runout_mm": 0.35})
    runout = _risk_by_name(payloads, "runout_risk")

    assert runout["claim_type"] == "measured_risk"
    assert runout["subject_field"] == "runout_mm"
    assert "runout_mm" in runout["evidence_fields"]
    assert "gemess" in str(runout["allowed_user_wording"]).casefold()
    assert "Rundlauf" in str(runout["allowed_user_wording"])


def test_system_pressure_does_not_create_seal_pressure_risk_claim() -> None:
    payloads = _risk_payloads({"sealing_type": "rwdr", "pressure_system_bar": 5.0})
    pressure = _risk_by_name(payloads, "pressure_risk")

    assert pressure["claim_type"] == "missing_input_risk"
    assert pressure["subject_field"] == "pressure_at_seal_bar"
    assert "pressure_system_bar" in pressure["evidence_fields"]
    assert "pressure_at_seal_bar" in pressure["missing_fields"]
    assert "Systemdruck" in str(pressure["allowed_user_wording"])
    assert pressure["claim_type"] != "measured_risk"


def test_ambiguous_pressure_creates_ambiguity_risk_not_measured_risk() -> None:
    payloads = _risk_payloads({"sealing_type": "rwdr", "ambiguous_pressure_bar": 5.0})
    pressure = _risk_by_name(payloads, "pressure_risk")

    assert pressure["claim_type"] == "ambiguity_risk"
    assert pressure["subject_field"] == "ambiguous_pressure_bar"
    assert "ambiguous_pressure_bar" in pressure["evidence_fields"]
    assert pressure["claim_type"] != "measured_risk"


def test_unknown_medium_blocks_material_risk_claim() -> None:
    payloads = _risk_payloads(
        {"sealing_type": "rwdr", "medium": "das medium", "material": "NBR"}
    )
    corrosion = _risk_by_name(payloads, "corrosion_risk")

    assert corrosion["claim_type"] == "missing_input_risk"
    assert corrosion["blocked_reason"] == "medium_missing_or_placeholder"
    assert "medium_name" in corrosion["missing_fields"]
    assert "Werkstoffvertraeglichkeit bleibt offen" in str(
        corrosion["allowed_user_wording"]
    )
    assert "Das Medium ist chemisch kritisch." in corrosion["forbidden_user_wording"]


def test_rwdr_type_is_not_rwdr_suitability_claim() -> None:
    challenge = build_challenge_state(_state({"sealing_type": "rwdr"}))
    visible_wording = " ".join(
        " ".join(
            [
                finding.title,
                finding.summary,
                finding.allowed_user_wording,
            ]
        )
        for finding in challenge.findings
    ).casefold()

    assert (
        _state({"sealing_type": "rwdr"})
        .asserted.assertions["sealing_type"]
        .asserted_value
        == "rwdr"
    )
    assert "rwdr ist geeignet" not in visible_wording
    assert "rwdr ist ungeeignet" not in visible_wording
    assert "freigegeben" not in visible_wording


def test_final_guard_blocks_unsupported_measured_claim() -> None:
    result = validate_final_output(
        "Der Wellenschlag ist hoch.",
        context=_final_context(),
    )

    assert result.decision == "block"
    assert result.final_stream_allowed is False
    assert "unsupported_measured_runout_claim" in result.detected_forbidden_claims
    assert "evidence_gate_failed" in result.blocked_reasons


def test_risk_claims_include_evidence_or_missing_fields() -> None:
    measured = _risk_by_name(
        _risk_payloads({"sealing_type": "rwdr", "runout_mm": 0.35}),
        "runout_risk",
    )
    missing = _risk_by_name(_risk_payloads({"sealing_type": "rwdr"}), "surface_risk")
    ambiguity = _risk_by_name(
        _risk_payloads({"sealing_type": "rwdr", "ambiguous_pressure_bar": 5.0}),
        "pressure_risk",
    )

    assert measured["claim_type"] == "measured_risk"
    assert measured["evidence_fields"]
    assert missing["claim_type"] == "missing_input_risk"
    assert missing["missing_fields"]
    assert ambiguity["claim_type"] == "ambiguity_risk"
    assert ambiguity["subject_field"] == "ambiguous_pressure_bar"
    assert ambiguity["evidence_fields"] == ["ambiguous_pressure_bar"]
