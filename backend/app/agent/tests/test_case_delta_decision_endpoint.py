from __future__ import annotations

import pytest

from app.agent.api.models import CaseDeltaDecisionRequest
from app.agent.api.routes.review import session_case_delta_decision_endpoint
from app.agent.domain.case_delta import build_assistant_delta_event, proposed_case_delta_from_extractions
from app.agent.state.models import GovernedPersistenceMarker, GovernedSessionState, ObservedExtraction
from app.services.auth.dependencies import RequestUser


@pytest.mark.asyncio
async def test_case_delta_accept_partially_applies_safe_fields_and_skips_blocked_pressure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delta = proposed_case_delta_from_extractions(
        [
            ObservedExtraction(
                field_name="pressure_bar",
                raw_value=4,
                raw_unit="bar",
                confidence=0.92,
                turn_index=1,
            ),
            ObservedExtraction(
                field_name="medium",
                raw_value="Salzwasser",
                confidence=0.93,
                turn_index=1,
            ),
            ObservedExtraction(
                field_name="shaft_diameter_mm",
                raw_value=42,
                raw_unit="mm",
                confidence=0.9,
                turn_index=1,
            ),
        ],
        turn_index=1,
    )
    proposal = build_assistant_delta_event(
        case_id="case-partial",
        turn_index=1,
        assistant_message="Ich habe Werte erkannt.",
        delta=delta,
    )
    governed = GovernedSessionState(
        case_events=[proposal],
        persistence_marker=GovernedPersistenceMarker(postgres_snapshot_revision=3),
    )
    persisted: list[GovernedSessionState] = []

    async def fake_load_live_governed_state(**kwargs):
        return governed

    async def fake_persist_live_governed_state(**kwargs):
        persisted.append(kwargs["state"])

    monkeypatch.setenv("REDIS_URL", "redis://unit-test")
    monkeypatch.setattr(
        "app.agent.api.loaders._load_live_governed_state",
        fake_load_live_governed_state,
    )
    monkeypatch.setattr(
        "app.agent.api.loaders._persist_live_governed_state",
        fake_persist_live_governed_state,
    )

    response = await session_case_delta_decision_endpoint(
        CaseDeltaDecisionRequest(action="accept"),
        session_id="case-partial",
        current_user=RequestUser(
            user_id="user-1",
            username="user-1",
            sub="user-1",
            roles=["admin"],
            tenant_id="tenant-1",
        ),
    )

    assert response.action == "accept"
    assert response.applied_fields == ["medium", "shaft_diameter_mm"]
    assert response.rejected_fields == ["pressure_bar"]
    assert len(persisted) == 1
    decision_event = persisted[0].case_events[-1]
    assert decision_event.event_type == "case_delta_accepted"
    assert set(decision_event.accepted_delta) == {"medium", "shaft_diameter_mm"}
    assert "pressure_bar" not in decision_event.accepted_delta
