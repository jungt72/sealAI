from __future__ import annotations

import json

import pytest

from sealai_v2.core.interview.contracts import (
    InterviewDecision,
    InterviewDirective,
    InterviewDirectiveType,
)
from sealai_v2.core.interview.policy import (
    InterviewContractError,
    next_question_payload,
)
from sealai_v2.knowledge.domain_packs import load_rwdr_v1_pack
from sealai_v2.pipeline.adaptive_interview import AdaptiveInterviewUnavailable
from sealai_v2.tests._apiutil import auth, make_client, make_pipeline


class _FailingPipeline:
    async def run(self, *_args, **_kwargs):
        raise AdaptiveInterviewUnavailable()


class _FailingService:
    def evaluate(self, **_kwargs):
        raise RuntimeError("sensitive internal interview error")


def test_missing_directed_catalog_question_is_controlled_error() -> None:
    pack = load_rwdr_v1_pack()
    decision = InterviewDecision(
        directives=(
            InterviewDirective(
                type=InterviewDirectiveType.ASK,
                reason_code="test",
                question_id="missing-question",
                pending_question_id="ipq-test",
            ),
        ),
        rule_refs=("AI-TEST",),
        pack_id=pack.pack_id,
        pack_version=pack.version,
        policy_version=pack.policy_version,
        state_revision=1,
    )
    with pytest.raises(InterviewContractError, match="missing from catalog"):
        next_question_payload(
            case_id="case-1",
            topic_id="rwdr.default",
            pack=pack,
            decision=decision,
        )


def test_incomplete_question_directive_is_controlled_error() -> None:
    pack = load_rwdr_v1_pack()
    decision = InterviewDecision(
        directives=(
            InterviewDirective(
                type=InterviewDirectiveType.ASK,
                reason_code="test",
                question_id="",
                pending_question_id="ipq-test",
            ),
        ),
        rule_refs=("AI-TEST",),
        pack_id=pack.pack_id,
        pack_version=pack.version,
        policy_version=pack.policy_version,
        state_revision=1,
    )
    with pytest.raises(InterviewContractError, match="requires question"):
        next_question_payload(
            case_id="case-1",
            topic_id="rwdr.default",
            pack=pack,
            decision=decision,
        )


def test_active_controller_translates_internal_error_instead_of_returning_none() -> (
    None
):
    pipeline = make_pipeline()
    pipeline.adaptive_interview_enabled = True
    pipeline.adaptive_interview_service = _FailingService()
    with pytest.raises(AdaptiveInterviewUnavailable):
        pipeline.refresh_adaptive_interview(tenant_id="tenant-A", session_id="sess-A")


def test_active_controller_without_required_service_is_unavailable() -> None:
    pipeline = make_pipeline()
    pipeline.adaptive_interview_enabled = True
    pipeline.adaptive_interview_service = None
    with pytest.raises(AdaptiveInterviewUnavailable):
        pipeline.refresh_adaptive_interview(tenant_id="tenant-A", session_id="sess-A")


def test_shadow_only_controller_remains_inert_on_internal_error() -> None:
    pipeline = make_pipeline()
    pipeline.adaptive_interview_enabled = False
    pipeline.adaptive_interview_service = _FailingService()
    assert (
        pipeline.refresh_adaptive_interview(tenant_id="tenant-A", session_id="sess-A")
        is None
    )


def test_chat_returns_stable_non_sensitive_503() -> None:
    client, _ = make_client(_FailingPipeline())
    response = client.post(
        "/api/v2/chat", json={"message": "RWDR-Fall"}, headers=auth("tok-A")
    )
    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "adaptive_interview_unavailable",
            "message": "Die fachliche Klärung ist vorübergehend nicht verfügbar.",
        }
    }
    assert "sensitive" not in response.text


def test_stream_ends_with_one_error_and_no_normal_result() -> None:
    client, _ = make_client(_FailingPipeline())
    with client.stream(
        "POST",
        "/api/v2/chat/stream",
        json={"message": "RWDR-Fall"},
        headers=auth("tok-A"),
    ) as response:
        raw = "".join(response.iter_text())
    assert response.status_code == 200
    assert raw.count("event: error") == 1
    assert "event: result" not in raw
    data_line = next(line for line in raw.splitlines() if line.startswith("data: "))
    payload = json.loads(data_line.removeprefix("data: "))
    assert payload["code"] == "adaptive_interview_unavailable"
    assert "sensitive" not in raw
