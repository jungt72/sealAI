"""Pure aggregation for privacy-minimized adaptive-interview shadow telemetry."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from sealai_v2.core.interview.contracts import InterviewShadowRecord

_DIVERGENCE_TYPES = (
    "same_need",
    "different_need",
    "legacy_question_only",
    "controller_question_only",
    "controller_escalates",
    "legacy_unstructured",
    "no_decision",
)
_COMPLETENESS_COUNTS = (
    "satisfied",
    "conflicted",
    "unobtainable",
    "not_applicable",
    "blocked",
)


@dataclass(frozen=True)
class InterviewShadowRecordPage:
    records: tuple[InterviewShadowRecord, ...]
    total: int
    limit: int

    @property
    def truncated(self) -> bool:
        return self.total > len(self.records)


@dataclass(frozen=True)
class ShadowCompletenessSummary:
    average_ratio: float | None
    minimum_ratio: float | None
    status_totals: dict[str, int]


@dataclass(frozen=True)
class ShadowLatencySummary:
    p50_ms: float | None
    p95_ms: float | None
    maximum_ms: float | None


@dataclass(frozen=True)
class InterviewShadowSummary:
    schema_version: str
    pack_id: str
    pack_version: str
    policy_version: str
    since: str | None
    until: str | None
    observations_total: int
    observations_analyzed: int
    duplicate_observations_discarded: int
    truncated: bool
    unique_cases_analyzed: int
    unique_case_revisions_analyzed: int
    legacy_questions_present: int
    comparable_decisions: int
    reviewable_divergences: int
    divergence_counts: dict[str, int]
    same_need_rate: float | None
    legacy_unstructured_rate: float | None
    legacy_need_counts: dict[str, int]
    need_transition_counts: dict[str, int]
    directive_counts: dict[str, int]
    question_counts: dict[str, int]
    completeness: ShadowCompletenessSummary
    latency: ShadowLatencySummary
    additional_llm_calls_by_controller: int
    review_state: str
    automatic_activation_authorized: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 3)


def summarize_shadow_records(
    page: InterviewShadowRecordPage,
    *,
    pack_id: str,
    pack_version: str,
    policy_version: str,
    since: str | None = None,
    until: str | None = None,
    question_to_need: Mapping[str, str] | None = None,
) -> InterviewShadowSummary:
    """Aggregate a bounded, version-homogeneous record page without exposing rows."""
    ordered = sorted(
        page.records,
        key=lambda item: (item.created_at, item.record_id),
        reverse=True,
    )
    records_by_revision: dict[tuple[str, int], InterviewShadowRecord] = {}
    for item in ordered:
        records_by_revision.setdefault((item.case_reference, item.state_revision), item)
    records = tuple(records_by_revision.values())
    divergence = Counter(item.divergence_type for item in records)
    directives = Counter(item.controller_directive for item in records)
    questions = Counter(
        item.controller_question_id
        for item in records
        if item.controller_question_id is not None
    )
    legacy_needs = Counter(
        item.legacy_need_id for item in records if item.legacy_need_id is not None
    )
    question_to_need = question_to_need or {}
    transitions = Counter(
        f"{item.legacy_need_id}->{controller_need}"
        for item in records
        if item.legacy_need_id is not None
        and item.controller_question_id is not None
        and (controller_need := question_to_need.get(item.controller_question_id))
        is not None
    )
    cases = {item.case_reference for item in records}
    comparable = divergence["same_need"] + divergence["different_need"]
    reviewable_divergences = sum(
        divergence[key]
        for key in (
            "different_need",
            "legacy_question_only",
            "controller_question_only",
            "controller_escalates",
        )
    )
    legacy_present = sum(item.legacy_question_present for item in records)
    completeness_ratios = [
        float(item.completeness["ratio"])
        for item in records
        if isinstance(item.completeness.get("ratio"), (int, float))
    ]
    completeness_totals = {
        key: sum(int(item.completeness.get(key, 0)) for item in records)
        for key in _COMPLETENESS_COUNTS
    }
    additional_llm_calls = sum(
        int(item.completeness.get("additional_llm_calls_by_controller", 0))
        for item in records
    )
    latencies = [max(0.0, item.decision_duration_ms) for item in records]
    review_state = "no_data" if not records else "human_review_required"

    return InterviewShadowSummary(
        schema_version="1.0",
        pack_id=pack_id,
        pack_version=pack_version,
        policy_version=policy_version,
        since=since,
        until=until,
        observations_total=page.total,
        observations_analyzed=len(page.records),
        duplicate_observations_discarded=len(page.records) - len(records),
        truncated=page.truncated,
        unique_cases_analyzed=len(cases),
        unique_case_revisions_analyzed=len(records),
        legacy_questions_present=legacy_present,
        comparable_decisions=comparable,
        reviewable_divergences=reviewable_divergences,
        divergence_counts={key: divergence[key] for key in _DIVERGENCE_TYPES},
        same_need_rate=_rate(divergence["same_need"], comparable),
        legacy_unstructured_rate=_rate(
            divergence["legacy_unstructured"], legacy_present
        ),
        legacy_need_counts=dict(sorted(legacy_needs.items())),
        need_transition_counts=dict(sorted(transitions.items())),
        directive_counts=dict(sorted(directives.items())),
        question_counts=dict(sorted(questions.items())),
        completeness=ShadowCompletenessSummary(
            average_ratio=(
                round(sum(completeness_ratios) / len(completeness_ratios), 6)
                if completeness_ratios
                else None
            ),
            minimum_ratio=(
                round(min(completeness_ratios), 6) if completeness_ratios else None
            ),
            status_totals=completeness_totals,
        ),
        latency=ShadowLatencySummary(
            p50_ms=_percentile(latencies, 0.50),
            p95_ms=_percentile(latencies, 0.95),
            maximum_ms=round(max(latencies), 3) if latencies else None,
        ),
        additional_llm_calls_by_controller=additional_llm_calls,
        review_state=review_state,
    )
