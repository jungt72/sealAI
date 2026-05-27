from __future__ import annotations

import json
from pathlib import Path

from app.agent.communication.rfq_intent import (
    RfqReadinessIntent,
    build_rfq_readiness_projection,
)
from app.agent.state.models import (
    AssertedClaim,
    AssertedState,
    GovernedSessionState,
    PendingQuestion,
)


CONTRACT_FIXTURE = (
    Path(__file__).resolve().parents[4]
    / "contracts"
    / "rfq_readiness_projection_v1.fixture.json"
)


def test_rfq_readiness_projection_public_dict_matches_contract_fixture() -> None:
    expected = json.loads(CONTRACT_FIXTURE.read_text(encoding="utf-8"))
    projection = build_rfq_readiness_projection(
        governed_state=GovernedSessionState(
            pending_question=PendingQuestion(
                target_field="medium",
                expected_answer_type="medium_value",
                question_text="Welches Medium soll abgedichtet werden?",
                source="governed_next_question",
                status="open",
            )
        ),
        intent=RfqReadinessIntent(
            detected=False,
            rfq_action_type="contract_fixture",
            reason="contract_drift_check",
        ),
    ).public_dict()

    assert projection == expected
    assert projection["pending_question"]["target_field"] == "medium"
    assert (
        projection["pending_question"]["question_text"]
        == "Welches Medium soll abgedichtet werden?"
    )
    assert projection["dispatch_allowed"] is False
    assert projection["external_contact_allowed"] is False
    assert projection["final_approval_claim_allowed"] is False


def test_rfq_readiness_projection_does_not_show_asserted_pending_field_as_missing() -> None:
    projection = build_rfq_readiness_projection(
        governed_state=GovernedSessionState(
            pending_question=PendingQuestion(
                target_field="temperature_c",
                expected_answer_type="temperature_value",
                question_text="Welche Betriebstemperatur liegt an?",
                source="governed_next_question",
                status="open",
            ),
            asserted=AssertedState(
                assertions={
                    "temperature_c": AssertedClaim(
                        field_name="temperature_c",
                        asserted_value=80,
                        confidence="confirmed",
                    )
                },
                blocking_unknowns=["temperature_c", "pressure_bar"],
            ),
        ),
        intent=RfqReadinessIntent(
            detected=True,
            rfq_action_type="show_missing_fields",
            reason="rfq_readiness",
        ),
    ).public_dict()

    assert "Temperatur" not in projection["known_missing_fields"]
    assert projection["known_missing_fields"] == ["Druck"]
    assert "pending_question" not in projection


def test_rfq_readiness_projection_maps_professional_check_blockers() -> None:
    projection = build_rfq_readiness_projection(
        governed_state=GovernedSessionState(
            asserted=AssertedState(
                assertions={
                    "sealing_type": AssertedClaim(
                        field_name="sealing_type",
                        asserted_value="rwdr",
                        confidence="confirmed",
                    ),
                    "pressure_system_bar": AssertedClaim(
                        field_name="pressure_system_bar",
                        asserted_value=5.0,
                        confidence="confirmed",
                    ),
                    "shaft_diameter_mm": AssertedClaim(
                        field_name="shaft_diameter_mm",
                        asserted_value=50.0,
                        confidence="confirmed",
                    ),
                    "speed_rpm": AssertedClaim(
                        field_name="speed_rpm",
                        asserted_value=1500,
                        confidence="confirmed",
                    ),
                }
            ),
        ),
        intent=RfqReadinessIntent(
            detected=True,
            rfq_action_type="show_readiness",
            reason="rfq_readiness",
        ),
    ).public_dict()

    assert projection["professional_check_groups"]
    assert projection["professional_check_blockers"]
    assert "Druck" in projection["blocking_reasons"]
    assert projection["evidence_status"] == "insufficient_evidence"
    pressure_checks = [
        check
        for group in projection["professional_check_groups"]
        for check in group["checks"]
        if check["check_id"] == "rwdr_pressure_role_check"
    ]
    assert pressure_checks
    assert pressure_checks[0]["final_approval_claim_allowed"] is False


def test_rfq_readiness_projection_professional_checks_can_clear_required_blockers() -> None:
    projection = build_rfq_readiness_projection(
        governed_state=GovernedSessionState(
            asserted=AssertedState(
                assertions={
                    "sealing_type": AssertedClaim(
                        field_name="sealing_type",
                        asserted_value="rwdr",
                        confidence="confirmed",
                    ),
                    "medium": AssertedClaim(
                        field_name="medium",
                        asserted_value="HLP46",
                        confidence="confirmed",
                    ),
                    "temperature_c": AssertedClaim(
                        field_name="temperature_c",
                        asserted_value=80,
                        confidence="confirmed",
                    ),
                    "material": AssertedClaim(
                        field_name="material",
                        asserted_value="PTFE",
                        confidence="confirmed",
                    ),
                    "pressure_at_seal_bar": AssertedClaim(
                        field_name="pressure_at_seal_bar",
                        asserted_value=1.0,
                        confidence="confirmed",
                    ),
                    "shaft_diameter_mm": AssertedClaim(
                        field_name="shaft_diameter_mm",
                        asserted_value=50.0,
                        confidence="confirmed",
                    ),
                    "speed_rpm": AssertedClaim(
                        field_name="speed_rpm",
                        asserted_value=1500,
                        confidence="confirmed",
                    ),
                }
            ),
        ),
        intent=RfqReadinessIntent(
            detected=True,
            rfq_action_type="show_readiness",
            reason="rfq_readiness",
        ),
    ).public_dict()

    assert projection["professional_check_groups"]
    assert projection["professional_check_blockers"] == []
    assert projection["evidence_status"] in {"evidence_found", "evidence_found_with_risks"}
