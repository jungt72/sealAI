from __future__ import annotations

import pytest

from app.agent.v92.adversarial_review import (
    AdversarialReviewError,
    build_adversarial_review_messages,
    parse_adversarial_review_output,
)
from app.agent.v92.contracts import AdversarialReviewVerdict, FinalAnswerContext
from app.agent.v92.runtime_contract import apply_async_adversarial_review_to_payload


def _context() -> FinalAnswerContext:
    return FinalAnswerContext(
        turn_id="turn-1",
        case_id="case-1",
        case_revision=4,
        route="engineering_recommendation",
        intent="engineering_recommendation",
        is_technical=True,
        user_message="Ist EPDM geeignet?",
        allowed_claim_level="L2_screening",
        forbidden_claims=["final_material_suitability"],
    )


def test_adversarial_reviewer_messages_use_jinja_template_and_schema_payload() -> None:
    messages = build_adversarial_review_messages(
        draft="EPDM ist geeignet.",
        context=_context(),
    )

    assert messages[0]["role"] == "system"
    assert "Adversarial Reviewer" in messages[0]["content"]
    assert "AdversarialReviewVerdict" in messages[1]["content"]
    assert "EPDM ist geeignet" in messages[1]["content"]


def test_parse_adversarial_reviewer_output_validates_schema() -> None:
    verdict = parse_adversarial_review_output(
        """
        {
          "decision": "revise",
          "severity": "high",
          "forbidden_claims": ["suitability_claim_without_expert_scope"],
          "required_revision_instructions": ["Downgrade suitability."],
          "user_visible_challenge_summary": "Claim must be downgraded."
        }
        """
    )

    assert verdict.decision == "revise"
    assert verdict.severity == "high"
    assert verdict.required_revision_instructions == ["Downgrade suitability."]


def test_parse_adversarial_reviewer_output_rejects_invalid_json() -> None:
    with pytest.raises(AdversarialReviewError):
        parse_adversarial_review_output("not json")


@pytest.mark.asyncio
async def test_async_payload_reviewer_preserves_payload_when_feature_flag_disabled() -> (
    None
):
    payload = {
        "answer_markdown": "EPDM als Screening prüfen.",
        "turn_envelope": {
            "requires_adversarial_review": True,
        },
        "final_answer_context": _context().model_dump(mode="json"),
    }

    result = await apply_async_adversarial_review_to_payload(payload, enabled=False)

    assert result is payload


@pytest.mark.asyncio
async def test_async_payload_reviewer_updates_challenge_card_when_enabled(
    monkeypatch,
) -> None:
    trace_calls: list[dict] = []

    async def fake_review(_draft, _context):  # noqa: ANN001
        return AdversarialReviewVerdict(
            decision="pass",
            severity="none",
            user_visible_challenge_summary="LLM review passed.",
        )

    def fake_emit_quality_trace(**kwargs):  # noqa: ANN003
        trace_calls.append(kwargs)

    monkeypatch.setattr(
        "app.agent.v92.runtime_contract.review_answer_draft_with_llm_fallback",
        fake_review,
    )
    monkeypatch.setattr(
        "app.agent.v92.runtime_contract.emit_quality_trace",
        fake_emit_quality_trace,
    )
    payload = {
        "reply": "EPDM als Screening prüfen.",
        "answer_markdown": "EPDM als Screening prüfen.",
        "assistant_message": "EPDM als Screening prüfen.",
        "turn_envelope": {
            "requires_adversarial_review": True,
        },
        "final_answer_context": _context().model_dump(mode="json"),
        "v92_dashboard": {},
        "ui": {},
        "run_meta": {"v92": {}},
    }

    result = await apply_async_adversarial_review_to_payload(payload, enabled=True)

    assert result["v92_dashboard"]["challenge_card"]["summary"] == "LLM review passed."
    assert result["run_meta"]["v92"]["adversarial_review_decision"] == "pass"
    assert (
        result["run_meta"]["v92"]["adversarial_review_source"]
        == "deterministic_fallback"
    )
    assert result["run_meta"]["v92"]["llm_reviewer_enabled"] is True
    assert result["run_meta"]["v92"]["llm_reviewer_succeeded"] is False
    assert trace_calls
    assert trace_calls[-1]["component"] == "v92_adversarial_review"
    assert trace_calls[-1]["adversarial_review_source"] == "deterministic_fallback"
    assert trace_calls[-1]["final_guard_decision"] == "pass"


@pytest.mark.asyncio
async def test_async_payload_reviewer_marks_llm_source_when_prompt_trace_present(
    monkeypatch,
) -> None:
    async def fake_review(_draft, _context):  # noqa: ANN001
        return AdversarialReviewVerdict(
            decision="pass",
            severity="none",
            user_visible_challenge_summary="LLM review passed.",
            prompt_trace={
                "prompt_template_id": "governed/adversarial_reviewer.j2",
                "prompt_template_version": "test",
                "rendered_prompt_hash": "h_test",
                "input_schema_version": "FinalAnswerContext.v1+draft",
                "output_schema_version": "AdversarialReviewVerdict.v1",
                "model_role": "critique",
                "case_revision": 4,
                "trace_id": "turn-1",
            },
        )

    monkeypatch.setattr(
        "app.agent.v92.runtime_contract.review_answer_draft_with_llm_fallback",
        fake_review,
    )
    payload = {
        "reply": "EPDM als Screening prüfen.",
        "answer_markdown": "EPDM als Screening prüfen.",
        "assistant_message": "EPDM als Screening prüfen.",
        "turn_envelope": {
            "requires_adversarial_review": True,
        },
        "final_answer_context": _context().model_dump(mode="json"),
        "v92_dashboard": {},
        "ui": {},
        "run_meta": {"v92": {}},
    }

    result = await apply_async_adversarial_review_to_payload(payload, enabled=True)

    assert result["run_meta"]["v92"]["adversarial_review_source"] == "llm"
    assert result["run_meta"]["v92"]["llm_reviewer_succeeded"] is True
    assert (
        result["final_answer_context"]["adversarial_review"]["prompt_trace"][
            "model_role"
        ]
        == "critique"
    )
