from __future__ import annotations

from app.agent.api.routes.review import (
    _build_critical_review_input,
    _build_review_handover_response,
)
from app.agent.domain.critical_review import run_critical_review_specialist


def test_review_route_builds_current_critical_review_contract() -> None:
    state = {
        "case_state": {
            "governance_state": {
                "release_status": "inquiry_ready",
                "rfq_admissibility": "ready",
                "unknowns_release_blocking": [],
                "unknowns_manufacturer_validation": ["Compounddatenblatt klaeren"],
                "scope_of_validity": ["Screening scope only"],
                "conflicts": [],
            },
            "requirement_class": {
                "requirement_class_id": "PTFE10",
                "description": "PTFE screening class",
            },
            "matching_state": {
                "status": "matched_primary_candidate",
                "selected_manufacturer_ref": {"manufacturer_name": "Acme"},
            },
            "rfq_state": {
                "recipient_refs": [{"manufacturer_name": "Acme"}],
                "rfq_object": {"object_type": "rfq_payload_basis"},
            },
        }
    }

    payload = _build_critical_review_input(state, review_required=False)
    result = run_critical_review_specialist(payload)

    assert result.critical_review_passed is True

    response = _build_review_handover_response(
        state,
        session_id="case-123",
        action="approve",
        outcome=result,
    )

    assert response.review_state == "approved_scope"
    assert response.release_status == "inquiry_ready"
    assert response.is_handover_ready is True


def test_review_route_blocks_stale_or_incomplete_contract() -> None:
    payload = _build_critical_review_input(
        {
            "case_state": {
                "governance_state": {"release_status": "inadmissible"},
                "matching_state": {},
            }
        },
        review_required=False,
    )

    result = run_critical_review_specialist(payload)

    assert result.critical_review_passed is False
    assert "release_status_not_inquiry_ready" in result.blocking_findings
    assert "requirement_class_missing" in result.blocking_findings
