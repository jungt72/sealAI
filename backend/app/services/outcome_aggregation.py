"""Outcome aggregation governance — the moat's global layer (V1.8 §8 / §4.3).

Raw outcomes are strictly tenant-scoped (``outcome_record_repository``). The ONLY
path by which outcome data leaves the tenant scope is this aggregation:
**anonymized richtwerte, emitted only above a defined minimum count per
aggregate**. The output carries no ``tenant_id``, ``case_id``, ``solution_ref``,
``evidence_refs`` or ``installed_at`` — nothing that could identify a tenant or
case. This is what lets cross-manufacturer field data become a shared signal
without exposing any single tenant's data (§4.3 "Diesen Datensatz hat niemand").

Pure code, no LLM, no I/O. The caller selects the source records (e.g. all
outcomes a governance job is allowed to aggregate); this function enforces the
min-count gate and the anonymization shape.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional, Sequence

from pydantic import BaseModel, Field

from app.agent.state.models import OutcomeRecord

#: Default minimum number of raw outcomes before an aggregate may leave the
#: tenant scope (§8 "ab definierter Mindestmenge je Aggregat").
DEFAULT_MIN_AGGREGATE_COUNT = 5


class OutcomeAggregate(BaseModel):
    """An anonymized global richtwert. Deliberately carries **no** tenant/case/
    evidence-identifying fields — only the failure-pattern signal and its size."""

    outcome_pattern: str
    suspected_cause: Optional[str] = None
    count: int
    confidence_counts: dict[str, int] = Field(default_factory=dict)


def aggregate_outcomes(
    records: Sequence[OutcomeRecord],
    *,
    min_count: int = DEFAULT_MIN_AGGREGATE_COUNT,
) -> list[OutcomeAggregate]:
    """Group raw outcomes into anonymized richtwerte above ``min_count``.

    - Groups by ``(outcome_pattern, suspected_cause)``.
    - Records without an ``outcome_pattern`` (no diagnosis) are excluded — an
      undiagnosed incident is not a richtwert.
    - An aggregate is emitted **only** if it reaches ``min_count``; smaller groups
      never leave the tenant scope (the core privacy guarantee).
    - Cross-tenant records combine into one aggregate (that is the moat), but the
      result reveals no tenant.
    """
    groups: dict[tuple[str, Optional[str]], list[OutcomeRecord]] = defaultdict(list)
    for record in records:
        pattern = (record.outcome_pattern or "").strip()
        if not pattern:
            continue
        groups[(pattern, record.suspected_cause)].append(record)

    aggregates: list[OutcomeAggregate] = []
    for (pattern, cause), grouped in groups.items():
        if len(grouped) < min_count:
            continue
        confidence_counts: dict[str, int] = defaultdict(int)
        for record in grouped:
            confidence_counts[record.confidence] += 1
        aggregates.append(
            OutcomeAggregate(
                outcome_pattern=pattern,
                suspected_cause=cause,
                count=len(grouped),
                confidence_counts=dict(confidence_counts),
            )
        )

    aggregates.sort(
        key=lambda a: (-a.count, a.outcome_pattern, a.suspected_cause or "")
    )
    return aggregates
