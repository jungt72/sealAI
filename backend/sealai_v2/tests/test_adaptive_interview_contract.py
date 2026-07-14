from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pytest
from pydantic import ValidationError

from sealai_v2.api.serializers import chat_response
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import Answer, Flags, PipelineResult
from sealai_v2.core.interview.contracts import NextQuestionPayload
from sealai_v2.pipeline.pipeline import build_pipeline
from sealai_v2.tests._fakes import FakeLlmClient


def _result(next_question=None) -> PipelineResult:
    return PipelineResult(
        question="q",
        tenant_id="tenant-a",
        flags=Flags(),
        understanding=None,
        answer=Answer(text="a", model="fake"),
        next_question=next_question,
    )


def _payload() -> NextQuestionPayload:
    return NextQuestionPayload(
        case_id="case-1",
        topic_id="rwdr.default",
        state_revision=7,
        pack_id="rwdr.v1",
        pack_version="1.0.1",
        policy_version="adaptive-interview.lexicographic.1.0.0",
        question_id="rwdr.q.medium_primary",
        primary_need_id="rwdr.medium.primary",
        related_need_ids=("rwdr.medium.concentration",),
        question_text="Welches konkrete Medium liegt an?",
        question_type="structured_text",
        answer_schema={"type": "object"},
        allowed_unknown=True,
        allowed_unobtainable=True,
        criticality="decision_critical",
        rule_refs=("AI-T4-REQUIRED-001", "RWDR-MEDIUM-001"),
        dependency_refs=(),
        pending_question_id="ipq_123",
    )


def test_next_question_is_absent_when_active_flag_path_is_inert() -> None:
    response = chat_response(_result())
    assert "next_question" not in response


def test_next_question_is_additive_and_carries_state_revision() -> None:
    response = chat_response(_result(_payload()))
    assert response["next_question"]["state_revision"] == 7
    assert response["next_question"]["question_id"] == "rwdr.q.medium_primary"
    assert response["next_question"]["related_need_ids"] == [
        "rwdr.medium.concentration"
    ]


def test_python_payload_rejects_unknown_fields() -> None:
    values = asdict(_payload())
    values["unreviewed_future_field"] = "must-not-be-silent"
    with pytest.raises(TypeError, match="unreviewed_future_field"):
        NextQuestionPayload(**values)


def test_typescript_next_question_contract_contains_every_python_field() -> None:
    contracts = (
        Path(__file__).parents[3] / "frontend-v2" / "src" / "contracts.ts"
    ).read_text(encoding="utf-8")
    interface = contracts.split("export interface NextQuestionPayload {", 1)[1].split(
        "}", 1
    )[0]
    for field_name in asdict(_payload()):
        assert f"  {field_name}:" in interface


def test_all_interview_flags_default_off() -> None:
    settings = Settings()
    assert settings.adaptive_interview_enabled is False
    assert settings.adaptive_interview_shadow_enabled is False
    assert settings.adaptive_interview_pack_rwdr_enabled is False
    assert settings.adaptive_interview_shadow_reporting_enabled is False


def test_mode_flag_requires_rwdr_pack_gate() -> None:
    with pytest.raises(ValidationError, match="adaptive_interview_pack_rwdr_enabled"):
        Settings(adaptive_interview_shadow_enabled=True)
    settings = Settings(
        adaptive_interview_shadow_enabled=True,
        adaptive_interview_pack_rwdr_enabled=True,
    )
    assert settings.adaptive_interview_shadow_enabled is True
    with pytest.raises(ValidationError, match="shadow reporting"):
        Settings(adaptive_interview_shadow_reporting_enabled=True)


def test_deploy_compose_allowlists_all_default_off_flags() -> None:
    compose = (Path(__file__).parents[3] / "docker-compose.deploy.yml").read_text(
        encoding="utf-8"
    )
    for name in (
        "SEALAI_V2_ADAPTIVE_INTERVIEW_ENABLED",
        "SEALAI_V2_ADAPTIVE_INTERVIEW_SHADOW_ENABLED",
        "SEALAI_V2_ADAPTIVE_INTERVIEW_PACK_RWDR_ENABLED",
        "SEALAI_V2_ADAPTIVE_INTERVIEW_SHADOW_REPORTING_ENABLED",
    ):
        assert f"{name}: ${{{name}:-false}}" in compose


def test_shadow_controller_adds_zero_llm_calls() -> None:
    client = FakeLlmClient()
    pipeline = build_pipeline(
        Settings(
            verify_enabled=False,
            ground_enabled=False,
            distill_enabled=False,
            adaptive_interview_shadow_enabled=True,
            adaptive_interview_pack_rwdr_enabled=True,
        ),
        client,
    )
    assert pipeline.adaptive_interview_service is not None
    pipeline.memory.edit_fact(
        tenant_id="tenant-a",
        session_id="case-1",
        feld="dichtungstyp",
        wert="rwdr",
        provenance="user-form",
    )
    evaluation = pipeline.refresh_adaptive_interview(
        tenant_id="tenant-a", session_id="case-1"
    )
    assert evaluation is not None
    assert client.calls == []


def test_default_off_pipeline_does_not_construct_controller() -> None:
    pipeline = build_pipeline(
        Settings(verify_enabled=False, ground_enabled=False, distill_enabled=False),
        FakeLlmClient(),
    )
    assert pipeline.adaptive_interview_service is None
