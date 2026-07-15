from __future__ import annotations

from fastapi.testclient import TestClient

from sealai_v2.api import deps
from sealai_v2.api.main import app
from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import VerifiedIdentity
from sealai_v2.core.interview.contracts import (
    InterviewRuntimeState,
    InterviewShadowRecord,
)
from sealai_v2.db.interview import InProcessInterviewRepository
from sealai_v2.security.auth import FakeAuthValidator

POLICY_VERSION = "adaptive-interview.lexicographic.1.0.0"


def _record(
    *, tenant_id: str, record_id: str, divergence: str
) -> InterviewShadowRecord:
    return InterviewShadowRecord(
        record_id=record_id,
        tenant_id=tenant_id,
        case_reference=f"hmac-{record_id}",
        state_revision=1,
        pack_id="rwdr.v1",
        pack_version="1.0.1",
        policy_version=POLICY_VERSION,
        legacy_question_present=True,
        legacy_question_fingerprint=f"fingerprint-{record_id}",
        controller_directive="ask",
        controller_question_id="rwdr.q.medium_primary",
        rule_refs=("AI-T4-REQUIRED-001",),
        divergence_type=divergence,
        decision_duration_ms=1.5,
        completeness={
            "ratio": 0.5,
            "satisfied": 2,
            "conflicted": 0,
            "unobtainable": 0,
            "not_applicable": 0,
            "blocked": 0,
            "additional_llm_calls_by_controller": 0,
        },
        created_at="2026-07-14T08:00:00+00:00",
        legacy_need_id="rwdr.medium.primary",
    )


def _add(repo: InProcessInterviewRepository, record: InterviewShadowRecord) -> None:
    repo.save_evaluation(
        tenant_id=record.tenant_id,
        session_id=f"session-{record.record_id}",
        state=InterviewRuntimeState(
            pack_id="rwdr.v1",
            pack_version="1.0.1",
            policy_version=POLICY_VERSION,
            state_revision=1,
        ),
        updated_at=record.created_at,
        shadow=record,
    )


def _client(*, reporting_enabled: bool = True) -> TestClient:
    repo = InProcessInterviewRepository()
    _add(repo, _record(tenant_id="tenant-a", record_id="a", divergence="same_need"))
    _add(
        repo,
        _record(
            tenant_id="tenant-b",
            record_id="b",
            divergence="different_need",
        ),
    )
    identities = {
        "admin-a": VerifiedIdentity(
            "tenant-a", "session-a", "operator-a", roles=("system_operator",)
        ),
        "user-a": VerifiedIdentity("tenant-a", "session-u", "user-a"),
    }
    app.dependency_overrides.clear()
    app.dependency_overrides[deps.get_validator] = lambda: FakeAuthValidator(identities)
    app.dependency_overrides[deps.get_interview_shadow_store] = lambda: repo
    app.dependency_overrides[deps.get_settings] = lambda: Settings(
        adaptive_interview_pack_rwdr_enabled=True,
        adaptive_interview_shadow_reporting_enabled=reporting_enabled,
    )
    return TestClient(app)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_shadow_summary_requires_operator_and_is_tenant_aggregate_only() -> None:
    client = _client()
    denied = client.get(
        "/api/v2/admin/adaptive-interview/shadow-summary",
        headers=_auth("user-a"),
    )
    assert denied.status_code == 403

    response = client.get(
        "/api/v2/admin/adaptive-interview/shadow-summary",
        headers=_auth("admin-a"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["observations_total"] == 1
    assert payload["summary"]["divergence_counts"]["same_need"] == 1
    assert payload["summary"]["divergence_counts"]["different_need"] == 0
    assert payload["summary"]["automatic_activation_authorized"] is False
    assert payload["individual_records_exposed"] is False
    assert "hmac-a" not in response.text
    assert "fingerprint-a" not in response.text
    assert "hmac-b" not in response.text


def test_shadow_summary_is_default_off() -> None:
    client = _client(reporting_enabled=False)
    response = client.get(
        "/api/v2/admin/adaptive-interview/shadow-summary",
        headers=_auth("admin-a"),
    )
    assert response.status_code == 503
    assert response.json()["detail"]["mode"] == "adaptive_interview_shadow_reporting"


def test_shadow_summary_validates_time_window() -> None:
    client = _client()
    response = client.get(
        "/api/v2/admin/adaptive-interview/shadow-summary"
        "?since=2026-07-15T00:00:00Z&until=2026-07-14T00:00:00Z",
        headers=_auth("admin-a"),
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "since must be earlier than until"
