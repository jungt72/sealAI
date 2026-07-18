from __future__ import annotations

from dataclasses import replace

from sealai_v2.core.interview.contracts import InterviewShadowRecord
from sealai_v2.core.interview.shadow_reporting import (
    InterviewShadowRecordPage,
    summarize_shadow_records,
)

PACK_ID = "rwdr.v1"
PACK_VERSION = "1.0.0"
POLICY_VERSION = "adaptive-interview.lexicographic.1.0.0"


def _record(
    *,
    record_id: str,
    case_reference: str,
    revision: int,
    divergence: str,
    question_id: str | None,
    duration: float,
    ratio: float,
    legacy_present: bool = True,
    legacy_need_id: str | None = "rwdr.medium.primary",
) -> InterviewShadowRecord:
    return InterviewShadowRecord(
        record_id=record_id,
        tenant_id="tenant-a",
        case_reference=case_reference,
        state_revision=revision,
        pack_id=PACK_ID,
        pack_version=PACK_VERSION,
        policy_version=POLICY_VERSION,
        legacy_question_present=legacy_present,
        legacy_question_fingerprint="hmac-only" if legacy_present else None,
        controller_directive="ask",
        controller_question_id=question_id,
        rule_refs=("AI-T4-REQUIRED-001",),
        divergence_type=divergence,
        decision_duration_ms=duration,
        completeness={
            "ratio": ratio,
            "satisfied": 2,
            "conflicted": 1 if divergence == "different_need" else 0,
            "unobtainable": 0,
            "not_applicable": 0,
            "blocked": 0,
            "additional_llm_calls_by_controller": 0,
        },
        created_at="2026-07-14T08:00:00+00:00",
        legacy_need_id=legacy_need_id,
    )


def test_shadow_summary_is_aggregate_only_and_human_gated() -> None:
    page = InterviewShadowRecordPage(
        records=(
            _record(
                record_id="1",
                case_reference="case-hmac-a",
                revision=1,
                divergence="same_need",
                question_id="rwdr.q.medium_primary",
                duration=1.0,
                ratio=0.4,
            ),
            _record(
                record_id="2",
                case_reference="case-hmac-a",
                revision=2,
                divergence="different_need",
                question_id="rwdr.q.pressure_regime",
                duration=5.0,
                ratio=0.7,
            ),
            _record(
                record_id="3",
                case_reference="case-hmac-b",
                revision=1,
                divergence="legacy_unstructured",
                question_id="rwdr.q.application_goal",
                duration=9.0,
                ratio=0.2,
                legacy_need_id=None,
            ),
        ),
        total=5,
        limit=3,
    )

    summary = summarize_shadow_records(
        page,
        pack_id=PACK_ID,
        pack_version=PACK_VERSION,
        policy_version=POLICY_VERSION,
        question_to_need={
            "rwdr.q.medium_primary": "rwdr.medium.primary",
            "rwdr.q.pressure_regime": "rwdr.pressure.regime",
            "rwdr.q.application_goal": "rwdr.application.goal",
        },
    )
    payload = summary.to_dict()

    assert payload["observations_total"] == 5
    assert payload["observations_analyzed"] == 3
    assert payload["duplicate_observations_discarded"] == 0
    assert payload["truncated"] is True
    assert payload["unique_cases_analyzed"] == 2
    assert payload["unique_case_revisions_analyzed"] == 3
    assert payload["comparable_decisions"] == 2
    assert payload["reviewable_divergences"] == 1
    assert payload["same_need_rate"] == 0.5
    assert payload["legacy_unstructured_rate"] == round(1 / 3, 6)
    assert payload["legacy_need_counts"] == {"rwdr.medium.primary": 2}
    assert payload["need_transition_counts"] == {
        "rwdr.medium.primary->rwdr.medium.primary": 1,
        "rwdr.medium.primary->rwdr.pressure.regime": 1,
    }
    assert payload["completeness"]["average_ratio"] == round(1.3 / 3, 6)
    assert payload["latency"] == {
        "p50_ms": 5.0,
        "p95_ms": 9.0,
        "maximum_ms": 9.0,
    }
    assert payload["additional_llm_calls_by_controller"] == 0
    assert payload["review_state"] == "human_review_required"
    assert payload["automatic_activation_authorized"] is False
    assert "case_reference" not in payload
    assert "legacy_question_fingerprint" not in payload


def test_shadow_summary_counts_replayed_case_revision_once() -> None:
    older = _record(
        record_id="older",
        case_reference="case-hmac-a",
        revision=1,
        divergence="different_need",
        question_id="rwdr.q.pressure_regime",
        duration=5.0,
        ratio=0.4,
    )
    newer = replace(
        older,
        record_id="newer",
        divergence_type="same_need",
        controller_question_id="rwdr.q.medium_primary",
        created_at="2026-07-14T08:01:00+00:00",
    )

    payload = summarize_shadow_records(
        InterviewShadowRecordPage(records=(older, newer), total=2, limit=100),
        pack_id=PACK_ID,
        pack_version=PACK_VERSION,
        policy_version=POLICY_VERSION,
        question_to_need={"rwdr.q.medium_primary": "rwdr.medium.primary"},
    ).to_dict()

    assert payload["observations_analyzed"] == 2
    assert payload["duplicate_observations_discarded"] == 1
    assert payload["unique_case_revisions_analyzed"] == 1
    assert payload["divergence_counts"]["same_need"] == 1
    assert payload["divergence_counts"]["different_need"] == 0
    assert payload["reviewable_divergences"] == 0


def test_empty_shadow_summary_has_no_invented_rates() -> None:
    summary = summarize_shadow_records(
        InterviewShadowRecordPage(records=(), total=0, limit=100),
        pack_id=PACK_ID,
        pack_version=PACK_VERSION,
        policy_version=POLICY_VERSION,
    )
    payload = summary.to_dict()
    assert payload["review_state"] == "no_data"
    assert payload["same_need_rate"] is None
    assert payload["legacy_unstructured_rate"] is None
    assert payload["completeness"]["average_ratio"] is None
    assert payload["latency"]["p95_ms"] is None
