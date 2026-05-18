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
