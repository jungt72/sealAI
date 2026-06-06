"""V1.8 §8 / AC16 outcome aggregation governance: anonymized richtwerte only,
and only above a minimum count (the moat's privacy guarantee)."""

from __future__ import annotations

from app.agent.state.models import OutcomeRecord
from app.services.outcome_aggregation import OutcomeAggregate, aggregate_outcomes


def _rec(pattern, cause="c", tenant="t", confidence="medium") -> OutcomeRecord:
    return OutcomeRecord(
        tenant_id=tenant,
        case_id="case_x",
        outcome_pattern=pattern,
        suspected_cause=cause,
        evidence_refs=["photo_1"],
        confidence=confidence,
    )


def test_below_min_count_never_leaves_tenant_scope() -> None:
    records = [_rec("lip_hardening_thermal") for _ in range(4)]
    assert aggregate_outcomes(records, min_count=5) == []


def test_at_min_count_emits_one_aggregate() -> None:
    records = [_rec("lip_hardening_thermal") for _ in range(5)]
    aggregates = aggregate_outcomes(records, min_count=5)
    assert len(aggregates) == 1
    assert aggregates[0].outcome_pattern == "lip_hardening_thermal"
    assert aggregates[0].count == 5


def test_aggregate_is_anonymized_no_identifying_fields() -> None:
    records = [_rec("dry_running_track", tenant=f"t{i}") for i in range(6)]
    aggregate = aggregate_outcomes(records, min_count=5)[0]
    dumped = aggregate.model_dump()
    # only the failure-pattern signal + size — nothing identifying
    assert set(dumped) == {
        "outcome_pattern",
        "suspected_cause",
        "count",
        "confidence_counts",
    }
    for forbidden in ("tenant_id", "case_id", "solution_ref", "evidence_refs"):
        assert forbidden not in dumped


def test_cross_tenant_records_combine_into_one_richtwert() -> None:
    # 3 tenants contribute to the same pattern → one aggregate, no tenant leaks
    records = (
        [_rec("running_groove_wear", tenant="a") for _ in range(2)]
        + [_rec("running_groove_wear", tenant="b") for _ in range(2)]
        + [_rec("running_groove_wear", tenant="c") for _ in range(1)]
    )
    aggregates = aggregate_outcomes(records, min_count=5)
    assert len(aggregates) == 1
    assert aggregates[0].count == 5


def test_records_without_pattern_are_excluded() -> None:
    records = [_rec(None) for _ in range(10)]
    assert aggregate_outcomes(records, min_count=5) == []


def test_distinct_patterns_and_causes_group_separately() -> None:
    records = (
        [_rec("lip_hardening_thermal", cause="hot") for _ in range(5)]
        + [_rec("lip_hardening_thermal", cause="other") for _ in range(5)]
        + [_rec("dry_running_track", cause="dry") for _ in range(6)]
    )
    aggregates = aggregate_outcomes(records, min_count=5)
    assert len(aggregates) == 3
    # sorted by count desc → dry_running_track (6) first
    assert aggregates[0].outcome_pattern == "dry_running_track"
    assert aggregates[0].count == 6


def test_confidence_distribution_is_counted() -> None:
    records = [_rec("lip_extrusion_pressure", confidence="high") for _ in range(3)] + [
        _rec("lip_extrusion_pressure", confidence="medium") for _ in range(2)
    ]
    aggregate = aggregate_outcomes(records, min_count=5)[0]
    assert aggregate.confidence_counts == {"high": 3, "medium": 2}


def test_default_min_count_is_applied() -> None:
    # without an explicit min_count, the §8 default gate applies
    assert aggregate_outcomes([_rec("x") for _ in range(4)]) == []
    assert len(aggregate_outcomes([_rec("x") for _ in range(5)])) == 1
