import pytest
from pydantic import ValidationError

from app.agent.api.models import ChatRequest, ChatResponse, VisibleCaseNarrativeResponse


def test_chat_request_valid():
    req = ChatRequest(message="Hallo", session_id="session-1")
    assert req.message == "Hallo"
    assert req.session_id == "session-1"


def test_chat_request_default_session():
    req = ChatRequest(message="Hallo")
    assert req.session_id == "default"


def test_chat_request_empty_message():
    with pytest.raises(ValidationError):
        ChatRequest(message="")


def test_chat_response_accepts_structured_contract_fields():
    res = ChatResponse(
        reply="Hallo zurück",
        session_id="session-123",
        sealing_state={"cycle": {"state_revision": 1}},
        interaction_class="structured_case",
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="ORIENTATION",
        has_case_state=True,
        visible_case_narrative={
            "governed_summary": "Aktuelle technische Richtung: No active technical direction.",
            "coverage_scope": [],
        },
        version_provenance={"policy_version": "interaction_policy_v1"},
    )
    assert res.runtime_path == "STRUCTURED_QUALIFICATION"
    assert res.visible_case_narrative is not None
    assert res.version_provenance["policy_version"] == "interaction_policy_v1"


def test_visible_case_narrative_response_accepts_coverage_scope():
    narrative = VisibleCaseNarrativeResponse(
        governed_summary="summary",
        coverage_scope=[
            {
                "key": "coverage_boundary",
                "label": "Coverage",
                "value": "partial",
                "detail": None,
                "severity": "medium",
            }
        ],
    )
    assert narrative.coverage_scope[0].key == "coverage_boundary"
