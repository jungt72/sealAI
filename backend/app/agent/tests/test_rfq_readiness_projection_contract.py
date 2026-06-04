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
    GovernanceState,
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


def test_rfq_readiness_projection_does_not_show_asserted_pending_field_as_missing() -> (
    None
):
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


def test_rfq_readiness_projection_professional_checks_can_clear_required_blockers() -> (
    None
):
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
    assert projection["evidence_status"] in {
        "evidence_found",
        "evidence_found_with_risks",
    }


def _readiness_intent() -> RfqReadinessIntent:
    return RfqReadinessIntent(
        detected=True,
        rfq_action_type="show_readiness",
        reason="rfq_readiness",
    )


def test_rfq_readiness_projection_class_b_value_conflict_is_open_point_not_blocked() -> (
    None
):
    # §12.6: a degraded (non-safety) value conflict lands in Class B. The reducer
    # already decided it is not hard-blocking, so the readiness projection must
    # speak "RFQ with open points": basis available, conflict an open point —
    # never a hard blocking reason. Resolves the AC14 binary contradiction.
    projection = build_rfq_readiness_projection(
        governed_state=GovernedSessionState(
            asserted=AssertedState(
                assertions={
                    "medium": AssertedClaim(
                        field_name="medium",
                        asserted_value="oil",
                        confidence="confirmed",
                    ),
                },
                conflict_flags=["clearance_fit"],
            ),
            governance=GovernanceState(
                gov_class="B",
                rfq_admissible=False,
                open_validation_points=["Unresolved conflict: 'clearance_fit'"],
            ),
        ),
        intent=_readiness_intent(),
    ).public_dict()

    assert projection["readiness_band"] == "rfq_with_open_points"
    assert projection["rfq_basis_ready"] is True
    assert projection["manufacturer_review_ready"] is False
    # The value conflict is an open point, not a hard blocker.
    assert projection["blocking_reasons"] == []
    assert any(
        "clearance_fit" in point or "conflict" in point.lower()
        for point in projection["open_points"]
    )


def test_rfq_readiness_projection_class_c_safety_conflict_still_blocked() -> None:
    # Counter-direction: a safety/compliance conflict stays Class C. The
    # readiness projection must keep speaking "blocked" — the safety path is not
    # softened by the AC14 reconciliation.
    projection = build_rfq_readiness_projection(
        governed_state=GovernedSessionState(
            asserted=AssertedState(
                assertions={
                    "medium": AssertedClaim(
                        field_name="medium",
                        asserted_value="oil",
                        confidence="confirmed",
                    ),
                },
                conflict_flags=["compliance"],
            ),
            governance=GovernanceState(
                gov_class="C",
                rfq_admissible=False,
                compliance_blockers=["food_pharma"],
                open_validation_points=["Unresolved conflict: 'compliance'"],
            ),
        ),
        intent=_readiness_intent(),
    ).public_dict()

    assert projection["readiness_band"] == "blocked"
    assert projection["rfq_basis_ready"] is False
    assert projection["manufacturer_review_ready"] is False
    # Safety/compliance conflict is preserved as a hard blocking reason.
    assert projection["blocking_reasons"]


def test_rfq_readiness_projection_class_a_clean_is_rfq_ready() -> None:
    projection = build_rfq_readiness_projection(
        governed_state=GovernedSessionState(
            asserted=AssertedState(
                assertions={
                    "medium": AssertedClaim(
                        field_name="medium",
                        asserted_value="oil",
                        confidence="confirmed",
                    ),
                },
            ),
            governance=GovernanceState(gov_class="A", rfq_admissible=True),
        ),
        intent=_readiness_intent(),
    ).public_dict()

    assert projection["readiness_band"] == "rfq_ready"
    assert projection["rfq_basis_ready"] is True
    assert projection["manufacturer_review_ready"] is True
    assert projection["blocking_reasons"] == []
