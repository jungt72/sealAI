import pytest
from pydantic import ValidationError
from unittest.mock import patch

from app.agent.api.models import (
    ChatRequest,
    ChatResponse,
    StructuredStateExposureResponse,
    VisibleCaseNarrativeResponse,
    _assert_public_response_core_mapping,
    build_public_response_core,
)


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
        policy_path="structured",
        run_meta={"policy_version": "interaction_policy_v1"},
        response_class="governed_recommendation",
        interaction_class="structured_case",
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="ORIENTATION",
        has_case_state=True,
        visible_case_narrative={
            "governed_summary": "Aktuelle technische Richtung: No active technical direction.",
            "coverage_scope": [],
        },
        version_provenance={"policy_version": "interaction_policy_v1"},
        structured_state={
            "case_status": "withheld_review",
            "output_status": "withheld_review",
            "next_step": "human_review",
            "primary_allowed_action": "await_review",
            "active_blockers": ["review_pending"],
        },
    )
    assert res.runtime_path == "STRUCTURED_QUALIFICATION"
    assert res.visible_case_narrative is not None
    assert res.version_provenance["policy_version"] == "interaction_policy_v1"
    assert res.policy_path == "structured"
    assert res.run_meta["policy_version"] == "interaction_policy_v1"
    assert res.response_class == "governed_recommendation"
    assert res.structured_state.primary_allowed_action == "await_review"


def test_structured_state_exposure_response_forbids_internal_projection_fields():
    with pytest.raises(ValidationError):
        StructuredStateExposureResponse(
            case_status="governed_non_binding_result",
            output_status="governed_non_binding_result",
            next_step="confirmed_result_review",
            primary_allowed_action="consume_governed_result",
            active_blockers=[],
            primary_reason="governed_releasable_result",
        )


def test_chat_response_allows_missing_structured_state_for_non_structured_paths():
    res = ChatResponse(
        reply="Orientierung.",
        session_id="session-123",
        policy_path="fast",
        run_meta={"path": "fast"},
        response_class="conversational_answer",
        runtime_path="FAST_GUIDANCE",
        structured_state=None,
    )
    assert res.structured_state is None
    assert res.sealing_state is None


def test_build_public_response_core_returns_only_shared_fields():
    core = build_public_response_core(
        reply="Antwort",
        structured_state={"case_status": "withheld_review", "output_status": "withheld_review"},
        policy_path="structured",
        run_meta={"path": "structured"},
    )
    assert core == {
        "reply": "Antwort",
        "structured_state": {"case_status": "withheld_review", "output_status": "withheld_review"},
        "policy_path": "structured",
        "run_meta": {"path": "structured"},
        "response_class": "governed_recommendation",
    }


def test_build_public_response_core_classifies_guidance_and_state_update():
    guidance = build_public_response_core(
        reply="Orientierung",
        structured_state=None,
        policy_path="fast",
        run_meta=None,
    )
    structured_update = build_public_response_core(
        reply="Status",
        structured_state={"output_status": "withheld_review"},
        policy_path="structured",
        run_meta=None,
        state_update=True,
    )
    assert guidance["response_class"] == "conversational_answer"
    assert structured_update["response_class"] == "governed_state_update"


def test_build_public_response_core_delegates_to_central_user_facing_reply_assembly():
    assembled = {
        "reply": "Assembled",
        "structured_state": {"output_status": "clarification_needed"},
        "policy_path": "structured",
        "run_meta": {"path": "structured"},
        "response_class": "structured_clarification",
    }
    with patch("app.agent.api.models.assemble_user_facing_reply", return_value=assembled) as mock_assemble:
        core = build_public_response_core(
            reply="Bitte Medium angeben.",
            structured_state={"output_status": "clarification_needed"},
            policy_path="structured",
            run_meta={"path": "structured"},
        )

    assert core == assembled
    mock_assemble.assert_called_once_with(
        reply="Bitte Medium angeben.",
        structured_state={"output_status": "clarification_needed"},
        policy_path="structured",
        run_meta={"path": "structured"},
        state_update=False,
        response_class="structured_clarification",
    )


def test_build_public_response_core_guards_legacy_structured_clarification_reply():
    core = build_public_response_core(
        reply="Welches Medium liegt an? Welcher Druck liegt an?",
        structured_state={
            "case_status": "clarification_needed",
            "output_status": "clarification_needed",
        },
        policy_path="structured",
        run_meta=None,
    )

    assert core["response_class"] == "structured_clarification"
    assert core["reply"] == "Das hilft schon deutlich. Bitte nennen Sie den naechsten entscheidenden Betriebsparameter."


def test_build_public_response_core_guards_legacy_governed_recommendation_reply():
    core = build_public_response_core(
        reply="Die technische Richtung ist final freigegeben.",
        structured_state={
            "case_status": "governed_non_binding_result",
            "output_status": "governed_non_binding_result",
        },
        policy_path="structured",
        run_meta=None,
    )

    assert core["response_class"] == "governed_recommendation"
    assert core["reply"] == "Ich kann die technische Richtung belastbar einordnen und die offenen Pruefpunkte klar benennen."


def test_build_public_response_core_rejects_impossible_mapping_combinations():
    with pytest.raises(ValueError, match="conversational_answer must not expose structured_state"):
        _assert_public_response_core_mapping(
            response_class="conversational_answer",
            structured_state={"output_status": "withheld_review"},
            policy_path="fast",
            state_update=False,
        )

    with pytest.raises(ValueError, match="requires state_update=True and structured_state"):
        _assert_public_response_core_mapping(
            response_class="governed_state_update",
            structured_state={"output_status": "withheld_review"},
            policy_path="structured",
            state_update=False,
        )


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
